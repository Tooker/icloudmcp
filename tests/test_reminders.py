from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient
import httpx2
from loguru import logger
from mcp_types import CallToolRequestParams
import pytest

from app.config import RemindersConfig, load_reminders_config
from app.main import create_app
from app.mcp_server import create_mcp_server
from app.reminders import GoRemindersService, REMINDER_TOOLS, RemindersError


PRIVATE = "PRIVATE_REMINDER_CONTENT_OR_CREDENTIAL"


def simulated_go(monkeypatch, *, result=None, failure=None, delay=0):
    calls = []
    original_client = httpx2.AsyncClient

    async def handle(request):
        assert request.url.path == "/mcp"
        assert request.headers.get("authorization") == f"Bearer {PRIVATE}"
        if request.method == "GET":
            return httpx2.Response(405)
        message = json.loads(request.content)
        calls.append(message)
        if message["method"] == "notifications/initialized":
            return httpx2.Response(202)
        if message["method"] == "initialize":
            payload = {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "simulated-go", "version": "1"},
            }
        elif message["method"] == "tools/list":
            payload = {"tools": [{
                "name": name, "inputSchema": {"type": "object", "properties": {}},
            } for name in REMINDER_TOOLS]}
        else:
            assert message["method"] == "tools/call"
            if delay:
                await asyncio.sleep(delay)
            if failure == "http":
                return httpx2.Response(403, text=PRIVATE)
            if failure == "json":
                return httpx2.Response(200, text=PRIVATE, headers={"content-type": "application/json"})
            if failure == "rpc":
                return httpx2.Response(200, json={
                    "jsonrpc": "2.0", "id": message["id"],
                    "error": {"code": -32603, "message": PRIVATE},
                })
            payload = result or {
                "content": [{"type": "text", "text": PRIVATE}],
                "structuredContent": {"reminders": [{"id": "exact-id", "title": PRIVATE}], "total": 1},
            }
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": payload})

    def client(**kwargs):
        return original_client(transport=httpx2.MockTransport(handle), **kwargs)

    monkeypatch.setattr("app.reminders.httpx2.AsyncClient", client)
    return GoRemindersService(RemindersConfig("http://reminders:8080/mcp", PRIVATE, 1)), calls


@pytest.mark.parametrize(("name", "arguments"), [
    ("list_reminder_lists", {}),
    ("list_reminders", {"list_id": "exact-list", "parent_id": "exact-parent", "query": PRIVATE,
                        "include_completed": True, "limit": 5, "offset": 10}),
    ("get_reminder", {"id": "exact-id"}),
    ("create_reminder", {"title": PRIVATE, "list_id": "exact-list", "parent_id": "exact-parent",
                         "notes": PRIVATE, "due": "2026-10-01", "priority": "high"}),
    ("update_reminder", {"id": "exact-id", "notes": PRIVATE, "priority": "none"}),
    ("complete_reminder", {"id": "exact-id"}),
    ("delete_reminder", {"id": "exact-id", "confirm": True}),
    ("sync_reminders", {"full": True}),
])
def test_python_tools_forward_through_real_mcp_client_once_and_keep_results_private(monkeypatch, caplog, name, arguments):
    backend, messages = simulated_go(monkeypatch)
    server = create_mcp_server(None, reminders_service=backend)
    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        with caplog.at_level(logging.DEBUG):
            result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments)))
    finally:
        logger.remove(sink)
    assert not result.is_error
    assert result.structured_content["reminders"][0]["title"] == PRIVATE
    assert result.content[0].text == PRIVATE
    forwarded = [message["params"] for message in messages if message["method"] == "tools/call"]
    assert len(forwarded) == 1
    assert forwarded[0]["name"] == name
    actual_arguments = forwarded[0]["arguments"]
    assert all(actual_arguments[key] == value for key, value in arguments.items())
    assert all(value is not None for value in actual_arguments.values())
    assert any("mcp_tool_complete" in message and "outcome=ok" in message for message in logs)
    assert any("phase=reminders_mcp_call" in message for message in logs)
    assert PRIVATE not in "\n".join(logs) + caplog.text


@pytest.mark.parametrize("code", ["auth_required", "icloud_access_denied", "request_timeout", "invalid_argument", "unknown"])
def test_upstream_tool_errors_use_safe_local_messages_without_retry(monkeypatch, caplog, code):
    backend, messages = simulated_go(monkeypatch, result={
        "content": [{"type": "text", "text": f"{code}: {PRIVATE}"}], "isError": True,
    })
    server = create_mcp_server(None, reminders_service=backend)
    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="create_reminder", arguments={
            "title": PRIVATE, "list_id": "exact-list",
        })))
    assert result.is_error
    assert PRIVATE not in str(result) + caplog.text
    assert (code if code != "unknown" else "backend_unavailable") in result.content[0].text
    assert len([message for message in messages if message["method"] == "tools/call"]) == 1


