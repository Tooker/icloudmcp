"""Asynchronous MCP client for the standalone Go Reminders service."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import Any

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, TextContent

from app.config import RemindersConfig
from app.timing import measure_phase


REMINDER_TOOLS = frozenset({
    "list_reminder_lists", "list_reminders", "get_reminder", "create_reminder",
    "update_reminder", "complete_reminder", "delete_reminder", "sync_reminders",
    "list_reminder_participants", "assign_reminder",
})

_PUBLIC_ERRORS = {
    "not_found": "Reminder or list not found. Refresh the available lists and reminders and use their exact IDs.",
    "not_shared": "Only reminders in a shared list can be assigned to a participant.",
    "permission_denied": "The current participant cannot modify this shared list.",
    "auth_required": "Stop the Go backend, run reminders auth with its data directory, then start it again.",
    "icloud_access_denied": (
        "Enable iCloud web data access, stop the Go backend, run reminders auth --approve-web-access "
        "with its data directory and approve on a trusted device, then start it again."
    ),
    "invalid_argument": "Reminders rejected the arguments. Check exact IDs, dates, priority and pagination; assignment needs one accepted participant ID from this list or clear=true.",
    "request_timeout": "Request ended before completion. A write may have succeeded; inspect the reminder before retrying.",
    "icloud_request_failed": "iCloud request failed. A write may have succeeded; inspect the reminder before retrying.",
    "backend_unavailable": "The Go Reminders backend could not complete the request. Check its service and bearer token. A write may have succeeded; inspect before retrying.",
}


class RemindersError(Exception):
    """Only application-owned messages cross the public MCP boundary."""

    def __init__(self, code: str) -> None:
        self.code = code if code in _PUBLIC_ERRORS else "backend_unavailable"
        super().__init__(f"{self.code}: {_PUBLIC_ERRORS[self.code]}")


_transport_active: ContextVar[bool] = ContextVar("reminders_transport_active", default=False)


class _TransportLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK debug/error logs can contain request bodies, URLs and exception
        # chains. The bridge emits its own correlated, content-free timings.
        return not _transport_active.get()


_transport_filter = _TransportLogFilter()


@contextmanager
def quiet_transport_logs():
    for name, item in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(item, logging.Logger) and name.startswith(("mcp.client", "mcp.shared", "httpx2", "httpcore")):
            if _transport_filter not in item.filters:
                item.addFilter(_transport_filter)
    token = _transport_active.set(True)
    try:
        yield
    finally:
        _transport_active.reset(token)


def _contains_timeout(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(_contains_timeout(item) for item in error.exceptions)
    return False


class GoRemindersService:
    def __init__(self, config: RemindersConfig) -> None:
        self.config = config

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name not in REMINDER_TOOLS:
            raise RemindersError("invalid_argument")
        headers = {"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}
        try:
            # A fresh MCP session per call survives backend restarts and avoids
            # sharing AnyIO task groups across incoming request tasks. Go is
            # stateless; neither a startup connection nor write retries are needed.
            with quiet_transport_logs():
                async with asyncio.timeout(self.config.timeout_seconds):
                    async with httpx2.AsyncClient(
                        headers=headers,
                        timeout=httpx2.Timeout(10, read=self.config.timeout_seconds),
                        trust_env=False,
                    ) as http_client:
                        async with streamable_http_client(
                            self.config.mcp_url, http_client=http_client, terminate_on_close=False,
                        ) as (read_stream, write_stream):
                            async with ClientSession(
                                read_stream, write_stream,
                                read_timeout_seconds=self.config.timeout_seconds,
                            ) as session:
                                with measure_phase("reminders_mcp_connect"):
                                    await session.initialize()
                                with measure_phase("reminders_mcp_call"):
                                    result = await session.call_tool(name, arguments)
        except Exception as error:
            raise RemindersError("request_timeout" if _contains_timeout(error) else "backend_unavailable") from None
        if not isinstance(result, CallToolResult):
            raise RemindersError("backend_unavailable")
        if result.is_error:
            # Do not trust upstream text, even for a familiar error prefix.
            code = next((
                content.text.split(":", 1)[0].strip()
                for content in result.content if isinstance(content, TextContent)
            ), "backend_unavailable")
            raise RemindersError(code)
        return result
