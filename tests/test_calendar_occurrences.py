from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo

from caldav import Event as CalDAVEvent
from icalendar import Calendar, Event, Timezone
import pytest

from app.config import ICloudConfig
from app.icloud import ICloudCalendarService
from app.icloud_cache import SQLiteICloudCalendarCache
from test_icloud import FakeCalendar, FakeClient, ICloudUIDReportCalendar, service_with


UID = "AAF8348A-C9E5-4336-A460-A61C46DE8755"
CALENDAR_ID = "86889C92-3C3C-4A5A-9DC3-A5DC6FC90086"
BERLIN = ZoneInfo("Europe/Berlin")


def recurring_event(*, all_day=False, floating=False):
    document = Calendar()
    document.add("VERSION", "2.0")
    document.add("PRODID", "-//Occurrence tests//EN")
    master = Event()
    master.add("UID", UID)
    master.add("SUMMARY", "Klettern Tobi")
    if all_day:
        master.add("DTSTART", date(2026, 9, 2))
        master.add("DTEND", date(2026, 9, 4))
    else:
        zone = None if floating else BERLIN
        master.add("DTSTART", datetime(2026, 9, 2, 18, tzinfo=zone))
        master.add("DTEND", datetime(2026, 9, 2, 22, 30, tzinfo=zone))
    master.add("RRULE", {"FREQ": "WEEKLY", "BYDAY": "WE"})
    document.add_component(master)
    return document


def override(identifier, start, end, *, status=None, range_value=None):
    component = Event()
    component.add("UID", UID)
    component.add("RECURRENCE-ID", identifier, parameters={"RANGE": range_value} if range_value else {})
    component.add("DTSTART", start)
    component.add("DTEND", end)
    component.add("SUMMARY", "Klettern verschoben")
    if status:
        component.add("STATUS", status)
    return component


def setup_series(document=None, *, cache=None, calendar_type=FakeCalendar):
    calendar = calendar_type(CALENDAR_ID, "Sport")
    resource = calendar.add_event((document if document is not None else recurring_event()).to_ical())
    if cache is None:
        service = service_with(calendar)
    else:
        client = FakeClient([calendar])
        service = ICloudCalendarService(
            ICloudConfig(username="user@example.com", app_specific_password="password", timezone="Europe/Berlin"),
            client_factory=lambda **_: client, cache=cache,
        )
    return service, resource


def day_events(service, start="2026-09-30", end="2026-10-01"):
    return service.list_events(calendar=CALENDAR_ID, start=start, end=end)


def delete_occurrence(service, identifier="2026-09-30T18:00:00+02:00"):
    return service.delete_event(CALENDAR_ID, UID, scope="occurrence", recurrence_id=identifier)


def test_day_query_returns_occurrence_times_and_stable_identity():
    service, _ = setup_series()
    events = day_events(service)
    assert len(events) == 1
    event = events[0]
    assert event["uid"] == event["series_uid"] == UID
    assert event["start"] == event["recurrence_id"] == "2026-09-30T18:00:00+02:00"
    assert event["end"] == "2026-09-30T22:30:00+02:00"
    assert event["is_recurring"] is True
    assert event["occurrence_id"] == day_events(service)[0]["occurrence_id"]
    following = day_events(service, "2026-10-07", "2026-10-08")[0]
    assert following["uid"] == UID
    assert following["occurrence_id"] != event["occurrence_id"]


