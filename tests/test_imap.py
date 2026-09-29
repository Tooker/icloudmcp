from __future__ import annotations

import base64
import imaplib
import ssl
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.config import IMAPConfig
from app.imap import EmailNotFoundError, ICloudIMAPService, IMAPServiceError
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
        self.uid_validity = "7"
        self.message = MESSAGE

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

    def response(self, code: str) -> tuple[str, list[Any]]:
        return code, [self.uid_validity.encode()] if code == "UIDVALIDITY" else [None]

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
                    raw = self.message.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                else:
                    raw = self.message
                internal_date = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S %z")
                metadata = (
                    f'{uid} FETCH (UID {uid} FLAGS (\\Seen) INTERNALDATE "{internal_date}" '
                    f'BODY {{{len(raw)}}})'
                ).encode()
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


class SearchMailboxIMAP(FakeIMAP):
    """A mailbox whose SEARCH applies filters before FETCH applies the limit."""

    def __init__(self, subjects: list[str], dates: list[date] | None = None) -> None:
        super().__init__()
        self.messages = {
            str(index): (subject, received)
            for index, (subject, received) in enumerate(
                zip(subjects, dates or [date.today()] * len(subjects)), start=1
            )
        }

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "SEARCH":
            self.calls.append((command, args))
            selected = []
            for uid, (subject, received) in self.messages.items():
                if "SUBJECT" in args and str(args[args.index("SUBJECT") + 1]).strip('"') not in subject:
                    continue
                if "SINCE" in args and received < datetime.strptime(
                    str(args[args.index("SINCE") + 1]), "%d-%b-%Y"
                ).date():
                    continue
                selected.append(uid)
            return "OK", [" ".join(selected).encode()]
        if command == "FETCH":
            self.calls.append((command, args))
            rows = []
            for uid in str(args[0]).split(","):
                subject, received = self.messages[uid]
                # Deliberately unrelated Date headers: SEARCH uses INTERNALDATE.
                raw = (
                    f"Subject: {subject}\r\nDate: Wed, 1 Jan 2020 10:00:00 +0000\r\n\r\n"
                ).encode()
                internal_date = received.strftime("%d-%b-%Y") + " 10:00:00 +0200"
                rows.append((
                    f'{uid} (UID {uid} FLAGS () INTERNALDATE "{internal_date}" BODY {{{len(raw)}}})'.encode(),
                    raw,
                ))
            return "OK", rows + [b")"]
        return super().uid(command, *args)


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


@pytest.mark.parametrize("name", ["Übersicht", "日本語", "A & B", 'Ü"ber\\sicht', "&ANw-bersicht"])
@pytest.mark.parametrize("literal", [False, True])
def test_utf8_mailbox_names_round_trip_through_all_commands(name: str, literal: bool) -> None:
    class UTF8IMAP(FakeIMAP):
        def enable(self, capability: str) -> tuple[str, list[bytes]]:
            return "OK", [b"enabled"]

        def list(self) -> tuple[str, list[Any]]:
            if literal:
                encoded = name.encode("utf-8")
                return "OK", [(f'(\\HasNoChildren) "/" {{{len(encoded)}}}'.encode(), encoded)]
            return "OK", [f'(\\HasNoChildren) "/" {ICloudIMAPService._quote_string(name)}'.encode("utf-8")]

    client = UTF8IMAP()
    mail = service_with(client)
    returned_name = mail.list_mailboxes()[0]["name"]
    assert returned_name == name
    mail.get_email(returned_name, "42")
    mail.create_draft(to=["bob@example.com"], subject="Draft", body="Body", mailbox=returned_name)
    mail.move_email("INBOX", returned_name, "42")
    quoted = ICloudIMAPService._quote_string(name)
    assert ("SELECT", (quoted, True)) in client.calls
    assert next(args[0] for command, args in client.calls if command == "APPEND") == quoted
    assert ("COPY", ("42", quoted)) in client.calls


def test_rejected_utf8_enable_preserves_modified_utf7_mailboxes() -> None:
    class LegacyIMAP(FakeIMAP):
        def enable(self, capability: str) -> tuple[str, list[bytes]]:
            return "NO", [b"not supported"]

    client = LegacyIMAP()
    mail = service_with(client)
    mailbox = mail.list_mailboxes()[1]["name"]
    assert mailbox == "Übersicht"
    mail.get_email(mailbox, "42")
    assert ("SELECT", ('"&ANw-bersicht"', True)) in client.calls


