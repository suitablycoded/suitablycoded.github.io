"""SQLite storage for the latest snapshot of each watch and the event history.

File paths are stored relative to the data folder so the folder can be moved.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    watch TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    screenshot TEXT NOT NULL,
    taken_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    watch TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('baseline', 'changed', 'failed', 'alert_failed')),
    detail TEXT NOT NULL DEFAULT '',
    evidence TEXT
);
"""


@dataclass(frozen=True)
class Snapshot:
    text: str
    screenshot: str
    taken_at: str


@dataclass(frozen=True)
class Event:
    id: int
    at: str
    watch: str
    url: str
    kind: str
    detail: str
    evidence: str | None


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def snapshot(self, watch: str) -> Snapshot | None:
        row = self.conn.execute(
            "SELECT text, screenshot, taken_at FROM snapshots WHERE watch = ?", (watch,)
        ).fetchone()
        return Snapshot(*row) if row else None

    def save_snapshot(self, watch: str, snap: Snapshot) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO snapshots (watch, text, screenshot, taken_at) VALUES (?, ?, ?, ?)",
                (watch, snap.text, snap.screenshot, snap.taken_at),
            )

    def add_event(self, at: str, watch: str, url: str, kind: str, detail: str = "", evidence: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (at, watch, url, kind, detail, evidence) VALUES (?, ?, ?, ?, ?, ?)",
                (at, watch, url, kind, detail, evidence),
            )

    def events(self, kind: str | None = None) -> list[Event]:
        sql = "SELECT id, at, watch, url, kind, detail, evidence FROM events"
        args: tuple[str, ...] = ()
        if kind:
            sql += " WHERE kind = ?"
            args = (kind,)
        return [Event(*row) for row in self.conn.execute(sql + " ORDER BY id", args)]
