import threading

from fastapi.testclient import TestClient
from loguru import logger
import pytest

from app.config import ICloudConfig
from app.icloud import ICloudCalendarService
from app.icloud_cache import SQLiteICloudCalendarCache
from app.main import create_app
from test_icloud import FakeCalendar, FakeClient


def cached_service(tmp_path, calendar, *, clock=None, ttl=60, service_type=ICloudCalendarService):
    client = FakeClient([calendar])
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3", events_ttl_seconds=ttl,
                                     **({"clock": clock} if clock else {}))
    service = service_type(
        ICloudConfig(username="user@example.com", app_specific_password="password"),
        client_factory=lambda **_: client, cache=cache,
    )
    return service, client


def add_event(service, title="Original"):
    return service.create_event(calendar="work", title=title,
                                start="2026-09-29T09:00:00Z", end="2026-09-29T10:00:00Z")


def test_poll_refreshes_fresh_cache_and_preserves_unfiltered_full_range(tmp_path):
    calendar = FakeCalendar("work", "Work")
    service, client = cached_service(tmp_path, calendar)
    event = add_event(service)
    add_event(service, "Another")
    args = {"calendar": "work", "start": "2026-09-01", "end": "2026-10-01"}
    assert len(service.list_events(**args, query="Original", limit=1)) == 1
    with calendar.resources[event["uid"]].edit_icalendar_component() as component:
        component["SUMMARY"] = "Changed externally"
    assert service.list_events(**args)[0]["summary"] == "Original"
    calls_before = client.get_calendars_calls
    assert service.refresh_cache_once() == {"ranges": 2, "errors": 0}
    after_poll = client.get_calendars_calls
    result = service.list_events(**args)
    assert {item["summary"] for item in result} == {"Changed externally", "Another"}
    assert after_poll > calls_before
    assert client.get_calendars_calls == after_poll


def test_poll_tracks_bounded_recent_windows_and_drops_idle_requests(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.icloud.monotonic", lambda: now[0])
    service, _ = cached_service(tmp_path, FakeCalendar("work", "Work"))
    service.list_events(calendar="work")
    assert service.refresh_cache_once() == {"ranges": 1, "errors": 0}
    for day in range(1, 11):
        service.list_events(start=f"2026-09-{day:02d}", end="2026-10-01")
    assert service.refresh_cache_once() == {"ranges": 9, "errors": 0}
    now[0] += 3601
    assert service.refresh_cache_once() == {"ranges": 1, "errors": 0}


def test_failed_poll_preserves_snapshot_age_and_never_logs_private_errors(tmp_path):
    now = [100.0]
    calendar = FakeCalendar("work", "Work")
    service, _ = cached_service(tmp_path, calendar, clock=lambda: now[0])
    add_event(service)
    service.list_events()
    start, end = service._search_window(None, None)
    keys = ("work", service._cache_datetime(start), service._cache_datetime(end))
    before = service._cache.get_events(*keys)

    def failing_search(**kwargs):
        raise RuntimeError("PRIVATE_UPSTREAM_ERROR")

    calendar.search = failing_search
    now[0] += 10
    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        assert service.refresh_cache_once() == {"ranges": 0, "errors": 1}
    finally:
        logger.remove(sink)
    after = service._cache.get_events(*keys)
    assert after.value == before.value
    assert after.fetched_at == before.fetched_at
    assert "PRIVATE_UPSTREAM_ERROR" not in "\n".join(logs)


def test_inflight_poll_cannot_repopulate_event_deleted_by_successful_write(tmp_path):
    calendar = FakeCalendar("work", "Work")
    service, _ = cached_service(tmp_path, calendar)
    event = add_event(service)
    service.list_events()
    original_search = calendar.search

    def racing_search(**kwargs):
        snapshot = original_search(**kwargs)
        calendar.search = original_search
        service.delete_event("work", event["uid"], scope="series")
        return snapshot

    calendar.search = racing_search
    service.refresh_cache_once()
    start, end = service._search_window(None, None)
    assert service._cache.get_events("work", service._cache_datetime(start), service._cache_datetime(end)) is None
    assert service._cache.get_event("work", event["uid"]) is None
    assert service.list_events() == []


def test_application_lifespan_warms_default_calendar_cache_and_stops_poller(tmp_path):
    warmed = threading.Event()

    class ObservedService(ICloudCalendarService):
        def refresh_cache_once(self):
            result = super().refresh_cache_once()
            warmed.set()
            return result

    service, client = cached_service(tmp_path, FakeCalendar("work", "Work"), service_type=ObservedService)
    app = create_app(tmp_path / "missing.yaml", environ={}, icloud_service=service)
    with TestClient(app) as http:
        assert warmed.wait(2)
        assert http.get("/healthz").status_code == 200
        before = client.get_calendars_calls
        assert service.list_events() == []
        assert client.get_calendars_calls == before
    assert service._refresh_stop.is_set()


def test_poller_retries_failures_without_slowing_successfully_refreshed_ranges(tmp_path, monkeypatch):
    service, _ = cached_service(tmp_path, FakeCalendar("work", "Work"))
    results = iter([{"ranges": 0, "errors": 1}, {"ranges": 1, "errors": 1}, {"ranges": 1, "errors": 0}])
    service.refresh_cache_once = lambda: next(results)
    monkeypatch.setattr("app.icloud.perf_counter", lambda: 0.0)

    class StopAfterThreeCycles:
        waits = []

        def is_set(self):
            return len(self.waits) >= 3

        def wait(self, delay):
            self.waits.append(delay)

    service._refresh_stop = StopAfterThreeCycles()
    service.run_cache_refresh(120)
    # A too-long configured interval is capped at half the cache TTL.
    # Complete failures back off; partial failures preserve healthy polling.
    assert service._refresh_stop.waits == [60, 30, 30]


@pytest.mark.parametrize("disabled", ["env", "ttl"])
def test_application_does_not_poll_when_disabled(tmp_path, disabled):
    service, client = cached_service(tmp_path, FakeCalendar("work", "Work"), ttl=0 if disabled == "ttl" else 60)
    env = {"ICLOUD_CACHE_REFRESH_ENABLED": "false"} if disabled == "env" else {}
    app = create_app(tmp_path / "missing.yaml", environ=env, icloud_service=service)
    with TestClient(app):
        pass
    assert client.get_calendars_calls == 0
