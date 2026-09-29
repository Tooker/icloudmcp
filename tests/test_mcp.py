from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


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
    assert '"name":"mark_email_read"' in tools_response.text
    assert '"name":"list_reminder_lists"' in tools_response.text
    assert '"name":"create_reminder"' in tools_response.text
