from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from app.icloud_cache import SQLiteICloudCalendarCache


def test_sqlite_cache_persists_and_expires_values(tmp_path: Path) -> None:
    now = [100.0]
    database = tmp_path / "cache.sqlite3"
    first = SQLiteICloudCalendarCache(
        database,
        events_ttl_seconds=10,
        calendars_ttl_seconds=30,
        clock=lambda: now[0],
    )
    calendars = [{"id": "work-id", "name": "Work"}]
    first.set_calendars(calendars)

    second = SQLiteICloudCalendarCache(
        database,
        events_ttl_seconds=10,
        calendars_ttl_seconds=30,
        clock=lambda: now[0],
    )
    cached = second.get_calendars()
    assert cached is not None
    assert cached.value == calendars
    assert cached.fresh is True

    now[0] = 131.0
    expired = second.get_calendars()
    assert expired is not None
    assert expired.value == calendars
    assert expired.fresh is False
    assert database.stat().st_mode & 0o077 == 0


def test_sqlite_cache_indexes_events_and_can_invalidate_them(tmp_path: Path) -> None:
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3", clock=lambda: 100.0)
    event = {
        "uid": "event-1",
        "calendar_id": "work-id",
        "calendar_name": "Work",
        "summary": "Planning",
    }
    cache.set_events("work-id", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00", [event])

    events = cache.get_events(
        "work-id",
        "2026-01-01T00:00:00+00:00",
        "2026-02-01T00:00:00+00:00",
    )
    assert events is not None
    assert events.value == [event]
    assert cache.get_event("work", "event-1").value == event

    cache.invalidate_events()
    assert cache.get_events(
        "work-id",
        "2026-01-01T00:00:00+00:00",
        "2026-02-01T00:00:00+00:00",
    ) is None
    assert cache.get_event("work", "event-1") is None


def test_calendar_cache_ignores_summaries_written_before_occurrence_expansion(tmp_path):
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    event = {"uid": "event", "calendar_id": "work", "calendar_name": "Work"}
    cache._set("events:" + cache._digest("work", "start", "end"), [event])
    cache._set("event:" + cache._digest("work", "event"), event)
    assert cache.get_events("work", "start", "end") is None
    assert cache.get_event("work", "event") is None
    assert cache.invalidate_events() == 2


def test_sqlite_cache_keeps_latest_email_headers_with_a_bound(tmp_path: Path) -> None:
    cache = SQLiteICloudCalendarCache(
        tmp_path / "cache.sqlite3",
        email_ttl_seconds=300,
        email_max_messages=2,
        clock=lambda: 100.0,
    )
    emails = [
        {"uid": "1", "date": "2026-01-01T10:00:00+00:00", "subject": "old"},
        {"uid": "3", "date": "2026-01-03T10:00:00+00:00", "subject": "newest"},
        {"uid": "2", "date": "2026-01-02T10:00:00+00:00", "subject": "middle"},
    ]
    cache.set_emails("INBOX", emails, "2025-10-01")

    cached = cache.get_emails("INBOX")
    assert cached is not None
    assert cached.fresh is True
    assert cached.value["coverage_since"] == "2025-10-01"
    assert [email["uid"] for email in cached.value["emails"]] == ["3", "2"]

    cache.invalidate_emails("INBOX")
    assert cache.get_emails("INBOX") is None


def test_full_message_summaries_are_unbounded_generation_checked_and_account_scoped(tmp_path):
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3", email_max_messages=1)
    alice = cache.for_account("imap", "mail.example.com:993", "alice@example.com")
    bob = cache.for_account("imap", "mail.example.com:993", "bob@example.com")
    alice.sync_uid_validity("INBOX", "7")
    messages = [{
        "mailbox": "INBOX", "uid": str(uid), "uid_validity": "7",
        "summary": {"subject": "Stored header"}, "raw_message": b"PRIVATE_BLOB",
    } for uid in range(1, 1002)]
    alice.set_email_messages(messages)
    assert alice.has_email_summaries("INBOX") is True
    assert bob.has_email_summaries("INBOX") is False
    assert alice.has_email_summaries("Archive") is False
    assert len(alice.get_email_summaries("INBOX", [str(uid) for uid in range(1, 1002)], uid_validity="7")) == 1001
    assert bob.get_email_summaries("INBOX", ["1"], uid_validity="7") == {}
    assert alice.get_email_summaries("INBOX", ["1"], uid_validity="99") == {}
    assert alice.get_email_summaries("INBOX", ["1"], uid_validity="") == {}
    alice.sync_uid_validity("INBOX", "99")
    assert alice.get_email_summaries("INBOX", ["1"], uid_validity="7") == {}


def test_unchanged_uid_validation_does_not_wait_for_embedding_writer(tmp_path):
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    cache.sync_uid_validity("INBOX", "7")
    with sqlite3.connect(cache.path) as writer, ThreadPoolExecutor() as pool:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO mailbox_states VALUES ('another-account', '99')")
        future = pool.submit(cache.sync_uid_validity, "INBOX", "7")
        try:
            assert future.result(timeout=1) == 0
        finally:
            writer.rollback()


def test_sqlite_cache_persists_mailboxes_and_full_messages(tmp_path: Path) -> None:
    cache = SQLiteICloudCalendarCache(
        tmp_path / "cache.sqlite3",
        mailboxes_ttl_seconds=300,
        email_content_ttl_seconds=300,
        clock=lambda: 100.0,
    )
    mailboxes = [{"name": "INBOX", "flags": []}]
    cache.set_mailboxes(mailboxes)
    cache.set_email_messages(
        [
            {
                "mailbox": "INBOX",
                "uid": "42",
                "uid_validity": "7",
                "summary": {"uid": "42", "message_id": "<one@example.com>"},
                "raw_message": b"Subject: Cached\r\n\r\nBody",
            }
        ]
    )

    assert cache.get_mailboxes().value == mailboxes
    cached = cache.get_email_message("INBOX", "42")
    assert cached is not None and cached.fresh
    assert cached.value["raw_message"] == b"Subject: Cached\r\n\r\nBody"
    assert cache.cached_email_uids("INBOX", ["41", "42"]) == {"42"}
    assert cache.email_cache_stats() == {"messages": 1, "bytes": 23, "mailboxes": 1}

    assert cache.invalidate_email_messages("INBOX") == 1
    assert cache.get_email_message("INBOX", "42") is None


def populate_account_cache(cache: SQLiteICloudCalendarCache, label: str) -> None:
    cache.set_calendars([{"id": "calendar", "name": label}])
    cache.set_mailboxes([{"name": label}])
    cache.set_events("calendar", "start", "end", [
        {"calendar_id": "calendar", "calendar_name": label, "uid": "event", "summary": label}
    ])
    cache.set_emails("INBOX", [{"uid": "42", "subject": label}], "2026-01-01")
    cache.set_email_messages([{
        "mailbox": "INBOX", "uid": "42", "summary": {"subject": label},
        "raw_message": label.encode(),
    }])


@pytest.mark.parametrize("other_identity", [
    ("imap", "mail.example.com:993", "bob@example.com"),
    ("imap", "other.example.com:993", "alice@example.com"),
    ("caldav", "mail.example.com:993", "alice@example.com"),
])
def test_account_namespaces_isolate_all_read_results_and_persist(tmp_path, other_identity) -> None:
    path = tmp_path / "cache.sqlite3"
    cache = SQLiteICloudCalendarCache(path)
    alice = cache.for_account("imap", "mail.example.com:993", "alice@example.com")
    populate_account_cache(alice, "Alice")
    other = cache.for_account(*other_identity)
    assert other.get_calendars() is None
    assert other.get_mailboxes() is None
    assert other.get_events("calendar", "start", "end") is None
    assert other.get_event("Alice", "event") is None
    assert other.get_emails("INBOX") is None
    assert other.get_email_message("INBOX", "42") is None
    assert other.cached_email_uids("INBOX", ["42"]) == set()
    assert other.email_cache_stats()["messages"] == 0
    populate_account_cache(other, "Other")

    reopened = SQLiteICloudCalendarCache(path).for_account(
        "imap", "mail.example.com:993", "alice@example.com"
    )
    assert reopened.get_calendars().value[0]["name"] == "Alice"
    assert reopened.get_events("calendar", "start", "end").value[0]["summary"] == "Alice"
    assert reopened.get_event("Alice", "event").value["summary"] == "Alice"
    assert reopened.get_emails("INBOX").value["emails"][0]["subject"] == "Alice"
    assert reopened.get_email_message("INBOX", "42").value["raw_message"] == b"Alice"


@pytest.mark.parametrize("mailboxes", [(), ("INBOX",)])
def test_account_invalidation_does_not_remove_another_accounts_entries(tmp_path, mailboxes) -> None:
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    alice = cache.for_account("imap", "server", "alice@example.com")
    bob = cache.for_account("imap", "server", "bob@example.com")
    populate_account_cache(alice, "Alice")
    populate_account_cache(bob, "Bob")
    alice.invalidate_events()
    alice.invalidate_emails(*mailboxes)
    alice.invalidate_email_messages(*mailboxes)
    assert alice.get_event("Alice", "event") is None
    assert alice.get_emails("INBOX") is None
    assert alice.get_email_message("INBOX", "42") is None
    assert bob.get_event("Bob", "event") is not None
    assert bob.get_emails("INBOX") is not None
    assert bob.get_email_message("INBOX", "42") is not None


def test_account_scope_does_not_reuse_legacy_entries_with_unknown_owner(tmp_path) -> None:
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    populate_account_cache(cache, "Unknown")
    scoped = cache.for_account("imap", "server", "alice@example.com")
    assert scoped.get_calendars() is None
    assert scoped.get_mailboxes() is None
    assert scoped.get_event("Unknown", "event") is None
    assert scoped.get_emails("INBOX") is None
    assert scoped.get_email_message("INBOX", "42") is None


def test_late_writes_from_old_uid_generation_cannot_repopulate_cache(tmp_path) -> None:
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3")
    cache.sync_uid_validity("INBOX", "7")
    cache.sync_uid_validity("Other", "7")
    cache.set_email_messages([{
        "mailbox": "Other", "uid": "42", "uid_validity": "7",
        "summary": {"subject": "Other"}, "raw_message": b"Other",
    }])
    cache.sync_uid_validity("INBOX", "99")
    cache.set_emails("INBOX", [{"uid": "42"}], "2026-01-01", complete=True, uid_validity="7")
    cache.set_email_messages([{
        "mailbox": "INBOX", "uid": "42", "uid_validity": "7",
        "summary": {"subject": "Old"}, "raw_message": b"Old",
    }])
    assert cache.get_emails("INBOX") is None
    assert cache.get_email_message("INBOX", "42") is None
    assert cache.get_email_message("Other", "42", uid_validity="7") is not None
    cache.set_emails("INBOX", [{"uid": "42"}], "2026-01-01", complete=True, uid_validity="99")
    cache.set_email_messages([{
        "mailbox": "INBOX", "uid": "42", "uid_validity": "99",
        "summary": {"subject": "New"}, "raw_message": b"New",
    }])
    assert cache.get_emails("INBOX").value["uid_validity"] == "99"
    assert cache.cached_email_uids("INBOX", ["42"], uid_validity="7") == set()
    assert cache.cached_email_uids("INBOX", ["42"], uid_validity="99") == {"42"}
