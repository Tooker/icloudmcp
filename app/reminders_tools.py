"""Fixed, typed Reminders tools on the common Python MCP endpoint."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, Literal

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ToolAnnotations

from app.reminders import GoRemindersService, READ_TOOLS, RemindersError
from app.timing import call_id, tool_trace


def register_reminders_tools(server: MCPServer, service: GoRemindersService | None) -> None:
    def annotations(read: bool, destructive: bool = False, idempotent: bool = True) -> ToolAnnotations:
        return ToolAnnotations(readOnlyHint=read, destructiveHint=destructive, idempotentHint=idempotent, openWorldHint=False)

    async def call(name: str, **arguments: Any) -> CallToolResult:
        with tool_trace(name):
            started = perf_counter()
            outcome = "cancelled"
            count = None
            diagnostic = None
            logger.info("mcp_tool_start tool={} call_id={}", name, call_id())
            try:
                if name == "delete_reminder" and arguments.get("confirm") is not True:
                    outcome = "invalid_argument"
                    raise RemindersError("invalid_argument", operation=name, request_id=call_id(),
                                         write_status="not_sent")
                if name == "assign_reminder" and bool(arguments.get("participant_id")) == arguments.get("clear", False):
                    outcome = "invalid_argument"
                    raise RemindersError("invalid_argument", operation=name, request_id=call_id(),
                                         write_status="not_sent")
                if name == "move_reminder" and any((
                    bool(arguments.get("parent_id")) and arguments.get("clear_parent", False),
                    bool(arguments.get("section_id")) and arguments.get("clear_section", False),
                    bool(arguments.get("before_id")) and bool(arguments.get("after_id")),
                )):
                    outcome = "invalid_argument"
                    raise RemindersError("invalid_argument", operation=name, request_id=call_id(),
                                         write_status="not_sent")
                if service is None:
                    outcome = "not_configured"
                    raise RemindersError("not_configured", operation=name, request_id=call_id(),
                                         write_status="not_sent" if name not in READ_TOOLS else None)
                result = await service.call_tool(name, {key: value for key, value in arguments.items() if value is not None})
                outcome = "ok"
                payload = result.structured_content
                if isinstance(payload, dict):
                    for key in ("reminders", "lists", "participants", "sections"):
                        if isinstance(payload.get(key), list):
                            count = len(payload[key])
                            break
                    else:
                        count = 1
                return result
            except RemindersError as error:
                outcome = error.code
                diagnostic = error.details
                return error.as_result()
            except (ToolError, asyncio.CancelledError):
                raise
            except Exception:
                outcome = "backend_unavailable"
                error = RemindersError(outcome, operation=name, request_id=call_id(),
                                       write_status="unknown" if name not in READ_TOOLS else None,
                                       retry_class="retryable_after_read" if name not in READ_TOOLS else "retryable_safe")
                diagnostic = error.details
                return error.as_result()
            finally:
                logger.info(
                    "mcp_tool_complete tool={} call_id={} outcome={} duration_ms={:.1f} result_count={} "
                    "write_status={} retry_class={} http_status={} upstream_status={}",
                    name, call_id(), outcome, (perf_counter() - started) * 1000, count,
                    (diagnostic or {}).get("write_status"), (diagnostic or {}).get("retry_class"),
                    (diagnostic or {}).get("http_status"), (diagnostic or {}).get("upstream_status"),
                )

    @server.tool(annotations=annotations(True), description="List iCloud Reminders lists and their exact IDs.")
    async def list_reminder_lists() -> CallToolResult:
        return await call("list_reminder_lists")

    @server.tool(annotations=annotations(True), description=(
        "List current reminders, optionally filtering by exact list_id or parent_id, title query, "
        "section and completion. view=tree adds nested subtasks for the returned page; parent_ref is the "
        "authoritative parent even when filtered out. Manual list order is preserved; pagination uses "
        "limit (1..500) and offset. Priority: 0=none, 9=low (!), 5=medium (!!), 1=high (!!!). "
        "A drag handle (≡) changes manual order, not priority. •=pending, ✓=complete, ↳=subtask. "
        "Use move_reminder or reorder_reminders with exact IDs to arrange tasks; never add these symbols to titles."
    ))
    async def list_reminders(
        list_id: str | None = None, parent_id: str | None = None, query: str | None = None,
        include_completed: bool = False, limit: int = 100, offset: int = 0,
        section_id: str | None = None, view: Literal["flat", "tree"] = "flat",
    ) -> CallToolResult:
        return await call("list_reminders", list_id=list_id, parent_id=parent_id, query=query,
                          include_completed=include_completed, limit=limit, offset=offset, section_id=section_id,
                          view=None if view == "flat" else view)

    @server.tool(annotations=annotations(True), description="Read one reminder by its exact ID, including notes and list/parent references.")
    async def get_reminder(id: str) -> CallToolResult:
        return await call("get_reminder", id=id)

    @server.tool(annotations=annotations(False, idempotent=False), description=(
        "Create a reminder in an existing list using its exact list_id; optionally set a parent_id "
        "in the same list, a section_id from list_reminder_sections, a due date (YYYY-MM-DD), notes and priority. "
        "Subtasks inherit their parent's section. Optionally supply a UUID client_request_id for durable "
        "idempotency on an upgraded backend; recover an uncertain creation with the same ID and identical arguments. "
        "An older backend rejects keyed requests before writing. Never blindly retry an unkeyed uncertain write."
    ))
    async def create_reminder(
        title: str, list_id: str, due: str | None = None,
        priority: Literal["none", "low", "medium", "high"] | None = None,
        notes: str | None = None, parent_id: str | None = None, section_id: str | None = None,
        client_request_id: str | None = None,
    ) -> CallToolResult:
        return await call("create_reminder", title=title, list_id=list_id, due=due,
                          priority=priority, notes=notes, parent_id=parent_id, section_id=section_id,
                          client_request_id=client_request_id)

    @server.tool(annotations=annotations(False, destructive=True), description=(
        "Update specified nonempty reminder fields by exact ID. priority=none clears priority. "
        "Clearing notes or due dates is unsupported. Inspect an uncertain write before retrying."
    ))
    async def update_reminder(
        id: str, title: str | None = None, due: str | None = None,
        priority: Literal["none", "low", "medium", "high"] | None = None,
        notes: str | None = None,
    ) -> CallToolResult:
        return await call("update_reminder", id=id, title=title, due=due, priority=priority, notes=notes)

    @server.tool(annotations=annotations(False), description="Mark a reminder complete by exact ID; an already completed reminder is unchanged.")
    async def complete_reminder(id: str) -> CallToolResult:
        return await call("complete_reminder", id=id)

    @server.tool(annotations=annotations(False, destructive=True, idempotent=False), description=(
        "Permanently delete a reminder by exact ID. Requires explicit confirm=true and the user's approval."
    ))
    async def delete_reminder(id: str, confirm: bool) -> CallToolResult:
        return await call("delete_reminder", id=id, confirm=confirm)

    @server.tool(annotations=annotations(True), description=(
        "Refresh the Go Reminders cache; full=true performs a full sync, which can take several minutes. "
        "This does not change iCloud data."
    ))
    async def sync_reminders(full: bool = False) -> CallToolResult:
        return await call("sync_reminders", full=full)

    @server.tool(annotations=annotations(True), description=(
        "List accepted participants of one shared Reminders list, including exact IDs, names and "
        "permissions. Obtain list_id from list_reminder_lists. Private lists return shared=false."
    ))
    async def list_reminder_participants(list_id: str) -> CallToolResult:
        return await call("list_reminder_participants", list_id=list_id)

    @server.tool(annotations=annotations(False, destructive=True), description=(
        "Assign a reminder to an accepted participant of its shared list. Use an exact participant_id "
        "from list_reminder_participants. To remove the assignment, set clear=true and omit participant_id. "
        "This changes iCloud data; inspect an uncertain write before retrying."
    ))
    async def assign_reminder(id: str, participant_id: str | None = None, clear: bool = False) -> CallToolResult:
        return await call("assign_reminder", id=id, participant_id=participant_id, clear=clear)

    @server.tool(annotations=annotations(True), description=(
        "List native Apple Reminders sections in one exact list_id, in their section order. "
        "Use the returned section IDs for creation, moving and filtering; section headings are not reminders."
    ))
    async def list_reminder_sections(list_id: str) -> CallToolResult:
        return await call("list_reminder_sections", list_id=list_id)

    @server.tool(annotations=annotations(False, idempotent=False), description=(
        "Create a native section heading in an existing Reminders list. Use its exact list_id. "
        "Returns an exact section ID. Never automatically retry an uncertain creation."
    ))
    async def create_reminder_section(list_id: str, title: str) -> CallToolResult:
        return await call("create_reminder_section", list_id=list_id, title=title)

    @server.tool(annotations=annotations(False, destructive=True), description=(
        "Arrange an existing reminder within its current list. Set parent_id to indent under another reminder, "
        "or clear_parent=true to make it top-level. Set section_id to move into a native section, or "
        "clear_section=true to move out; subtasks inherit the parent's section. Omitted parent/section stays unchanged. "
        "Use exactly one before_id or after_id to place beside a sibling; without an anchor append to the target "
        "sibling group. The reminder's subtree stays together. IDs must come from the same list; cycles are rejected. "
        "Inspect uncertain writes before retrying."
    ))
    async def move_reminder(
        id: str, parent_id: str | None = None, clear_parent: bool = False,
        section_id: str | None = None, clear_section: bool = False,
        before_id: str | None = None, after_id: str | None = None,
    ) -> CallToolResult:
        return await call("move_reminder", id=id, parent_id=parent_id, clear_parent=clear_parent,
                          section_id=section_id, clear_section=clear_section, before_id=before_id, after_id=after_id)

    @server.tool(annotations=annotations(False, destructive=True), description=(
        "Set the manual order of all siblings in one list, parent or section using reminder_ids in the desired "
        "order. Supply every sibling exactly once, including completed reminders (discover with include_completed=true). "
        "Omit parent_id for top-level reminders; omit section_id for the unsectioned group. "
        "Each subtree stays together. This changes manual order only; priority and completion stay unchanged. "
        "Inspect uncertain writes before retrying."
    ))
    async def reorder_reminders(
        list_id: str, reminder_ids: list[str], parent_id: str | None = None, section_id: str | None = None,
    ) -> CallToolResult:
        return await call("reorder_reminders", list_id=list_id, reminder_ids=reminder_ids,
                          parent_id=parent_id, section_id=section_id)
