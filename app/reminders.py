"""Asynchronous MCP client for the standalone Go Reminders service."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import re
from typing import Any
from uuid import UUID, uuid4

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, PaginatedRequestParams, TextContent, Tool

from app.config import RemindersConfig
from app.timing import call_id, measure_phase


REMINDER_TOOLS = frozenset({
    "list_reminder_lists", "list_reminders", "get_reminder", "create_reminder",
    "update_reminder", "complete_reminder", "delete_reminder", "sync_reminders",
    "list_reminder_participants", "assign_reminder",
    "list_reminder_sections", "create_reminder_section", "move_reminder", "reorder_reminders",
    "batch_update_reminders",
})

_PUBLIC_ERRORS = {
    "not_configured": "Reminders is not configured. Set REMINDERS_MCP_URL to the Go backend's private MCP endpoint.",
    "backend_auth_failed": "The Go backend rejected authentication. Check REMINDERS_MCP_TOKEN on both services.",
    "backend_protocol_error": "The Go backend returned an invalid MCP response.",
    "idempotency_conflict": "This client_request_id was already used with different creation arguments. Use the original arguments or a new ID.",
    "local_state_failed": "The write succeeded but local state could not be saved. Inspect current data; recover a keyed creation using the same client_request_id.",
    "unsupported_backend": "This Go backend does not support client_request_id. Upgrade it before making a keyed creation.",
    "backend_upgrade_required": "The Go backend lacks tools required for this structure. Upgrade it before applying the batch. No write was attempted.",
    "not_found": "Reminder, list or section not found. Refresh the available lists and reminders and use their exact IDs.",
    "not_shared": "Only reminders in a shared list can be assigned to a participant.",
    "permission_denied": "The current participant cannot modify this shared list.",
    "auth_required": "Stop the Go backend, run reminders auth with its data directory, then start it again.",
    "icloud_access_denied": (
        "Enable iCloud web data access, stop the Go backend, run reminders auth --approve-web-access "
        "with its data directory and approve on a trusted device, then start it again."
    ),
    "invalid_argument": "Reminders rejected the arguments. Check exact IDs, dates, priority, pagination and same-list structure references. Batches require every existing reminder, including completed tasks, and every existing section in current order. Assignment needs one accepted participant ID from this list or clear=true.",
    "unsupported_structure": "This list uses an unsupported structure format. No write was attempted; refresh or inspect the list in Apple Reminders.",
    "unsupported_text_document": "This reminder's text document cannot be updated safely. No write was attempted; inspect it in Apple Reminders.",
    "write_result_unknown": "iCloud did not confirm the complete write. Inspect current reminders and sections before retrying.",
    "icloud_write_failed": "iCloud rejected the write. Inspect current reminders and sections before retrying.",
    "upstream_mismatch": "iCloud accepted the write but its saved manual order differs from the requested order. Inspect current data before retrying.",
    "write_verification_failed": "iCloud accepted the write but its saved manual order could not be verified. Inspect current data before retrying.",
    "request_timeout": "Request ended before completion. A write may have succeeded; inspect the reminder before retrying.",
    "icloud_request_failed": "iCloud request failed. A write may have succeeded; inspect the reminder before retrying.",
    "backend_unavailable": "The Go Reminders backend could not complete the request. Check its service and bearer token. A write may have succeeded; inspect before retrying.",
}


class RemindersError(Exception):
    """Only application-owned messages cross the public MCP boundary."""

    def __init__(
        self, code: str, *, operation: str | None = None, request_id: str | None = None,
        write_status: str | None = None, retry_class: str = "not_retryable",
        http_status: int | None = None, upstream_status: int | None = None,
        upstream_error_code: str | None = None,
        list_id: str | None = None, record_type: str | None = None,
        structure_field: str | None = None, structure_reason: str | None = None,
        structure_version: int | None = None, order_verification: str | None = None,
    ) -> None:
        self.code = code if code in _PUBLIC_ERRORS else "backend_unavailable"
        self.details = {"error_code": self.code, "retry_class": retry_class,
                        "retryable": retry_class != "not_retryable"}
        for key, value in {
            "operation": operation, "request_id": request_id, "write_status": write_status,
            "http_status": http_status, "upstream_status": upstream_status,
            "upstream_error_code": upstream_error_code,
            "list_id": list_id, "record_type": record_type, "structure_field": structure_field,
            "structure_reason": structure_reason, "structure_version": structure_version,
            "order_verification": order_verification,
        }.items():
            if value is not None:
                self.details[key] = value
        super().__init__(f"{self.code}: {_PUBLIC_ERRORS[self.code]}")

    def as_result(self) -> CallToolResult:
        return CallToolResult(is_error=True, structured_content=self.details,
                              content=[TextContent(type="text", text=str(self))])


READ_TOOLS = frozenset({
    "list_reminder_lists", "list_reminders", "get_reminder", "sync_reminders",
    "list_reminder_participants", "list_reminder_sections",
})
_RETRY_CLASSES = frozenset({"retryable_safe", "retryable_after_read", "not_retryable"})
_WRITE_STATES = frozenset({"not_sent", "failed", "succeeded", "unknown"})
_UPSTREAM_CODES = frozenset({
    "BAD_REQUEST", "AUTHENTICATION_REQUIRED", "ACCESS_DENIED", "NOT_FOUND", "UNKNOWN_ITEM",
    "CONFLICT", "SERVER_RECORD_CHANGED", "ZONE_NOT_FOUND", "QUOTA_EXCEEDED", "LIMIT_EXCEEDED",
    "THROTTLED", "SERVICE_UNAVAILABLE", "INTERNAL_ERROR", "BATCH_REQUEST_FAILED", "INVALID_FIELD_TYPE", "ATOMIC_FAILURE", "VALIDATING_REFERENCE_ERROR",
})
_STRUCTURE_FIELDS = frozenset({"ReminderIDs", "ReminderIDsAsset", "MembershipsOfRemindersInSectionsAsData", "SectionIDsOrderingAsData", "ResolutionTokenMap", "TitleDocument", "NotesDocument"})
_STRUCTURE_REASONS = frozenset({"too_large", "invalid_json", "invalid_version", "unsupported_version", "missing_entries", "invalid_entries", "metadata_unavailable", "non_native_record_id"})


def _exceptions(error: BaseException):
    yield error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            yield from _exceptions(child)


def _http_status(error: BaseException) -> int | None:
    return next((item.response.status_code for item in _exceptions(error)
                 if isinstance(item, httpx2.HTTPStatusError)), None)


def _error_code(result: CallToolResult) -> str:
    payload = result.structured_content
    if isinstance(payload, dict) and isinstance(payload.get("error_code"), str) and payload["error_code"] in _PUBLIC_ERRORS:
        return payload["error_code"]
    # Older Go SDKs wrap tool errors, e.g. 'calling "tool": code: message'.
    # Only known enum values survive; upstream text is never returned or logged.
    for item in result.content:
        if isinstance(item, TextContent):
            for match in re.finditer(r"(?:^|:\s+)([a-z_]+):", item.text):
                if match[1] in _PUBLIC_ERRORS:
                    return match[1]
    return "backend_unavailable"


def _upstream_error(result: CallToolResult, operation: str, request_id: str) -> RemindersError:
    code = _error_code(result)
    mutation = operation not in READ_TOOLS
    status = "unknown" if mutation else None
    retry = "retryable_after_read" if mutation else "retryable_safe"
    if code in {"invalid_argument", "not_found", "not_shared", "permission_denied", "unsupported_structure",
                "idempotency_conflict", "backend_upgrade_required", "unsupported_backend"}:
        status, retry = "not_sent" if mutation else None, "not_retryable"
    details = result.structured_content
    safe: dict[str, Any] = {}
    if isinstance(details, dict):
        if mutation and isinstance(details.get("write_status"), str) and details["write_status"] in _WRITE_STATES:
            status = details["write_status"]
        if isinstance(details.get("retry_class"), str) and details["retry_class"] in _RETRY_CLASSES:
            retry = details["retry_class"]
        # A retry is never safe after an unknown/confirmed mutation.
        if mutation and status in {"unknown", "succeeded"} and retry == "retryable_safe":
            retry = "retryable_after_read"
        value = details.get("upstream_status")
        if type(value) is int and 100 <= value <= 599:
            safe["upstream_status"] = value
        if isinstance(details.get("upstream_error_code"), str) and details["upstream_error_code"] in _UPSTREAM_CODES:
            safe["upstream_error_code"] = details["upstream_error_code"]
        if isinstance(details.get("order_verification"), str) and details["order_verification"] in {"mismatch", "unavailable"}:
            safe["order_verification"] = details["order_verification"]
        for key, allowed in (("structure_field", _STRUCTURE_FIELDS), ("structure_reason", _STRUCTURE_REASONS), ("record_type", {"List", "ReminderList", "Reminder"})):
            value = details.get(key)
            if isinstance(value, str) and value in allowed:
                safe[key] = value
        version = details.get("structure_version")
        if type(version) is int and 0 <= version <= 2**53:
            safe["structure_version"] = version
        list_id = details.get("list_id")
        if isinstance(list_id, str) and list_id.startswith("List/"):
            try:
                UUID(list_id[5:])
                safe["list_id"] = list_id
            except ValueError:
                pass
    return RemindersError(code, operation=operation, request_id=request_id,
                          write_status=status, retry_class=retry, **safe)


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


@dataclass
class _RemindersSession:
    request_id: str
    operation: str
    client: ClientSession | None = None
    dispatched: bool = False
    confirmed: bool = False
    response_status: int | None = None
    tools: dict[str, Tool] | None = None


class GoRemindersService:
    def __init__(self, config: RemindersConfig) -> None:
        self.config = config

    @staticmethod
    def _validate(name: str, arguments: dict[str, Any], request_id: str) -> None:
        if name not in REMINDER_TOOLS:
            raise RemindersError("invalid_argument", operation=name, request_id=request_id,
                                 write_status="not_sent")
        if name == "create_reminder" and "client_request_id" in arguments:
            try:
                UUID(arguments["client_request_id"])
            except (ValueError, TypeError, AttributeError):
                raise RemindersError("invalid_argument", operation=name, request_id=request_id,
                                     write_status="not_sent") from None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self._validate(name, arguments, call_id())
        if name == "batch_update_reminders":
            from app.reminders_batch import run_batch

            return await run_batch(self, arguments)
        async with self.tool_session(operation=name) as session:
            return await self.invoke(session, name, arguments)

    @asynccontextmanager
    async def tool_session(self, *, operation: str = "batch_update_reminders"):
        """One fresh session and one total deadline, including every batch step."""
        request_id = call_id()
        if request_id == "none":
            request_id = uuid4().hex[:16]
        state = _RemindersSession(request_id, operation)
        headers = {"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}

        async def record_response(response: httpx2.Response) -> None:
            if response.request.method == "POST" and response.status_code >= 400:
                state.response_status = response.status_code

        try:
            with quiet_transport_logs():
                async with asyncio.timeout(self.config.timeout_seconds):
                    async with httpx2.AsyncClient(
                        headers=headers,
                        timeout=httpx2.Timeout(10, read=self.config.timeout_seconds),
                        trust_env=False,
                        event_hooks={"response": [record_response]},
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
                                state.client = session
                                yield state
        except RemindersError:
            raise
        except Exception as error:
            known = next((item for item in _exceptions(error) if isinstance(item, RemindersError)), None)
            if known is not None:
                raise known from None
            status = state.response_status or _http_status(error)
            code = "request_timeout" if _contains_timeout(error) else "backend_unavailable"
            if status in {401, 403}:
                code = "backend_auth_failed"
            mutation = state.operation not in READ_TOOLS
            write_status = None
            if mutation:
                write_status = "succeeded" if state.confirmed else "unknown" if state.dispatched else "not_sent"
            retry = "retryable_after_read" if mutation and state.dispatched else "retryable_safe"
            if code == "backend_auth_failed":
                retry = "not_retryable"
            raise RemindersError(code, operation=state.operation, request_id=request_id,
                                 write_status=write_status, retry_class=retry, http_status=status) from None

    @staticmethod
    async def discover(session: _RemindersSession) -> dict[str, Tool]:
        if session.tools is not None:
            return session.tools
        available: dict[str, Tool] = {}
        cursor = None
        for _ in range(8):
            with measure_phase("reminders_mcp_capabilities"):
                page = await session.client.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
            available.update({tool.name: tool for tool in page.tools})
            cursor = page.next_cursor
            if not cursor:
                session.tools = available
                return available
        raise RemindersError("backend_protocol_error", operation=session.operation,
                             request_id=session.request_id, write_status="not_sent")

    async def invoke(self, session: _RemindersSession, name: str, arguments: dict[str, Any]) -> CallToolResult:
        session.operation = name
        session.dispatched = session.confirmed = False
        session.response_status = None
        self._validate(name, arguments, session.request_id)
        if name == "create_reminder" and arguments.get("client_request_id") is not None:
            available = await self.discover(session)
            tool = available.get(name)
            if tool is None or "client_request_id" not in tool.input_schema.get("properties", {}):
                raise RemindersError("unsupported_backend", operation=name, request_id=session.request_id,
                                     write_status="not_sent")
        with measure_phase("reminders_mcp_call"):
            session.dispatched = True
            result = await session.client.call_tool(name, arguments)
        if not isinstance(result, CallToolResult):
            raise RemindersError("backend_protocol_error", operation=name, request_id=session.request_id,
                                 write_status="unknown" if name not in READ_TOOLS else None,
                                 retry_class="retryable_after_read" if name not in READ_TOOLS else "retryable_safe")
        if result.is_error:
            raise _upstream_error(result, name, session.request_id)
        session.confirmed = True
        return result
