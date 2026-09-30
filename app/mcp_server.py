from __future__ import annotations

import asyncio
import json
from functools import partial
from time import perf_counter
from typing import Any, Callable, Literal, TypeVar

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from app.icloud import ICloudCalendarService, ICloudServiceError
from app.imap import ICloudIMAPService, IMAPServiceError
from app.mcp_resources import AttachmentMCPServer
from app.reminders import GoRemindersService
from app.reminders_tools import register_reminders_tools
from app.search_clients import MailSearchError
from app.semantic_search import SemanticMailSearch
from app.timing import call_id, log_elapsed, measure_phase, tool_trace

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
    mail_search: SemanticMailSearch | None = None,
    reminders_service: GoRemindersService | None = None,
) -> MCPServer:
    server = AttachmentMCPServer(
        name="icloud-cruncher",
        title="iCloud Calendar, Mail & Reminders",
        description=(
            "Read and write iCloud Calendar and Mail through CalDAV/IMAP, and Reminders through the Go backend."
        ),
        instructions=(
            "Use list_calendars before selecting a calendar when the calendar is unknown. "
            "Use ISO 8601 timestamps for timed events and YYYY-MM-DD for all-day events. "
            "Write and delete operations change the user's iCloud data; summarize the "
            "planned change and obtain user approval before calling them. Draft tools "
            "upload messages to IMAP but never send them; the user sends drafts manually. "
            "Use list_reminder_lists and list_reminders to get exact IDs before Reminders operations. "
            "Native section headings are separate from reminders. Use list_reminder_sections for section IDs. "
            "Use view=tree for nested subtasks, move_reminder for indentation/sections and reorder_reminders for manual order. "
            "Use batch_update_reminders for a complete target tree with sections and subtasks: preview with dry_run=true, "
            "then apply the approved structure with dry_run=false. Include completed tasks; batches are not atomic. "
            "Priority numbers: 0=none, 9=low (!), 5=medium (!!), 1=high (!!!); ≡ is a manual drag handle, not priority. "
            "• means pending, ✓ complete and ↳ a subtask. These are display symbols, never title text. "
            "Never blindly retry a failed or timed-out Reminders write; inspect current data first. "
            "Reminders authentication and device approval are separate administrative Go CLI operations."
        ),
        version="1.1.0",
    )

    async def call_service(
        target: Any | None,
        operation: str,
        function: Callable[[], ResultT],
        missing_message: str,
    ) -> ResultT:
        with tool_trace(operation):
            started = perf_counter()
            logger.info("mcp_tool_start tool={} call_id={}", operation, call_id())
            if target is None:
                _log_tool_complete(operation, started, "not_configured")
                raise ToolError(missing_message)
            try:
                queued = perf_counter()

                def invoke():
                    log_elapsed("worker_queue", queued)
                    with measure_phase("service"):
                        return function()

                result = await asyncio.to_thread(invoke)
                _log_tool_complete(
                    operation,
                    started,
                    "ok",
                    result_count=_result_count(result),
                )
                return result
            except (ICloudServiceError, IMAPServiceError, MailSearchError, ValueError) as exc:
                _log_tool_complete(
                    operation,
                    started,
                    "validation_error",
                    error_type=exc.__class__.__name__,
                )
                raise ToolError(str(exc)) from None
            except Exception as exc:
                # Client exceptions can contain request details. Keep them out of
                # the MCP response and log only a stable exception class.
                logger.warning(
                    "mcp_tool_complete tool={} call_id={} outcome=error duration_ms={:.1f} error_type={}",
                    operation,
                    call_id(),
                    (perf_counter() - started) * 1000,
                    exc.__class__.__name__,
                )
                # The SDK logs unexpected exceptions with their entire chain.
                # An expected ToolError with no cause keeps private client details
                # out of both the response and the SDK's logs.
                raise ToolError("iCloud service request failed") from None

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
            call_id(),
            outcome,
            (perf_counter() - started) * 1000,
        ]
        message = "mcp_tool_complete tool={} call_id={} outcome={} duration_ms={:.1f}"
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
            "filters for a narrower range (end exclusive) and query for summary, description, or location text. "
            "Recurring events are expanded with their actual occurrence start/end, series_uid, "
            "occurrence_id and recurrence_id. Use that recurrence_id unchanged to delete one occurrence; "
            "it identifies the original slot even when an occurrence has moved."
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
            "Permanently delete one occurrence or an entire event/series from iCloud. "
            "scope is required: occurrence requires the exact recurrence_id from list_events; "
            "series deletes the entire event/series and must omit recurrence_id. "
            "A UID alone identifies the series. Never use scope=series for requests to delete only one day. "
            "This is destructive and requires confirm=true in addition to the client's approval flow."
        ),
        annotations=DELETE_ANNOTATIONS,
    )
    async def delete_event(
        calendar: str,
        uid: str,
        confirm: bool,
        scope: Literal["occurrence", "series"],
        recurrence_id: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise ValueError("delete_event requires confirm=true")
        return await call_service(
            service,
            "delete_event",
            partial(service.delete_event, calendar, uid, scope=scope, recurrence_id=recurrence_id) if service else lambda: {},
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
        name="semantic_search_emails",
        title="Search mail and attachments by meaning",
        description=(
            "Search the local SQLite mail snapshots by meaning, including extracted PDF/text "
            "attachments. The query is embedded with OpenAI; matching text excerpts come from "
            "the local Qdrant index. This covers cached mail only, not a live or complete IMAP "
            "search. Results include mailbox, uid, uid_validity, score, source and attachment_id. "
            "Use get_email/get_email_attachment to retrieve the current original; snapshots may "
            "be older than iCloud. source may be body or attachment. Scans need OCR and are skipped. "
            "The response includes indexing progress and omitted/truncated source counts."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    async def semantic_search_emails(
        query: str,
        mailbox: str | None = None,
        source: Literal["body", "attachment"] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return await call_service(
            mail_search, "semantic_search_emails",
            partial(mail_search.search if mail_search else lambda **_: {}, query=query, mailbox=mailbox, source=source, limit=limit),
            "Semantic mail search is not configured. Set MAIL_SEARCH_ENABLED=true and OPENAI_API_KEY, and start Qdrant.",
        )

    @server.tool(
        name="email_search_index_status",
        title="Check mail search index progress",
        description="Return local mail index counts, model, worker state and omitted/truncated counts without reading iCloud or calling OpenAI.",
        annotations=READ_ANNOTATIONS,
    )
    async def email_search_index_status() -> dict[str, Any]:
        if mail_search is None:
            return {"configured": False, "source": "sqlite_cached_emails"}
        return await call_service(mail_search, "email_search_index_status", mail_search.status, "Semantic mail search is not configured.")

    @server.tool(
        name="get_email",
        title="Read an iCloud Mail message",
        description=(
            "Read one email by its mailbox-local IMAP UID. The message is fetched with "
            "BODY.PEEK so reading it does not mark it read. Attachments include metadata and "
            "attachment_id; call get_email_attachment with that ID to retrieve the original "
            "file as a native MCP resource, or use format=text for PDF/text contents."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def get_email(
        uid: str,
        mailbox: str | None = None,
        max_body_chars: int = 20_000,
        expected_uid_validity: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            imap_service,
            "get_email",
            partial(
                imap_service.get_email if imap_service else lambda **_: {},
                mailbox=mailbox,
                uid=uid,
                max_body_chars=max_body_chars,
                **({"expected_uid_validity": expected_uid_validity} if expected_uid_validity is not None else {}),
            ),
            imap_missing,
        )

    @server.tool(
        name="get_email_attachment",
        title="Read an iCloud Mail attachment",
        description=(
            "Read an attachment using uid, mailbox and attachment_id from get_email. "
            "Default format=file returns the COMPLETE original attachment as an embedded "
            "binary MCP resource and resource link, with filename and MIME type (up to 10 MB). "
            "File mode requires offset=0 and ignores limit; resource links can be read through "
            "resources/read for up to 15 minutes, until capacity eviction or service restart. "
            "Use format=text to extract readable PDF/text content; scanned PDFs without "
            "embedded text need OCR. Use format=base64 for bounded original byte chunks. "
            "offset/limit count characters for text and decoded bytes for base64 "
            "(limit 1–100000). Follow next_offset while has_more=true; decode each base64 chunk "
            "separately before concatenating bytes. Reads use BODY.PEEK and never mark mail read."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def get_email_attachment(
        uid: str,
        attachment_id: str,
        mailbox: str | None = None,
        format: Literal["file", "text", "base64"] = "file",
        offset: int = 0,
        limit: int = 20_000,
        expected_uid_validity: str | None = None,
    ) -> CallToolResult:
        attachment = await call_service(
            imap_service,
            "get_email_attachment",
            partial(
                imap_service.get_email_attachment if imap_service else lambda **_: {},
                mailbox=mailbox,
                uid=uid,
                attachment_id=attachment_id,
                format=format,
                offset=offset,
                limit=limit,
                **({"expected_uid_validity": expected_uid_validity} if expected_uid_validity is not None else {}),
            ),
            imap_missing,
        )
        if format == "file":
            return server.attachment_result(attachment)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(attachment, ensure_ascii=False))],
            structured_content=attachment,
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

    register_reminders_tools(server, reminders_service)
    return server
