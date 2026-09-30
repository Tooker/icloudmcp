from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from app.timing import measure_phase, timed_phase


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
        self._namespace = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.path.chmod(0o600)
        self._initialize()

    def for_account(self, protocol: str, server: str, username: str) -> SQLiteICloudCalendarCache:
        """Share the database with an opaque namespace for one remote account.

        Legacy entries without an account namespace are intentionally not
        reused: their owner cannot be determined safely.
        """

        scoped = copy(self)
        scoped._namespace = "account:" + self._digest(protocol, server, username.strip().casefold()) + ":"
        return scoped

    def _scoped_key(self, key: str) -> str:
        return self._namespace + key

    @property
    def account_namespace(self) -> str:
        """Opaque account identity for derived indexes in the same database."""
        return self._namespace

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with measure_phase("sqlite_connect"):
            connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            with measure_phase("sqlite_transaction"):
                yield connection
                with measure_phase("sqlite_commit"):
                    connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            # Embedding writes must not block concurrent cache readers.
            connection.execute("PRAGMA journal_mode = WAL")
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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mailbox_states ("
                "mailbox_key TEXT PRIMARY KEY, uid_validity TEXT NOT NULL)"
            )

    @timed_phase("sqlite_uid_validity_sync")
    def sync_uid_validity(self, mailbox: str, uid_validity: str) -> int:
        """Invalidate one mailbox atomically when its UID generation changes."""

        mailbox_key = self._scoped_key(mailbox.casefold())
        with self._connection() as connection:
            # The common case is read-only. Do not take the global SQLite
            # writer lock just to confirm an unchanged mailbox generation.
            row = connection.execute(
                "SELECT uid_validity FROM mailbox_states WHERE mailbox_key = ?", (mailbox_key,)
            ).fetchone()
            if row is not None and row[0] == uid_validity:
                return 0
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT uid_validity FROM mailbox_states WHERE mailbox_key = ?", (mailbox_key,)
            ).fetchone()
            if row is not None and row[0] == uid_validity:
                return 0
            headers = connection.execute(
                "DELETE FROM cache_entries WHERE cache_key = ?",
                (self._scoped_key(self._email_key(mailbox)),),
            ).rowcount
            messages = connection.execute(
                "DELETE FROM email_messages WHERE mailbox_key = ?", (mailbox_key,)
            ).rowcount
            connection.execute(
                "INSERT OR REPLACE INTO mailbox_states(mailbox_key, uid_validity) VALUES (?, ?)",
                (mailbox_key, uid_validity),
            )
            return max(headers, 0) + max(messages, 0)

    @staticmethod
    def _generation_matches(connection: sqlite3.Connection, mailbox_key: str, uid_validity: str) -> bool:
        row = connection.execute(
            "SELECT uid_validity FROM mailbox_states WHERE mailbox_key = ?", (mailbox_key,)
        ).fetchone()
        return row is None or (bool(uid_validity) and row[0] == uid_validity)

    @timed_phase("sqlite_calendars_read")
    def get_calendars(self) -> CacheEntry | None:
        return self._get("calendars", self.calendars_ttl_seconds)

    def set_calendars(self, calendars: list[dict[str, Any]]) -> None:
        self._set("calendars", calendars)

    def get_mailboxes(self) -> CacheEntry | None:
        return self._get("mailboxes", self.mailboxes_ttl_seconds)

    def set_mailboxes(self, mailboxes: list[dict[str, Any]]) -> None:
        self._set("mailboxes", mailboxes)

    @timed_phase("sqlite_events_read")
    def get_events(
        self,
        calendar_id: str,
        start: str,
        end: str,
    ) -> CacheEntry | None:
        return self._get(self._events_key(calendar_id, start, end), self.events_ttl_seconds)

    @timed_phase("sqlite_events_write")
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
                self._scoped_key(self._events_key(calendar_id, start, end)),
                json.dumps(events, ensure_ascii=False),
                fetched_at,
            )
        ]
        for event in events:
            uid = str(event.get("uid") or "").strip()
            # An expanded occurrence must never replace get_event's master
            # summary, whose lookup is keyed only by calendar and series UID.
            if uid and not event.get("is_recurring") and not event.get("recurrence_id"):
                rows.append(
                    (
                        self._scoped_key(self._event_key(str(event.get("calendar_id") or calendar_id), uid)),
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
                "WHERE cache_key LIKE ?",
                (self._scoped_key("event:v2:") + "%",),
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
                "DELETE FROM cache_entries WHERE cache_key LIKE ? OR cache_key LIKE ?",
                (self._scoped_key("events:") + "%", self._scoped_key("event:") + "%"),
            )
            return max(cursor.rowcount, 0)

    @timed_phase("sqlite_header_cache_read")
    def get_emails(self, mailbox: str) -> CacheEntry | None:
        return self._get(self._email_key(mailbox), self.email_ttl_seconds)

    @timed_phase("sqlite_header_cache_write")
    def set_emails(
        self,
        mailbox: str,
        emails: list[dict[str, Any]],
        coverage_since: str,
        *,
        complete: bool = False,
        uid_validity: str | None = None,
    ) -> None:
        if self.email_max_messages == 0:
            return
        ordered = sorted(
            emails,
            key=self._email_sort_key,
            reverse=True,
        )[: self.email_max_messages]
        value = {
            "coverage_since": coverage_since,
            "complete": complete and len(emails) <= self.email_max_messages,
            "uid_validity": uid_validity,
            "emails": ordered,
        }
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if uid_validity is not None and not self._generation_matches(
                connection, self._scoped_key(mailbox.casefold()), uid_validity
            ):
                return
            connection.execute(
                "INSERT OR REPLACE INTO cache_entries(cache_key, value_json, fetched_at) VALUES (?, ?, ?)",
                (self._scoped_key(self._email_key(mailbox)), json.dumps(value, ensure_ascii=False), self._clock()),
            )

    def invalidate_emails(self, *mailboxes: str) -> int:
        with self._connection() as connection:
            if not mailboxes:
                cursor = connection.execute(
                    "DELETE FROM cache_entries WHERE cache_key LIKE ?",
                    (self._scoped_key("emails:") + "%",),
                )
                return max(cursor.rowcount, 0)
            total = 0
            for mailbox in mailboxes:
                cursor = connection.execute(
                    "DELETE FROM cache_entries WHERE cache_key = ?",
                    (self._scoped_key(self._email_key(mailbox)),),
                )
                total += max(cursor.rowcount, 0)
            return total

    @timed_phase("sqlite_message_read")
    def get_email_message(
        self, mailbox: str, uid: str, *, uid_validity: str | None = None,
    ) -> CacheEntry | None:
        if uid_validity == "":
            return None
        mailbox_key = self._scoped_key(mailbox.casefold())
        with self._connection() as connection:
            row = connection.execute(
                "SELECT summary_json, raw_message, uid_validity, fetched_at "
                "FROM email_messages WHERE mailbox_key = ? AND uid = ? "
                "ORDER BY fetched_at DESC LIMIT 1",
                (mailbox_key, uid),
            ).fetchone()
        if row is None or (uid_validity is not None and row[2] != uid_validity):
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

    @timed_phase("sqlite_messages_write")
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
                    self._scoped_key(self._email_message_key(mailbox, uid)),
                    self._scoped_key(mailbox.casefold()),
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
            connection.execute("BEGIN IMMEDIATE")
            rows = [row for row in rows if self._generation_matches(connection, row[1], row[4])]
            connection.executemany(
                "INSERT OR REPLACE INTO email_messages("
                "cache_key, mailbox_key, mailbox, uid, uid_validity, message_id, "
                "summary_json, raw_message, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    @timed_phase("sqlite_summary_presence")
    def has_email_summaries(self, mailbox: str) -> bool:
        """Check for reusable headers without reading any message BLOBs."""
        with self._connection() as connection:
            return connection.execute(
                "SELECT 1 FROM email_messages e LEFT JOIN mailbox_states m "
                "ON m.mailbox_key = e.mailbox_key WHERE e.mailbox_key = ? "
                "AND e.uid_validity != '' "
                "AND (m.uid_validity IS NULL OR m.uid_validity = e.uid_validity) LIMIT 1",
                (self._scoped_key(mailbox.casefold()),),
            ).fetchone() is not None

    @timed_phase("sqlite_matched_headers_read")
    def get_email_summaries(
        self, mailbox: str, uids: list[str], *, uid_validity: str,
    ) -> dict[str, dict[str, Any]]:
        """Reuse immutable headers for live-matched UIDs, regardless of age.

        Caller checks UIDVALIDITY and refreshes mutable flags/INTERNALDATE
        from IMAP. Reading summary_json never loads or parses .eml BLOBs.
        """
        if not uids or not uid_validity:
            return {}
        result = {}
        with self._connection() as connection:
            for offset in range(0, len(uids), 900):
                batch = uids[offset:offset + 900]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    "SELECT e.uid, e.summary_json FROM email_messages e "
                    "LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key "
                    "WHERE e.mailbox_key = ? AND e.uid_validity = ? "
                    "AND (m.uid_validity IS NULL OR m.uid_validity = e.uid_validity) "
                    f"AND e.uid IN ({placeholders})",
                    (self._scoped_key(mailbox.casefold()), uid_validity, *batch),
                ).fetchall()
                for uid, raw_summary in rows:
                    try:
                        summary = json.loads(raw_summary)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(summary, dict):
                        result[uid] = {**summary, "uid": uid, "mailbox": mailbox}
        return result

    def email_cache_stats(self) -> dict[str, int]:
        """Return aggregate content-cache counters without exposing message data."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(raw_message)), 0), "
                "COUNT(DISTINCT mailbox_key) FROM email_messages WHERE cache_key LIKE ?",
                (self._scoped_key("email_message:") + "%",),
            ).fetchone()
        return {
            "messages": int(row[0] or 0),
            "bytes": int(row[1] or 0),
            "mailboxes": int(row[2] or 0),
        }

    def cached_email_uids(
        self,
        mailbox: str,
        uids: list[str],
        *,
        fresh_only: bool = True,
        uid_validity: str | None = None,
    ) -> set[str]:
        if not uids or uid_validity == "":
            return set()
        mailbox_key = self._scoped_key(mailbox.casefold())
        cached: set[str] = set()
        with self._connection() as connection:
            for offset in range(0, len(uids), 900):
                batch = uids[offset : offset + 900]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    "SELECT uid, fetched_at, uid_validity FROM email_messages "
                    f"WHERE mailbox_key = ? AND uid IN ({placeholders})",
                    (mailbox_key, *batch),
                ).fetchall()
                for uid, fetched_at, stored_validity in rows:
                    if uid_validity is not None and stored_validity != uid_validity:
                        continue
                    if not fresh_only or self._is_fresh(fetched_at, self.email_content_ttl_seconds):
                        cached.add(str(uid))
        if fresh_only and self.email_content_ttl_seconds <= 0:
            return set()
        return cached

    def invalidate_email_messages(self, *mailboxes: str) -> int:
        with self._connection() as connection:
            if not mailboxes:
                cursor = connection.execute(
                    "DELETE FROM email_messages WHERE cache_key LIKE ?",
                    (self._scoped_key("email_message:") + "%",),
                )
                return max(cursor.rowcount, 0)
            total = 0
            for mailbox in mailboxes:
                cursor = connection.execute(
                    "DELETE FROM email_messages WHERE mailbox_key = ?",
                    (self._scoped_key(mailbox.casefold()),),
                )
                total += max(cursor.rowcount, 0)
            return total

    def _get(self, key: str, ttl_seconds: int) -> CacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value_json, fetched_at FROM cache_entries WHERE cache_key = ?",
                (self._scoped_key(key),),
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
                (self._scoped_key(key), json.dumps(value, ensure_ascii=False), self._clock()),
            )

    def _is_fresh(self, fetched_at: float, ttl_seconds: int) -> bool:
        return ttl_seconds > 0 and fetched_at + ttl_seconds > self._clock()

    @staticmethod
    def _email_sort_key(email: dict[str, Any]) -> tuple[str, int]:
        uid = str(email.get("uid") or "")
        return str(email.get("date") or ""), int(uid) if uid.isdigit() else 0

    @staticmethod
    def _events_key(calendar_id: str, start: str, end: str) -> str:
        # Ignore persisted summaries from before occurrence expansion.
        return "events:v2:" + SQLiteICloudCalendarCache._digest(calendar_id, start, end)

    @staticmethod
    def _event_key(calendar_id: str, uid: str) -> str:
        return "event:v2:" + SQLiteICloudCalendarCache._digest(calendar_id, uid)

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
