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
    """Persistent, TTL-based cache for normalized iCloud calendar and mail data.

    iCloud remains the source of truth. The database only stores read results
    so repeated MCP requests do not reopen a CalDAV or IMAP connection
    unnecessarily. Calendar and mail writes invalidate their corresponding
    cached read results after the remote operation succeeds. Full IMAP
    messages are stored separately as SQLite BLOBs so headers and message
    content can be refreshed independently.
    """

    def __init__(
        self,
        path: Path,
        *,
        events_ttl_seconds: int = 60,
        calendars_ttl_seconds: int = 300,
        mailboxes_ttl_seconds: int = 1800,
        email_ttl_seconds: int = 300,
        email_content_ttl_seconds: int = 86400,
        email_max_messages: int = 1000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if events_ttl_seconds < 0:
            raise ValueError("events_ttl_seconds must not be negative")
        if calendars_ttl_seconds < 0:
            raise ValueError("calendars_ttl_seconds must not be negative")
        if mailboxes_ttl_seconds < 0:
            raise ValueError("mailboxes_ttl_seconds must not be negative")
        if email_ttl_seconds < 0:
            raise ValueError("email_ttl_seconds must not be negative")
        if email_content_ttl_seconds < 0:
            raise ValueError("email_content_ttl_seconds must not be negative")
        if email_max_messages < 0:
            raise ValueError("email_max_messages must not be negative")

        self.path = Path(path)
        self.events_ttl_seconds = events_ttl_seconds
        self.calendars_ttl_seconds = calendars_ttl_seconds
        self.mailboxes_ttl_seconds = mailboxes_ttl_seconds
        self.email_ttl_seconds = email_ttl_seconds
        self.email_content_ttl_seconds = email_content_ttl_seconds
        self.email_max_messages = email_max_messages
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS email_messages (
                    cache_key TEXT PRIMARY KEY,
                    mailbox_key TEXT NOT NULL,
                    mailbox TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    uid_validity TEXT NOT NULL DEFAULT '',
                    message_id TEXT,
                    summary_json TEXT NOT NULL,
                    raw_message BLOB NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS email_messages_mailbox_idx "
                "ON email_messages(mailbox_key, uid)"
            )

    def get_calendars(self) -> CacheEntry | None:
        return self._get("calendars", self.calendars_ttl_seconds)

    def set_calendars(self, calendars: list[dict[str, Any]]) -> None:
        self._set("calendars", calendars)

    def get_mailboxes(self) -> CacheEntry | None:
        return self._get("mailboxes", self.mailboxes_ttl_seconds)

    def set_mailboxes(self, mailboxes: list[dict[str, Any]]) -> None:
        self._set("mailboxes", mailboxes)

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

    def invalidate_events(self) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM cache_entries WHERE cache_key LIKE 'events:%' "
                "OR cache_key LIKE 'event:%'"
            )
            return max(cursor.rowcount, 0)

    def get_emails(self, mailbox: str) -> CacheEntry | None:
        return self._get(self._email_key(mailbox), self.email_ttl_seconds)

    def set_emails(
        self,
        mailbox: str,
        emails: list[dict[str, Any]],
        coverage_since: str,
    ) -> None:
        if self.email_max_messages == 0:
            return
        ordered = sorted(
            emails,
            key=self._email_sort_key,
            reverse=True,
        )[: self.email_max_messages]
        self._set(
            self._email_key(mailbox),
            {
                "coverage_since": coverage_since,
                "emails": ordered,
            },
        )

    def invalidate_emails(self, *mailboxes: str) -> int:
        with self._connection() as connection:
            if not mailboxes:
                cursor = connection.execute(
                    "DELETE FROM cache_entries WHERE cache_key LIKE 'emails:%'"
                )
                return max(cursor.rowcount, 0)
            total = 0
            for mailbox in mailboxes:
                cursor = connection.execute(
                    "DELETE FROM cache_entries WHERE cache_key = ?",
                    (self._email_key(mailbox),),
                )
                total += max(cursor.rowcount, 0)
            return total

    def get_email_message(self, mailbox: str, uid: str) -> CacheEntry | None:
        mailbox_key = mailbox.casefold()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT summary_json, raw_message, uid_validity, fetched_at "
                "FROM email_messages WHERE mailbox_key = ? AND uid = ? "
                "ORDER BY fetched_at DESC LIMIT 1",
                (mailbox_key, uid),
            ).fetchone()
        if row is None:
            return None
        try:
            summary = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return CacheEntry(
            value={
                "summary": summary,
                "raw_message": bytes(row[1]),
                "uid_validity": row[2],
            },
            fresh=self._is_fresh(row[3], self.email_content_ttl_seconds),
            fetched_at=row[3],
        )

    def set_email_messages(self, messages: list[dict[str, Any]]) -> None:
        if not messages:
            return
        fetched_at = self._clock()
        rows = []
        for message in messages:
            mailbox = str(message.get("mailbox") or "")
            uid = str(message.get("uid") or "")
            raw_message = message.get("raw_message")
            summary = message.get("summary")
            if not mailbox or not uid or not isinstance(raw_message, bytes):
                continue
            if not isinstance(summary, dict):
                continue
            rows.append(
                (
                    self._email_message_key(mailbox, uid),
                    mailbox.casefold(),
                    mailbox,
                    uid,
                    str(message.get("uid_validity") or ""),
                    str(summary.get("message_id") or "") or None,
                    json.dumps(summary, ensure_ascii=False),
                    raw_message,
                    fetched_at,
                )
            )
        if not rows:
            return
        with self._connection() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO email_messages("
                "cache_key, mailbox_key, mailbox, uid, uid_validity, message_id, "
                "summary_json, raw_message, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def cached_email_uids(
        self,
        mailbox: str,
        uids: list[str],
        *,
        fresh_only: bool = True,
    ) -> set[str]:
        if not uids:
            return set()
        mailbox_key = mailbox.casefold()
        cached: set[str] = set()
        with self._connection() as connection:
            for offset in range(0, len(uids), 900):
                batch = uids[offset : offset + 900]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    "SELECT uid, fetched_at FROM email_messages "
                    f"WHERE mailbox_key = ? AND uid IN ({placeholders})",
                    (mailbox_key, *batch),
                ).fetchall()
                for uid, fetched_at in rows:
                    if not fresh_only or self._is_fresh(fetched_at, self.email_content_ttl_seconds):
                        cached.add(str(uid))
        if fresh_only and self.email_content_ttl_seconds <= 0:
            return set()
        return cached

    def invalidate_email_messages(self, *mailboxes: str) -> int:
        with self._connection() as connection:
            if not mailboxes:
                cursor = connection.execute("DELETE FROM email_messages")
                return max(cursor.rowcount, 0)
            total = 0
            for mailbox in mailboxes:
                cursor = connection.execute(
                    "DELETE FROM email_messages WHERE mailbox_key = ?",
                    (mailbox.casefold(),),
                )
                total += max(cursor.rowcount, 0)
            return total

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
    def _email_sort_key(email: dict[str, Any]) -> tuple[str, int]:
        uid = str(email.get("uid") or "")
        return str(email.get("date") or ""), int(uid) if uid.isdigit() else 0

    @staticmethod
    def _events_key(calendar_id: str, start: str, end: str) -> str:
        return "events:" + SQLiteICloudCalendarCache._digest(calendar_id, start, end)

    @staticmethod
    def _event_key(calendar_id: str, uid: str) -> str:
        return "event:" + SQLiteICloudCalendarCache._digest(calendar_id, uid)

    @staticmethod
    def _email_key(mailbox: str) -> str:
        return "emails:" + SQLiteICloudCalendarCache._digest(mailbox.casefold())

    @staticmethod
    def _email_message_key(mailbox: str, uid: str) -> str:
        return "email_message:" + SQLiteICloudCalendarCache._digest(mailbox.casefold(), uid)

    @staticmethod
    def _digest(*parts: str) -> str:
        payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
