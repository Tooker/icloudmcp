from __future__ import annotations

import base64
import imaplib
import re
import ssl
import threading
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from loguru import logger
from queue import LifoQueue
from time import perf_counter, sleep
from typing import Any

from app.config import IMAPConfig
from app.icloud_cache import SQLiteICloudCalendarCache


class IMAPServiceError(RuntimeError):
    """A safe, user-facing IMAP operation error."""


class MailboxNotFoundError(IMAPServiceError):
    pass


class EmailNotFoundError(IMAPServiceError):
    pass


@dataclass(frozen=True)
class _HeaderSearchResult:
    emails: list[dict[str, Any]]
    total_matches: int


class ICloudIMAPService:
    """Small synchronous IMAP facade used from MCP worker threads.

    IMAP operations are blocking. The MCP layer deliberately calls this
    service with ``asyncio.to_thread`` so a slow mail server cannot block the
    ASGI event loop.
    """

    _MAX_LIMIT = 1000
    _MAX_BODY_CHARS = 100_000
    _MAX_DRAFT_BYTES = 25_000_000
    _MAX_ATTACHMENT_BYTES = 10_000_000
    _HEADER_FETCH_BATCH_SIZE = 100
    _FETCH_HEADERS = (
        "(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS "
        "(DATE FROM TO CC SUBJECT MESSAGE-ID)])"
    )

    def __init__(
        self,
        config: IMAPConfig,
        client_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
        cache: SQLiteICloudCalendarCache | None = None,
        email_cache_days: int = 100,
        email_cache_max_messages: int = 1000,
        connection_pool_size: int = 4,
        crawl_batch_size: int = 25,
        crawl_interval_seconds: float = 0.1,
        max_cached_message_bytes: int = 25_000_000,
    ) -> None:
        if email_cache_days < 0:
            raise ValueError("email_cache_days must not be negative")
        if email_cache_max_messages < 0 or email_cache_max_messages > self._MAX_LIMIT:
            raise ValueError(f"email_cache_max_messages must be between 0 and {self._MAX_LIMIT}")
        if connection_pool_size < 1 or connection_pool_size > 16:
            raise ValueError("connection_pool_size must be between 1 and 16")
        if crawl_batch_size < 1 or crawl_batch_size > 100:
            raise ValueError("crawl_batch_size must be between 1 and 100")
        if crawl_interval_seconds < 0:
            raise ValueError("crawl_interval_seconds must not be negative")
        if max_cached_message_bytes < 1:
            raise ValueError("max_cached_message_bytes must be positive")
        self.config = config
        self._client_factory = client_factory
        self._cache = (
            cache.for_account("imap", f"{config.host.casefold()}:{config.port}", config.username)
            if cache is not None else None
        )
        self._email_cache_days = email_cache_days
        self._email_cache_max_messages = email_cache_max_messages
        self._crawl_batch_size = crawl_batch_size
        self._crawl_interval_seconds = crawl_interval_seconds
        self._max_cached_message_bytes = max_cached_message_bytes
        self._refresh_locks_guard = threading.Lock()
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._crawl_stop_event = threading.Event()
        self._connection_pool: LifoQueue[Any | None] = LifoQueue(maxsize=connection_pool_size)
        for _ in range(connection_pool_size):
            self._connection_pool.put_nowait(None)

    @contextmanager
    def _connected(self, operation: str) -> Iterator[Any]:
        acquire_started = perf_counter()
        client = self._connection_pool.get()
        reused = client is not None
        logger.info(
            "imap_phase tool={} phase=connection_acquire reused={} duration_ms={:.1f}",
            operation,
            reused,
            (perf_counter() - acquire_started) * 1000,
        )
        discard = False
        try:
            if client is None:
                client = self._open_connection(operation)
            yield client
        except Exception:
            # A protocol or socket error can leave a connection in an unknown
            # state. Do not return it to the pool; the next operation gets a
            # fresh TLS session instead.
            discard = True
            raise
        finally:
            if discard:
                self._close_connection(client)
                client = None
            self._connection_pool.put_nowait(client)

    def _open_connection(self, operation: str) -> Any:
        started = perf_counter()
        client: Any | None = None
        try:
            client = self._client_factory(
                self.config.host,
                self.config.port,
                ssl_context=ssl.create_default_context(),
                timeout=30,
            )
            status, _ = client.login(
                self.config.username,
                self.config.app_specific_password,
            )
            self._ensure_ok(status, "IMAP login failed")
            self._enable_utf8(client, operation)
        except imaplib.IMAP4.error as exc:
            self._close_connection(client)
            raise IMAPServiceError(
                "IMAP login failed; check the iCloud Mail address and app-specific password"
            ) from exc
        except Exception:
            self._close_connection(client)
            raise
        logger.info(
            "imap_phase tool={} phase=connection_open duration_ms={:.1f}",
            operation,
            (perf_counter() - started) * 1000,
        )
        return client

    @staticmethod
    def _enable_utf8(client: Any, operation: str) -> None:
        enable = getattr(client, "enable", None)
        if not callable(enable):
            # Test doubles and a few IMAP-compatible clients do not expose
            # ENABLE. imaplib accepts bytes search arguments as a fallback.
            return
        started = perf_counter()
        try:
            status, _ = enable("UTF8=ACCEPT")
        except Exception:
            logger.info("imap_phase tool={} phase=utf8_enable status=unsupported", operation)
            return
        if ICloudIMAPService._is_ok(status):
            # imaplib defaults to ASCII when encoding string command
            # arguments. UTF8=ACCEPT allows UTF-8 search criteria.
            try:
                client._encoding = "utf-8"
            except Exception:
                pass
            state = "enabled"
        else:
            state = "unsupported"
        logger.info(
            "imap_phase tool={} phase=utf8_enable status={} duration_ms={:.1f}",
            operation,
            state,
            (perf_counter() - started) * 1000,
        )

    @staticmethod
    def _close_connection(client: Any | None) -> None:
        if client is None:
            return
        try:
            logout = getattr(client, "logout", None)
            if callable(logout):
                logout()
                return
        except Exception:
            pass
        shutdown = getattr(client, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass

    def close(self) -> None:
        """Close idle pooled IMAP connections during application shutdown."""

        self._crawl_stop_event.set()
        while True:
            try:
                client = self._connection_pool.get_nowait()
            except Exception:
                return
            self._close_connection(client)

    def stop_crawl(self) -> None:
        self._crawl_stop_event.set()

    @contextmanager
    def _refresh_lock(self, key: str) -> Iterator[None]:
        with self._refresh_locks_guard:
            lock = self._refresh_locks.setdefault(key, threading.Lock())
        with lock:
            yield

    def list_mailboxes(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            cached = self._cache.get_mailboxes()
            if cached is not None and cached.fresh:
                logger.info(
                    "imap_cache tool=list_mailboxes action=read status=hit entries={}",
                    len(cached.value),
                )
                return cached.value
            logger.info(
                "imap_cache tool=list_mailboxes action=read status={}",
                "stale" if cached is not None else "miss",
            )

        lock_key = "mailboxes"
        with self._refresh_lock(lock_key):
            if self._cache is not None:
                cached = self._cache.get_mailboxes()
                if cached is not None and cached.fresh:
                    logger.info(
                        "imap_cache tool=list_mailboxes action=read status=coalesced_hit entries={}",
                        len(cached.value),
                    )
                    return cached.value
            logger.info(
                "imap_cache tool=list_mailboxes action=read status=refresh reason=mailbox_listing_live"
            )
            with self._connected("list_mailboxes") as client:
                started = perf_counter()
                status, rows = client.list()
                self._ensure_ok(status, "IMAP mailbox listing failed")
                logger.info(
                    "imap_phase tool=list_mailboxes phase=list duration_ms={:.1f}",
                    (perf_counter() - started) * 1000,
                )

                result: list[dict[str, Any]] = []
                for row in rows or []:
                    parsed = self._parse_list_row(row)
                    if parsed is not None:
                        result.append(parsed)
            if self._cache is not None:
                self._cache.set_mailboxes(result)
                logger.info(
                    "imap_cache tool=list_mailboxes action=write status=refresh entries={}",
                    len(result),
                )
            return result

    def search_emails(
        self,
        mailbox: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
        subject: str | None = None,
        query: str | None = None,
        since: str | None = None,
        before: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = self._validate_limit(limit)
        selected_mailbox = self._mailbox(mailbox)
        filters = dict(
            from_address=from_address, to_address=to_address, subject=subject,
            since=since, before=before, unread_only=unread_only, limit=limit,
        )
        cache_enabled = self._email_cache_enabled()
        cache_range_supported = (
            self._cache_range_supported(since, before)
            if cache_enabled and not query else False
        )
        if cache_enabled and not query and cache_range_supported:
            with self._refresh_lock(f"headers:{selected_mailbox.casefold()}"):
                cached = self._cache.get_emails(selected_mailbox)
                if cached is None or not cached.fresh or self._cached_emails(cached) is None:
                    logger.info(
                        "imap_cache tool=search_emails action=read status={}",
                        "stale" if cached is not None else "miss",
                    )
                    coverage_since = self._email_cache_since()
                    recent = self._search_live(
                        selected_mailbox, since=coverage_since,
                        limit=self._email_cache_max_messages,
                    )
                    self._cache.set_emails(
                        selected_mailbox, recent.emails, coverage_since,
                        complete=recent.total_matches == len(recent.emails),
                    )
                    cached = self._cache.get_emails(selected_mailbox)
                    logger.info(
                        "imap_cache tool=search_emails action=write status=refresh entries={} coverage_days={} max_messages={}",
                        len(recent.emails), self._email_cache_days, self._email_cache_max_messages,
                    )
                if self._cache_covers_search(cached, since):
                    result = self._filter_cached_emails(self._cached_emails(cached), **filters)
                    logger.info(
                        "imap_cache tool=search_emails action=read status=hit entries={}",
                        len(result),
                    )
                    return result
            bypass_reason = "incomplete_cache"
        else:
            bypass_reason = (
                "full_text_query" if query else "range_outside_cache" if cache_enabled else "disabled"
            )
        logger.info(
            "imap_cache tool=search_emails action=read status=bypass reason={}", bypass_reason,
        )
        return self._search_live(selected_mailbox, query=query, **filters).emails

    def _search_live(
        self,
        selected_mailbox: str,
        from_address: str | None = None,
        to_address: str | None = None,
        subject: str | None = None,
        query: str | None = None,
        since: str | None = None,
        before: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> _HeaderSearchResult:
        criteria: list[str | bytes] = []
        if from_address:
            criteria.extend(("FROM", self._quote_search_value(from_address, "from_address")))
        if to_address:
            criteria.extend(("TO", self._quote_search_value(to_address, "to_address")))
        if subject:
            criteria.extend(("SUBJECT", self._quote_search_value(subject, "subject")))
        if query:
            criteria.extend(("TEXT", self._quote_search_value(query, "query")))
        if since:
            criteria.extend(("SINCE", self._imap_date(since, "since")))
        if before:
            criteria.extend(("BEFORE", self._imap_date(before, "before")))
        if unread_only:
            criteria.append("UNSEEN")
        if not criteria:
            criteria.append("ALL")

        with self._connected("search_emails") as client:
            self._select(client, selected_mailbox, readonly=True, operation="search_emails")
            started = perf_counter()
            status, data = client.uid("SEARCH", None, *criteria)
            self._ensure_ok(status, "IMAP search failed")
            uids = self._parse_uids(data)
            logger.info(
                "imap_phase tool=search_emails phase=search duration_ms={:.1f} uid_count={}",
                (perf_counter() - started) * 1000,
                len(uids),
            )

            # IMAP SEARCH normally returns ascending UIDs. Returning newest
            # candidates first makes the limit useful for large inboxes.
            selected_uids = list(reversed(uids[-limit:]))
            result_by_uid: dict[str, dict[str, Any]] = {}
            for offset in range(0, len(selected_uids), self._HEADER_FETCH_BATCH_SIZE):
                batch = selected_uids[offset : offset + self._HEADER_FETCH_BATCH_SIZE]
                started = perf_counter()
                status, fetched = client.uid(
                    "FETCH",
                    ",".join(batch),
                    self._FETCH_HEADERS,
                )
                self._ensure_ok(status, "IMAP header fetch failed")
                logger.info(
                    "imap_phase tool=search_emails phase=header_fetch duration_ms={:.1f} batch_entries={}",
                    (perf_counter() - started) * 1000,
                    len(batch),
                )
                parse_started = perf_counter()
                result_by_uid.update(
                    self._parse_header_fetch(
                        fetched,
                        mailbox=selected_mailbox,
                    )
                )
                logger.info(
                    "imap_phase tool=search_emails phase=header_parse duration_ms={:.1f} entries={}",
                    (perf_counter() - parse_started) * 1000,
                    len(batch),
                )
            return _HeaderSearchResult(
                emails=[result_by_uid[uid] for uid in selected_uids if uid in result_by_uid],
                total_matches=len(uids),
            )

    def _email_cache_enabled(self) -> bool:
        return (
            self._cache is not None
            and self._cache.email_ttl_seconds > 0
            and self._email_cache_days > 0
            and self._email_cache_max_messages > 0
        )

    def _email_cache_since(self) -> str:
        return (date.today() - timedelta(days=self._email_cache_days)).isoformat()

    def _cache_range_supported(self, since: str | None, before: str | None) -> bool:
        if not since:
            # A rolling window cannot cover an unbounded mailbox search.
            return False
        coverage_since = self._parse_cache_date(self._email_cache_since(), "since")
        if since is not None and self._parse_cache_date(since, "since") < coverage_since:
            return False
        if before is not None and self._parse_cache_date(before, "before") <= coverage_since:
            return False
        return True

    def _cache_covers_search(self, cached: Any, since: str | None) -> bool:
        emails = self._cached_emails(cached)
        if emails is None or not since or cached.value.get("complete") is not True:
            return False
        coverage_since = cached.value.get("coverage_since")
        if not isinstance(coverage_since, str):
            return False
        try:
            coverage_date = self._parse_cache_date(coverage_since, "coverage_since")
        except ValueError:
            return False
        return (
            self._parse_cache_date(since, "since") >= coverage_date
            and all(email.get("internal_date") for email in emails)
        )

    @staticmethod
    def _parse_cache_date(value: str, field: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc

    @staticmethod
    def _cached_emails(cached: Any) -> list[dict[str, Any]] | None:
        if cached is None or not isinstance(cached.value, dict):
            return None
        emails = cached.value.get("emails")
        if not isinstance(emails, list) or not all(isinstance(email, dict) for email in emails):
            return None
        return emails

    def _filter_cached_emails(
        self,
        emails: list[dict[str, Any]],
        *,
        from_address: str | None,
        to_address: str | None,
        subject: str | None,
        since: str | None,
        before: str | None,
        unread_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        since_date = self._parse_cache_date(since, "since") if since else None
        before_date = self._parse_cache_date(before, "before") if before else None
        result: list[dict[str, Any]] = []
        for email in emails:
            if from_address and not self._contains_header(email.get("from"), from_address):
                continue
            if to_address and not self._contains_header(email.get("to"), to_address):
                continue
            if subject and not self._contains_header(email.get("subject"), subject):
                continue
            if unread_only and email.get("read") is True:
                continue
            message_date = self._email_date(email)
            if since_date is not None and (message_date is None or message_date < since_date):
                continue
            if before_date is not None and (message_date is None or message_date >= before_date):
                continue
            result.append(email)

        result.sort(key=self._email_sort_key, reverse=True)
        return result[:limit]

    @staticmethod
    def _contains_header(value: Any, needle: str) -> bool:
        return needle.strip().casefold() in str(value or "").casefold()

    @staticmethod
    def _email_date(email: dict[str, Any]) -> date | None:
        # IMAP SINCE/BEFORE use the server's INTERNALDATE, not the Date header.
        value = str(email.get("internal_date") or "")
        if len(value) < 10:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @staticmethod
    def _email_sort_key(email: dict[str, Any]) -> int:
        uid = str(email.get("uid") or "")
        return int(uid) if uid.isdigit() else 0

    @classmethod
    def _parse_header_fetch(
        cls,
        data: Any,
        *,
        mailbox: str,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in data or []:
            if not isinstance(item, tuple):
                continue
            metadata = next(
                (
                    part
                    for part in item
                    if isinstance(part, bytes) and re.search(rb"\bUID\s+\d+\b", part)
                ),
                b"",
            )
            match = re.search(rb"\bUID\s+(\d+)\b", metadata)
            if match is None:
                continue
            uid = match.group(1).decode("ascii")
            raw_headers = cls._literal_bytes(item)
            if not raw_headers:
                continue
            message = cls._parse_message(raw_headers)
            result[uid] = cls._message_summary(
                message,
                uid=uid,
                mailbox=mailbox,
                flags=cls._fetch_flags(item),
            )
            match = re.search(rb'INTERNALDATE "([^"]+)"', metadata)
            if match:
                try:
                    result[uid]["internal_date"] = parsedate_to_datetime(
                        match.group(1).decode("ascii").replace("-", " ", 2)
                    ).isoformat()
                except (ValueError, TypeError, OverflowError):
                    pass
        return result

    @classmethod
    def _parse_full_fetch(
        cls,
        data: Any,
        *,
        mailbox: str,
    ) -> dict[str, tuple[dict[str, Any], bytes]]:
        result: dict[str, tuple[dict[str, Any], bytes]] = {}
        for item in data or []:
            if not isinstance(item, tuple):
                continue
            metadata = next(
                (
                    part
                    for part in item
                    if isinstance(part, bytes) and re.search(rb"\bUID\s+\d+\b", part)
                ),
                b"",
            )
            match = re.search(rb"\bUID\s+(\d+)\b", metadata)
            if match is None:
                continue
            uid = match.group(1).decode("ascii")
            raw_message = cls._literal_bytes(item)
            if not raw_message:
                continue
            message = cls._parse_message(raw_message)
            result[uid] = (
                cls._message_summary(
                    message,
                    uid=uid,
                    mailbox=mailbox,
                    flags=cls._fetch_flags(item),
                ),
                raw_message,
            )
        return result

    @staticmethod
    def _uid_validity(client: Any, selected_data: Any) -> str:
        for item in selected_data or []:
            if isinstance(item, bytes):
                match = re.search(rb"UIDVALIDITY\s+(\d+)", item, re.IGNORECASE)
                if match:
                    return match.group(1).decode("ascii")
        response = getattr(client, "response", None)
        if callable(response):
            try:
                status, data = response("UIDVALIDITY")
                if ICloudIMAPService._is_ok(status):
                    for item in data or []:
                        if isinstance(item, bytes):
                            match = re.search(rb"\d+", item)
                            if match:
                                return match.group(0).decode("ascii")
            except Exception:
                pass
        return ""

    def get_email(
        self,
        mailbox: str | None,
        uid: str,
        max_body_chars: int = 20_000,
    ) -> dict[str, Any]:
        uid = self._uid(uid)
        if not 1 <= max_body_chars <= self._MAX_BODY_CHARS:
            raise ValueError(
                f"max_body_chars must be between 1 and {self._MAX_BODY_CHARS}"
            )
        selected_mailbox = self._mailbox(mailbox)
        if self._cache is not None:
            cached = self._cache.get_email_message(selected_mailbox, uid)
            if cached is not None and cached.fresh:
                logger.info(
                    "imap_cache tool=get_email action=read status=hit bytes={}",
                    len(cached.value.get("raw_message", b"")),
                )
                return self._render_cached_email(cached.value, max_body_chars)
            logger.info(
                "imap_cache tool=get_email action=read status={}",
                "stale" if cached is not None else "miss",
            )

        lock_key = f"message:{selected_mailbox.casefold()}:{uid}"
        with self._refresh_lock(lock_key):
            if self._cache is not None:
                cached = self._cache.get_email_message(selected_mailbox, uid)
                if cached is not None and cached.fresh:
                    logger.info(
                        "imap_cache tool=get_email action=read status=coalesced_hit bytes={}",
                        len(cached.value.get("raw_message", b"")),
                    )
                    return self._render_cached_email(cached.value, max_body_chars)

            logger.info("imap_cache tool=get_email action=read status=refresh")
            with self._connected("get_email") as client:
                self._select(client, selected_mailbox, readonly=True, operation="get_email")
                started = perf_counter()
                status, fetched = client.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])")
                self._ensure_ok(status, "IMAP message fetch failed")
                raw_message = self._literal_bytes(fetched)
                logger.info(
                    "imap_phase tool=get_email phase=message_fetch duration_ms={:.1f} bytes={}",
                    (perf_counter() - started) * 1000,
                    len(raw_message),
                )
                if not raw_message:
                    raise EmailNotFoundError(f"Email not found: {uid}")
                parse_started = perf_counter()
                message = self._parse_message(raw_message)
                summary = self._message_summary(
                    message,
                    uid=uid,
                    mailbox=selected_mailbox,
                    flags=self._fetch_flags(fetched),
                )
                logger.info(
                    "imap_phase tool=get_email phase=parse duration_ms={:.1f}",
                    (perf_counter() - parse_started) * 1000,
                )
            if self._cache is not None and len(raw_message) <= self._max_cached_message_bytes:
                self._cache.set_email_messages(
                    [
                        {
                            "mailbox": selected_mailbox,
                            "uid": uid,
                            "summary": summary,
                            "raw_message": raw_message,
                        }
                    ]
                )
                logger.info(
                    "imap_cache tool=get_email action=write status=refresh bytes={}",
                    len(raw_message),
                )
            elif self._cache is not None:
                logger.info(
                    "imap_cache tool=get_email action=write status=skip reason=message_too_large bytes={} max_bytes={}",
                    len(raw_message),
                    self._max_cached_message_bytes,
                )
            result = dict(summary)
            result.update(self._message_body(message, max_body_chars))
            return result

    @staticmethod
    def _render_cached_email(value: dict[str, Any], max_body_chars: int) -> dict[str, Any]:
        raw_message = value.get("raw_message")
        if not isinstance(raw_message, bytes):
            raise IMAPServiceError("Cached email content is invalid")
        message = ICloudIMAPService._parse_message(raw_message)
        summary = value.get("summary")
        if not isinstance(summary, dict):
            raise IMAPServiceError("Cached email summary is invalid")
        result = dict(summary)
        result.update(ICloudIMAPService._message_body(message, max_body_chars))
        return result

    def crawl_email_cache(self) -> dict[str, int]:
        """Download uncached messages from newest to oldest in small batches."""

        if self._cache is None:
            logger.info("imap_cache tool=crawl_email_cache action=complete status=disabled")
            return {"mailboxes": 0, "messages": 0, "bytes": 0, "skipped": 0}

        self._crawl_stop_event.clear()
        crawl_started = perf_counter()
        cache_stats = self._cache.email_cache_stats()
        logger.info(
            "imap_cache tool=crawl_email_cache action=start status=running "
            "cached_messages={} cached_bytes={} cached_mailboxes={} batch_size={} "
            "interval_seconds={} max_message_bytes={}",
            cache_stats["messages"],
            cache_stats["bytes"],
            cache_stats["mailboxes"],
            self._crawl_batch_size,
            self._crawl_interval_seconds,
            self._max_cached_message_bytes,
        )
        totals = {
            "mailboxes": 0,
            "mailboxes_completed": 0,
            "mailboxes_failed": 0,
            "messages": 0,
            "bytes": 0,
            "skipped": 0,
        }
        try:
            mailboxes = self.list_mailboxes()
        except Exception as exc:
            cache_stats = self._cache.email_cache_stats()
            logger.warning(
                "imap_cache tool=crawl_email_cache action=complete status=error "
                "error_type={} duration_ms={:.1f} cached_messages={} cached_bytes={} "
                "cached_mailboxes={}",
                exc.__class__.__name__,
                (perf_counter() - crawl_started) * 1000,
                cache_stats["messages"],
                cache_stats["bytes"],
                cache_stats["mailboxes"],
            )
            return totals

        selectable_mailboxes = [
            mailbox
            for mailbox in mailboxes
            if "\\noselect" not in {str(flag).casefold() for flag in mailbox.get("flags", [])}
        ]
        mailbox_total = len(selectable_mailboxes)
        logger.info(
            "imap_cache tool=crawl_email_cache action=mailboxes status=ready "
            "mailbox_total={} cached_messages={} cached_bytes={} cached_mailboxes={}",
            mailbox_total,
            cache_stats["messages"],
            cache_stats["bytes"],
            cache_stats["mailboxes"],
        )
        for mailbox_index, mailbox in enumerate(selectable_mailboxes, start=1):
            if self._crawl_stop_event.is_set():
                break
            totals["mailboxes"] += 1
            try:
                stats = self._crawl_mailbox(
                    str(mailbox["name"]),
                    mailbox_index=mailbox_index,
                    mailbox_total=mailbox_total,
                )
            except Exception as exc:
                totals["mailboxes_failed"] += 1
                cache_stats = self._cache.email_cache_stats()
                logger.warning(
                    "imap_cache tool=crawl_email_cache action=mailbox status=error "
                    "mailbox_index={} mailbox_total={} error_type={} "
                    "cached_messages={} cached_bytes={} cached_mailboxes={}",
                    mailbox_index,
                    mailbox_total,
                    exc.__class__.__name__,
                    cache_stats["messages"],
                    cache_stats["bytes"],
                    cache_stats["mailboxes"],
                )
                continue
            totals["mailboxes_completed"] += 1
            for key in ("messages", "bytes", "skipped"):
                totals[key] += stats[key]
        cache_stats = self._cache.email_cache_stats()
        status = "stopped" if self._crawl_stop_event.is_set() else "ok"
        logger.info(
            "imap_cache tool=crawl_email_cache action=complete status={} duration_ms={:.1f} "
            "mailboxes={} mailboxes_completed={} mailboxes_failed={} messages={} bytes={} skipped={} "
            "cached_messages={} cached_bytes={} cached_mailboxes={}",
            status,
            (perf_counter() - crawl_started) * 1000,
            totals["mailboxes"],
            totals["mailboxes_completed"],
            totals["mailboxes_failed"],
            totals["messages"],
            totals["bytes"],
            totals["skipped"],
            cache_stats["messages"],
            cache_stats["bytes"],
            cache_stats["mailboxes"],
        )
        return totals

    def _crawl_mailbox(
        self,
        mailbox: str,
        *,
        mailbox_index: int,
        mailbox_total: int,
    ) -> dict[str, int]:
        mailbox_started = perf_counter()
        stats = {"messages": 0, "bytes": 0, "skipped": 0, "pending": 0}
        with self._connected("crawl_email_cache") as client:
            selected_data = self._select(
                client,
                mailbox,
                readonly=True,
                operation="crawl_email_cache",
            )
            uid_validity = self._uid_validity(client, selected_data)
            started = perf_counter()
            status, data = client.uid("SEARCH", None, "ALL")
            self._ensure_ok(status, "IMAP cache crawl search failed")
            uids = self._parse_uids(data)
            logger.info(
                "imap_phase tool=crawl_email_cache phase=search duration_ms={:.1f} uid_count={}",
                (perf_counter() - started) * 1000,
                len(uids),
            )
            cached_uids = self._cache.cached_email_uids(mailbox, uids)
            pending = [uid for uid in reversed(uids) if uid not in cached_uids]
            stats["pending"] = len(pending)
            logger.info(
                "imap_cache tool=crawl_email_cache action=mailbox status=running "
                "mailbox_index={} mailbox_total={} uid_count={} cached_messages={} "
                "pending_messages={}",
                mailbox_index,
                mailbox_total,
                len(uids),
                len(cached_uids),
                len(pending),
            )
            processed = 0
            for offset in range(0, len(pending), self._crawl_batch_size):
                if self._crawl_stop_event.is_set():
                    break
                batch = pending[offset : offset + self._crawl_batch_size]
                processed += len(batch)
                started = perf_counter()
                status, fetched = client.uid(
                    "FETCH",
                    ",".join(batch),
                    "(UID FLAGS BODY.PEEK[])",
                )
                self._ensure_ok(status, "IMAP cache message fetch failed")
                parsed = self._parse_full_fetch(fetched, mailbox=mailbox)
                messages = []
                for uid in batch:
                    item = parsed.get(uid)
                    if item is None:
                        continue
                    summary, raw_message = item
                    if len(raw_message) > self._max_cached_message_bytes:
                        stats["skipped"] += 1
                        continue
                    messages.append(
                        {
                            "mailbox": mailbox,
                            "uid": uid,
                            "uid_validity": uid_validity,
                            "summary": summary,
                            "raw_message": raw_message,
                        }
                    )
                self._cache.set_email_messages(messages)
                batch_bytes = sum(len(item["raw_message"]) for item in messages)
                stats["messages"] += len(messages)
                stats["bytes"] += batch_bytes
                cache_stats = self._cache.email_cache_stats()
                logger.info(
                    "imap_cache tool=crawl_email_cache action=write status=refresh "
                    "mailbox_index={} mailbox_total={} batch_entries={} progress={}/{} "
                    "pending_remaining={} bytes={} duration_ms={:.1f} cached_messages={} "
                    "cached_bytes={} cached_mailboxes={}",
                    mailbox_index,
                    mailbox_total,
                    len(messages),
                    min(offset + len(batch), len(pending)),
                    len(pending),
                    max(len(pending) - offset - len(batch), 0),
                    batch_bytes,
                    (perf_counter() - started) * 1000,
                    cache_stats["messages"],
                    cache_stats["bytes"],
                    cache_stats["mailboxes"],
                )
                if self._crawl_interval_seconds:
                    sleep(self._crawl_interval_seconds)
            stats["pending"] = max(len(pending) - processed, 0)
        cache_stats = self._cache.email_cache_stats()
        status = "stopped" if self._crawl_stop_event.is_set() else "complete"
        logger.info(
            "imap_cache tool=crawl_email_cache action=mailbox status={} "
            "mailbox_index={} mailbox_total={} fetched_messages={} fetched_bytes={} "
            "skipped_messages={} pending_messages={} cached_messages={} cached_bytes={} "
            "cached_mailboxes={} duration_ms={:.1f}",
            status,
            mailbox_index,
            mailbox_total,
            stats["messages"],
            stats["bytes"],
            stats["skipped"],
            stats["pending"],
            cache_stats["messages"],
            cache_stats["bytes"],
            cache_stats["mailboxes"],
            (perf_counter() - mailbox_started) * 1000,
        )
        return stats

    def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        mailbox: str | None = None,
        body_format: str = "plain",
        attachments: list[dict[str, str]] | None = None,
        from_address: str | None = None,
    ) -> dict[str, Any]:
        selected_mailbox = self._draft_mailbox(mailbox)
        message, attachment_count = self._build_draft_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            body_format=body_format,
            attachments=attachments,
            from_address=from_address,
        )

        with self._connected("create_draft") as client:
            uid = self._append_draft(client, selected_mailbox, message)
        self._invalidate_email_cache("create_draft", selected_mailbox)
        return {
            "created": True,
            "mailbox": selected_mailbox,
            "uid": uid,
            "subject": subject.strip(),
            "attachment_count": attachment_count,
        }

    def update_draft(
        self,
        uid: str,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        mailbox: str | None = None,
        body_format: str = "plain",
        attachments: list[dict[str, str]] | None = None,
        from_address: str | None = None,
    ) -> dict[str, Any]:
        uid = self._uid(uid)
        selected_mailbox = self._draft_mailbox(mailbox)
        message, attachment_count = self._build_draft_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            body_format=body_format,
            attachments=attachments,
            from_address=from_address,
        )

        with self._connected("update_draft") as client:
            self._select(client, selected_mailbox, readonly=False, operation="update_draft")
            self._require_draft(client, uid)
            new_uid = self._append_draft(client, selected_mailbox, message)
            status, _ = client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)")
            self._ensure_ok(status, "IMAP draft replacement failed")
            old_expunged = self._expunge_uid_safely(client, uid)
        self._invalidate_email_cache("update_draft", selected_mailbox)
        return {
            "updated": True,
            "mailbox": selected_mailbox,
            "old_uid": uid,
            "uid": new_uid,
            "old_draft_marked_deleted": True,
            "old_draft_expunged": old_expunged,
            "subject": subject.strip(),
            "attachment_count": attachment_count,
        }

    def _require_draft(self, client: Any, uid: str) -> None:
        status, fetched = client.uid("FETCH", uid, "(UID FLAGS)")
        self._ensure_ok(status, "IMAP draft lookup failed")
        for item in fetched or []:
            metadata = item[0] if isinstance(item, tuple) and item else item
            if not isinstance(metadata, bytes):
                continue
            match = re.search(rb"\bUID\s+(\d+)\b", metadata)
            if match is None or int(match.group(1)) != int(uid):
                continue
            flags = {flag.casefold() for flag in self._fetch_flags([metadata])}
            if r"\draft" not in flags or r"\deleted" in flags:
                raise IMAPServiceError("Only an existing, non-deleted draft can be updated")
            return
        raise EmailNotFoundError(f"Draft not found: {uid}")

    def _draft_mailbox(self, mailbox: str | None) -> str:
        return self._mailbox(mailbox or self.config.drafts_mailbox)

    def _build_draft_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None,
        bcc: list[str] | None,
        body_format: str,
        attachments: list[dict[str, str]] | None,
        from_address: str | None,
    ) -> tuple[EmailMessage, int]:
        recipients = {
            "To": self._draft_recipients(to, "to"),
            "Cc": self._draft_recipients(cc or [], "cc"),
            "Bcc": self._draft_recipients(bcc or [], "bcc"),
        }
        if not any(recipients.values()):
            raise ValueError("at least one recipient is required")

        subject = self._draft_header(subject, "subject")
        if not isinstance(body, str):
            raise ValueError("body must be a string")
        if len(body.encode("utf-8")) > self._MAX_DRAFT_BYTES:
            raise ValueError("body is too large")
        body_format = body_format.strip().casefold()
        if body_format not in {"plain", "html"}:
            raise ValueError("body_format must be plain or html")

        message = EmailMessage(policy=policy.SMTP)
        message["From"] = self._draft_header(from_address or self.config.username, "from_address")
        message["Subject"] = subject
        for header, values in recipients.items():
            if values:
                message[header] = ", ".join(values)
        if body_format == "html":
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        attachment_count = 0
        total_attachment_bytes = 0
        for attachment in attachments or []:
            payload, filename, content_type = self._draft_attachment(attachment)
            total_attachment_bytes += len(payload)
            if total_attachment_bytes > self._MAX_DRAFT_BYTES:
                raise ValueError("attachments are too large")
            maintype, subtype = content_type.split("/", 1)
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )
            attachment_count += 1

        if len(message.as_bytes()) > self._MAX_DRAFT_BYTES:
            raise ValueError("draft is too large")
        return message, attachment_count

    @staticmethod
    def _draft_recipients(values: list[str], field: str) -> list[str]:
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list of email addresses")
        result: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"{field} must contain strings")
            normalized = value.strip()
            if not normalized:
                continue
            if any(character in normalized for character in "\r\n"):
                raise ValueError(f"{field} must not contain line breaks")
            result.append(normalized)
        return result

    @staticmethod
    def _draft_header(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must not be empty")
        normalized = value.strip()
        if any(character in normalized for character in "\r\n"):
            raise ValueError(f"{field} must not contain line breaks")
        return normalized

    def _draft_attachment(
        self,
        attachment: dict[str, str],
    ) -> tuple[bytes, str, str]:
        if not isinstance(attachment, dict):
            raise ValueError("attachments must contain objects")
        filename = attachment.get("filename")
        content_base64 = attachment.get("content_base64")
        content_type = attachment.get("content_type") or "application/octet-stream"
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("attachment filename must not be empty")
        filename = filename.strip()
        if any(
            character in filename
            for character in "\\/\r\n"
        ) or any(ord(character) < 32 or ord(character) == 127 for character in filename):
            raise ValueError("attachment filename is invalid")
        if not isinstance(content_base64, str) or not content_base64:
            raise ValueError("attachment content_base64 must not be empty")
        try:
            payload = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("attachment content_base64 is invalid") from exc
        if len(payload) > self._MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment is too large")
        if (
            not isinstance(content_type, str)
            or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type)
        ):
            raise ValueError("attachment content_type must be a MIME type")
        return payload, filename, content_type.lower()

    def _append_draft(
        self,
        client: Any,
        mailbox: str,
        message: EmailMessage,
    ) -> str | None:
        status, data = client.append(
            self._quote_mailbox(mailbox),
            r"(\Draft)",
            imaplib.Time2Internaldate(datetime.now(timezone.utc)),
            message.as_bytes(),
        )
        self._ensure_ok(status, "IMAP draft creation failed")
        return self._append_uid(data)

    @staticmethod
    def _append_uid(data: Any) -> str | None:
        for item in data or []:
            if not isinstance(item, bytes):
                continue
            match = re.search(rb"APPENDUID\s+\d+\s+(\d+)", item, re.IGNORECASE)
            if match:
                return match.group(1).decode("ascii")
        return None

    def mark_email_read(
        self,
        mailbox: str | None,
        uid: str,
        read: bool = True,
    ) -> dict[str, Any]:
        uid = self._uid(uid)
        selected_mailbox = self._mailbox(mailbox)
        operation = "+FLAGS.SILENT" if read else "-FLAGS.SILENT"

        with self._connected("mark_email_read") as client:
            self._select(client, selected_mailbox, readonly=False, operation="mark_email_read")
            status, _ = client.uid("STORE", uid, operation, r"(\Seen)")
            self._ensure_ok(status, "IMAP flag update failed")
            result = {
                "uid": uid,
                "mailbox": selected_mailbox,
                "read": read,
            }
        self._invalidate_email_cache("mark_email_read", selected_mailbox)
        return result

    def move_email(
        self,
        source_mailbox: str | None,
        destination_mailbox: str,
        uid: str,
    ) -> dict[str, Any]:
        uid = self._uid(uid)
        source = self._mailbox(source_mailbox)
        destination = self._mailbox(destination_mailbox)
        if source.casefold() == destination.casefold():
            raise ValueError("source_mailbox and destination_mailbox must differ")

        with self._connected("move_email") as client:
            self._select(client, source, readonly=False, operation="move_email")
            status, _ = client.uid("COPY", uid, self._quote_mailbox(destination))
            self._ensure_ok(status, "IMAP copy failed")
            status, _ = client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)")
            self._ensure_ok(status, "IMAP source flag update failed")
            expunged = self._expunge_uid_safely(client, uid)
            result = {
                "uid": uid,
                "source_mailbox": source,
                "destination_mailbox": destination,
                "moved": expunged,
                "source_marked_deleted": True,
                "source_expunged": expunged,
            }
        self._invalidate_email_cache("move_email", source, destination)
        return result

    def delete_email(self, mailbox: str | None, uid: str) -> dict[str, Any]:
        """Mark one message deleted and expunge it when that is safe.

        UID EXPUNGE is not available on every IMAP server. If it is not
        supported, this method leaves the target marked for deletion rather
        than risking a mailbox-wide expunge of unrelated messages.
        """

        uid = self._uid(uid)
        selected_mailbox = self._mailbox(mailbox)
        with self._connected("delete_email") as client:
            self._select(client, selected_mailbox, readonly=False, operation="delete_email")
            status, _ = client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)")
            self._ensure_ok(status, "IMAP delete flag update failed")
            expunged = self._expunge_uid_safely(client, uid)
            result = {
                "uid": uid,
                "mailbox": selected_mailbox,
                "deleted": expunged,
                "marked_deleted": True,
                "expunged": expunged,
            }
        self._invalidate_email_cache("delete_email", selected_mailbox)
        return result

    def _invalidate_email_cache(self, tool: str, *mailboxes: str) -> None:
        if self._cache is not None:
            invalidated = self._cache.invalidate_emails(*mailboxes)
            invalidated_messages = self._cache.invalidate_email_messages(*mailboxes)
            logger.info(
                "imap_cache tool={} action=invalidate kind=email_headers mailboxes={} entries={}",
                tool,
                len(mailboxes),
                invalidated,
            )
            logger.info(
                "imap_cache tool={} action=invalidate kind=email_messages mailboxes={} entries={}",
                tool,
                len(mailboxes),
                invalidated_messages,
            )

    def _expunge_uid_safely(self, client: Any, uid: str) -> bool:
        """Expunge only the requested UID; never use mailbox-wide EXPUNGE."""

        try:
            status, _ = client.uid("EXPUNGE", uid)
            if self._is_ok(status):
                return True
        except Exception:
            pass

        # A SEARCH followed by EXPUNGE cannot isolate a deletion: another
        # connection may mark additional messages deleted between commands.
        return False

    def _select(
        self,
        client: Any,
        mailbox: str,
        *,
        readonly: bool,
        operation: str,
    ) -> list[Any]:
        started = perf_counter()
        try:
            status, data = client.select(self._quote_mailbox(mailbox), readonly=readonly)
        except Exception as exc:
            raise MailboxNotFoundError(f"Mailbox not available: {mailbox}") from exc
        if not self._is_ok(status):
            raise MailboxNotFoundError(f"Mailbox not available: {mailbox}")
        logger.info(
            "imap_phase tool={} phase=select duration_ms={:.1f}",
            operation,
            (perf_counter() - started) * 1000,
        )
        return data or []

    @staticmethod
    def _ensure_ok(status: Any, message: str) -> None:
        if not ICloudIMAPService._is_ok(status):
            raise IMAPServiceError(message)

    @staticmethod
    def _is_ok(status: Any) -> bool:
        if isinstance(status, bytes):
            status = status.decode("ascii", errors="ignore")
        return str(status).upper() == "OK"

    def _mailbox(self, mailbox: str | None) -> str:
        value = (mailbox or self.config.default_mailbox).strip()
        if not value:
            raise ValueError("mailbox must not be empty")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("mailbox must not contain control characters")
        return value

    @staticmethod
    def _uid(uid: str) -> str:
        value = uid.strip()
        if not value.isdigit() or int(value) < 1:
            raise ValueError("uid must be a positive IMAP UID")
        return value

    def _validate_limit(self, limit: int) -> int:
        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {self._MAX_LIMIT}")
        return limit

    @staticmethod
    def _quote_search_value(value: str, field: str) -> str | bytes:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} must not be empty")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError(f"{field} must not contain control characters")
        if len(normalized) > 512:
            raise ValueError(f"{field} is too long")
        if any(ord(character) > 127 for character in normalized):
            encoded = normalized.encode("utf-8")
            return b'"' + encoded.replace(b"\\", b"\\\\").replace(b'"', b'\\"') + b'"'
        return ICloudIMAPService._quote_string(normalized)

    @staticmethod
    def _quote_string(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @classmethod
    def _quote_mailbox(cls, value: str) -> str:
        return cls._quote_string(cls._encode_modified_utf7(value))

    @staticmethod
    def _imap_date(value: str, field: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc
        return parsed.strftime("%d-%b-%Y")

    @classmethod
    def _parse_list_row(cls, row: Any) -> dict[str, Any] | None:
        if isinstance(row, tuple):
            row = row[0] if row else None
        if not isinstance(row, bytes):
            return None
        match = re.match(rb'^\((?P<flags>[^)]*)\)\s+(?P<delimiter>NIL|"(?:\\.|[^"])*")\s+(?P<name>.*)$', row)
        if match is None:
            return None
        flags = [
            item.decode("ascii", errors="replace")
            for item in match.group("flags").split()
        ]
        delimiter = cls._unquote_wire(match.group("delimiter"))
        name = cls._decode_modified_utf7(cls._unquote_wire(match.group("name")))
        return {"name": name, "delimiter": delimiter, "flags": flags}

    @staticmethod
    def _unquote_wire(value: bytes) -> str:
        if value == b"NIL":
            return ""
        if len(value) >= 2 and value[:1] == b'"' and value[-1:] == b'"':
            value = value[1:-1].replace(b"\\\"", b'"').replace(b"\\\\", b"\\")
        return value.decode("ascii", errors="replace")

    @staticmethod
    def _decode_modified_utf7(value: str) -> str:
        """Decode IMAP's modified UTF-7 mailbox representation."""

        output: list[str] = []
        index = 0
        while index < len(value):
            if value[index] != "&":
                output.append(value[index])
                index += 1
                continue
            end = value.find("-", index + 1)
            if end < 0:
                output.append(value[index:])
                break
            encoded = value[index + 1 : end]
            if not encoded:
                output.append("&")
            else:
                encoded = encoded.replace(",", "/")
                encoded += "=" * ((4 - len(encoded) % 4) % 4)
                try:
                    output.append(base64.b64decode(encoded).decode("utf-16-be"))
                except (ValueError, UnicodeDecodeError):
                    output.append(value[index : end + 1])
            index = end + 1
        return "".join(output)

    @staticmethod
    def _encode_modified_utf7(value: str) -> str:
        """Encode a Unicode mailbox name using IMAP's modified UTF-7."""

        output: list[str] = []
        non_ascii: list[str] = []

        def flush_non_ascii() -> None:
            if not non_ascii:
                return
            encoded = base64.b64encode("".join(non_ascii).encode("utf-16-be"))
            output.append("&" + encoded.decode("ascii").rstrip("=").replace("/", ",") + "-")
            non_ascii.clear()

        for character in value:
            if character == "&":
                flush_non_ascii()
                output.append("&-")
            elif 0x20 <= ord(character) <= 0x7E:
                flush_non_ascii()
                output.append(character)
            else:
                non_ascii.append(character)
        flush_non_ascii()
        return "".join(output)

    @staticmethod
    def _parse_uids(data: Any) -> list[str]:
        if not data:
            return []
        values: list[str] = []
        for item in data:
            if isinstance(item, bytes):
                values.extend(
                    value.decode("ascii", errors="ignore")
                    for value in item.split()
                    if value.isdigit()
                )
            elif isinstance(item, str):
                values.extend(value for value in item.split() if value.isdigit())
        return values

    @staticmethod
    def _literal_bytes(data: Any) -> bytes:
        if not data:
            return b""
        candidates: list[bytes] = []
        for item in data:
            if isinstance(item, tuple):
                candidates.extend(part for part in item if isinstance(part, bytes))
            elif isinstance(item, bytes) and not item.startswith(b")"):
                candidates.append(item)
        return candidates[-1] if candidates else b""

    @staticmethod
    def _fetch_flags(data: Any) -> list[str]:
        flags: list[str] = []
        pattern = re.compile(rb"FLAGS \(([^)]*)\)")
        for item in data or []:
            parts = item if isinstance(item, tuple) else (item,)
            for part in parts:
                if not isinstance(part, bytes):
                    continue
                match = pattern.search(part)
                if match:
                    flags.extend(
                        flag.decode("ascii", errors="replace")
                        for flag in match.group(1).split()
                    )
        return flags

    @staticmethod
    def _parse_message(raw: bytes) -> Message:
        try:
            return BytesParser(policy=policy.default).parsebytes(raw)
        except Exception as exc:
            raise IMAPServiceError("Email could not be parsed") from exc

    @classmethod
    def _message_summary(
        cls,
        message: Message,
        *,
        uid: str,
        mailbox: str,
        flags: list[str],
    ) -> dict[str, Any]:
        raw_date = message.get("Date")
        parsed_date: str | None = None
        if raw_date:
            try:
                parsed_date = parsedate_to_datetime(raw_date).isoformat()
            except (TypeError, ValueError, OverflowError):
                parsed_date = str(raw_date)
        return {
            "uid": uid,
            "mailbox": mailbox,
            "subject": cls._header(message, "Subject"),
            "from": cls._header(message, "From"),
            "to": cls._header(message, "To"),
            "cc": cls._header(message, "Cc"),
            "date": parsed_date,
            "message_id": cls._header(message, "Message-ID"),
            "flags": flags,
            "read": r"\Seen" in flags,
        }

    @staticmethod
    def _header(message: Message, name: str) -> str | None:
        value = message.get(name)
        return str(value).strip() if value is not None else None

    @classmethod
    def _message_body(cls, message: Message, max_chars: int) -> dict[str, Any]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[dict[str, Any]] = []

        for part in message.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            disposition = (part.get_content_disposition() or "").lower()
            payload = part.get_payload(decode=True) or b""
            if filename or disposition == "attachment":
                attachments.append(
                    {
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(payload),
                    }
                )
                continue
            if part.get_content_maintype() != "text":
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            if part.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

        body = "\n\n".join(plain_parts) or "\n\n".join(html_parts)
        truncated = len(body) > max_chars
        return {
            "body": body[:max_chars],
            "body_truncated": truncated,
            "body_format": "plain" if plain_parts else ("html" if html_parts else None),
            "attachments": attachments,
        }