@pytest.mark.parametrize("failure", ["http", "json", "rpc"])
def test_private_transport_failures_do_not_escape_or_replay_writes(monkeypatch, caplog, failure):
    backend, messages = simulated_go(monkeypatch, failure=failure)
    server = create_mcp_server(None, reminders_service=backend)
    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="create_reminder", arguments={
            "title": PRIVATE, "list_id": "exact-list",
        })))
    assert result.is_error
    assert "backend_unavailable" in result.content[0].text
    assert PRIVATE not in str(result) + caplog.text
    assert len([message for message in messages if message["method"] == "tools/call"]) == 1


def test_unconfirmed_deletion_and_missing_confirm_never_reach_go(monkeypatch):
    backend, messages = simulated_go(monkeypatch)
    server = create_mcp_server(None, reminders_service=backend)
    for arguments in ({"id": "exact-id", "confirm": False}, {"id": "exact-id"}):
        result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="delete_reminder", arguments=arguments)))
        assert result.is_error
    assert messages == []


def test_timeout_and_cancellation_end_calls_without_retry(monkeypatch):
    backend, messages = simulated_go(monkeypatch, delay=60)

    async def run():
        with pytest.raises(RemindersError, match="request_timeout"):
            await backend.call_tool("create_reminder", {"title": PRIVATE, "list_id": "exact-list"})
        task = asyncio.create_task(backend.call_tool("list_reminders", {}))
        while len([message for message in messages if message["method"] == "tools/call"]) < 2:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len([message for message in messages if message["method"] == "tools/call"]) == 2


def test_parallel_calls_own_independent_sessions(monkeypatch):
    backend, messages = simulated_go(monkeypatch, delay=0.02)

    async def run():
        return await asyncio.gather(*(backend.call_tool("get_reminder", {"id": str(index)}) for index in range(3)))

    results = asyncio.run(run())
    assert all(not result.is_error for result in results)
    assert len([message for message in messages if message["method"] == "initialize"]) == 3
    assert {message["params"]["arguments"]["id"] for message in messages if message["method"] == "tools/call"} == {"0", "1", "2"}


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_common_endpoint_discovers_calendar_mail_and_reminders_when_go_is_offline(tmp_path: Path, path):
    app = create_app(tmp_path / "missing.yaml", environ={"REMINDERS_MCP_URL": "http://reminders:8080/mcp"})
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app) as client:
        response = client.post(path, headers=headers, follow_redirects=False, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "pytest", "version": "1"}},
        })
        assert response.status_code == 200
        response = client.post(path, headers={**headers, "mcp-session-id": response.headers["mcp-session-id"]}, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
    assert response.status_code == 200
    assert all(f'"name":"{name}"' in response.text for name in REMINDER_TOOLS | {"list_calendars", "search_emails", "get_email_attachment"})


def test_reminders_schema_annotations_and_optional_configuration():
    server = create_mcp_server(None)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"id", "confirm"} <= set(tools["delete_reminder"].input_schema["required"])
    assert tools["delete_reminder"].annotations.destructive_hint
    assert not tools["create_reminder"].annotations.idempotent_hint
    assert tools["list_reminders"].annotations.read_only_hint
    result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="list_reminder_lists", arguments={})))
    assert result.is_error
    assert "REMINDERS_MCP_URL" in result.content[0].text


def test_reminders_configuration_does_not_reuse_apple_passwords_or_expose_token():
    assert load_reminders_config({"ICLOUD_APP_PASSWORD": PRIVATE}) is None
    config = load_reminders_config({"REMINDERS_MCP_URL": "http://reminders:8080/mcp/", "REMINDERS_MCP_TOKEN": PRIVATE})
    assert config is not None and config.timeout_seconds == 210
    assert PRIVATE not in repr(config)


@pytest.mark.parametrize("settings", [
    {"REMINDERS_MCP_URL": "http://user:secret@reminders:8080/mcp"},
    {"REMINDERS_MCP_URL": "http://reminders:8080/mcp?token=secret"},
    {"REMINDERS_MCP_URL": "ftp://reminders/mcp"},
    {"REMINDERS_MCP_URL": "http://reminders:8080/"},
    {"REMINDERS_MCP_URL": "http://reminders:bad/mcp"},
    {"REMINDERS_MCP_TIMEOUT_SECONDS": "0"},
    {"REMINDERS_MCP_TIMEOUT_SECONDS": "901"},
    {"REMINDERS_MCP_TIMEOUT_SECONDS": "bad"},
    {"REMINDERS_MCP_TOKEN": " secret "},
    {"REMINDERS_MCP_TOKEN": "secret\r\nHeader: bad"},
])
def test_invalid_reminders_configuration_uses_non_private_errors(settings):
    with pytest.raises(ValueError) as error:
        load_reminders_config({"REMINDERS_MCP_URL": "http://reminders:8080/mcp", **settings})
    assert "secret" not in str(error.value)