def test_delete_september_30_preserves_series_future_and_cache(tmp_path):
    service, resource = setup_series(cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    selected = day_events(service)[0]
    following = day_events(service, "2026-10-07", "2026-11-01")
    deleted = delete_occurrence(service, selected["recurrence_id"])
    assert deleted == {
        "deleted": True, "scope": "occurrence", "uid": UID, "series_uid": UID,
        "calendar_id": CALENDAR_ID, "calendar_name": "Sport",
        "recurrence_id": selected["recurrence_id"], "occurrence_id": selected["occurrence_id"],
        "occurrence_date": "2026-09-30", "affected_date": "2026-09-30", "already_deleted": False,
    }
    assert resource.saved is True
    assert resource.deleted is False
    assert day_events(service) == []
    assert day_events(service, "2026-10-07", "2026-11-01") == following
    assert [event["start"] for event in following] == [
        "2026-10-07T18:00:00+02:00", "2026-10-14T18:00:00+02:00",
        "2026-10-21T18:00:00+02:00", "2026-10-28T18:00:00+01:00",
    ]
    master = resource.get_icalendar_component()
    assert master["RRULE"].to_ical() == recurring_event().subcomponents[0]["RRULE"].to_ical()
    assert master["DTSTART"].dt == datetime(2026, 9, 2, 18, tzinfo=BERLIN)
    assert master["EXDATE"].params["TZID"] == "Europe/Berlin"
    persisted = resource.get_icalendar_instance().to_ical()
    resource.saved = False
    repeated = delete_occurrence(service, "2026-09-30T16:00:00Z")
    assert repeated["already_deleted"] is True
    assert repeated["recurrence_id"] == selected["recurrence_id"]
    assert repeated["occurrence_id"] == selected["occurrence_id"]
    assert resource.saved is False
    assert resource.get_icalendar_instance().to_ical() == persisted


@pytest.mark.parametrize("arguments", [
    {"scope": "occurrence"},
    {"scope": "occurrence", "recurrence_id": ""},
    {"scope": "occurrence", "recurrence_id": "invalid"},
    {"scope": "occurrence", "recurrence_id": "2026-09-30"},
    {"scope": "occurrence", "recurrence_id": "2026-09-30T18:00:00"},
    {"scope": "occurrence", "recurrence_id": "2026-09-30T19:00:00+02:00"},
    {"scope": "occurrence", "recurrence_id": "2026-10-01T18:00:00+02:00"},
    {"scope": "occurrence", "recurrence_id": "2026-09-30T18:00:00.001+02:00"},
    {"scope": "occurrence", "recurrence_id": "2026-09-30T99:00:00+02:00"},
    {"scope": "series", "recurrence_id": "2026-09-30T18:00:00+02:00"},
    {"scope": "series", "recurrence_id": ""},
    {"scope": "invalid"},
])
def test_invalid_delete_never_mutates_or_deletes_series(arguments):
    service, resource = setup_series()
    before = resource.get_icalendar_instance().to_ical()
    with pytest.raises(ValueError):
        service.delete_event(CALENDAR_ID, UID, **arguments)
    assert resource.get_icalendar_instance().to_ical() == before
    assert resource.saved is resource.deleted is False
    assert len(day_events(service)) == 1


def test_explicit_series_scope_and_missing_scope():
    service, resource = setup_series()
    with pytest.raises(TypeError):
        service.delete_event(CALENDAR_ID, UID)
    assert resource.deleted is False
    result = service.delete_event(CALENDAR_ID, UID, scope="series")
    assert result["scope"] == "series"
    assert resource.deleted is True
    assert day_events(service, "2026-09-01", "2026-11-01") == []


def test_all_day_occurrence_uses_date_exdate_and_exclusive_end():
    service, resource = setup_series(recurring_event(all_day=True))
    event = day_events(service)[0]
    assert event["start"] == event["recurrence_id"] == "2026-09-30"
    assert event["end"] == "2026-10-02"
    assert event["all_day"] is True
    with pytest.raises(ValueError, match="ISO date"):
        delete_occurrence(service, "2026-09-30T00:00:00+02:00")
    deleted = delete_occurrence(service, event["recurrence_id"])
    assert deleted["occurrence_date"] == deleted["affected_date"] == "2026-09-30"
    assert resource.get_icalendar_component()["EXDATE"].params["VALUE"] == "DATE"
    assert day_events(service) == []
    assert day_events(service, "2026-10-01", "2026-10-02") == []
    assert day_events(service, "2026-10-07", "2026-10-08")[0]["start"] == "2026-10-07"
    assert delete_occurrence(service, "2026-09-30")["already_deleted"] is True


def test_floating_occurrence_preserves_floating_time_type():
    service, resource = setup_series(recurring_event(floating=True))
    event = day_events(service, "2026-09-30T17:30:00+02:00", "2026-09-30T18:30:00+02:00")[0]
    assert event["recurrence_id"] == event["start"] == "2026-09-30T18:00:00"
    with pytest.raises(ValueError, match="timezone type"):
        delete_occurrence(service)
    delete_occurrence(service, event["recurrence_id"])
    exdate = resource.get_icalendar_component()["EXDATE"]
    assert exdate.dts[0].dt.tzinfo is None
    assert "TZID" not in exdate.params
    assert day_events(service) == []


def test_autumn_dst_utc_identity_and_wrong_offset_are_checked():
    service, _ = setup_series()
    event = day_events(service, "2026-10-28", "2026-10-29")[0]
    assert event["start"] == "2026-10-28T18:00:00+01:00"
    assert event["end"] == "2026-10-28T22:30:00+01:00"
    with pytest.raises(ValueError, match="does not identify"):
        delete_occurrence(service, "2026-10-28T18:00:00+02:00")
    deleted = delete_occurrence(service, "2026-10-28T17:00:00Z")
    assert deleted["recurrence_id"] == event["recurrence_id"]
    assert deleted["occurrence_id"] == event["occurrence_id"]
    assert day_events(service, "2026-10-28", "2026-10-29") == []
    assert day_events(service, "2026-11-04", "2026-11-05")[0]["start"] == "2026-11-04T18:00:00+01:00"


def test_spring_dst_preserves_local_start_and_end():
    document = recurring_event()
    master = document.subcomponents[0]
    master["DTSTART"].dt = datetime(2026, 3, 4, 18, tzinfo=BERLIN)
    master["DTEND"].dt = datetime(2026, 3, 4, 22, 30, tzinfo=BERLIN)
    service, _ = setup_series(document)
    events = day_events(service, "2026-03-25", "2026-04-02")
    assert [event["start"] for event in events] == ["2026-03-25T18:00:00+01:00", "2026-04-01T18:00:00+02:00"]
    assert [event["end"] for event in events] == ["2026-03-25T22:30:00+01:00", "2026-04-01T22:30:00+02:00"]
    delete_occurrence(service, "2026-04-01T16:00:00Z")
    assert len(day_events(service, "2026-03-25", "2026-03-26")) == 1
    assert day_events(service, "2026-04-01", "2026-04-02") == []


@pytest.mark.parametrize("moved_day", [30, 1])
def test_changed_occurrence_uses_original_id_and_preserves_other_exceptions(moved_day):
    document = recurring_event()
    month = 9 if moved_day == 30 else 10
    document.add_component(override(
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime(2026, month, moved_day, 19, tzinfo=BERLIN),
        datetime(2026, month, moved_day, 23, 45, tzinfo=BERLIN),
    ))
    document.add_component(override(
        datetime(2026, 10, 7, 18, tzinfo=BERLIN),
        datetime(2026, 10, 7, 20, tzinfo=BERLIN),
        datetime(2026, 10, 7, 23, tzinfo=BERLIN),
    ))
    service, resource = setup_series(document)
    events = day_events(service, "2026-09-30", "2026-10-02")
    assert len(events) == 1
    event = events[0]
    assert event["start"] == f"2026-{month:02d}-{moved_day:02d}T19:00:00+02:00"
    assert event["recurrence_id"] == "2026-09-30T18:00:00+02:00"
    with pytest.raises(ValueError, match="does not identify"):
        delete_occurrence(service, event["start"])
    remaining = deepcopy(resource.get_icalendar_instance().subcomponents[2])
    deleted = delete_occurrence(service, event["recurrence_id"])
    assert deleted["occurrence_date"] == "2026-09-30"
    assert deleted["affected_date"] == f"2026-{month:02d}-{moved_day:02d}"
    assert day_events(service, "2026-09-30", "2026-10-02") == []
    assert resource.get_icalendar_instance().subcomponents[1].to_ical() == remaining.to_ical()
    assert day_events(service, "2026-10-07", "2026-10-08")[0]["start"] == "2026-10-07T20:00:00+02:00"
    assert day_events(service, "2026-10-14", "2026-10-15")[0]["start"] == "2026-10-14T18:00:00+02:00"
    assert delete_occurrence(service)["already_deleted"] is True


def test_already_cancelled_occurrence_is_hidden_and_idempotent():
    document = recurring_event()
    document.add_component(override(
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime(2026, 9, 30, 22, 30, tzinfo=BERLIN), status="CANCELLED",
    ))
    service, resource = setup_series(document)
    assert day_events(service) == []
    assert delete_occurrence(service)["already_deleted"] is True
    assert resource.saved is resource.deleted is False
    assert len(day_events(service, "2026-10-07", "2026-10-08")) == 1


def test_changed_all_day_occurrence_uses_original_date_and_removes_only_its_override():
    document = recurring_event(all_day=True)
    document.add_component(override(date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 4)))
    service, _ = setup_series(document)
    assert day_events(service) == []
    event = day_events(service, "2026-10-01", "2026-10-02")[0]
    assert event["recurrence_id"] == "2026-09-30"
    assert event["start"] == "2026-10-01"
    assert event["end"] == "2026-10-04"
    result = delete_occurrence(service, event["recurrence_id"])
    assert result["occurrence_date"] == "2026-09-30"
    assert result["affected_date"] == "2026-10-01"
    assert day_events(service, "2026-10-01", "2026-10-04") == []
    assert len(day_events(service, "2026-10-07", "2026-10-08")) == 1


