from __future__ import annotations

from contextlib import contextmanager
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import threading
from time import monotonic, perf_counter
from typing import Any, Callable, Iterator, Literal
from urllib.parse import unquote, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from caldav import DAVClient
from caldav.lib import error as caldav_error
from icalendar import Calendar as ICalendar
from icalendar import Event as ICalendarEvent
from loguru import logger
import recurring_ical_events

from app.config import ICloudConfig
from app.icloud_cache import SQLiteICloudCalendarCache
from app.timing import measure_phase, timed_phase


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
        cache: SQLiteICloudCalendarCache | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory
        self._cache = (
            cache.for_account("caldav", config.caldav_url.rstrip("/"), config.username)
            if cache is not None else None
        )
        self._refresh_stop = threading.Event()
        self._refresh_ranges_lock = threading.Lock()
        self._refresh_ranges: OrderedDict[tuple[str | None, str | None, str | None], float] = OrderedDict()
        self._cache_publish_lock = threading.Lock()
        self._events_revision = 0

    @property
    def cache_refresh_supported(self) -> bool:
        return self._cache is not None and self._cache.events_ttl_seconds > 0

    def stop_cache_refresh(self) -> None:
        self._refresh_stop.set()

    def _remember_event_range(self, calendar: str | None, start: str | None, end: str | None) -> None:
        if not self.cache_refresh_supported:
            return
        key = ((calendar or "").strip() or None, start, end)
        if start is None and end is None:
            return  # The rolling default already covers every calendar.
        with self._refresh_ranges_lock:
            self._refresh_ranges[key] = monotonic()
            self._refresh_ranges.move_to_end(key)
            while len(self._refresh_ranges) > 8:
                self._refresh_ranges.popitem(last=False)

    def refresh_cache_once(self) -> dict[str, int]:
        """Warm the rolling default and bounded recent requests, without filters."""
        if not self.cache_refresh_supported or self._refresh_stop.is_set():
            return {"ranges": 0, "errors": 0}
        now = monotonic()
        with self._refresh_ranges_lock:
            for key, used_at in list(self._refresh_ranges.items()):
                if now - used_at >= 3600:
                    self._refresh_ranges.pop(key)
            ranges = [(None, None, None), *self._refresh_ranges]
        refreshed, errors = 0, 0
        for calendar, start, end in ranges:
            if self._refresh_stop.is_set():
                break
            try:
                self._list_events(calendar, start, end, force_refresh=True)
                refreshed += 1
            except Exception as exc:
                errors += 1
                logger.warning("icloud_cache_refresh action=range status=error error_type={}", type(exc).__name__)
        return {"ranges": refreshed, "errors": errors}

    def run_cache_refresh(self, interval_seconds: float = 30) -> None:
        if not self.cache_refresh_supported:
            return
        interval = min(interval_seconds, self._cache.events_ttl_seconds / 2)
        if interval <= 0:
            raise ValueError("Cache refresh interval must be positive")
        logger.info("icloud_cache_refresh action=start status=running interval_seconds={}", interval)
        failures = 0
        while not self._refresh_stop.is_set():
            started = perf_counter()
            result = self.refresh_cache_once()
            failures = failures + 1 if result["errors"] and not result["ranges"] else 0
            logger.info(
                "icloud_cache_refresh action=complete status={} ranges={} errors={} duration_ms={:.1f}",
                "partial" if result["errors"] else "ok", result["ranges"], result["errors"],
                (perf_counter() - started) * 1000,
            )
            delay = min(300, interval * 2 ** min(failures, 4)) if failures else interval
            self._refresh_stop.wait(max(0.1, delay - (perf_counter() - started)))
        logger.info("icloud_cache_refresh action=stop status=stopped")

    @contextmanager
    def _connected_client(self) -> Iterator[Any]:
        with measure_phase("caldav_client_setup"):
            client = self._client_factory(
                url=self.config.caldav_url,
                username=self.config.username,
                password=self.config.app_specific_password,
                auth_type="basic",
                timeout=30,
                enable_rfc6764=False,
            )
            self._disable_http3(client)
        try:
            yield client
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                with measure_phase("caldav_client_close"):
                    close()

    @staticmethod
    def _disable_http3(client: Any) -> None:
        """Avoid QUIC/HTTP3 on CalDAV connections.

        iCloud advertises HTTP/3, but the UDP receive path used by the
        container can fail with ``OSError: [Errno 90] Message too long``.
        ``caldav`` exposes its Niquests session on the client, so replace it
        with the same session type while disabling HTTP/3. Older session
        implementations that do not accept this option are left unchanged.
        """

        session = getattr(client, "session", None)
        if session is None:
            return

        try:
            safe_session = type(session)(disable_http3=True)
        except TypeError:
            return

        client.session = safe_session
        close = getattr(session, "close", None)
        if callable(close):
            close()

    def list_calendars(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            cached = self._cache.get_calendars()
            if cached is not None and cached.fresh:
                logger.info(
                    "icloud_cache tool=list_calendars action=read status=hit entries={}",
                    len(cached.value),
                )
                return cached.value
            logger.info(
                "icloud_cache tool=list_calendars action=read status={}",
                "stale" if cached is not None else "miss",
            )

        with self._connected_client() as client:
            with measure_phase("caldav_calendar_discovery"):
                calendars = list(client.get_calendars())
            result = [self._calendar_summary(calendar) for calendar in calendars]
        if self._cache is not None:
            self._cache.set_calendars(result)
            logger.info(
                "icloud_cache tool=list_calendars action=write status=refresh entries={}",
                len(result),
            )
        return result

    def list_events(
        self,
        calendar: str | None = None,
        start: str | None = None,
        end: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        result = self._list_events(calendar, start, end, query, limit)
        self._remember_event_range(calendar, start, end)
        return result

    def _list_events(
        self,
        calendar: str | None = None,
        start: str | None = None,
        end: str | None = None,
        query: str | None = None,
        limit: int = 50,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")

        search_start, search_end = self._search_window(start, end)
        cache_start = self._cache_datetime(search_start)
        cache_end = self._cache_datetime(search_end)
        cached_by_id: dict[str, list[dict[str, Any]]] = {}
        with self._cache_publish_lock:
            revision = self._events_revision

        if self._cache is not None and not force_refresh:
            cached_calendars = self._cache.get_calendars()
            if cached_calendars is not None and cached_calendars.fresh:
                selected_summaries = self._resolve_calendar_summaries(
                    cached_calendars.value,
                    calendar,
                )
                cached_events: list[dict[str, Any]] = []
                all_cache_hits = True
                for summary in selected_summaries:
                    cached = self._cache.get_events(
                        summary["id"],
                        cache_start,
                        cache_end,
                    )
                    if cached is None or not cached.fresh:
                        all_cache_hits = False
                    else:
                        cached_by_id[summary["id"]] = cached.value
                        cached_events.extend(cached.value)
                if all_cache_hits:
                    logger.info(
                        "icloud_cache tool=list_events action=read status=hit calendars={} entries={}",
                        len(selected_summaries),
                        len(cached_events),
                    )
                    return self._filter_events(cached_events, query, limit)
            logger.info("icloud_cache tool=list_events action=read status=miss")

        with self._connected_client() as client:
            calendars = self._selected_calendars(client, calendar)
            events: list[dict[str, Any]] = []

            for target_calendar in calendars:
                if force_refresh and self._refresh_stop.is_set():
                    break
                summary = self._calendar_summary(target_calendar)
                if self._cache is not None and not force_refresh and summary["id"] not in cached_by_id:
                    cached = self._cache.get_events(summary["id"], cache_start, cache_end)
                    if cached is not None and cached.fresh:
                        cached_by_id[summary["id"]] = cached.value
                if summary["id"] in cached_by_id:
                    events.extend(cached_by_id[summary["id"]])
                    continue
                with measure_phase("caldav_event_search"):
                    search_results = list(target_calendar.search(
                        event=True,
                        start=search_start,
                        end=search_end,
                        expand=False,
                    ))
                calendar_events = [
                    occurrence
                    for resource in search_results
                    for occurrence in self._event_occurrences(
                        resource, summary, search_start, search_end,
                    )
                ]
                events.extend(calendar_events)
                if self._cache is not None:
                    with self._cache_publish_lock:
                        if revision == self._events_revision:
                            self._cache.set_events(
                                summary["id"], cache_start, cache_end, calendar_events,
                            )

            if self._cache is not None:
                logger.info(
                    "icloud_cache tool=list_events action=write status=refresh entries={}",
                    len(events),
                )
            return self._filter_events(events, query, limit)

    def get_event(self, calendar: str, uid: str) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        if self._cache is not None:
            cached = self._cache.get_event(calendar, uid)
            if cached is not None and cached.fresh:
                logger.info("icloud_cache tool=get_event action=read status=hit")
                return cached.value
            logger.info(
                "icloud_cache tool=get_event action=read status={}",
                "stale" if cached is not None else "miss",
            )

        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(
                client,
                calendar,
                tool="get_event",
            )
            resource = self._get_event_resource(target_calendar, uid)
            result = self._event_summary(resource, calendar_summary)
        if self._cache is not None:
            self._cache.set_event(result)
            logger.info("icloud_cache tool=get_event action=write status=refresh entries=1")
        return result

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
            target_calendar, calendar_summary = self._resolve_calendar(
                client,
                calendar,
                tool="create_event",
            )
            resource = target_calendar.add_event(icalendar.to_ical())
            result = self._event_summary(resource, calendar_summary)
        if self._cache is not None:
            self._invalidate_event_cache("create_event")
        return result

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
            target_calendar, calendar_summary = self._resolve_calendar(
                client,
                calendar,
                tool="update_event",
            )
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
            result = self._event_summary(resource, calendar_summary)
        if self._cache is not None:
            self._invalidate_event_cache("update_event")
        return result

    def delete_event(
        self,
        calendar: str,
        uid: str,
        *,
        scope: Literal["occurrence", "series"],
        recurrence_id: str | None = None,
    ) -> dict[str, Any]:
        uid = self._require_text(uid, "uid")
        if scope not in {"occurrence", "series"}:
            raise ValueError("scope must be occurrence or series")
        if scope == "occurrence":
            recurrence_id = self._require_text(recurrence_id or "", "recurrence_id")
        elif recurrence_id is not None:
            raise ValueError("recurrence_id must be omitted for scope=series")

        with self._connected_client() as client:
            target_calendar, calendar_summary = self._resolve_calendar(
                client,
                calendar,
                tool="delete_event",
            )
            resource = self._get_event_resource(target_calendar, uid)
            occurrence = {}
            if scope == "occurrence":
                occurrence = self._delete_occurrence(resource, uid, recurrence_id, calendar_summary["id"])
            else:
                resource.delete()
            result = {
                "deleted": True,
                "scope": scope,
                "uid": uid,
                "calendar_id": calendar_summary["id"],
                "calendar_name": calendar_summary["name"],
                **occurrence,
            }
        if self._cache is not None:
            self._invalidate_event_cache("delete_event")
        return result

    @timed_phase("calendar_occurrence_delete")
    def _delete_occurrence(
        self, resource: Any, uid: str, recurrence_id: str, calendar_id: str,
    ) -> dict[str, Any]:
        # Always edit the complete, unexpanded VCALENDAR. Saving or deleting an
        # expanded CalDAV Event can otherwise overwrite/delete the whole series.
        document = resource.get_icalendar_instance()
        components = [
            component for component in document.subcomponents
            if component.name == "VEVENT" and self._component_text(component, "UID") == uid
        ]
        masters = [component for component in components if "RECURRENCE-ID" not in component]
        if len(masters) != 1 or not any(name in masters[0] for name in ("RRULE", "RDATE")):
            raise ValueError("scope=occurrence requires a recurring event with a master component")
        master = masters[0]
        start = self._component_datetime(master, "DTSTART")
        if not isinstance(start, date):
            raise ValueError("recurring event has no valid DTSTART")
        identifier = self._parse_recurrence_id(recurrence_id, start)
        overrides = [
            component for component in components
            if self._same_recurrence_id(self._component_datetime(component, "RECURRENCE-ID"), identifier)
        ]
        if any(
            component["RECURRENCE-ID"].params.get("RANGE") not in {None, "THISANDFUTURE"}
            for component in overrides
        ):
            raise ValueError("unsupported RANGE recurrence exception")

        # A moved exception is identified by its original RECURRENCE-ID, never
        # by its new DTSTART. For ordinary instances validate membership against
        # the master, without EXDATEs, so repeated deletions remain idempotent.
        if not overrides:
            original = deepcopy(document)
            original_master = deepcopy(master)
            original_master.pop("EXDATE", None)
            original.subcomponents = [
                component for component in original.subcomponents if component.name == "VTIMEZONE"
            ] + [original_master]
            candidates = recurring_ical_events.of(original).at(identifier)
            if not any(
                self._same_recurrence_id(self._component_datetime(candidate, "RECURRENCE-ID"), identifier)
                for candidate in candidates
            ):
                raise ValueError("recurrence_id does not identify an occurrence of this series")

        excluded = any(
            self._same_recurrence_id(value, identifier)
            for value in self._exception_dates(master)
        )
        range_overrides = [
            component for component in overrides
            if component["RECURRENCE-ID"].params.get("RANGE") == "THISANDFUTURE"
        ]
        already_deleted = (excluded and len(range_overrides) == len(overrides)) or (
            bool(overrides) and all(self._component_text(component, "STATUS") == "CANCELLED" for component in overrides)
        )
        affected_start = self._component_datetime(overrides[0], "DTSTART") if overrides else identifier
        if not overrides:
            preceding_ranges = [
                component for component in components
                if "RECURRENCE-ID" in component
                and component["RECURRENCE-ID"].params.get("RANGE") == "THISANDFUTURE"
                and component["RECURRENCE-ID"].dt <= identifier
            ]
            if preceding_ranges:
                source = max(preceding_ranges, key=lambda component: component["RECURRENCE-ID"].dt)
                affected_start = self._shift_occurrence(
                    identifier, source["RECURRENCE-ID"].dt, source["DTSTART"].dt,
                )
        if isinstance(affected_start, datetime) and isinstance(start, datetime) and start.tzinfo is not None:
            affected_start = affected_start.astimezone(start.tzinfo)
        if not already_deleted:
            if not excluded:
                parameters = {}
                dtstart = master["DTSTART"]
                if "TZID" in dtstart.params:
                    parameters["TZID"] = dtstart.params["TZID"]
                master.add("EXDATE", identifier, parameters=parameters)
            # EXDATE suppresses the range anchor itself. Retain its RANGE
            # component to preserve modifications to future occurrences.
            removed = {id(component) for component in overrides if component not in range_overrides}
            document.subcomponents = [
                component for component in document.subcomponents
                if id(component) not in removed
            ]
            self._replace_component_value(master, "DTSTAMP", datetime.now(timezone.utc))
            self._replace_component_value(master, "SEQUENCE", int(master.get("SEQUENCE", 0)) + 1)
            with resource.edit_icalendar_instance() as current:
                current.subcomponents = document.subcomponents
            # CalDAV's default SEQUENCE update targets the first VEVENT, which
            # may be an unrelated override. We updated the master explicitly.
            resource.save(only_this_recurrence=False, increase_seqno=False)

        return {
            "series_uid": uid,
            "recurrence_id": identifier.isoformat(),
            "occurrence_id": self._occurrence_id(calendar_id, uid, identifier),
            "occurrence_date": self._date_string(identifier),
            "affected_date": self._date_string(affected_start or identifier),
            "already_deleted": already_deleted,
        }

    @staticmethod
    def _parse_recurrence_id(value: str, start: date | datetime) -> date | datetime:
        if not isinstance(start, datetime):
            if len(value) != 10:
                raise ValueError("all-day recurrence_id must be an ISO date (YYYY-MM-DD)")
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("all-day recurrence_id must be an ISO date (YYYY-MM-DD)") from exc
        if "T" not in value:
            raise ValueError("timed recurrence_id must be a complete ISO datetime from list_events")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recurrence_id must be a valid ISO datetime") from exc
        if parsed.microsecond:
            raise ValueError("recurrence_id must use whole seconds")
        if (parsed.tzinfo is None) != (start.tzinfo is None):
            raise ValueError("recurrence_id must match the series timezone type; use the value from list_events")
        return parsed.astimezone(start.tzinfo) if start.tzinfo is not None else parsed

    @staticmethod
    def _same_recurrence_id(left: date | datetime | None, right: date | datetime) -> bool:
        if isinstance(left, datetime) and isinstance(right, datetime):
            if (left.tzinfo is None) != (right.tzinfo is None):
                return False
            if left.tzinfo is not None:
                return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)
            return left == right
        return not isinstance(left, datetime) and not isinstance(right, datetime) and left == right

    @staticmethod
    def _exception_dates(component: Any) -> Iterator[date | datetime]:
        properties = component.get("EXDATE", [])
        if not isinstance(properties, list):
            properties = [properties]
        for prop in properties:
            for value in prop.dts:
                yield value.dt

    @staticmethod
    def _date_string(value: date | datetime) -> str:
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()

    @staticmethod
    def _shift_occurrence(
        value: date | datetime, source: date | datetime, target: date | datetime,
    ) -> date | datetime:
        # Use elapsed local calendar time, retaining DST transitions in the
        # target timezone, rather than the fixed offset of the range anchor.
        if isinstance(value, datetime) and isinstance(source, datetime) and source.tzinfo is not None:
            value = value.astimezone(source.tzinfo)
        return target + (value - source)

    @staticmethod
    def _occurrence_id(calendar_id: str, uid: str, identifier: date | datetime | None) -> str:
        if isinstance(identifier, datetime) and identifier.tzinfo is not None:
            identifier = identifier.astimezone(timezone.utc)
        value = identifier.isoformat() if identifier is not None else None
        return hashlib.sha256(json.dumps([str(calendar_id), uid, value]).encode()).hexdigest()

    @timed_phase("calendar_selection")
    def _selected_calendars(self, client: Any, selector: str | None) -> list[Any]:
        with measure_phase("caldav_calendar_discovery"):
            calendars = list(client.get_calendars())
        self._cache_calendars(calendars, tool="list_events")
        if selector is None or not selector.strip():
            return calendars
        return [self._resolve_calendar_from_list(calendars, selector)[0]]

    def _resolve_calendar(
        self,
        client: Any,
        selector: str | None,
        *,
        tool: str,
    ) -> tuple[Any, dict[str, Any]]:
        with measure_phase("caldav_calendar_discovery"):
            calendars = list(client.get_calendars())
        self._cache_calendars(calendars, tool=tool)
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

    def _cache_calendars(self, calendars: list[Any], *, tool: str) -> None:
        if self._cache is None:
            return
        summaries = [self._calendar_summary(calendar) for calendar in calendars]
        self._cache.set_calendars(summaries)
        logger.info(
            "icloud_cache tool={} action=write kind=calendars status=update entries={}",
            tool,
            len(summaries),
        )

    def _invalidate_event_cache(self, tool: str) -> None:
        if self._cache is None:
            return
        with self._cache_publish_lock:
            self._events_revision += 1
            invalidated = self._cache.invalidate_events()
        logger.info(
            "icloud_cache tool={} action=invalidate kind=events entries={}",
            tool,
            invalidated,
        )

    def _resolve_calendar_summaries(
        self,
        summaries: list[dict[str, Any]],
        selector: str | None,
    ) -> list[dict[str, Any]]:
        if not summaries:
            raise CalendarNotFoundError("No iCloud calendars are available")

        # Read searches without a selector span every calendar, including
        # when a default calendar is configured for writes.
        effective_selector = (selector or "").strip()
        if not effective_selector:
            return summaries

        normalized_selector = effective_selector.casefold()
        for summary in summaries:
            if effective_selector == summary["id"] or effective_selector == summary["name"]:
                return [summary]
            if normalized_selector == summary["name"].casefold():
                return [summary]

        raise CalendarNotFoundError(f"Calendar not found: {effective_selector}")

    @timed_phase("calendar_local_filter")
    def _filter_events(
        self,
        events: list[dict[str, Any]],
        query: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip().casefold() if query else None
        if normalized_query:
            events = [
                event for event in events if self._matches_query(event, normalized_query)
            ]
        zone = self._zone(None)
        events.sort(key=lambda item: (
            self._parse_datetime(item["start"], zone).astimezone(timezone.utc)
            if item.get("start") else datetime.min.replace(tzinfo=timezone.utc)
        ))
        return events[:limit]

    @staticmethod
    def _cache_datetime(value: datetime) -> str:
        return value.replace(microsecond=0).isoformat()

    def _get_event_resource(self, calendar: Any, uid: str) -> Any:
        try:
            getter = getattr(calendar, "get_event_by_uid", None) or getattr(calendar, "event_by_uid")
            return getter(uid)
        except caldav_error.NotFoundError as exc:
            raise EventNotFoundError(f"Event not found: {uid}") from exc
        except caldav_error.ReportError as exc:
            if not self._is_precondition_failed(exc):
                raise
            return self._find_event_by_uid_with_time_range(calendar, uid)

    def _find_event_by_uid_with_time_range(self, calendar: Any, uid: str) -> Any:
        """Work around iCloud rejecting UID-only calendar-query REPORTs.

        iCloud accepts calendar queries with a time range but responds with
        ``412 Precondition Failed`` to the UID-only query used by
        ``Calendar.get_event_by_uid``. Search progressively wider windows and
        compare the UID locally instead of relying on that server-side filter.
        """

        zone = self._zone(None)
        now = datetime.now(zone)
        for days in (365, 3650):
            search_start = now - timedelta(days=days)
            search_end = now + timedelta(days=days)
            for resource in calendar.search(
                event=True,
                start=search_start,
                end=search_end,
                expand=False,
            ):
                if self._resource_uid(resource) == uid:
                    return resource

        raise EventNotFoundError(f"Event not found: {uid}")

    @staticmethod
    def _is_precondition_failed(exc: caldav_error.ReportError) -> bool:
        response_status = str(getattr(exc, "url", "") or "").strip()
        return response_status.startswith("412 Precondition Failed")

    def _resource_uid(self, resource: Any) -> str | None:
        component = resource.get_icalendar_component()
        component_uid = self._component_text(component, "UID")
        if component_uid:
            return component_uid

        resource_id = getattr(resource, "id", None)
        if resource_id is None:
            return None
        resource_id = str(resource_id).strip()
        return resource_id or None

    @timed_phase("calendar_properties")
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

    @timed_phase("calendar_event_parse")
    def _event_summary(self, resource: Any, calendar: dict[str, Any]) -> dict[str, Any]:
        components = resource.get_icalendar_instance().walk("VEVENT")
        component = next(
            (component for component in components if "RECURRENCE-ID" not in component),
            components[0],
        )
        return self._component_summary(component, calendar)

    @timed_phase("calendar_recurrence_expand")
    def _event_occurrences(
        self,
        resource: Any,
        calendar: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        document = resource.get_icalendar_instance()
        recurring_uids = {
            self._component_text(component, "UID")
            for component in document.subcomponents
            if component.name == "VEVENT" and any(
                name in component for name in ("RRULE", "RDATE", "RECURRENCE-ID")
            )
        }
        # Floating times and DATE values use the configured calendar timezone.
        # Both bounds must use the same tzinfo for recurring-ical-events.
        zone = self._zone(None)
        occurrences = recurring_ical_events.of(document, keep_recurrence_attributes=True).between(
            start.astimezone(zone), end.astimezone(zone),
        )
        results = []
        for component in occurrences:
            if self._component_text(component, "STATUS") == "CANCELLED":
                continue
            identifier = component.get("RECURRENCE-ID")
            if identifier is not None and identifier.params.get("RANGE") == "THISANDFUTURE":
                # recurring-ical-events 3.8 copies the range anchor's RID to
                # every following occurrence. Recover each original slot from
                # the expanded DTSTART and the source exception's time shift.
                source = next((
                    source for source in document.subcomponents
                    if source.name == "VEVENT"
                    and self._component_text(source, "UID") == self._component_text(component, "UID")
                    and self._same_recurrence_id(self._component_datetime(source, "RECURRENCE-ID"), identifier.dt)
                ), None)
                if source is not None:
                    original_slot = self._shift_occurrence(
                        component["DTSTART"].dt, source["DTSTART"].dt, identifier.dt,
                    )
                    self._replace_component_value(component, "RECURRENCE-ID", original_slot)
            results.append(self._component_summary(
                component, calendar,
                is_recurring=self._component_text(component, "UID") in recurring_uids,
            ))
        return results

    def _component_summary(
        self, component: Any, calendar: dict[str, Any], *, is_recurring: bool | None = None,
    ) -> dict[str, Any]:
        start = self._component_datetime(component, "DTSTART")
        end = self._component_datetime(component, "DTEND")
        uid = self._component_text(component, "UID")
        if is_recurring is None:
            is_recurring = any(name in component for name in ("RRULE", "RDATE", "RECURRENCE-ID"))
        identifier = self._component_datetime(component, "RECURRENCE-ID") if is_recurring else None
        occurrence_id = (
            self._occurrence_id(calendar["id"], str(uid), identifier)
            if identifier is not None or not is_recurring else None
        )
        return {
            "uid": str(uid),
            "series_uid": str(uid) if is_recurring else None,
            "is_recurring": is_recurring,
            "recurrence_id": self._serialize_datetime(identifier),
            "occurrence_id": occurrence_id,
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
        # Implicit bounds represent whole days. Changing seconds on each
        # invocation otherwise defeats the exact-range SQLite cache.
        now = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0)
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