def test_reuses_a_successful_connection_for_sequential_operations() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    mail.list_mailboxes()
    mail.list_mailboxes()

    assert sum(call[0] == "LOGIN" for call in client.calls) == 1
    assert sum(call[0] == "LOGOUT" for call in client.calls) == 0


def test_list_mailboxes_and_get_email_use_persistent_cache(tmp_path) -> None:
    client = FakeIMAP()
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    mail = service_with(client, cache=cache)

    mail.list_mailboxes()
    mail.list_mailboxes()
    mail.get_email("INBOX", "42")
    mail.get_email("INBOX", "42")

    assert sum(call[0] == "LOGIN" for call in client.calls) == 1
    assert sum(call[0] == "FETCH" for call in client.calls) == 1


def test_switching_imap_account_fetches_its_own_message(tmp_path) -> None:
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    first = service_with(FakeIMAP(), cache=cache)
    first.get_email("INBOX", "42")

    class OtherAccountIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            status, fetched = super().uid(command, *args)
            if command == "FETCH":
                fetched = [
                    (item[0], item[1].replace(b"Hello from iCloud.", b"Other account msg."))
                    if isinstance(item, tuple) else item for item in fetched
                ]
            return status, fetched

    second_client = OtherAccountIMAP()
    second = ICloudIMAPService(
        IMAPConfig(username="other@example.com", app_specific_password="other-password"),
        client_factory=lambda *args, **kwargs: second_client,
        cache=cache,
    )
    assert second.get_email("INBOX", "42")["body"] == "Other account msg.\r\n"
    assert any(call[0] == "LOGIN" for call in second_client.calls)
    assert first.get_email("INBOX", "42")["body"] == "Hello from iCloud.\r\n"


def test_utf8_search_values_are_sent_as_bytes() -> None:
    assert ICloudIMAPService._quote_search_value("Straße", "query") == (
        b'"Stra' + bytes((0xC3, 0x9F)) + b'e"'
    )


def test_crawler_stores_full_messages_newest_first(tmp_path) -> None:
    client = FakeIMAP()
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    mail = service_with(client, cache=cache)

    stats = mail.crawl_email_cache()

    assert stats["messages"] == 4
    assert mail._cache.get_email_message("INBOX", "42") is not None
    assert mail._cache.get_email_message("Übersicht", "41") is not None


def test_reads_normal_imaplib_uid_validity_response() -> None:
    assert ICloudIMAPService._uid_validity(FakeIMAP(), [b"1"]) == "7"
    assert ICloudIMAPService._uid_validity(FakeIMAP(), [b"[UIDVALIDITY 99]"]) == "99"


@pytest.mark.parametrize("restart", [False, True])
def test_get_email_validates_uid_generation_before_cached_read(tmp_path, restart) -> None:
    client = FakeIMAP()
    path = tmp_path / "cache.sqlite3"
    mail = service_with(client, cache=SQLiteICloudCalendarCache(path))
    assert mail.get_email("INBOX", "42")["body"] == "Hello from iCloud.\r\n"
    if restart:
        client = FakeIMAP()
        mail = service_with(client, cache=SQLiteICloudCalendarCache(path))
    client.uid_validity = "99"
    client.message = MESSAGE.replace(b"Hello from iCloud.", b"A different message.")
    assert mail.get_email("INBOX", "42")["body"] == "A different message.\r\n"
    assert mail._cache.get_email_message("INBOX", "42", uid_validity="7") is None
    assert mail._cache.get_email_message("INBOX", "42", uid_validity="99") is not None


