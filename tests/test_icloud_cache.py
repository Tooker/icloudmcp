from pathlib import Path

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
