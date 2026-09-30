"""Regression coverage for safe mutation diagnostics at the Python MCP boundary."""

import asyncio
import json
import logging
from uuid import uuid4

import httpx2
from loguru import logger
from mcp_types import CallToolRequestParams
import pytest

from app.config import RemindersConfig
from app.mcp_server import create_mcp_server
from app.reminders import GoRemindersService
from test_reminders import PRIVATE, simulated_go


def call(backend, name="create_reminder", **extra):
    server = create_mcp_server(None, reminders_service=backend)
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(
        name=name, arguments={"title": PRIVATE, "list_id": "exact-list", **extra} if name == "create_reminder" else extra,
    )))


@pytest.mark.parametrize("prefix", ["", 'calling "complete_reminder": '])
def test_wrapped_backend_error_codes_are_not_lost(monkeypatch, prefix):
    backend, messages = simulated_go(monkeypatch, result={
        "content": [{"type": "text", "text": prefix + "icloud_write_failed: " + PRIVATE}], "isError": True,
    })
    result = call(backend)
    assert result.is_error
    assert result.structured_content["error_code"] == "icloud_write_failed"
    # Old servers supply no commit evidence; don't infer a safe retry from text.
    assert result.structured_content["write_status"] == "unknown"
    assert result.structured_content["retry_class"] == "retryable_after_read"
    assert len([m for m in messages if m["method"] == "tools/call"]) == 1
    assert PRIVATE not in str(result)


@pytest.mark.parametrize(("state", "retry"), [
    ("not_sent", "retryable_safe"), ("failed", "not_retryable"),
    ("unknown", "retryable_after_read"), ("succeeded", "retryable_after_read"),
])
def test_safe_structured_backend_details_survive_and_correlate(monkeypatch, caplog, state, retry):
    backend, _ = simulated_go(monkeypatch, result={
        "isError": True, "content": [{"type": "text", "text": PRIVATE}],
        "structuredContent": {"error_code": "write_result_unknown", "write_status": state,
                              "retry_class": retry, "upstream_status": 504, "upstream_error_code": "CONFLICT",
                              "request_id": PRIVATE, "reminder_id": PRIVATE, "body": PRIVATE},
    })
    logs = []
    sink = logger.add(lambda msg: logs.append(msg.record["message"]))
    try:
        with caplog.at_level(logging.DEBUG):
            result = call(backend)
    finally:
        logger.remove(sink)
    details = result.structured_content
    assert details["write_status"] == state
    assert details["retry_class"] == retry
    assert details["upstream_status"] == 504
    assert details["upstream_error_code"] == "CONFLICT"
    assert details["operation"] == "create_reminder"
    assert any(f'call_id={details["request_id"]}' in line for line in logs)
    assert PRIVATE not in str(result) + "\n".join(logs) + caplog.text


def test_unknown_mutation_can_never_advertise_a_safe_retry(monkeypatch):
    backend, _ = simulated_go(monkeypatch, result={
        "isError": True, "content": [], "structuredContent": {
            "error_code": "write_result_unknown", "write_status": "unknown", "retry_class": "retryable_safe",
        },
    })
    assert call(backend).structured_content["retry_class"] == "retryable_after_read"


def test_malformed_private_diagnostics_are_sanitized(monkeypatch):
    backend, _ = simulated_go(monkeypatch, result={
        "isError": True, "content": [{"type": "text", "text": PRIVATE}], "structuredContent": {
            "error_code": [PRIVATE], "write_status": {"private": PRIVATE}, "retry_class": [PRIVATE],
            "upstream_status": True, "upstream_error_code": [PRIVATE],
        },
    })
    result = call(backend)
    assert result.structured_content["error_code"] == "backend_unavailable"
    assert result.structured_content["write_status"] == "unknown"
    assert "upstream_status" not in result.structured_content
    assert PRIVATE not in str(result)


def test_timeout_before_initialize_proves_no_mutation_was_sent(monkeypatch):
    original = httpx2.AsyncClient
    async def handle(request):
        if request.method == "POST":
            await asyncio.sleep(1)
        return httpx2.Response(405)
    monkeypatch.setattr("app.reminders.httpx2.AsyncClient", lambda **kw: original(transport=httpx2.MockTransport(handle), **kw))
    backend = GoRemindersService(RemindersConfig("http://reminders:8080/mcp", PRIVATE, 0.03))
    result = call(backend)
    assert result.structured_content["error_code"] == "request_timeout"
    assert result.structured_content["write_status"] == "not_sent"
    assert result.structured_content["retry_class"] == "retryable_safe"


def test_authentication_response_reports_bridge_status_without_assuming_commit(monkeypatch):
    backend, _ = simulated_go(monkeypatch, failure="http")
    result = call(backend)
    assert result.structured_content["error_code"] == "backend_auth_failed"
    assert result.structured_content["http_status"] == 403
    assert result.structured_content["write_status"] == "unknown"
    assert not result.structured_content["retryable"]


def test_unconfirmed_delete_returns_not_sent_without_contacting_backend(monkeypatch):
    backend, messages = simulated_go(monkeypatch)
    result = call(backend, name="delete_reminder", id="exact-id", confirm=False)
    assert result.structured_content["write_status"] == "not_sent"
    assert result.structured_content["retry_class"] == "not_retryable"
    assert messages == []


def test_keyed_creation_is_rejected_before_write_on_an_older_backend(monkeypatch):
    backend, messages = simulated_go(monkeypatch)
    result = call(backend, client_request_id=str(uuid4()))
    assert result.structured_content["error_code"] == "unsupported_backend"
    assert result.structured_content["write_status"] == "not_sent"
    assert not any(m["method"] == "tools/call" for m in messages)


@pytest.mark.parametrize("key", ["", "not-a-uuid"])
def test_invalid_key_never_contacts_backend(monkeypatch, key):
    backend, messages = simulated_go(monkeypatch)
    result = call(backend, client_request_id=key)
    assert result.structured_content["error_code"] == "invalid_argument"
    assert result.structured_content["write_status"] == "not_sent"
    assert messages == []


def test_keyed_creation_is_forwarded_once_when_backend_declares_support(monkeypatch):
    backend, messages = simulated_go(monkeypatch, supports_key=True)
    key = str(uuid4())
    result = call(backend, client_request_id=key)
    assert not result.is_error
    calls = [m for m in messages if m["method"] == "tools/call"]
    assert len(calls) == 1
    assert calls[0]["params"]["arguments"]["client_request_id"] == key
