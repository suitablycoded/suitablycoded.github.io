"""Run each watch once and record the outcome."""

from __future__ import annotations

import difflib
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

from .alerts import Alert, keep_failed, retry_failed, send, write_dry_run
from .config import Config, Watch
from .fetch import FetchError, capture
from .store import Snapshot, Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Result:
    watch: str
    status: str  # "baseline", "unchanged", "changed" or "failed"
    detail: str = ""
    evidence: str | None = None
    alert_failed: bool = False


def unified_diff(before: str, after: str) -> str:
    return "\n".join(
        difflib.unified_diff(before.splitlines(), after.splitlines(), "before", "after", lineterm="")
    )


def _record_change(config: Config, watch: Watch, old: Snapshot, text: str, shot: bytes, now: datetime) -> tuple[str, Alert]:
    rel = Path("evidence") / now.strftime("%Y-%m-%d") / f"{now.strftime('%H%M%S')}-{watch.slug}"
    n = 1
    while (config.data_dir / rel).exists():  # two changes in the same second
        n += 1
        rel = rel.with_name(f"{now.strftime('%H%M%S')}-{watch.slug}-{n}")
    folder = config.data_dir / rel
    folder.mkdir(parents=True)
    diff = unified_diff(old.text, text)
    (folder / "before.txt").write_text(old.text + "\n", encoding="utf-8")
    (folder / "after.txt").write_text(text + "\n", encoding="utf-8")
    (folder / "diff.txt").write_text(diff + "\n", encoding="utf-8")
    shutil.copyfile(config.data_dir / old.screenshot, folder / "before.png")
    (folder / "after.png").write_bytes(shot)

    body = diff.splitlines()[2:]
    alert = Alert(
        watch=watch.name,
        url=watch.url,
        at=now.isoformat(timespec="seconds"),
        evidence=rel.as_posix(),
        added=sum(1 for line in body if line.startswith("+")),
        removed=sum(1 for line in body if line.startswith("-")),
        diff=diff,
    )
    return rel.as_posix(), alert


def _alert(config: Config, store: Store, watch: Watch, alert: Alert, dry_run: bool) -> bool:
    """Send or write the alert. Returns False if it could not be sent."""
    if dry_run:
        path = write_dry_run(alert, config.alerts_dir)
        log.info("dry run: alert written to %s", path.name)
        return True
    errors = send(alert, config.data_dir)
    if not errors:
        return True
    kept = keep_failed(alert, config.failed_alerts_dir, sorted(errors))
    detail = "; ".join(f"{name}: {err}" for name, err in errors.items())
    store.add_event(alert.at, watch.name, watch.url, "alert_failed", detail, kept.name)
    log.error("%s: alert kept in %s and will be retried on the next check", watch.name, kept.name)
    return False


def check_watch(browser: Browser, config: Config, store: Store, watch: Watch, dry_run: bool) -> Result:
    now = datetime.now().replace(microsecond=0)
    at = now.isoformat(timespec="seconds")
    log.info("%s: checking", watch.name)
    try:
        cap = capture(browser, watch, config.timeout_seconds)
    except FetchError as exc:
        log.warning("%s: check failed: %s", watch.name, exc)
        store.add_event(at, watch.name, watch.url, "failed", str(exc))
        return Result(watch.name, "failed", str(exc))

    shot_rel = f"snapshots/{watch.slug}.png"
    old = store.snapshot(watch.name)
    if old is not None and old.text == cap.text:
        log.info("%s: no change", watch.name)
        return Result(watch.name, "unchanged")

    evidence = None
    alert = None
    if old is not None:
        evidence, alert = _record_change(config, watch, old, cap.text, cap.screenshot, now)

    shot_path = config.data_dir / shot_rel
    shot_path.parent.mkdir(parents=True, exist_ok=True)
    shot_path.write_bytes(cap.screenshot)
    store.save_snapshot(watch.name, Snapshot(cap.text, shot_rel, at))

    if alert is None:
        log.info("%s: baseline stored", watch.name)
        store.add_event(at, watch.name, watch.url, "baseline")
        return Result(watch.name, "baseline")

    log.info("%s: CHANGED (+%d/-%d), evidence in %s", watch.name, alert.added, alert.removed, evidence)
    store.add_event(at, watch.name, watch.url, "changed", f"+{alert.added}/-{alert.removed}", evidence)
    sent = _alert(config, store, watch, alert, dry_run)
    return Result(watch.name, "changed", evidence=evidence, alert_failed=not sent)


def _isolated(browser: Browser, config: Config, store: Store, watch: Watch, dry_run: bool) -> Result:
    """Run one watch so that no error in it can stop the others."""
    try:
        return check_watch(browser, config, store, watch, dry_run)
    except Exception as exc:
        detail = f"unexpected error: {type(exc).__name__}: {exc}".splitlines()[0]
        log.error("%s: %s", watch.name, detail)
        try:
            store.add_event(datetime.now().isoformat(timespec="seconds"), watch.name, watch.url, "failed", detail)
        except Exception as db_exc:
            log.error("%s: could not record the failure: %s", watch.name, db_exc)
        return Result(watch.name, "failed", detail)


def run_checks(config: Config, dry_run: bool, watches: list[Watch] | None = None) -> list[Result]:
    """Check the given watches (all by default) in one browser session.

    On Ctrl+C the browser is deliberately not closed: Playwright can hang while
    closing after an interrupt. The caller exits the process instead, which
    also ends the browser.
    """
    store = Store(config.db_path)
    try:
        if not dry_run:
            unsent = retry_failed(config.failed_alerts_dir, config.data_dir)
            if unsent:
                log.warning("%d kept alert(s) still could not be sent", unsent)
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
            results = [_isolated(browser, config, store, w, dry_run) for w in (watches or config.watches)]
        except KeyboardInterrupt:
            raise
        except BaseException:
            pw.stop()
            raise
        browser.close()
        pw.stop()
        return results
    finally:
        store.close()
