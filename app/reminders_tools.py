"""Fixed, typed Reminders tools on the common Python MCP endpoint."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, Literal

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ToolAnnotations

from app.reminders import GoRemindersService, RemindersError
from app.timing import call_id, tool_trace


def register_reminders_tools(server: MCPServer, service: GoRemindersService | None) -> None:
    def annotations(read: bool, destructive: bool = False, idempotent: bool = True) -> ToolAnnotations:
        return ToolAnnotations(readOnlyHint=read, destructiveHint=destructive, idempotentHint=idempotent, openWorldHint=False)

    async def call(name: str, **arguments: Any) -> CallToolResult:
        with tool_trace(name):
            started = perf_counter()
            outcome = "cancelled"
            count = None
            logger.info("mcp_tool_start tool={} call_id={}", name, call_id())
            try:
                if name == "delete_reminder" and arguments.get("confirm") is not True:
                    outcome = "invalid_argument"
                    raise ToolError("delete_reminder requires confirm=true")
                if service is None:
                    outcome = "not_configured"
                    raise ToolError("Reminders is not configured. Set REMINDERS_MCP_URL to the Go backend's private MCP endpoint.")
                result = await service.call_tool(name, {key: value for key, value in arguments.items() if value is not None})
                outcome = "ok"
                payload = result.structured_content
                if isinstance(payload, dict):
                    for key in ("reminders", "lists"):
                        if isinstance(payload.get(key), list):
                            count = len(payload[key])
                            break
                    else:
                        count = 1
                return result
            except RemindersError as error:
                outcome = error.code
                raise ToolError(str(error)) from None
            except (ToolError, asyncio.CancelledError):
                raise
            except Exception:
                outcome = "backend_unavailable"
                raise ToolError(str(RemindersError(outcome))) from None
            finally:
                logger.info(
                    "mcp_tool_complete tool={} call_id={} outcome={} duration_ms={:.1f} result_count={}",
                    name, call_id(), outcome, (perf_counter() - started) * 1000, count,
                )

    @server.tool(annotations=annotations(True), description="List iCloud Reminders lists and their exact IDs.")
    async def list_reminder_lists() -> CallToolResult:
        return await call("list_reminder_lists")

    @server.tool(annotations=annotations(True), description=(
        "List current reminders, optionally filtering by exact list_id or parent_id, title query, "
        "and completion. Pagination uses limit (1..500) and offset; due dates use YYYY-MM-DD."
    ))
    async def list_reminders(
        list_id: str | None = None, parent_id: str | None = None, query: str | None = None,
        include_completed: bool = False, limit: int = 100, offset: int = 0,
    ) -> CallToolResult:
        return await call("list_reminders", list_id=list_id, parent_id=parent_id, query=query,
                          include_completed=include_completed, limit=limit, offset=offset)

    @server.tool(annotations=annotations(True), description="Read one reminder by its exact ID, including notes and list/parent references.")
    async def get_reminder(id: str) -> CallToolResult:
        return await call("get_reminder", id=id)

    @server.tool(annotations=annotations(False, idempotent=False), description=(
        "Create a reminder in an existing list using its exact list_id; optionally set a parent_id "
        "in the same list, a due date (YYYY-MM-DD), notes and priority. Never automatically retry an uncertain write."
    ))
    async def create_reminder(
        title: str, list_id: str, due: str | None = None,
        priority: Literal["none", "low", "medium", "high"] | None = None,
        notes: str | None = None, parent_id: str | None = None,
    ) -> CallToolResult:
        return await call("create_reminder", title=title, list_id=list_id, due=due,
                          priority=priority, notes=notes, parent_id=parent_id)

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
