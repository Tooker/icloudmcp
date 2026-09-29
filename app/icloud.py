from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterator
from urllib.parse import unquote, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from caldav import DAVClient
from caldav.lib import error as caldav_error
from icalendar import Calendar as ICalendar
from icalendar import Event as ICalendarEvent

from app.config import ICloudConfig


class ICloudServiceError(RuntimeError):
    """A safe, user-facing iCloud operation error."""


class CalendarNotFoundError(ICloudServiceError):
    pass


class EventNotFoundError(ICloudServiceError):
    pass


class ICloudCalendarService:
    """Small synchronous CalDAV facade used from MCP worker threads.

    ``caldav`` is a blocking client. Keeping this facade synchronous makes its
    connection lifecycle explicit; the MCP layer calls it via ``to_thread`` so
    one slow iCloud request does not block the ASGI event loop.
    """

    def __init__(
        self,
        config: ICloudConfig,
        client_factory: Callable[..., Any] = DAVClient,
    ) -> None:
        self.config = config
        self._client_factory = client_factory

    @contextmanager
    def _connected_client(self) -> Iterator[Any]:
        client = self._client_factory(
            url=self.config.caldav_url,
            username=self.config.username,
            password=self.config.app_specific_password,
            auth_type="basic",
            timeout=30,
            enable_rfc6764=False,
        )
        try:
            yield client
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def list_calendars(self) -> list[dict[str, Any]]:
        with self._connected_client() as client:
            return [self._calendar_summary(calendar) for calendar in client.get_calendars()]

    def list_events(
        self,
        calendar: str | None = None,
        start: str | None = None,
        end: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")

        search_start, search_end = self._search_window(start, end)
        with self._connected_client() as client:
            calendars = self._selected_calendars(client, calendar)
            events: list[dict[str, Any]] = []
            normalized_query = query.strip().casefold() if query else None

            for target_calendar in calendars:
                summary = self._calendar_summary(target_calendar)
                search_results = target_calendar.search(
                    event=True,
                    start=search_start,
                    end=search_end,
                )
                for resource in search_results:
                    item = self._event_summary(resource, summary)
                    if normalized_query and not self._matches_query(item, normalized_query):
                        continue
                    events.append(item)

            events.sort(key=lambda item: item.get("start") or "")
            return events[:limit]

    def get_event(self, calendar: str, uid: str) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(client, calendar)
            resource = self._get_event_resource(target_calendar, uid)
            return self._event_summary(resource, calendar_summary)

    def create_event(
        self,
        calendar: str | None,
        title: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        all_day: bool = False,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        title = self._require_text(title, "title")
        start = self._require_text(start, "start")
        end = self._require_text(end, "end")
        start_value, end_value = self._event_bounds(
            start,
            end,
            all_day=all_day,
            timezone_name=timezone_name,
        )

        icalendar = ICalendar()
        icalendar.add("prodid", "-//IcloudCruncher//iCloud MCP//EN")
        icalendar.add("version", "2.0")
        event = ICalendarEvent()
        event.add("uid", str(uuid4()))
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("dtstart", start_value)
        event.add("dtend", end_value)
        event.add("summary", title)
        if description:
            event.add("description", description)
        if location:
            event.add("location", location)
        icalendar.add_component(event)

        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(client, calendar)
            resource = target_calendar.add_event(icalendar.to_ical())
            return self._event_summary(resource, calendar_summary)

    def update_event(
        self,
        calendar: str,
        uid: str,
        title: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        all_day: bool | None = None,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        if title is not None and not title.strip():
            raise ValueError("title must not be empty")
        if start is not None and not start.strip():
            raise ValueError("start must not be empty")
        if end is not None and not end.strip():
            raise ValueError("end must not be empty")
        if (start is not None and end is None) or (start is None and end is not None):
            raise ValueError("start and end must be supplied together")
        if all(
            value is None
            for value in (title, start, end, description, location, all_day, timezone_name)
        ):
            raise ValueError("at least one event field must be supplied for update")
        if timezone_name is not None and start is None and end is None and all_day is None:
            raise ValueError("timezone_name requires start/end or all_day")

        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(client, calendar)
            resource = self._get_event_resource(target_calendar, uid)

            with resource.edit_icalendar_component() as component:
                if title is not None:
                    self._replace_component_value(component, "SUMMARY", title.strip())
                if description is not None:
                    self._replace_optional_component_value(component, "DESCRIPTION", description)
                if location is not None:
                    self._replace_optional_component_value(component, "LOCATION", location)

                current_start = self._component_datetime(component, "DTSTART")
                current_end = self._component_datetime(component, "DTEND")
                current_all_day = isinstance(current_start, date) and not isinstance(current_start, datetime)

                if start is not None and end is not None:
                    new_start, new_end = self._event_bounds(
                        start,
                        end,
                        all_day=current_all_day if all_day is None else all_day,
                        timezone_name=timezone_name,
                    )
                    self._replace_component_value(component, "DTSTART", new_start)
                    self._replace_component_value(component, "DTEND", new_end)
                elif all_day is not None and all_day != current_all_day:
                    if current_start is None:
                        raise ValueError("event has no DTSTART and cannot be converted")
                    new_start, new_end = self._convert_bounds(
                        current_start,
                        current_end,
                        all_day=all_day,
                        timezone_name=timezone_name,
                    )
                    self._replace_component_value(component, "DTSTART", new_start)
                    self._replace_component_value(component, "DTEND", new_end)

            resource.save()
            return self._event_summary(resource, calendar_summary)

    def delete_event(self, calendar: str, uid: str) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(client, calendar)
            resource = self._get_event_resource(target_calendar, uid)
            resource.delete()
            return {
                "deleted": True,
                "uid": uid,
                "calendar_id": calendar_summary["id"],
                "calendar_name": calendar_summary["name"],
            }

    def _selected_calendars(self, client: Any, selector: str | None) -> list[Any]:
        calendars = list(client.get_calendars())
        if selector is None or not selector.strip():
            return calendars
        return [self._resolve_calendar_from_list(calendars, selector)[0]]

    def _resolve_calendar(self, client: Any, selector: str | None) -> tuple[Any, dict[str, Any]]:
        calendars = list(client.get_calendars())
        calendar, summary = self._resolve_calendar_from_list(calendars, selector)
        return calendar, summary

    def _resolve_calendar_from_list(
        self,
        calendars: list[Any],
        selector: str | None,
    ) -> tuple[Any, dict[str, Any]]:
        if not calendars:
            raise CalendarNotFoundError("No iCloud calendars are available")

        effective_selector = (selector or self.config.default_calendar or "").strip()
        summaries = [(calendar, self._calendar_summary(calendar)) for calendar in calendars]

        if not effective_selector:
            if len(summaries) == 1:
                return summaries[0]
            raise CalendarNotFoundError(
                "calendar is required because the iCloud account has multiple calendars"
            )

        normalized_selector = effective_selector.casefold()
        for calendar, summary in summaries:
            if effective_selector == summary["id"] or effective_selector == summary["name"]:
                return calendar, summary
            if normalized_selector == summary["name"].casefold():
                return calendar, summary

        raise CalendarNotFoundError(f"Calendar not found: {effective_selector}")

    def _get_event_resource(self, calendar: Any, uid: str) -> Any:
        try:
            getter = getattr(calendar, "get_event_by_uid", None) or getattr(calendar, "event_by_uid")
            return getter(uid)
        except caldav_error.NotFoundError as exc:
            raise EventNotFoundError(f"Event not found: {uid}") from exc

    def _calendar_summary(self, calendar: Any) -> dict[str, Any]:
        identifier = getattr(calendar, "id", None)
        if identifier is None or not str(identifier).strip():
            identifier = self._identifier_from_url(getattr(calendar, "url", None))

        try:
            name = calendar.get_display_name()
        except Exception:
            name = None
        name = str(name).strip() if name is not None else ""
        if not name:
            name = str(identifier)

        return {"id": str(identifier), "name": name}

    @staticmethod
    def _identifier_from_url(url: Any) -> str:
        if url is None:
            return "unknown"
        path = urlparse(str(url)).path.rstrip("/")
        if path:
            return unquote(path.rsplit("/", 1)[-1])
        return "unknown"

    def _event_summary(self, resource: Any, calendar: dict[str, Any]) -> dict[str, Any]:
        component = resource.get_icalendar_component()
        start = self._component_datetime(component, "DTSTART")
        end = self._component_datetime(component, "DTEND")
        uid = getattr(resource, "id", None) or self._component_text(component, "UID")
        return {
            "uid": str(uid),
            "calendar_id": calendar["id"],
            "calendar_name": calendar["name"],
            "summary": self._component_text(component, "SUMMARY"),
            "description": self._component_text(component, "DESCRIPTION"),
            "location": self._component_text(component, "LOCATION"),
            "start": self._serialize_datetime(start),
            "end": self._serialize_datetime(end),
            "all_day": isinstance(start, date) and not isinstance(start, datetime),
            "status": self._component_text(component, "STATUS"),
            "recurrence_rule": self._component_text(component, "RRULE"),
        }

    @staticmethod
    def _matches_query(item: dict[str, Any], query: str) -> bool:
        searchable = " ".join(
            str(item.get(field) or "")
            for field in ("summary", "description", "location", "status")
        )
        return query in searchable.casefold()

    def _search_window(
        self,
        start: str | None,
        end: str | None,
    ) -> tuple[datetime, datetime]:
        zone = self._zone(None)
        now = datetime.now(zone)
        if start is None and end is None:
            return now - timedelta(days=30), now + timedelta(days=365)

        parsed_start = self._parse_datetime(start, zone) if start else now - timedelta(days=30)
        parsed_end = self._parse_datetime(end, zone) if end else now + timedelta(days=365)
        if parsed_end <= parsed_start:
            raise ValueError("end must be after start")
        return parsed_start, parsed_end

    def _event_bounds(
        self,
        start: str,
        end: str,
        *,
        all_day: bool,
        timezone_name: str | None,
    ) -> tuple[date | datetime, date | datetime]:
        if all_day:
            try:
                start_value = date.fromisoformat(start)
                end_value = date.fromisoformat(end)
            except ValueError as exc:
                raise ValueError("all-day start and end must be ISO dates (YYYY-MM-DD)") from exc
        else:
            zone = self._zone(timezone_name)
            start_value = self._parse_datetime(start, zone)
            end_value = self._parse_datetime(end, zone)

        if end_value <= start_value:
            raise ValueError("end must be after start")
        return start_value, end_value

    def _convert_bounds(
        self,
        start: date | datetime,
        end: date | datetime | None,
        *,
        all_day: bool,
        timezone_name: str | None,
    ) -> tuple[date | datetime, date | datetime]:
        zone = self._zone(timezone_name)
        if all_day:
            new_start = start.astimezone(zone).date() if isinstance(start, datetime) else start
            if isinstance(end, datetime):
                new_end = end.astimezone(zone).date()
            elif isinstance(end, date):
                new_end = end
            else:
                new_end = new_start + timedelta(days=1)
        else:
            if isinstance(start, datetime):
                new_start = start
            else:
                new_start = datetime.combine(start, time.min, tzinfo=zone)
            if isinstance(end, datetime):
                new_end = end
            elif isinstance(end, date):
                new_end = datetime.combine(end, time.min, tzinfo=zone)
            else:
                new_end = new_start + timedelta(days=1)

        if new_end <= new_start:
            new_end = new_start + timedelta(days=1)
        return new_start, new_end

    def _zone(self, timezone_name: str | None) -> ZoneInfo:
        name = timezone_name or self.config.timezone
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {name}") from exc

    @staticmethod
    def _parse_datetime(value: str, zone: ZoneInfo) -> datetime:
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(normalized), time.min)
            except ValueError as exc:
                raise ValueError(f"invalid ISO datetime: {value}") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=zone)
        return parsed

    @staticmethod
    def _component_datetime(component: Any, name: str) -> date | datetime | None:
        value = component.get(name)
        if value is None:
            return None
        return getattr(value, "dt", value)

    @staticmethod
    def _component_text(component: Any, name: str) -> str | None:
        value = component.get(name)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _serialize_datetime(value: date | datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _replace_component_value(component: Any, name: str, value: Any) -> None:
        component.pop(name, None)
        component.add(name, value)

    @staticmethod
    def _replace_optional_component_value(component: Any, name: str, value: str) -> None:
        component.pop(name, None)
        if value:
            component.add(name, value)

    @staticmethod
    def _require_text(value: str, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} must not be empty")
        return normalized