def test_crawler_refetches_fresh_uids_after_generation_change(tmp_path) -> None:
    client = FakeIMAP()
    mail = service_with(client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    assert mail._crawl_mailbox("INBOX", mailbox_index=1, mailbox_total=1)["messages"] == 2
    client.uid_validity = "99"
    client.message = MESSAGE.replace(b"Hello from iCloud.", b"A different message.")
    assert mail._crawl_mailbox("INBOX", mailbox_index=1, mailbox_total=1)["messages"] == 2
    assert mail.get_email("INBOX", "42")["body"] == "A different message.\r\n"


def test_header_cache_is_invalidated_on_uid_generation_change(tmp_path) -> None:
    client = FakeIMAP()
    mail = service_with(client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    mail.search_emails(since=mail._email_cache_since())
    client.uid_validity = "99"
    client.message = MESSAGE.replace(b"Subject: =?utf-8?b?VGVzdCDDpA==?=", b"Subject: Replacement")
    results = mail.search_emails(subject="Replacement", since=mail._email_cache_since())
    assert len(results) == 2
    assert all(message["subject"] == "Replacement" for message in results)
    assert mail._cache.get_emails("INBOX").value["uid_validity"] == "99"


def test_unknown_uid_generation_disables_content_cache_reuse(tmp_path) -> None:
    client = FakeIMAP()
    mail = service_with(client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    mail.get_email("INBOX", "42")
    client.uid_validity = ""
    client.message = MESSAGE.replace(b"Hello from iCloud.", b"A different message.")
    assert mail.get_email("INBOX", "42")["body"] == "A different message.\r\n"
    mail.get_email("INBOX", "42")
    assert mail._crawl_mailbox("INBOX", mailbox_index=1, mailbox_total=1)["messages"] == 0
    assert sum(call[0] == "FETCH" for call in client.calls) == 3


def test_login_failure_is_safe_and_actionable() -> None:
    mail = service_with(FailingLoginIMAP())

    with pytest.raises(IMAPServiceError, match="iCloud Mail address and app-specific password"):
        mail.list_mailboxes()


def test_imap_connection_requires_valid_certificate_and_hostname() -> None:
    client = FakeIMAP()
    contexts: list[ssl.SSLContext] = []

    def factory(*args: Any, **kwargs: Any) -> FakeIMAP:
        contexts.append(kwargs["ssl_context"])
        return client

    mail = ICloudIMAPService(
        IMAPConfig(username="user@example.com", app_specific_password="app-password"),
        client_factory=factory,
    )
    mail.list_mailboxes()

    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
    assert contexts[0].get_ca_certs()


def test_certificate_failure_prevents_imap_login() -> None:
    client = FakeIMAP()

    def factory(*args: Any, **kwargs: Any) -> FakeIMAP:
        raise ssl.SSLCertVerificationError("certificate rejected")

    mail = ICloudIMAPService(
        IMAPConfig(username="user@example.com", app_specific_password="app-password"),
        client_factory=factory,
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        mail.list_mailboxes()
    assert client.calls == []


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

    first = mail.search_emails(subject="Test", since=mail._email_cache_since(), limit=1)
    second = mail.search_emails(subject="Test", since=mail._email_cache_since(), limit=1)

    assert first == second
    assert sum(call[0] == "SEARCH" for call in client.calls) == 1


def test_truncated_header_cache_does_not_hide_filtered_matches(tmp_path) -> None:
    client = SearchMailboxIMAP(["Rechnung", "Other", "Other"])
    mail = service_with(
        client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"),
        email_cache_max_messages=2,
    )
    args = {"subject": "Rechnung", "since": mail._email_cache_since()}
    assert [message["uid"] for message in mail.search_emails(**args)] == ["1"]
    assert mail._cache.get_emails("INBOX").value["complete"] is False
    assert [message["uid"] for message in mail.search_emails(**args)] == ["1"]
    # Only the first request refreshes the known-incomplete header cache.
    assert sum(call[0] == "SEARCH" for call in client.calls) == 3


def test_unbounded_header_search_includes_matches_older_than_cache_window(tmp_path) -> None:
    client = SearchMailboxIMAP(
        ["Rechnung", "Other"], [date.today() - timedelta(days=101), date.today()]
    )
    mail = service_with(client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    assert [message["uid"] for message in mail.search_emails(subject="Rechnung")] == ["1"]
    assert not any("SINCE" in args for command, args in client.calls if command == "SEARCH")


def test_complete_cache_at_limit_uses_internal_dates_and_uid_order(tmp_path) -> None:
    client = SearchMailboxIMAP(["First", "Second"])
    mail = service_with(
        client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3", email_max_messages=2),
        email_cache_max_messages=2,
    )
    args = {"since": date.today().isoformat(), "limit": 2}
    first = mail.search_emails(**args)
    second = mail.search_emails(**args)
    assert [message["uid"] for message in first] == ["2", "1"]
    assert second == first
    assert mail._cache.get_emails("INBOX").value["complete"] is True
    assert sum(call[0] == "SEARCH" for call in client.calls) == 1


def test_cached_coverage_is_checked_after_cache_window_configuration_changes(tmp_path) -> None:
    client = SearchMailboxIMAP(["Rechnung"], [date.today() - timedelta(days=20)])
    mail = service_with(client, cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    mail._cache.set_emails(
        "INBOX", [], (date.today() - timedelta(days=5)).isoformat(), complete=True
    )
    results = mail.search_emails(
        subject="Rechnung", since=(date.today() - timedelta(days=30)).isoformat()
    )
    assert [message["uid"] for message in results] == ["1"]
    assert sum(call[0] == "SEARCH" for call in client.calls) == 1


def test_email_write_invalidates_mailbox_cache(tmp_path) -> None:
    client = FakeIMAP()
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    mail = service_with(client, cache=cache)
    mail.search_emails(since=mail._email_cache_since(), limit=1)

    assert mail._cache.get_emails("INBOX") is not None
    mail.mark_email_read("INBOX", "42", read=False)
    assert mail._cache.get_emails("INBOX") is None


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
    class DraftIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            if command == "FETCH" and args[1] == "(UID FLAGS)":
                self.calls.append((command, args))
                return "OK", [b"1 (UID 42 FLAGS (\\Draft))"]
            return super().uid(command, *args)

    client = DraftIMAP()
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
    commands = [call[0] for call in client.calls]
    assert commands.index("FETCH") < commands.index("APPEND") < commands.index("STORE")


@pytest.mark.parametrize("flags", [r"\Seen", r"\Draft \Deleted"])
def test_update_draft_rejects_non_drafts_before_any_write(flags: str) -> None:
    class NotDraftIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            if command == "FETCH":
                return "OK", [f"1 (UID 42 FLAGS ({flags}))".encode()]
            return super().uid(command, *args)

    client = NotDraftIMAP()
    with pytest.raises(IMAPServiceError, match="non-deleted draft"):
        service_with(client).update_draft(
            uid="42", mailbox="INBOX", to=["bob@example.com"], subject="Update", body="Body"
        )
    assert not any(call[0] in {"APPEND", "STORE", "EXPUNGE"} for call in client.calls)


def test_update_draft_rejects_missing_uid_before_any_write() -> None:
    class MissingDraftIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            if command == "FETCH":
                return "OK", [None]
            return super().uid(command, *args)

    client = MissingDraftIMAP()
    with pytest.raises(EmailNotFoundError):
        service_with(client).update_draft(
            uid="42", to=["bob@example.com"], subject="Update", body="Body"
        )
    assert not any(call[0] in {"APPEND", "STORE", "EXPUNGE"} for call in client.calls)


def test_write_operations_mark_move_and_delete_by_uid() -> None:
    client = FakeIMAP()
    mail = service_with(client)

    assert mail.mark_email_read("INBOX", "42", read=False)["read"] is False
    moved = mail.move_email("INBOX", "Archive", "42")
    deleted = mail.delete_email("INBOX", "42")

    assert moved["source_marked_deleted"] is True
    assert moved["source_expunged"] is False
    assert deleted["marked_deleted"] is True
    assert deleted["expunged"] is False
    assert any(call[0] == "COPY" for call in client.calls)


@pytest.mark.parametrize("outcome", ["BAD", "NO", "abort"])
def test_unsupported_uid_expunge_never_uses_mailbox_wide_expunge(outcome: str) -> None:
    class NoUIDExpungeIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            if command == "EXPUNGE":
                self.calls.append((command, args))
                if outcome == "abort":
                    raise imaplib.IMAP4.abort("connection failed")
                return outcome, [b"not available"]
            return super().uid(command, *args)

        def expunge(self) -> tuple[str, list[bytes]]:
            raise AssertionError("mailbox-wide EXPUNGE must never be sent")

    client = NoUIDExpungeIMAP()
    result = service_with(client).delete_email("INBOX", "42")
    assert result["marked_deleted"] is True
    assert result["expunged"] is False
    assert not any(call[0] == "SEARCH" for call in client.calls)


def test_supported_uid_expunge_targets_only_requested_message() -> None:
    class UIDExpungeIMAP(FakeIMAP):
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            if command == "EXPUNGE":
                self.calls.append((command, args))
                return "OK", [b"done"]
            return super().uid(command, *args)

    client = UIDExpungeIMAP()
    result = service_with(client).delete_email("INBOX", "42")
    assert result["expunged"] is True
    assert ("EXPUNGE", ("42",)) in client.calls
    assert ("EXPUNGE", ()) not in client.calls