def test_utc_override_reports_affected_date_in_series_timezone():
    document = recurring_event()
    document.add_component(override(
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime.fromisoformat("2026-09-30T23:00:00+00:00"),
        datetime.fromisoformat("2026-10-01T01:00:00+00:00"),
    ))
    service, _ = setup_series(document)
    assert day_events(service) == []
    result = delete_occurrence(service)
    assert result["occurrence_date"] == "2026-09-30"
    assert result["affected_date"] == "2026-10-01"
    assert day_events(service, "2026-10-01", "2026-10-02") == []


def test_finite_rule_rejects_a_date_after_the_last_occurrence():
    document = recurring_event()
    document.subcomponents[0].pop("RRULE")
    document.subcomponents[0].add("RRULE", {"FREQ": "WEEKLY", "COUNT": 5})
    service, resource = setup_series(document)
    with pytest.raises(ValueError, match="does not identify"):
        delete_occurrence(service, "2026-10-07T18:00:00+02:00")
    assert resource.saved is resource.deleted is False
    assert len(day_events(service)) == 1


def test_autumn_ambiguous_hour_distinguishes_the_two_utc_instants():
    document = recurring_event()
    master = document.subcomponents[0]
    master["DTSTART"].dt = datetime(2026, 10, 11, 2, 30, tzinfo=BERLIN)
    master["DTEND"].dt = datetime(2026, 10, 11, 3, 30, tzinfo=BERLIN)
    master.pop("RRULE")
    master.add("RRULE", {"FREQ": "WEEKLY", "COUNT": 4})
    service, _ = setup_series(document)
    event = day_events(service, "2026-10-25", "2026-10-26")[0]
    assert event["recurrence_id"] == "2026-10-25T02:30:00+02:00"
    with pytest.raises(ValueError, match="does not identify"):
        delete_occurrence(service, "2026-10-25T02:30:00+01:00")
    delete_occurrence(service, event["recurrence_id"])
    assert day_events(service, "2026-10-25", "2026-10-26") == []
    assert day_events(service, "2026-11-01", "2026-11-02")[0]["start"] == "2026-11-01T02:30:00+01:00"


