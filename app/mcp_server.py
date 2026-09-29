from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Callable, TypeVar

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from app.icloud import ICloudCalendarService, ICloudServiceError

ResultT = TypeVar("ResultT")

READ_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
DELETE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


def create_mcp_server(service: ICloudCalendarService | None) -> MCPServer:
    server = MCPServer(
        name="icloud-cruncher",
        title="iCloud Calendar",
        description="Read and write iCloud Calendar events through CalDAV.",
        instructions=(
            "Use list_calendars before selecting a calendar when the calendar is unknown. "
            "Use ISO 8601 timestamps for timed events and YYYY-MM-DD for all-day events. "
            "Write and delete operations change the user's iCloud data; summarize the "
            "planned change and obtain user approval before calling them."
        ),
        version="0.2.0",
    )

    async def call_service(
        operation: str,
        function: Callable[[], ResultT],
    ) -> ResultT:
        if service is None:
            raise RuntimeError(
                "iCloud is not configured. Set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD."
            )
        try:
            return await asyncio.to_thread(function)
        except (ICloudServiceError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        except Exception as exc:
            # CalDAV exceptions can contain request details. Keep them out of
            # the MCP response and log only a stable exception class.
            logger.warning(
                "mcp_icloud_failed operation={} error_type={}",
                operation,
                exc.__class__.__name__,
            )
            raise RuntimeError("iCloud request failed") from exc

    @server.tool(
        name="list_calendars",
        title="List iCloud calendars",
        description="List the iCloud calendars available to the configured Apple Account.",
        annotations=READ_ANNOTATIONS,
    )
    async def list_calendars() -> list[dict[str, Any]]:
        return await call_service("list_calendars", service.list_calendars if service else lambda: [])

    @server.tool(
        name="list_events",
        title="List iCloud calendar events",
        description=(
            "List events in one calendar or across all calendars. By default, return events "
            "from 30 days in the past through 365 days in the future. Use ISO 8601 start/end "
            "filters for a narrower range and query for summary, description, or location text."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def list_events(
        calendar: str | None = None,
        start: str | None = None,
        end: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if service is None:
            return await call_service("list_events", lambda: [])
        return await call_service(
            "list_events",
            partial(
                service.list_events,
                calendar=calendar,
                start=start,
                end=end,
                query=query,
                limit=limit,
            ),
        )

    @server.tool(
        name="get_event",
        title="Get an iCloud calendar event",
        description="Fetch one event by its UID from the selected iCloud calendar.",
        annotations=READ_ANNOTATIONS,
    )
    async def get_event(calendar: str, uid: str) -> dict[str, Any]:
        if service is None:
            return await call_service("get_event", lambda: {})
        return await call_service("get_event", partial(service.get_event, calendar, uid))

    @server.tool(
        name="create_event",
        title="Create an iCloud calendar event",
        description=(
            "Create a VEVENT in iCloud. This changes external state. For timed events use "
            "ISO 8601 timestamps; for all-day events set all_day=true and use YYYY-MM-DD. "
            "If calendar is omitted, the configured default is used or the account must have "
            "exactly one calendar."
        ),
        annotations=WRITE_ANNOTATIONS,
    )
    async def create_event(
        title: str,
        start: str,
        end: str,
        calendar: str | None = None,
        description: str | None = None,
        location: str | None = None,
        all_day: bool = False,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        if service is None:
            return await call_service("create_event", lambda: {})
        return await call_service(
            "create_event",
            partial(
                service.create_event,
                calendar=calendar,
                title=title,
                start=start,
                end=end,
                description=description,
                location=location,
                all_day=all_day,
                timezone_name=timezone_name,
            ),
        )

    @server.tool(
        name="update_event",
        title="Update an iCloud calendar event",
        description=(
            "Update only the supplied fields of an existing event. This changes external state. "
            "Pass description or location as an empty string to clear it; start and end must be "
            "supplied together."
        ),
        annotations=WRITE_ANNOTATIONS,
    )
    async def update_event(
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
        if service is None:
            return await call_service("update_event", lambda: {})
        return await call_service(
            "update_event",
            partial(
                service.update_event,
                calendar=calendar,
                uid=uid,
                title=title,
                start=start,
                end=end,
                description=description,
                location=location,
                all_day=all_day,
                timezone_name=timezone_name,
            ),
        )

    @server.tool(
        name="delete_event",
        title="Delete an iCloud calendar event",
        description=(
            "Permanently delete an event from iCloud. This is destructive and requires "
            "confirm=true in addition to the client's approval flow."
        ),
        annotations=DELETE_ANNOTATIONS,
    )
    async def delete_event(calendar: str, uid: str, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise ValueError("delete_event requires confirm=true")
        if service is None:
            return await call_service("delete_event", lambda: {})
        return await call_service("delete_event", partial(service.delete_event, calendar, uid))

    return server
