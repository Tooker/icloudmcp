from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from uuid import uuid4

from caldav.lib import error as caldav_error
from icalendar import Calendar as ICalendar
from icalendar import Todo as ICalendarTodo

from app.icloud import CalendarNotFoundError, ICloudCalendarService, ICloudServiceError


class ReminderListNotFoundError(CalendarNotFoundError):
    pass


class ReminderNotFoundError(ICloudServiceError):
    pass


class ICloudReminderService(ICloudCalendarService):
    """Read/write facade for CalDAV VTODO reminder lists.

    iCloud Reminders is not a documented public CalDAV API. Some accounts
    still expose task-capable VTODO collections, while newer/upgraded lists
    may only exist in Apple's private CloudKit-backed store. The service only
    advertises collections that explicitly report VTODO support, and keeps an
    explicitly selected list usable for servers that omit that property.
    """

    _MAX_LIMIT = 200

    def list_reminder_lists(self) -> list[dict[str, Any]]:
        with self._connected_client() as client:
            result: list[dict[str, Any]] = []
            for calendar in client.get_calendars():
                if not self._supports_todo(calendar):
                    continue
                summary = self._calendar_summary(calendar)
                summary["component"] = "VTODO"
                result.append(summary)
            return result

    def list_reminders(
        self,
        list_name: str | None = None,
        completed: bool | None = None,
        query: str | None = None,
        due_after: str | None = None,
        due_before: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > self._MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {self._MAX_LIMIT}")
        normalized_query = query.strip().casefold() if query else None
        after = self._parse_filter_datetime(due_after, "due_after") if due_after else None
        before = self._parse_filter_datetime(due_before, "due_before") if due_before else None
        if after is not None and before is not None and before <= after:
            raise ValueError("due_before must be after due_after")

        with self._connected_client() as client:
            calendars = self._selected_reminder_calendars(client, list_name)
            reminders: list[dict[str, Any]] = []
            for calendar, calendar_summary in calendars:
                try:
                    resources = calendar.get_todos(include_completed=True)
                except TypeError:
                    resources = calendar.get_todos()
                for resource in resources:
                    item = self._reminder_summary(resource, calendar_summary)
                    if completed is not None and item["completed"] != completed:
                        continue
                    if normalized_query and not self._matches_query(item, normalized_query):
                        continue
                    due = self._comparison_datetime(item.get("due"))
                    if after is not None and (due is None or due <= after):
                        continue
                    if before is not None and (due is None or due >= before):
                        continue
                    reminders.append(item)

            reminders.sort(key=lambda item: item.get("due") or "9999-12-31")
            return reminders[:limit]

    def get_reminder(self, list_name: str, uid: str) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        with self._connected_client() as client:
            calendar, calendar_summary = self._resolve_reminder_calendar(client, list_name)
            resource = self._get_todo_resource(calendar, uid)
            return self._reminder_summary(resource, calendar_summary)

    def create_reminder(
        self,
        list_name: str | None,
        title: str,
        notes: str | None = None,
        due: str | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        title = self._require_text(title, "title")
        if notes is not None and not isinstance(notes, str):
            raise ValueError("notes must be a string or null")
        due_value = self._parse_due(due, "due") if due else None
        priority = self._validate_priority(priority)

        calendar_data = ICalendar()
        calendar_data.add("prodid", "-//IcloudCruncher//iCloud Reminders MCP//EN")
        calendar_data.add("version", "2.0")
        todo = ICalendarTodo()
        todo.add("uid", str(uuid4()))
        todo.add("dtstamp", datetime.now(timezone.utc))
        todo.add("summary", title)
        todo.add("status", "NEEDS-ACTION")
        todo.add("percent-complete", 0)
        if notes:
            todo.add("description", notes)
        if due_value is not None:
            todo.add("due", due_value)
        if priority is not None:
            todo.add("priority", priority)
        calendar_data.add_component(todo)

        with self._connected_client() as client:
            calendar, calendar_summary = self._resolve_reminder_calendar(client, list_name)
            resource = calendar.add_todo(calendar_data.to_ical())
            return self._reminder_summary(resource, calendar_summary)

    def update_reminder(
        self,
        list_name: str,
        uid: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
        completed: bool | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        if title is not None and not title.strip():
            raise ValueError("title must not be empty")
        if notes is not None and not isinstance(notes, str):
            raise ValueError("notes must be a string or null")
        if all(value is None for value in (title, notes, due, completed, priority)):
            raise ValueError("at least one reminder field must be supplied for update")
        due_value = self._parse_due(due, "due") if due else None
        priority = self._validate_priority(priority)

        with self._connected_client() as client:
            calendar, calendar_summary = self._resolve_reminder_calendar(client, list_name)
            resource = self._get_todo_resource(calendar, uid)
            with resource.edit_icalendar_component() as component:
                if title is not None:
                    self._replace_component_value(component, "SUMMARY", title.strip())
                if notes is not None:
                    self._replace_optional_component_value(component, "DESCRIPTION", notes)
                if due is not None:
                    component.pop("DUE", None)
                    if due_value is not None:
                        component.add("DUE", due_value)
                if priority is not None:
                    self._replace_component_value(component, "PRIORITY", priority)
                if completed is not None:
                    self._set_completed(component, completed)
            resource.save()
            return self._reminder_summary(resource, calendar_summary)

    def delete_reminder(self, list_name: str, uid: str) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        with self._connected_client() as client:
            calendar, calendar_summary = self._resolve_reminder_calendar(client, list_name)
            resource = self._get_todo_resource(calendar, uid)
            resource.delete()
            return {
                "deleted": True,
                "uid": uid,
                "list_id": calendar_summary["id"],
                "list_name": calendar_summary["name"],
            }

    def _selected_reminder_calendars(
        self,
        client: Any,
        selector: str | None,
    ) -> list[tuple[Any, dict[str, Any]]]:
        if selector and selector.strip():
            return [self._resolve_reminder_calendar(client, selector)]

        entries = [
            (calendar, self._calendar_summary(calendar))
            for calendar in client.get_calendars()
            if self._supports_todo(calendar)
        ]
        if not entries:
            raise ReminderListNotFoundError(
                "No CalDAV reminder lists with VTODO support are available"
            )
        return entries

    def _resolve_reminder_calendar(
        self,
        client: Any,
        selector: str | None,
    ) -> tuple[Any, dict[str, Any]]:
        all_calendars = list(client.get_calendars())
        task_calendars = [calendar for calendar in all_calendars if self._supports_todo(calendar)]
        effective_selector = (selector or self.config.default_calendar or "").strip()

        if effective_selector:
            for calendar in [*task_calendars, *all_calendars]:
                summary = self._calendar_summary(calendar)
                if (
                    effective_selector == summary["id"]
                    or effective_selector == summary["name"]
                    or effective_selector.casefold() == summary["name"].casefold()
                ):
                    if self._supports_todo(calendar) or self._component_set_is_unknown(calendar):
                        return calendar, summary
                    raise ReminderListNotFoundError(
                        f"Calendar is not a VTODO reminder list: {effective_selector}"
                    )
            raise ReminderListNotFoundError(f"Reminder list not found: {effective_selector}")

        if len(task_calendars) == 1:
            calendar = task_calendars[0]
            return calendar, self._calendar_summary(calendar)
        if not task_calendars:
            raise ReminderListNotFoundError(
                "No CalDAV reminder lists with VTODO support are available"
            )
        raise ReminderListNotFoundError(
            "list_name is required because the iCloud account has multiple reminder lists"
        )

    @staticmethod
    def _supports_todo(calendar: Any) -> bool:
        getter = getattr(calendar, "get_supported_components", None)
        if not callable(getter):
            return False
        try:
            try:
                components = getter(with_fallback=False)
            except TypeError:
                components = getter()
        except Exception:
            return False
        return any(str(component).upper() == "VTODO" for component in components or [])

    @staticmethod
    def _component_set_is_unknown(calendar: Any) -> bool:
        """Return true when an explicit list has no component-set property."""

        getter = getattr(calendar, "get_supported_components", None)
        if not callable(getter):
            return True
        try:
            try:
                getter(with_fallback=False)
            except TypeError:
                getter()
        except Exception:
            # A missing supported-component property is a valid CalDAV case;
            # an explicitly named list may still be a VTODO collection.
            return True
        return False

    @staticmethod
    def _get_todo_resource(calendar: Any, uid: str) -> Any:
        try:
            getter = getattr(calendar, "get_todo_by_uid", None)
            if getter is None:
                getter = getattr(calendar, "get_object_by_uid")
            return getter(uid)
        except (caldav_error.NotFoundError, KeyError) as exc:
            raise ReminderNotFoundError(f"Reminder not found: {uid}") from exc

    def _reminder_summary(
        self,
        resource: Any,
        calendar: dict[str, Any],
    ) -> dict[str, Any]:
        component = resource.get_icalendar_component()
        uid = getattr(resource, "id", None) or self._component_text(component, "UID")
        status = self._component_text(component, "STATUS")
        percent = self._component_text(component, "PERCENT-COMPLETE")
        completed = status.casefold() == "completed" if status else False
        if percent:
            try:
                completed = completed or int(percent) >= 100
            except ValueError:
                pass
        priority = self._component_text(component, "PRIORITY")
        try:
            priority_value: int | None = int(priority) if priority is not None else None
        except ValueError:
            priority_value = None
        return {
            "uid": str(uid),
            "list_id": calendar["id"],
            "list_name": calendar["name"],
            "title": self._component_text(component, "SUMMARY"),
            "notes": self._component_text(component, "DESCRIPTION"),
            "due": self._serialize_datetime(self._component_datetime(component, "DUE")),
            "remind_at": self._serialize_datetime(
                self._component_datetime(component, "DTSTART")
            ),
            "completed": completed,
            "completed_at": self._serialize_datetime(
                self._component_datetime(component, "COMPLETED")
            ),
            "status": status,
            "priority": priority_value,
        }

    @staticmethod
    def _matches_query(item: dict[str, Any], query: str) -> bool:
        searchable = " ".join(
            str(item.get(field) or "") for field in ("title", "notes", "status")
        )
        return query in searchable.casefold()

    def _parse_due(self, value: str, field: str) -> date | datetime:
        normalized = value.strip().replace("Z", "+00:00")
        if len(normalized) == 10:
            try:
                return date.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError(f"{field} must be an ISO date or datetime") from exc
        try:
            parsed_datetime = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                return date.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError(f"{field} must be an ISO date or datetime") from exc
        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=self._zone(None))
        return parsed_datetime

    def _parse_filter_datetime(self, value: str, field: str) -> datetime:
        parsed = self._parse_due(value, field)
        if isinstance(parsed, datetime):
            return parsed
        return datetime.combine(parsed, time.min, tzinfo=self._zone(None))

    def _comparison_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        parsed = self._parse_due(value, "due")
        if isinstance(parsed, datetime):
            return parsed
        return datetime.combine(parsed, time.min, tzinfo=self._zone(None))

    @staticmethod
    def _validate_priority(priority: int | None) -> int | None:
        if priority is None:
            return None
        if not isinstance(priority, int) or not 0 <= priority <= 9:
            raise ValueError("priority must be an integer between 0 and 9")
        return priority

    @staticmethod
    def _set_completed(component: Any, completed: bool) -> None:
        component.pop("STATUS", None)
        component.pop("PERCENT-COMPLETE", None)
        component.pop("COMPLETED", None)
        if completed:
            component.add("STATUS", "COMPLETED")
            component.add("PERCENT-COMPLETE", 100)
            component.add("COMPLETED", datetime.now(timezone.utc))
        else:
            component.add("STATUS", "NEEDS-ACTION")
            component.add("PERCENT-COMPLETE", 0)