def test_existing_multiple_exdates_are_preserved():
    document = recurring_event()
    master = document.subcomponents[0]
    master.add("EXDATE", [datetime(2026, 9, 16, 18, tzinfo=BERLIN), datetime(2026, 9, 23, 18, tzinfo=BERLIN)])
    master.add("EXDATE", datetime(2026, 10, 14, 18, tzinfo=BERLIN))
    service, resource = setup_series(document)
    delete_occurrence(service)
    assert list(service._exception_dates(resource.get_icalendar_component())) == [
        datetime(2026, 9, 16, 18, tzinfo=BERLIN), datetime(2026, 9, 23, 18, tzinfo=BERLIN),
        datetime(2026, 10, 14, 18, tzinfo=BERLIN), datetime(2026, 9, 30, 18, tzinfo=BERLIN),
    ]
    assert delete_occurrence(service)["already_deleted"] is True


def test_rdate_only_occurrence_can_be_removed():
    document = recurring_event()
    master = document.subcomponents[0]
    master.pop("RRULE")
    master.add("RDATE", [datetime(2026, 9, 30, 18, tzinfo=BERLIN), datetime(2026, 10, 7, 18, tzinfo=BERLIN)])
    service, _ = setup_series(document)
    assert len(day_events(service)) == 1
    delete_occurrence(service)
    assert day_events(service) == []
    assert len(day_events(service, "2026-10-07", "2026-10-08")) == 1


