from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    fresh: bool
    fetched_at: float


class SQLiteICloudCalendarCache:
    """Persistent, TTL-based cache for normalized iCloud calendar data.

    iCloud remains the source of truth. The database only stores read results
    so repeated MCP requests do not reopen a CalDAV connection unnecessarily.
    Calendar writes invalidate cached event results after the remote operation
    succeeds.
    """

    def __init__(
        self,
        path: Path,
        *,
        events_ttl_seconds: int = 60,
        calendars_ttl_seconds: int = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if events_ttl_seconds < 0:
            raise ValueError("events_ttl_seconds must not be negative")
        if calendars_ttl_seconds < 0:
            raise ValueError("calendars_ttl_seconds must not be negative")

        self.path = Path(path)
        self.events_ttl_seconds = events_ttl_seconds
        self.calendars_ttl_seconds = calendars_ttl_seconds
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.path.chmod(0o600)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS cache_entries_prefix_idx "
                "ON cache_entries(cache_key)"
            )

    def get_calendars(self) -> CacheEntry | None:
        return self._get("calendars", self.calendars_ttl_seconds)

    def set_calendars(self, calendars: list[dict[str, Any]]) -> None:
        self._set("calendars", calendars)

    def get_events(
        self,
        calendar_id: str,
        start: str,
        end: str,
    ) -> CacheEntry | None:
        return self._get(self._events_key(calendar_id, start, end), self.events_ttl_seconds)

    def set_events(
        self,
        calendar_id: str,
        start: str,
        end: str,
        events: list[dict[str, Any]],
    ) -> None:
        fetched_at = self._clock()
        rows = [
            (
                self._events_key(calendar_id, start, end),
                json.dumps(events, ensure_ascii=False),
                fetched_at,
            )
        ]
        for event in events:
            uid = str(event.get("uid") or "").strip()
            if uid:
                rows.append(
                    (
                        self._event_key(str(event.get("calendar_id") or calendar_id), uid),
                        json.dumps(event, ensure_ascii=False),
                        fetched_at,
                    )
                )

        with self._connection() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO cache_entries(cache_key, value_json, fetched_at) "
                "VALUES (?, ?, ?)",
                rows,
            )

    def set_event(self, event: dict[str, Any]) -> None:
        calendar_id = str(event.get("calendar_id") or "").strip()
        uid = str(event.get("uid") or "").strip()
        if not calendar_id or not uid:
            return
        self._set(self._event_key(calendar_id, uid), event)

    def get_event(self, calendar: str, uid: str) -> CacheEntry | None:
        selector = calendar.strip().casefold()
        normalized_uid = uid.strip()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT value_json, fetched_at FROM cache_entries "
                "WHERE cache_key LIKE 'event:%'"
            ).fetchall()

        newest: tuple[float, dict[str, Any]] | None = None
        for value_json, fetched_at in rows:
            try:
                event = json.loads(value_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or str(event.get("uid") or "") != normalized_uid:
                continue
            calendar_id = str(event.get("calendar_id") or "").casefold()
            calendar_name = str(event.get("calendar_name") or "").casefold()
            if selector not in {calendar_id, calendar_name}:
                continue
            if newest is None or fetched_at > newest[0]:
                newest = (fetched_at, event)

        if newest is None:
            return None
        fetched_at, event = newest
        return CacheEntry(
            value=event,
            fresh=self._is_fresh(fetched_at, self.events_ttl_seconds),
            fetched_at=fetched_at,
        )

    def invalidate_events(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM cache_entries WHERE cache_key LIKE 'events:%' "
                "OR cache_key LIKE 'event:%'"
            )

    def _get(self, key: str, ttl_seconds: int) -> CacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value_json, fetched_at FROM cache_entries WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None

        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return CacheEntry(
            value=value,
            fresh=self._is_fresh(row[1], ttl_seconds),
            fetched_at=row[1],
        )

    def _set(self, key: str, value: Any) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO cache_entries(cache_key, value_json, fetched_at) "
                "VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), self._clock()),
            )

    def _is_fresh(self, fetched_at: float, ttl_seconds: int) -> bool:
        return ttl_seconds > 0 and fetched_at + ttl_seconds > self._clock()

    @staticmethod
    def _events_key(calendar_id: str, start: str, end: str) -> str:
        return "events:" + SQLiteICloudCalendarCache._digest(calendar_id, start, end)

    @staticmethod
    def _event_key(calendar_id: str, uid: str) -> str:
        return "event:" + SQLiteICloudCalendarCache._digest(calendar_id, uid)

    @staticmethod
    def _digest(*parts: str) -> str:
        payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
