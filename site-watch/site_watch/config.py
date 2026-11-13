"""Load and validate the JSON config file."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when the config file is missing a field or has a bad value."""


@dataclass(frozen=True)
class Watch:
    name: str
    url: str
    selector: str | None = None
    ignore: tuple[str, ...] = ()
    interval_minutes: float = 60.0
    wait_for: str | None = None
    settle_seconds: float = 0.0

    @property
    def slug(self) -> str:
        # \w is Unicode-aware, so names in any script keep their letters.
        # Kept short so evidence paths stay within Windows path limits.
        return re.sub(r"[^\w]+|_+", "-", self.name.lower())[:60].strip("-") or "watch"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    alerts_dir: Path
    timeout_seconds: float
    watches: list[Watch] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "site-watch.sqlite3"

    @property
    def failed_alerts_dir(self) -> Path:
        return self.data_dir / "failed-alerts"


def _number(value: Any, what: str, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{what} must be a number of at least {minimum:g}, got {value!r}")
    return float(value)


def _text(value: Any, what: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{what} must be text, got {value!r}")
    return value


def _watch(i: int, item: Any) -> Watch:
    if not isinstance(item, dict):
        raise ConfigError(f"watch {i + 1} must be an object with 'name' and 'url'")
    name = _text(item.get("name"), f"watch {i + 1} name")
    url = _text(item.get("url"), f"watch {i + 1} url")
    if not name or not url:
        raise ConfigError(f"watch {i + 1} needs both 'name' and 'url'")
    ignore = item.get("ignore", [])
    if not isinstance(ignore, list) or not all(isinstance(p, str) for p in ignore):
        raise ConfigError(f"watch '{name}': 'ignore' must be a list of regex strings")
    for pattern in ignore:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"watch '{name}': bad ignore pattern {pattern!r}: {exc}") from exc
    return Watch(
        name=name,
        url=url,
        selector=_text(item.get("selector"), f"watch '{name}' selector"),
        ignore=tuple(ignore),
        interval_minutes=_number(item.get("interval_minutes", 60), f"watch '{name}' interval_minutes", 0.1),
        wait_for=_text(item.get("wait_for"), f"watch '{name}' wait_for"),
        settle_seconds=_number(item.get("settle_seconds", 0), f"watch '{name}' settle_seconds", 0),
    )


def load_config(path: Path) -> Config:
    """Read a config file. Relative paths inside it are resolved from its folder."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object with a 'watches' list")

    base = path.resolve().parent
    data_dir = base / (_text(raw.get("data_dir"), "data_dir") or "data")
    alerts = _text(raw.get("alerts_dir"), "alerts_dir")
    alerts_dir = base / alerts if alerts else data_dir / "alerts"
    timeout = _number(raw.get("timeout_seconds", 20), "timeout_seconds", 1)

    items = raw.get("watches", [])
    if not isinstance(items, list):
        raise ConfigError("'watches' must be a list")
    watches: list[Watch] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        watch = _watch(i, item)
        if watch.slug in seen:
            raise ConfigError(f"two watches share the name '{watch.name}' (names are compared ignoring case and punctuation, on the first 60 characters)")
        seen.add(watch.slug)
        watches.append(watch)

    if not watches:
        raise ConfigError("config has no watches")
    return Config(data_dir=data_dir, alerts_dir=alerts_dir, timeout_seconds=timeout, watches=watches)
