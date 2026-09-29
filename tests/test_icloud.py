from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator

import pytest
from icalendar import Calendar

from app.config import ICloudConfig
from app.icloud import CalendarNotFoundError, ICloudCalendarService


class FakeResource:
    def __init__(self, data: bytes, parent: "FakeCalendar") -> None:
        self.parent = parent
        self._calendar = Calendar.from_ical(data)
        self.deleted = False
        self.saved = False

    @property
    def id(self) -> str:
        return str(self.get_icalendar_component()["UID"])

    def get_icalendar_component(self) -> Any:
        return deepcopy(next(component for component in self._calendar.subcomponents if component.name == "VEVENT"))

    @contextmanager
    def edit_icalendar_component(self) -> Iterator[Any]:
        component = next(component for component in self._calendar.subcomponents if component.name == "VEVENT")
        yield component

    def save(self) -> None:
        self.saved = True
        self.parent.resources[self.id] = self

    def delete(self) -> None:
        self.deleted = True
        self.parent.resources.pop(self.id, None)


class FakeCalendar:
    def __init__(self, identifier: str, name: str) -> None:
        self.id = identifier
        self._name = name
        self.resources: dict[str, FakeResource] = {}

    def get_display_name(self) -> str:
        return self._name

    def search(self, **_: Any) -> list[FakeResource]:
        return list(self.resources.values())

    def get_event_by_uid(self, uid: str) -> FakeResource:
        if uid not in self.resources:
            from caldav.lib.error import NotFoundError

            raise NotFoundError(uid)
        return self.resources[uid]

    def add_event(self, data: bytes) -> FakeResource:
        resource = FakeResource(data, self)
        self.resources[resource.id] = resource
        return resource


class ICloudUIDReportCalendar(FakeCalendar):
    def get_event_by_uid(self, uid: str) -> FakeResource:
        from caldav.lib.error import ReportError

        raise ReportError("412 Precondition Failed")


class FakeClient:
    def __init__(self, calendars: list[FakeCalendar]) -> None:
        self.calendars = calendars

    def get_calendars(self) -> list[FakeCalendar]:
        return self.calendars

    def close(self) -> None:
        pass


def service_with(*calendars: FakeCalendar) -> ICloudCalendarService:
    client = FakeClient(list(calendars))
    config = ICloudConfig(
        username="user@example.com",
        app_specific_password="app-password",
        timezone="Europe/Berlin",
    )
    return ICloudCalendarService(config, client_factory=lambda **_: client)


def test_create_update_and_delete_event() -> None:
    service = service_with(FakeCalendar("work-id", "Work"))

    created = service.create_event(
        calendar="Work",
        title="Planning",
        start="2026-01-02T09:00:00+01:00",
        end="2026-01-02T10:00:00+01:00",
        description="Agenda",
        location="Room 1",
    )

    assert created["calendar_name"] == "Work"
    assert created["summary"] == "Planning"
    assert created["description"] == "Agenda"
    assert created["all_day"] is False

    updated = service.update_event(
        calendar="work-id",
        uid=created["uid"],
        title="Planning updated",
        description="",
    )
    assert updated["summary"] == "Planning updated"
    assert updated["description"] is None

    deleted = service.delete_event("Work", created["uid"])
    assert deleted["deleted"] is True
    assert service.list_events(calendar="Work") == []


def test_list_events_filters_query_and_serializes_all_day() -> None:
    calendar = FakeCalendar("personal-id", "Personal")
    service = service_with(calendar)
    created = service.create_event(
        calendar="Personal",
        title="Holiday",
        start="2026-01-03",
        end="2026-01-05",
        all_day=True,
    )

    events = service.list_events(calendar="Personal", query="hol")

    assert events[0]["uid"] == created["uid"]
    assert events[0]["start"] == "2026-01-03"
    assert events[0]["end"] == "2026-01-05"
    assert events[0]["all_day"] is True


def test_get_event_falls_back_when_icloud_rejects_uid_report() -> None:
    calendar = ICloudUIDReportCalendar("personal-id", "Personal")
    service = service_with(calendar)
    created = service.create_event(
        calendar="Personal",
        title="Fallback lookup",
        start="2026-01-03T09:00:00+01:00",
        end="2026-01-03T10:00:00+01:00",
    )

    event = service.get_event("Personal", created["uid"])

    assert event["uid"] == created["uid"]
    assert event["summary"] == "Fallback lookup"


def test_multiple_calendars_require_selector_for_writes() -> None:
    service = service_with(
        FakeCalendar("one", "One"),
        FakeCalendar("two", "Two"),
    )

    with pytest.raises(CalendarNotFoundError, match="multiple calendars"):
        service.create_event(
            calendar=None,
            title="Ambiguous",
            start="2026-01-02T09:00:00Z",
            end="2026-01-02T10:00:00Z",
        )
