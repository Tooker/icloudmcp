from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator

import pytest
from icalendar import Calendar

from app.config import ICloudConfig
from app.reminders import ICloudReminderService, ReminderListNotFoundError


class FakeReminderResource:
    def __init__(self, data: bytes, parent: "FakeReminderCalendar") -> None:
        self.parent = parent
        self._calendar = Calendar.from_ical(data)
        self.deleted = False
        self.saved = False

    @property
    def id(self) -> str:
        return str(self.get_icalendar_component()["UID"])

    def get_icalendar_component(self) -> Any:
        return deepcopy(next(component for component in self._calendar.subcomponents if component.name == "VTODO"))

    @contextmanager
    def edit_icalendar_component(self) -> Iterator[Any]:
        component = next(component for component in self._calendar.subcomponents if component.name == "VTODO")
        yield component

    def save(self) -> None:
        self.saved = True
        self.parent.resources[self.id] = self

    def delete(self) -> None:
        self.deleted = True
        self.parent.resources.pop(self.id, None)


class FakeReminderCalendar:
    def __init__(self, identifier: str, name: str, component: str | None) -> None:
        self.id = identifier
        self._name = name
        self.component = component
        self.resources: dict[str, FakeReminderResource] = {}

    def get_display_name(self) -> str:
        return self._name

    def get_supported_components(self, **_: Any) -> list[str]:
        if self.component is None:
            raise RuntimeError("supported component property is unavailable")
        return [self.component]

    def get_todos(self, include_completed: bool = False) -> list[FakeReminderResource]:
        return list(self.resources.values())

    def get_todo_by_uid(self, uid: str) -> FakeReminderResource:
        if uid not in self.resources:
            from caldav.lib.error import NotFoundError

            raise NotFoundError(uid)
        return self.resources[uid]

    def add_todo(self, data: bytes) -> FakeReminderResource:
        resource = FakeReminderResource(data, self)
        self.resources[resource.id] = resource
        return resource


class FakeClient:
    def __init__(self, calendars: list[FakeReminderCalendar]) -> None:
        self.calendars = calendars

    def get_calendars(self) -> list[FakeReminderCalendar]:
        return self.calendars

    def close(self) -> None:
        pass


def service_with(*calendars: FakeReminderCalendar) -> ICloudReminderService:
    config = ICloudConfig(
        username="user@example.com",
        app_specific_password="app-password",
        timezone="Europe/Berlin",
    )
    client = FakeClient(list(calendars))
    return ICloudReminderService(config, client_factory=lambda **_: client)


def test_lists_vtodo_lists_and_round_trips_reminder() -> None:
    service = service_with(
        FakeReminderCalendar("tasks-id", "Tasks", "VTODO"),
        FakeReminderCalendar("calendar-id", "Calendar", "VEVENT"),
    )

    lists = service.list_reminder_lists()
    created = service.create_reminder(
        "Tasks",
        "Buy milk",
        notes="2 liters",
        due="2026-09-30T18:00:00+02:00",
        priority=5,
    )
    updated = service.update_reminder("Tasks", created["uid"], completed=True)

    assert lists == [{"id": "tasks-id", "name": "Tasks", "component": "VTODO"}]
    assert created["title"] == "Buy milk"
    assert created["priority"] == 5
    assert updated["completed"] is True
    assert service.list_reminders(completed=True)[0]["uid"] == created["uid"]


def test_explicit_list_can_be_selected_when_server_omits_component_property() -> None:
    service = service_with(FakeReminderCalendar("tasks-id", "Tasks", None))

    with pytest.raises(ReminderListNotFoundError):
        service.list_reminders()

    created = service.create_reminder("Tasks", "Explicit selection")

    assert created["list_name"] == "Tasks"