def test_occurrence_scope_rejects_nonrecurring_event():
    document = recurring_event()
    document.subcomponents[0].pop("RRULE")
    service, resource = setup_series(document)
    event = day_events(service, "2026-09-02", "2026-09-03")[0]
    assert event["is_recurring"] is False
    assert event["recurrence_id"] is event["series_uid"] is None
    with pytest.raises(ValueError, match="recurring event"):
        delete_occurrence(service, event["start"])
    assert resource.saved is resource.deleted is False


def test_range_anchor_delete_preserves_shift_and_ids_of_later_occurrences():
    document = recurring_event()
    document.add_component(override(
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime(2026, 9, 30, 19, tzinfo=BERLIN),
        datetime(2026, 9, 30, 23, 30, tzinfo=BERLIN), range_value="THISANDFUTURE",
    ))
    service, resource = setup_series(document)
    before = day_events(service, "2026-09-30", "2026-11-01")
    assert [event["recurrence_id"] for event in before] == [
        "2026-09-30T18:00:00+02:00", "2026-10-07T18:00:00+02:00", "2026-10-14T18:00:00+02:00",
        "2026-10-21T18:00:00+02:00", "2026-10-28T18:00:00+01:00",
    ]
    assert len({event["occurrence_id"] for event in before}) == 5
    delete_occurrence(service)
    assert resource.deleted is False
    assert day_events(service, "2026-09-30", "2026-11-01") == before[1:]
    assert resource.get_icalendar_instance().subcomponents[1]["RECURRENCE-ID"].params["RANGE"] == "THISANDFUTURE"
    assert delete_occurrence(service)["already_deleted"] is True
    following = delete_occurrence(service, before[1]["recurrence_id"])
    assert following["affected_date"] == "2026-10-07"
    assert day_events(service, "2026-10-07", "2026-10-08") == []
    assert day_events(service, "2026-10-14", "2026-11-01") == before[2:]


def test_all_day_range_anchor_and_shifted_following_day_are_individually_deleted():
    document = recurring_event(all_day=True)
    document.add_component(override(
        date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 3), range_value="THISANDFUTURE",
    ))
    service, _ = setup_series(document)
    before = day_events(service, "2026-10-01", "2026-10-30")
    assert [event["recurrence_id"] for event in before] == [
        "2026-09-30", "2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28",
    ]
    assert [event["start"] for event in before] == [
        "2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22", "2026-10-29",
    ]
    assert delete_occurrence(service, "2026-09-30")["affected_date"] == "2026-10-01"
    assert day_events(service, "2026-10-01", "2026-10-30") == before[1:]
    assert delete_occurrence(service, "2026-10-07")["affected_date"] == "2026-10-08"
    assert day_events(service, "2026-10-01", "2026-10-30") == before[2:]


def test_uid_report_fallback_never_uses_expanded_resources():
    class CheckedCalendar(ICloudUIDReportCalendar):
        def search(self, **arguments):
            assert arguments["expand"] is False
            return super().search(**arguments)

    service, resource = setup_series(calendar_type=CheckedCalendar)
    delete_occurrence(service)
    assert resource.deleted is False
    assert day_events(service) == []
    assert len(day_events(service, "2026-10-07", "2026-10-08")) == 1


