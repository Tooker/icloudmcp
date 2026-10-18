"""One additive error contract; native backend evidence is never discarded."""

from copy import deepcopy
import json
from typing import Literal
from uuid import uuid4

from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from loguru import logger

from app.mcp_groups import service_for_tool
from app.timing import call_id


MESSAGES = {
    "invalid_argument": "Invalid parameters. Use the published parameter contract.",
    "confirmation_required": "This operation requires explicit confirm=true; no write was attempted.",
    "unknown_tool": "Unknown tool; use an exact name from tools/list.",
    "not_configured": "This service is not configured. Check the service configuration before another call.",
    "not_found": "The requested item is unavailable. Refresh discovery; incomplete coverage cannot establish absence.",
    "mailbox_unavailable": "The mailbox could not be selected. Use list_mailboxes to verify its exact name and access.",
    "authentication_failed": "The service rejected authentication. Check its configured credentials.",
    "backend_unavailable": "The backend could not complete the operation. Inspect write state before repeating any mutation.",
    "timeout": "The operation timed out. A submitted write may have succeeded; inspect the preserved state before another action.",
    "protocol_error": "The backend returned an unsupported response. Preserve confirmed changes and inspect current state.",
    "backend_protocol_error": "The response does not match the published contract. Preserve native results and confirmed changes; inspect before repeating a write.",
    "service_error": "The service rejected or could not complete the operation. The exact upstream cause is not available.",
    "write_failed": "The service rejected a write step. Earlier confirmed steps remain effective; inspect preserved state.",
    "write_uncertain": "A submitted write step could not be confirmed. Inspect current state; never replay or roll back automatically.",
    "snapshot_expired": "The private file snapshot is unknown or expired. Retrieve the original file again.",
    "local_state_failed": "The write succeeded but local state could not be updated. Inspect current state; do not repeat the write solely to repair local state.",
}

# Backend codes are preserved, with application-owned messages only.
BACKEND_CODES = {
    "auth_required", "access_required", "lookup_incomplete", "unsupported_item", "version_changed", "too_large",
    "unsafe_target", "backend_auth_failed", "conflict", "read_only", "addressbook_required", "access_denied",
    "response_too_large", "coverage_incomplete", "backend_upgrade_required", "unsupported_backend",
    "idempotency_conflict", "local_state_failed", "permission_denied", "not_shared", "icloud_access_denied",
    "unsupported_structure", "unsupported_text_document", "write_result_unknown", "icloud_write_failed",
    "upstream_mismatch", "write_verification_failed", "request_timeout", "icloud_request_failed",
}
ErrorCode = Literal[tuple(sorted(set(MESSAGES) | BACKEND_CODES))]
WriteStatus = Literal["not_sent", "failed", "succeeded", "partial", "unknown"]
RetryClass = Literal["retryable_safe", "retryable_after_read", "not_retryable"]


class InvalidParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    parameter: str
    expected: str
    description: str


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    code: ErrorCode
    message: str
    service: Literal["calendar", "mail", "contacts", "drive", "reminders", "unknown"]
    operation: str
    request_operation: str = Field(description="Exact tool originally called; a preserved native operation may identify its failed sub-step.")
    request_id: str
    phase: str = Field(description="Application-owned phase or write step; never raw exception text.")
    write_status: WriteStatus | None = Field(description="Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.")
    overall_write_status: WriteStatus | None = Field(description="Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.")
    confirmed_steps: list[str]
    uncertain_step: str | None
    retry_class: RetryClass
    retryable: bool = Field(description="Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.")
    inspect_before_retry: bool
    automatic_retry_allowed: Literal[False] = False
    invalid_parameters: list[InvalidParameter] | None = None


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    error: ErrorInfo


class ToolFailure(ToolError):
    def __init__(self, code, *, details=None, phase="service", message=None):
        self.code = code
        self.details = details or {}
        self.phase = phase
        self.public_message = message or MESSAGES.get(code, MESSAGES["service_error"])
        super().__init__(self.public_message)


def error_result(name, code, *, result=None, details=None, phase="service", message=None,
                 write=False, before_call=False):
    payload = deepcopy(result.structured_content) if result and isinstance(result.structured_content, dict) else {}
    payload.update(deepcopy(details or {}))
    native = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = code if code in MESSAGES or code in BACKEND_CODES else "backend_protocol_error"
    status = payload.get("write_status", native.get("write_status"))
    confirmed = payload.get("confirmed_steps", [])
    confirmed = confirmed if isinstance(confirmed, list) and all(isinstance(step, str) for step in confirmed) else []
    uncertain = payload.get("uncertain_step")
    uncertain = uncertain if isinstance(uncertain, str) else None
    if not write:
        state = None
    elif before_call or status in {"not_sent", "not_started"}:
        state = "not_sent"
    elif status in {"succeeded", "unknown", "partial"}:
        state = status
    elif status == "failed":
        state = "partial" if confirmed else "failed"
    else:
        state = "unknown"
    if write and type(payload.get("completed_operations")) is int and payload["completed_operations"] > 0 and state in {"not_sent", "failed"}:
        state = "partial"
    inspect = write and state in {"unknown", "partial", "succeeded"}
    # Do not promote a backend's not_retryable decision or an uncertain write.
    native_retry = payload.get("retry_class", native.get("retry_class"))
    if inspect:
        retry = "not_retryable" if native_retry == "not_retryable" else "retryable_after_read"
    elif code in {"invalid_argument", "confirmation_required", "unknown_tool", "authentication_failed", "auth_required", "access_required", "not_configured", "unsafe_target", "backend_auth_failed"}:
        retry = "not_retryable"
    elif native_retry in {"retryable_safe", "retryable_after_read", "not_retryable"}:
        retry = native_retry
    else:
        retry = "retryable_safe" if not write else "not_retryable"
    public_message = message or MESSAGES.get(code) or native.get("message") or "The backend rejected the operation. Inspect the returned application-owned diagnostics."
    info = ErrorInfo(
        code=code, message=public_message, service=service_for_tool(name) or "unknown", operation=name, request_operation=name,
        request_id=call_id() if call_id() != "none" else uuid4().hex,
        phase=phase, write_status=state, overall_write_status=state, confirmed_steps=confirmed, uncertain_step=uncertain,
        retry_class=retry, retryable=retry != "not_retryable", inspect_before_retry=inspect,
        invalid_parameters=(details or {}).get("invalid_parameters"),
    ).model_dump(exclude_none=False)
    payload["error"] = {**info, **native}
    try:
        ErrorInfo.model_validate(payload["error"])
    except ValidationError:
        payload["error"] = info
    if write:
        payload.setdefault("write_status", state)
    if service_for_tool(name) == "reminders":
        payload.setdefault("error_code", code)
        payload.setdefault("retry_class", retry)
        payload.setdefault("retryable", retry != "not_retryable")
    if phase == "input_validation":
        logger.info("mcp_tool_start tool={} call_id={}", name, info["request_id"])
        logger.info("mcp_tool_complete tool={} call_id={} outcome={} duration_ms=0 result_count=0", name, info["request_id"], code)
    else:
        logger.info("mcp_error tool={} call_id={} code={} write_status={} confirmed_count={}",
                    name, info["request_id"], code, state, len(confirmed))
    # Preserve original native content blocks and payload fields. The additional
    # error block supplies a consistent client contract without replacing evidence.
    content = list(result.content) if result else []
    content.append(TextContent(type="text", text=json.dumps({"error": payload["error"]}, ensure_ascii=False)))
    return CallToolResult(isError=True, structuredContent=payload, content=content,
                          **({"_meta": result.meta} if result and result.meta else {}))
