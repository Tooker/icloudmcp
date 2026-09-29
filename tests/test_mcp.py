from pathlib import Path
import asyncio
import logging
import threading

from fastapi.testclient import TestClient
from mcp_types import CallToolRequestParams
import pytest

from app.main import create_app
from app.icloud import ICloudServiceError
from app.mcp_server import create_mcp_server


def test_streamable_http_mcp_endpoint_exposes_calendar_tools(tmp_path: Path) -> None:
    app = create_app(tmp_path / "missing.yaml", environ={})
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }

    with TestClient(app) as client:
        response = client.post("/mcp", json=initialize, headers=headers, follow_redirects=False)

        assert response.status_code == 200
        session_id = response.headers["mcp-session-id"]

        tools_response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={**headers, "mcp-session-id": session_id},
        )

    assert tools_response.status_code == 200
    assert '"name":"list_calendars"' in tools_response.text
    assert '"name":"create_event"' in tools_response.text
    assert '"name":"delete_event"' in tools_response.text
    assert '"name":"search_emails"' in tools_response.text
    assert '"name":"get_email_attachment"' in tools_response.text
    assert '"name":"create_draft"' in tools_response.text
    assert '"name":"update_draft"' in tools_response.text
    assert '"name":"mark_email_read"' in tools_response.text


@pytest.mark.parametrize("error", [RuntimeError, ValueError, ICloudServiceError])
def test_mcp_errors_do_not_log_private_exception_causes(caplog, error) -> None:
    marker = "PRIVATE_UPSTREAM_DETAIL_DO_NOT_LOG"

    class FailingCalendar:
        def list_calendars(self):
            try:
                raise RuntimeError(marker)
            except RuntimeError as cause:
                message = "safe validation message" if error is not RuntimeError else "upstream failed"
                raise error(message) from cause

    server = create_mcp_server(FailingCalendar())
    with caplog.at_level(logging.INFO, logger="mcp.server.mcpserver.server"):
        result = asyncio.run(server._handle_call_tool(
            None, CallToolRequestParams(name="list_calendars", arguments={})
        ))
    assert result.is_error is True
    assert marker not in str(result)
    assert marker not in caplog.text
    assert not any(record.exc_info for record in caplog.records)


@pytest.mark.parametrize("options", [
    {"format": "text"}, {"format": "base64", "offset": 17, "limit": 50},
])
def test_attachment_tool_forwards_options_in_worker_and_returns_content(options) -> None:
    class MailService:
        def get_email_attachment(self, **arguments):
            assert threading.current_thread() is not threading.main_thread()
            self.arguments = arguments
            return {"text": "Invoice total: 42 EUR", "text_status": "ok"}

    service = MailService()
    server = create_mcp_server(None, service)
    result = asyncio.run(server._handle_call_tool(
        None, CallToolRequestParams(name="get_email_attachment", arguments={
            "uid": "42", "mailbox": "Archive", "attachment_id": "2", **options,
        })
    ))
    assert result.is_error is False
    assert result.structured_content["text"] == "Invoice total: 42 EUR"
    assert service.arguments == {
        "uid": "42", "mailbox": "Archive", "attachment_id": "2",
        "format": "text", "offset": 0, "limit": 20_000, **options,
    }
    tool = next(tool for tool in asyncio.run(server.list_tools()) if tool.name == "get_email_attachment")
    assert tool.annotations.model_dump(by_alias=True)["readOnlyHint"] is True


def test_attachment_tool_reports_missing_imap_configuration() -> None:
    server = create_mcp_server(None)
    result = asyncio.run(server._handle_call_tool(
        None, CallToolRequestParams(name="get_email_attachment", arguments={
            "uid": "42", "attachment_id": "1",
        })
    ))
    assert result.is_error is True
    assert "iCloud IMAP is not configured" in str(result)
