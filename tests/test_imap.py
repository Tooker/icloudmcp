from __future__ import annotations

import base64
import imaplib
from typing import Any

import pytest

from app.config import IMAPConfig
from app.imap import ICloudIMAPService, IMAPServiceError
from app.icloud_cache import SQLiteICloudCalendarCache


MESSAGE = (
    b"From: Alice <alice@example.com>\r\n"
    b"To: Bob <bob@example.com>\r\n"
    b"Subject: =?utf-8?b?VGVzdCDDpA==?=\r\n"
    b"Date: Tue, 29 Sep 2026 10:00:00 +0000\r\n"
    b"Message-ID: <message-1@example.com>\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Hello from iCloud.\r\n"
)


class FakeIMAP:
    def __init__(self, *_: Any, **__: Any) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.calls.append(("LOGIN", (username, password)))
        return "OK", [b"logged in"]

    def logout(self) -> tuple[str, list[bytes]]:
        self.calls.append(("LOGOUT", ()))
        return "OK", [b"bye"]

    def list(self) -> tuple[str, list[bytes]]:
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "&ANw-bersicht"',
        ]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.calls.append(("SELECT", (mailbox, readonly)))
        return "OK", [b"1"]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        self.calls.append((command, args))
        if command == "SEARCH":
            if args[-1] == "DELETED":
                return "OK", [b"42"]
            return "OK", [b"41 42"]
        if command == "FETCH":
            uids = str(args[0]).split(",")
            fetched: list[Any] = []
            for uid in uids:
                if "HEADER.FIELDS" in str(args[1]):
                    raw = MESSAGE.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                else:
                    raw = MESSAGE
                metadata = f"{uid} FETCH (UID {uid} FLAGS (\\Seen) BODY {{{len(raw)}}})".encode()
                fetched.append((metadata, raw))
            fetched.append(b")")
            return "OK", fetched
        if command == "EXPUNGE":
            return "BAD", [b"UID EXPUNGE unsupported"]
        return "OK", [b"done"]

    def expunge(self) -> tuple[str, list[bytes]]:
        self.calls.append(("EXPUNGE", ()))
        return "OK", [b"expunged"]

    def append(
        self,
        mailbox: str,
        flags: str,
        date_time: Any,
        message: bytes,
    ) -> tuple[str, list[bytes]]:
        self.calls.append(("APPEND", (mailbox, flags, date_time, message)))
        return "OK", [b"[APPENDUID 1 77] APPEND completed"]


class FailingLoginIMAP(FakeIMAP):
    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication Failed")


def service_with(
    client: FakeIMAP,
    cache: SQLiteICloudCalendarCache | None = None,
    email_cache_days: int = 100,
    email_cache_max_messages: int = 1000,
) -> ICloudIMAPService:
    config = IMAPConfig(
        username="user@example.com",
        app_specific_password="app-password",
    )
    return ICloudIMAPService(
        config,
        client_factory=lambda *_args, **_kwargs: client,
        cache=cache,
        email_cache_days=email_cache_days,
        email_cache_max_messages=email_cache_max_messages,
    )


def test_lists_mailboxes_and_decodes_modified_utf7() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    mailboxes = mail.list_mailboxes()

    assert mailboxes[0]["name"] == "INBOX"
    assert mailboxes[1]["name"] == "Übersicht"


def test_reuses_a_successful_connection_for_sequential_operations() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    mail.list_mailboxes()
    mail.list_mailboxes()

    assert sum(call[0] == "LOGIN" for call in client.calls) == 1
    assert sum(call[0] == "LOGOUT" for call in client.calls) == 0


def test_login_failure_is_safe_and_actionable() -> None:
    mail = service_with(FailingLoginIMAP())

    with pytest.raises(IMAPServiceError, match="iCloud Mail address and app-specific password"):
        mail.list_mailboxes()


def test_search_and_read_use_uid_and_peek() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    results = mail.search_emails(subject="Test", unread_only=True, limit=1)
    message = mail.get_email("INBOX", "42")

    assert results[0]["uid"] == "42"
    assert results[0]["subject"] == "Test ä"
    assert message["body"] == "Hello from iCloud.\r\n"
    assert any(
        call[0] == "FETCH" and "BODY.PEEK[]" in str(call[1])
        for call in client.calls
    )


def test_recent_email_header_search_uses_cache(tmp_path) -> None:
    client = FakeIMAP()
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    mail = service_with(client, cache=cache)

    first = mail.search_emails(subject="Test", limit=1)
    second = mail.search_emails(subject="Test", limit=1)

    assert first == second
    assert sum(call[0] == "SEARCH" for call in client.calls) == 1


def test_email_write_invalidates_mailbox_cache(tmp_path) -> None:
    client = FakeIMAP()
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    mail = service_with(client, cache=cache)
    mail.search_emails(limit=1)

    assert cache.get_emails("INBOX") is not None
    mail.mark_email_read("INBOX", "42", read=False)
    assert cache.get_emails("INBOX") is None


def test_create_draft_appends_mime_message_with_attachment() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    draft = mail.create_draft(
        to=["Bob <bob@example.com>"],
        subject="A draft",
        body="Hello from a draft",
        attachments=[
            {
                "filename": "note.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(b"attachment").decode("ascii"),
            }
        ],
    )

    assert draft["created"] is True
    assert draft["uid"] == "77"
    assert draft["attachment_count"] == 1
    append = next(call for call in client.calls if call[0] == "APPEND")
    assert append[1][0] == '"Drafts"'
    assert b"Subject: A draft" in append[1][3]
    assert b"note.txt" in append[1][3]


def test_update_draft_replaces_old_draft_without_sending() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    updated = mail.update_draft(
        uid="42",
        to=["Bob <bob@example.com>"],
        subject="Updated draft",
        body="Updated body",
    )

    assert updated["updated"] is True
    assert updated["uid"] == "77"
    assert updated["old_draft_marked_deleted"] is True
    assert any(call[0] == "STORE" for call in client.calls)


def test_write_operations_mark_move_and_delete_by_uid() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    assert mail.mark_email_read("INBOX", "42", read=False)["read"] is False
    moved = mail.move_email("INBOX", "Archive", "42")
    deleted = mail.delete_email("INBOX", "42")

    assert moved["source_marked_deleted"] is True
    assert moved["source_expunged"] is True
    assert deleted["expunged"] is True
    assert any(call[0] == "COPY" for call in client.calls)
