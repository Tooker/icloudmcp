from __future__ import annotations

import base64
import imaplib
import re
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from datetime import date
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any

from app.config import IMAPConfig


class IMAPServiceError(RuntimeError):
    """A safe, user-facing IMAP operation error."""


class MailboxNotFoundError(IMAPServiceError):
    pass


class EmailNotFoundError(IMAPServiceError):
    pass


class ICloudIMAPService:
    """Small synchronous IMAP facade used from MCP worker threads.

    IMAP operations are blocking. The MCP layer deliberately calls this
    service with ``asyncio.to_thread`` so a slow mail server cannot block the
    ASGI event loop.
    """

    _MAX_LIMIT = 200
    _MAX_BODY_CHARS = 100_000
    _FETCH_HEADERS = (
        "(UID FLAGS BODY.PEEK[HEADER.FIELDS "
        "(DATE FROM TO CC SUBJECT MESSAGE-ID)])"
    )

    def __init__(
        self,
        config: IMAPConfig,
        client_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
    ) -> None:
        self.config = config
        self._client_factory = client_factory

    @contextmanager
    def _connected(self) -> Iterator[Any]:
        client = self._client_factory(self.config.host, self.config.port, timeout=30)
        try:
            try:
                status, _ = client.login(
                    self.config.username,
                    self.config.app_specific_password,
                )
            except imaplib.IMAP4.error as exc:
                raise IMAPServiceError(
                    "IMAP login failed; check the iCloud Mail address and app-specific password"
                ) from exc
            self._ensure_ok(status, "IMAP login failed")
            yield client
        finally:
            try:
                logout = getattr(client, "logout", None)
                if callable(logout):
                    logout()
            except Exception:
                # Closing a connection must not replace the useful operation
                # result or leak server-specific connection details.
                shutdown = getattr(client, "shutdown", None)
                if callable(shutdown):
                    try:
                        shutdown()
                    except Exception:
                        pass

    def list_mailboxes(self) -> list[dict[str, Any]]:
        with self._connected() as client:
            status, rows = client.list()
            self._ensure_ok(status, "IMAP mailbox listing failed")

            result: list[dict[str, Any]] = []
            for row in rows or []:
                parsed = self._parse_list_row(row)
                if parsed is not None:
                    result.append(parsed)
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
        criteria: list[str] = []
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

        selected_mailbox = self._mailbox(mailbox)
        with self._connected() as client:
            self._select(client, selected_mailbox, readonly=True)
            status, data = client.uid("SEARCH", None, *criteria)
            self._ensure_ok(status, "IMAP search failed")
            uids = self._parse_uids(data)

            # IMAP SEARCH normally returns ascending UIDs. Returning newest
            # candidates first makes the limit useful for large inboxes.
            selected_uids = list(reversed(uids[-limit:]))
            result: list[dict[str, Any]] = []
            for uid in selected_uids:
                status, fetched = client.uid("FETCH", uid, self._FETCH_HEADERS)
                self._ensure_ok(status, "IMAP header fetch failed")
                raw_headers = self._literal_bytes(fetched)
                message = self._parse_message(raw_headers)
                result.append(
                    self._message_summary(
                        message,
                        uid=uid,
                        mailbox=selected_mailbox,
                        flags=self._fetch_flags(fetched),
                    )
                )
            return result

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

        with self._connected() as client:
            self._select(client, selected_mailbox, readonly=True)
            status, fetched = client.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])")
            self._ensure_ok(status, "IMAP message fetch failed")
            raw_message = self._literal_bytes(fetched)
            if not raw_message:
                raise EmailNotFoundError(f"Email not found: {uid}")
            message = self._parse_message(raw_message)
            result = self._message_summary(
                message,
                uid=uid,
                mailbox=selected_mailbox,
                flags=self._fetch_flags(fetched),
            )
            result.update(self._message_body(message, max_body_chars))
            return result

    def mark_email_read(
        self,
        mailbox: str | None,
        uid: str,
        read: bool = True,
    ) -> dict[str, Any]:
        uid = self._uid(uid)
        selected_mailbox = self._mailbox(mailbox)
        operation = "+FLAGS.SILENT" if read else "-FLAGS.SILENT"

        with self._connected() as client:
            self._select(client, selected_mailbox, readonly=False)
            status, _ = client.uid("STORE", uid, operation, r"(\Seen)")
            self._ensure_ok(status, "IMAP flag update failed")
            return {
                "uid": uid,
                "mailbox": selected_mailbox,
                "read": read,
            }

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

        with self._connected() as client:
            self._select(client, source, readonly=False)
            status, _ = client.uid("COPY", uid, self._quote_mailbox(destination))
            self._ensure_ok(status, "IMAP copy failed")
            status, _ = client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)")
            self._ensure_ok(status, "IMAP source flag update failed")
            expunged = self._expunge_uid_safely(client, uid)
            return {
                "uid": uid,
                "source_mailbox": source,
                "destination_mailbox": destination,
                "moved": expunged,
                "source_marked_deleted": True,
                "source_expunged": expunged,
            }

    def delete_email(self, mailbox: str | None, uid: str) -> dict[str, Any]:
        """Mark one message deleted and expunge it when that is safe.

        UID EXPUNGE is not available on every IMAP server. If it is not
        supported and other messages are already marked ``\\Deleted``, this
        method intentionally leaves the target marked for deletion rather
        than expunging unrelated messages.
        """

        uid = self._uid(uid)
        selected_mailbox = self._mailbox(mailbox)
        with self._connected() as client:
            self._select(client, selected_mailbox, readonly=False)
            status, _ = client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)")
            self._ensure_ok(status, "IMAP delete flag update failed")
            expunged = self._expunge_uid_safely(client, uid)
            return {
                "uid": uid,
                "mailbox": selected_mailbox,
                "deleted": expunged,
                "marked_deleted": True,
                "expunged": expunged,
            }

    def _expunge_uid_safely(self, client: Any, uid: str) -> bool:
        """Try UID EXPUNGE, otherwise expunge only an isolated deletion."""

        try:
            status, _ = client.uid("EXPUNGE", uid)
            if self._is_ok(status):
                return True
        except Exception:
            pass

        try:
            status, data = client.uid("SEARCH", None, "DELETED")
            if not self._is_ok(status):
                return False
            deleted_uids = set(self._parse_uids(data))
            if deleted_uids != {uid}:
                return False
            status, _ = client.expunge()
            return self._is_ok(status)
        except Exception:
            return False

    def _select(self, client: Any, mailbox: str, *, readonly: bool) -> None:
        try:
            status, _ = client.select(self._quote_mailbox(mailbox), readonly=readonly)
        except Exception as exc:
            raise MailboxNotFoundError(f"Mailbox not available: {mailbox}") from exc
        if not self._is_ok(status):
            raise MailboxNotFoundError(f"Mailbox not available: {mailbox}")

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
    def _quote_search_value(value: str, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} must not be empty")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError(f"{field} must not contain control characters")
        if len(normalized) > 512:
            raise ValueError(f"{field} is too long")
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