def test_occurrence_cache_does_not_replace_master_summary(tmp_path):
    service, _ = setup_series(cache=SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3"))
    master = service.get_event(CALENDAR_ID, UID)
    assert master["start"] == "2026-09-02T18:00:00+02:00"
    day_events(service)
    day_events(service, "2026-10-07", "2026-10-08")
    assert service.get_event(CALENDAR_ID, UID) == master


def test_window_is_exclusive_and_includes_overlapping_occurrences():
    service, _ = setup_series()
    assert day_events(service, "2026-09-30T17:00:00+02:00", "2026-09-30T18:00:00+02:00") == []
    assert len(day_events(service, "2026-09-30T20:00:00+02:00", "2026-09-30T21:00:00+02:00")) == 1
    assert day_events(service, "2026-09-30T22:30:00+02:00", "2026-10-01T00:00:00+02:00") == []


def test_list_sorts_actual_instants_across_timezones_before_applying_limit():
    service, resource = setup_series()
    second = Event()
    second.add("UID", "utc-event")
    second.add("DTSTART", datetime.fromisoformat("2026-09-30T17:00:00+00:00"))
    second.add("DTEND", datetime.fromisoformat("2026-09-30T18:00:00+00:00"))
    second.add("SUMMARY", "Later in UTC")
    document = Calendar()
    document.add_component(second)
    resource.parent.add_event(document.to_ical())
    assert day_events(service)[0]["uid"] == UID
    assert service.list_events(calendar=CALENDAR_ID, start="2026-09-30", end="2026-10-01", limit=1)[0]["uid"] == UID


def test_native_caldav_save_preserves_master_timezone_and_other_overrides(monkeypatch):
    document = recurring_event()
    document.subcomponents[0].add("SEQUENCE", 3)
    timezone_component = Timezone.from_tzinfo(BERLIN, first_date=date(2026, 1, 1), last_date=date(2027, 1, 1))
    document.add_component(timezone_component)
    changed = override(
        datetime(2026, 9, 30, 18, tzinfo=BERLIN),
        datetime(2026, 10, 1, 19, tzinfo=BERLIN),
        datetime(2026, 10, 1, 23, 30, tzinfo=BERLIN),
    )
    other = override(
        datetime(2026, 10, 7, 18, tzinfo=BERLIN),
        datetime(2026, 10, 7, 20, tzinfo=BERLIN),
        datetime(2026, 10, 7, 23, tzinfo=BERLIN),
    )
    other.add("SEQUENCE", 7)
    # Master ordering must not be assumed when saving the complete resource.
    document.subcomponents.insert(0, other)
    document.add_component(changed)
    calendar = FakeCalendar(CALENDAR_ID, "Sport")
    calendar.client = None
    resource = CalDAVEvent(data=document.to_ical(), parent=calendar, url="https://example.invalid/event.ics")
    calendar.resources[UID] = resource
    writes = []

    def record_put(**arguments):
        writes.append(Calendar.from_ical(resource.data))

    monkeypatch.setattr(resource, "_create", record_put)
    monkeypatch.setattr(resource, "delete", lambda: pytest.fail("occurrence delete must not send DELETE"))
    monkeypatch.setattr(calendar, "get_event_by_uid", lambda uid: resource if uid == UID else pytest.fail("wrong UID"))
    service = service_with(calendar)
    result = delete_occurrence(service)
    assert result["scope"] == "occurrence"
    assert len(writes) == 1
    saved = writes[0]
    masters = [component for component in saved.walk("VEVENT") if "RECURRENCE-ID" not in component]
    assert len(masters) == 1
    assert "RRULE" in masters[0]
    assert masters[0]["SEQUENCE"] == 4
    assert masters[0]["EXDATE"].dts[0].dt == datetime(2026, 9, 30, 18, tzinfo=BERLIN)
    assert saved.walk("VTIMEZONE")[0].to_ical() == timezone_component.to_ical()
    assert len(saved.walk("VEVENT")) == 2
    assert str(saved.walk("VEVENT")[0]["RECURRENCE-ID"]) == str(other["RECURRENCE-ID"])
    assert saved.walk("VEVENT")[0]["SEQUENCE"] == 7
    assert day_events(service, "2026-09-30", "2026-10-02") == []
    assert day_events(service, "2026-10-07", "2026-10-08")[0]["start"] == "2026-10-07T20:00:00+02:00"
