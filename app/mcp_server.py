from __future__ import annotations

import asyncio
from functools import partial
from time import perf_counter
from typing import Any, Callable, TypeVar

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from app.icloud import ICloudCalendarService, ICloudServiceError
from app.imap import ICloudIMAPService, IMAPServiceError

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


def create_mcp_server(
    service: ICloudCalendarService | None,
    imap_service: ICloudIMAPService | None = None,
) -> MCPServer:
    server = MCPServer(
        name="icloud-cruncher",
        title="iCloud Calendar & Mail",
        description=(
            "Read and write iCloud Calendar and iCloud Mail through CalDAV and IMAP."
        ),
        instructions=(
            "Use list_calendars before selecting a calendar when the calendar is unknown. "
            "Use ISO 8601 timestamps for timed events and YYYY-MM-DD for all-day events. "
            "Write and delete operations change the user's iCloud data; summarize the "
            "planned change and obtain user approval before calling them. Draft tools "
            "upload messages to IMAP but never send them; the user sends drafts manually."
        ),
        version="0.3.0",
    )

    async def call_service(
        target: Any | None,
        operation: str,
        function: Callable[[], ResultT],
        missing_message: str,
    ) -> ResultT:
        started = perf_counter()
        logger.info("mcp_tool_start tool={}", operation)
        if target is None:
            _log_tool_complete(operation, started, "not_configured")
            raise RuntimeError(missing_message)
        try:
            result = await asyncio.to_thread(function)
            _log_tool_complete(
                operation,
                started,
                "ok",
                result_count=_result_count(result),
            )
            return result
        except (ICloudServiceError, IMAPServiceError, ValueError) as exc:
            _log_tool_complete(
                operation,
                started,
                "validation_error",
                error_type=exc.__class__.__name__,
            )
            raise ValueError(str(exc)) from exc
        except Exception as exc:
            # Client exceptions can contain request details. Keep them out of
            # the MCP response and log only a stable exception class.
            logger.warning(
                "mcp_tool_complete tool={} outcome=error duration_ms={:.1f} error_type={}",
                operation,
                (perf_counter() - started) * 1000,
                exc.__class__.__name__,
            )
            raise RuntimeError("iCloud service request failed") from exc

    def _log_tool_complete(
        operation: str,
        started: float,
        outcome: str,
        *,
        result_count: int | None = None,
        error_type: str | None = None,
    ) -> None:
        fields: list[Any] = [
            operation,
            outcome,
            (perf_counter() - started) * 1000,
        ]
        message = "mcp_tool_complete tool={} outcome={} duration_ms={:.1f}"
        if result_count is not None:
            message += " result_count={}"
            fields.append(result_count)
        if error_type is not None:
            message += " error_type={}"
            fields.append(error_type)
        logger.info(message, *fields)

    def _result_count(result: Any) -> int | None:
        if isinstance(result, (list, tuple, set, dict)):
            return len(result)
        return None

    calendar_missing = "iCloud CalDAV is not configured. Set ICLOUD_USERNAME and ICLOUD_APP_PASSWORD."
    imap_missing = "iCloud IMAP is not configured. Set IMAP_USERNAME and IMAP_APP_PASSWORD."

    @server.tool(
        name="list_calendars",
        title="List iCloud calendars",
        description="List the iCloud calendars available to the configured Apple Account.",
        annotations=READ_ANNOTATIONS,
    )
    async def list_calendars() -> list[dict[str, Any]]:
        if service is None:
            logger.info("mcp_tool tool=list_calendars outcome=not_configured")
            return []
        return await call_service(service, "list_calendars", service.list_calendars, calendar_missing)

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
            logger.info("mcp_tool tool=list_events outcome=not_configured")
            return []
        return await call_service(
            service,
            "list_events",
            partial(
                service.list_events,
                calendar=calendar,
                start=start,
                end=end,
                query=query,
                limit=limit,
            ),
            calendar_missing,
        )

    @server.tool(
        name="get_event",
        title="Get an iCloud calendar event",
        description="Fetch one event by its UID from the selected iCloud calendar.",
        annotations=READ_ANNOTATIONS,
    )
    async def get_event(calendar: str, uid: str) -> dict[str, Any]:
        return await call_service(
            service,
            "get_event",
            partial(service.get_event, calendar, uid) if service else lambda: {},
            calendar_missing,
        )

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
        return await call_service(
            service,
            "create_event",
            partial(
                service.create_event if service else lambda **_: {},
                calendar=calendar,
                title=title,
                start=start,
                end=end,
                description=description,
                location=location,
                all_day=all_day,
                timezone_name=timezone_name,
            ),
            calendar_missing,
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
        return await call_service(
            service,
            "update_event",
            partial(
                service.update_event if service else lambda **_: {},
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
            calendar_missing,
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
        return await call_service(
            service,
            "delete_event",
            partial(service.delete_event, calendar, uid) if service else lambda: {},
            calendar_missing,
        )

    @server.tool(
        name="list_mailboxes",
        title="List iCloud Mail mailboxes",
        description="List IMAP mailboxes available in the configured iCloud Mail account.",
        annotations=READ_ANNOTATIONS,
    )
    async def list_mailboxes() -> list[dict[str, Any]]:
        return await call_service(
            imap_service,
            "list_mailboxes",
            imap_service.list_mailboxes if imap_service else lambda: [],
            imap_missing,
        )

    @server.tool(
        name="search_emails",
        title="Search iCloud Mail",
        description=(
            "Search iCloud Mail by sender, recipient, subject, text, ISO dates, or unread "
            "status. Results contain headers only; use get_email to read a message body."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def search_emails(
        mailbox: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
        subject: str | None = None,
        query: str | None = None,
        since: str | None = None,
        before: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await call_service(
            imap_service,
            "search_emails",
            partial(
                imap_service.search_emails if imap_service else lambda **_: [],
                mailbox=mailbox,
                from_address=from_address,
                to_address=to_address,
                subject=subject,
                query=query,
                since=since,
                before=before,
                unread_only=unread_only,
                limit=limit,
            ),
            imap_missing,
        )

    @server.tool(
        name="get_email",
        title="Read an iCloud Mail message",
        description=(
            "Read one email by its mailbox-local IMAP UID. The message is fetched with "
            "BODY.PEEK so reading it does not mark it read; attachments are represented by "
            "metadata and are not returned as raw binary data."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def get_email(
        uid: str,
        mailbox: str | None = None,
        max_body_chars: int = 20_000,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "get_email",
            partial(
                imap_service.get_email if imap_service else lambda **_: {},
                mailbox=mailbox,
                uid=uid,
                max_body_chars=max_body_chars,
            ),
            imap_missing,
        )

    @server.tool(
        name="create_draft",
        title="Create an iCloud Mail draft",
        description=(
            "Create a draft in the configured iCloud Mail Drafts mailbox. Supports plain text "
            "or HTML and optional base64-encoded attachments. The draft is uploaded but never "
            "sent; send it manually from a mail client."
        ),
        annotations=WRITE_ANNOTATIONS,
    )
    async def create_draft(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        mailbox: str | None = None,
        body_format: str = "plain",
        attachments: list[dict[str, str]] | None = None,
        from_address: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "create_draft",
            partial(
                imap_service.create_draft if imap_service else lambda **_: {},
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                mailbox=mailbox,
                body_format=body_format,
                attachments=attachments,
                from_address=from_address,
            ),
            imap_missing,
        )

    @server.tool(
        name="update_draft",
        title="Update an iCloud Mail draft",
        description=(
            "Replace an existing draft with new recipients, subject, body, and optional "
            "base64-encoded attachments. The old draft is marked deleted when safe. Nothing "
            "is sent; send the resulting draft manually from a mail client."
        ),
        annotations=WRITE_ANNOTATIONS,
    )
    async def update_draft(
        uid: str,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        mailbox: str | None = None,
        body_format: str = "plain",
        attachments: list[dict[str, str]] | None = None,
        from_address: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "update_draft",
            partial(
                imap_service.update_draft if imap_service else lambda **_: {},
                uid=uid,
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                mailbox=mailbox,
                body_format=body_format,
                attachments=attachments,
                from_address=from_address,
            ),
            imap_missing,
        )

    @server.tool(
        name="mark_email_read",
        title="Mark an iCloud Mail message read or unread",
        description="Change the Seen flag of one email. This changes external mail state.",
        annotations=WRITE_ANNOTATIONS,
    )
    async def mark_email_read(
        uid: str,
        read: bool = True,
        mailbox: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "mark_email_read",
            partial(
                imap_service.mark_email_read if imap_service else lambda **_: {},
                mailbox=mailbox,
                uid=uid,
                read=read,
            ),
            imap_missing,
        )

    @server.tool(
        name="move_email",
        title="Move an iCloud Mail message",
        description=(
            "Copy an email to another mailbox and mark the source for deletion. This changes "
            "external mail state and requires client approval."
        ),
        annotations=WRITE_ANNOTATIONS,
    )
    async def move_email(
        uid: str,
        destination_mailbox: str,
        source_mailbox: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "move_email",
            partial(
                imap_service.move_email if imap_service else lambda **_: {},
                source_mailbox=source_mailbox,
                destination_mailbox=destination_mailbox,
                uid=uid,
            ),
            imap_missing,
        )

    @server.tool(
        name="delete_email",
        title="Delete an iCloud Mail message",
        description=(
            "Delete one email by marking it Deleted and expunging it when safe. This is "
            "destructive and requires confirm=true in addition to the client's approval flow."
        ),
        annotations=DELETE_ANNOTATIONS,
    )
    async def delete_email(
        uid: str,
        confirm: bool,
        mailbox: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise ValueError("delete_email requires confirm=true")
        return await call_service(
            imap_service,
            "delete_email",
            partial(
                imap_service.delete_email if imap_service else lambda **_: {},
                mailbox=mailbox,
                uid=uid,
            ),
            imap_missing,
        )

    return server
