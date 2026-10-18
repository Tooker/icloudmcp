from __future__ import annotations

import asyncio
import imaplib
import json
from functools import partial
from time import perf_counter
from typing import Any, Callable, Literal, TypeVar

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from app.icloud import ICloudCalendarService, ICloudServiceError, CalendarNotFoundError, EventNotFoundError
from app.contacts import ICloudContactsService
from app.contacts_tools import register_contacts_tools
from app.drive_client import DriveBackendClient
from app.drive_tools import register_drive_tools
from app.imap import ICloudIMAPService, IMAPServiceError, MailboxNotFoundError, EmailNotFoundError, AttachmentNotFoundError
from app.mcp_errors import ToolFailure
from app.mail_schemas import DraftAttachment
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
REPLACE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False,
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
    contacts_service: ICloudContactsService | None = None,
    drive_service: DriveBackendClient | None = None,
) -> MCPServer:
    server = AttachmentMCPServer(
        name="icloud-cruncher",
        title="iCloud Calendar, Mail, Contacts, Drive & Reminders",
        description=(
            "Read and write iCloud Calendar, Mail and Contacts through CalDAV/IMAP/CardDAV, and Drive/Reminders through private backends."
        ),
        instructions=(
            "Use list_calendars before selecting a calendar when the calendar is unknown. "
            "Use ISO 8601 timestamps for timed events and YYYY-MM-DD for all-day events. "
            "Write and delete operations change the user's iCloud data; summarize the "
            "planned change and obtain user approval before calling them. Draft tools "
            "upload messages to IMAP but never send them; the user sends drafts manually. "
            "Before mail writes use mail_account_info and list_mailboxes; select an exact existing mailbox, "
            "prefer its native Drafts special-use flag. Folder names do not prove the provider. "
            "Draft body_format accepts only plain or html, never text. Never infer a sender name from a signature; "
            "report only returned From header fields. A configured username is not verified send-as authorization. "
            "After a failed draft write inspect the mailbox before retrying; creation/replacement may have partially succeeded. "
            "Use list_addressbooks and exact account-scoped IDs for Contacts. Contacts creation never merges duplicates. "
            "Never blindly retry a failed or timed-out create_contact: preserve write_status, contact_id and UID, "
            "and inspect get_contact first. A succeeded status remains confirmed if readback fails. "
            "Contacts IDs do not identify Reminders participants. "
            "Tools are grouped by Calendar, Mail, Contacts, Drive and Reminders through titles and service metadata; tool names remain stable. "
            "Start Drive with drive_status and list_drive_items; use issued opaque IDs. "
            "Drive uploads reject existing names. replace_drive_file requires confirm=true and the expected version; it stages verified bytes, "
            "moves the original to Trash and returns a new ID. It is non-atomic. Preserve all write state and never retry uncertain Drive writes. "
            "Drive authentication/ADP approval happen only through the administrative CLI. Check search coverage. "
            "Use the returned download version on subsequent Drive file chunks; discard chunks on version_changed. "
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
        version="1.4.0",
    )
    contact_offset_max = getattr(getattr(contacts_service, "config", None), "max_contacts", 5000)
    server.numeric_bound_overrides = {
        (tool, "offset"): {"ge": 0, "le": contact_offset_max}
        for tool in ("list_contacts", "search_contacts")
    }

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
                raise ToolFailure("not_configured", message=missing_message, details={"write_status": "not_sent"})
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
                details = getattr(exc, "details", {})
                code = getattr(exc, "code", None)
                if code is None:
                    code = "mailbox_unavailable" if isinstance(exc, MailboxNotFoundError) else "not_found" if isinstance(exc, (CalendarNotFoundError, EventNotFoundError, EmailNotFoundError, AttachmentNotFoundError)) else "invalid_argument" if isinstance(exc, ValueError) else "service_error"
                raise ToolFailure(code, details=details, phase=details.get("phase", "service")) from None
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
                code = "timeout" if isinstance(exc, TimeoutError) else "protocol_error" if isinstance(exc, imaplib.IMAP4.error) else "backend_unavailable"
                raise ToolFailure(code) from None

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
        return await call_service(service, "list_calendars", service.list_calendars if service else lambda: [], calendar_missing)

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
        return await call_service(
            service,
            "list_events",
            partial(
                service.list_events if service else lambda **_: [],
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
            raise ToolFailure("confirmation_required", phase="input_validation", details={"write_status": "not_sent"})
        return await call_service(
            service,
            "delete_event",
            partial(service.delete_event, calendar, uid, scope=scope, recurrence_id=recurrence_id) if service else lambda: {},
            calendar_missing,
        )

    @server.tool(
        name="list_mailboxes",
        title="List mailboxes in the connected account",
        description=(
            "List exact available IMAP mailbox names, delimiter and native flags in the connected account. "
            "Prefer a folder marked with the Drafts special-use flag for drafts. If no such flag exists, "
            "select a verified folder name; never assume Drafts exists. Folder labels such as Gmail do not "
            "prove the provider or sender identity; inspect mail_account_info for the configured endpoint."
        ),
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
        title="Search the connected mail account",
        description=(
            "Search the connected IMAP account by sender, recipient, subject, text, ISO dates, or unread "
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
            "be older than the live mailbox. source may be body or attachment. Scans need OCR and are skipped. "
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
        title="Read a message from the connected mail account",
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
        title="Read an attachment from the connected mail account",
        description=(
            "Read an attachment using uid, mailbox and attachment_id from get_email. "
            "Default format=file returns the COMPLETE original attachment as an embedded "
            "binary MCP resource and resource link, with filename and MIME type (up to 30 MB). "
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
        name="mail_account_info",
        title="Inspect configured mail account",
        description=(
            "Read the configured IMAP endpoint, account, default mailbox, configured draft folder and default From header. "
            "No network request is made; configured folder names do not prove that those folders exist. "
            "Use list_mailboxes to discover exact available folders and native special-use flags before draft writes. "
            "An IMAP mirror may expose folders from another provider: neither folder names nor the From address prove the upstream provider. "
            "Credentials are never returned. This service stores drafts but cannot send mail or verify send-as permissions."
        ),
        annotations=READ_ANNOTATIONS,
    )
    async def mail_account_info() -> dict[str, Any]:
        return await call_service(
            imap_service, "mail_account_info",
            imap_service.account_info if imap_service else lambda: {}, imap_missing,
        )

    @server.tool(
        name="create_draft",
        title="Create a draft in the connected mail account",
        description=(
            "Create a draft in the connected IMAP account. First inspect mail_account_info and list_mailboxes, "
            "then pass the exact existing draft mailbox name, preferably marked with the native Drafts special-use flag. "
            "body_format is exactly plain or html (not text). Optional attachments are structured base64 objects. "
            "The returned from_header/from_address/from_name describe the MIME header actually submitted; body signatures "
            "do not set sender identity, and send-as authorization is not verified. Never claim a provider based on folder names. "
            "Nothing is sent. A failure after submission can leave a draft behind: inspect the mailbox before any retry."
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
        body_format: Literal["plain", "html"] = "plain",
        attachments: list[DraftAttachment] | None = None,
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
                attachments=[item.model_dump() for item in attachments] if attachments is not None else None,
                from_address=from_address,
            ),
            imap_missing,
        )

    @server.tool(
        name="update_draft",
        title="Replace a draft in the connected mail account",
        description=(
            "Replace an existing draft with new recipients, subject, body, and optional "
            "base64-encoded attachments. The old draft is marked deleted when safe. Nothing "
            "is sent; send the resulting draft manually from a mail client. This is a complete replacement, "
            "not a partial patch: supply all recipients, subject, body and desired attachments. First discover "
            "the exact mailbox and UID with list_mailboxes/search_emails/get_email. body_format accepts plain or html. "
            "An append may succeed before deleting the old draft fails; never blindly retry. Inspect the mailbox first. "
            "Returned From fields describe the submitted MIME header; body signatures do not set the sender name."
        ),
        annotations=REPLACE_ANNOTATIONS,
    )
    async def update_draft(
        uid: str,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        mailbox: str | None = None,
        body_format: Literal["plain", "html"] = "plain",
        attachments: list[DraftAttachment] | None = None,
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
                attachments=[item.model_dump() for item in attachments] if attachments is not None else None,
                from_address=from_address,
            ),
            imap_missing,
        )

    @server.tool(
        name="mark_email_read",
        title="Mark a message read or unread",
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
        title="Move a message in the connected mail account",
        description=(
            "Copy an email to another mailbox and mark the source for deletion. This changes "
            "external mail state and requires client approval."
        ),
        annotations=REPLACE_ANNOTATIONS,
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
        title="Delete a message from the connected mail account",
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
            raise ToolFailure("confirmation_required", phase="input_validation", details={"write_status": "not_sent"})
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
    register_contacts_tools(server, contacts_service)
    register_drive_tools(server, drive_service)
    return server
