from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from mcp_types import CallToolRequestParams, ReadResourceRequestParams

from app.main import create_app
from app.mcp_resources import AttachmentMCPServer
from app.mcp_server import create_mcp_server


PAYLOAD = b"%PDF-1.7\n" + bytes(range(256)) * 100


def file_result(payload: bytes = PAYLOAD, filename: str | None = "Rechnung März.pdf") -> dict:
    return {
        "uid": "42", "mailbox": "Private/Übersicht", "attachment_id": "1",
        "filename": filename, "content_type": "application/pdf", "size": len(payload),
        "format": "file", "offset": 0, "content_bytes": payload,
        "returned_bytes": len(payload), "has_more": False, "next_offset": None,
    }


class FileMailService:
    def get_email_attachment(self, **arguments):
        self.arguments = arguments
        return file_result()


def test_default_attachment_tool_delivers_binary_resource_filename_and_readable_link() -> None:
    service = FileMailService()
    server = create_mcp_server(None, service)
    result = asyncio.run(server._handle_call_tool(
        None, CallToolRequestParams(name="get_email_attachment", arguments={
            "uid": "42", "mailbox": "Private/Übersicht", "attachment_id": "1",
        }),
    ))
    assert result.is_error is False
    assert service.arguments["format"] == "file"
    link = next(block for block in result.content if block.type == "resource_link")
    embedded = next(block for block in result.content if block.type == "resource")
    assert link.name == "Rechnung März.pdf"
    assert link.size == len(PAYLOAD)
    assert link.mime_type == embedded.resource.mime_type == "application/pdf"
    assert link.uri == embedded.resource.uri == result.structured_content["resource_uri"]
    UUID(link.uri.rsplit("/", 1)[1])
    assert "Private" not in link.uri and "Rechnung" not in link.uri
    assert base64.b64decode(embedded.resource.blob, validate=True) == PAYLOAD
    assert "content_bytes" not in result.structured_content
    assert "blob" not in result.structured_content
    assert json.loads(result.content[0].text) == result.structured_content

    read = asyncio.run(server._handle_read_resource(None, ReadResourceRequestParams(uri=link.uri)))
    assert read.contents[0].mime_type == "application/pdf"
    assert base64.b64decode(read.contents[0].blob, validate=True) == PAYLOAD
    assert asyncio.run(server.list_resources()) == []
    templates = asyncio.run(server.list_resource_templates())
    assert templates[0].uri_template == "icloud-mail://attachments/{resource_id}"


def test_resource_snapshot_does_not_change_when_the_original_mail_changes() -> None:
    server = AttachmentMCPServer("test")
    first = server.attachment_result(file_result(b"first file"))
    second = server.attachment_result(file_result(b"replacement file"))
    first_uri = first.structured_content["resource_uri"]
    second_uri = second.structured_content["resource_uri"]
    assert first_uri != second_uri
    assert asyncio.run(server.read_resource(first_uri))[0].content == b"first file"
    assert asyncio.run(server.read_resource(second_uri))[0].content == b"replacement file"


def test_resource_expiry_and_unknown_ids_are_neutral(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr("app.mcp_resources.monotonic", lambda: now[0])
    server = AttachmentMCPServer("test")
    result = server.attachment_result(file_result())
    uri = result.structured_content["resource_uri"]
    assert asyncio.run(server.read_resource(uri))[0].content == PAYLOAD
    now[0] += 900
    for unknown_uri in (uri, "icloud-mail://attachments/not-issued"):
        with pytest.raises(ResourceNotFoundError, match="unknown or expired"):
            asyncio.run(server.read_resource(unknown_uri))
    assert server._attachment_resource_bytes == 0
    assert not server._attachment_resources


@pytest.mark.parametrize("maximum_bytes, maximum_entries", [(6, 64), (100, 1)])
def test_resource_capacity_eviction_bounds_memory(monkeypatch, maximum_bytes, maximum_entries) -> None:
    server = AttachmentMCPServer("test")
    monkeypatch.setattr(server, "_MAX_RESOURCE_BYTES", maximum_bytes)
    monkeypatch.setattr(server, "_MAX_RESOURCES", maximum_entries)
    first = server.attachment_result(file_result(b"first"))
    second = server.attachment_result(file_result(b"new"))
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(server.read_resource(first.structured_content["resource_uri"]))
    assert asyncio.run(server.read_resource(second.structured_content["resource_uri"]))[0].content == b"new"
    assert server._attachment_resource_bytes == 3


def test_unnamed_attachment_has_a_display_name() -> None:
    server = AttachmentMCPServer("test")
    result = server.attachment_result(file_result(filename=None))
    link = next(block for block in result.content if block.type == "resource_link")
    assert link.name == "attachment-1"


def _response_json(response) -> dict:
    assert response.status_code == 200
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        return next(json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: "))
    return response.json()


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_native_pdf_resource_round_trips_over_streamable_http(tmp_path: Path, path: str) -> None:
    app = create_app(tmp_path / "missing.yaml", environ={}, imap_service=FileMailService())
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app) as client:
        initialized = client.post(path, headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "pytest-file", "version": "1.0"},
            },
        })
        assert "resources" in _response_json(initialized)["result"]["capabilities"]
        headers["mcp-session-id"] = initialized.headers["mcp-session-id"]
        called = _response_json(client.post(path, headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "get_email_attachment", "arguments": {"uid": "42", "attachment_id": "1"},
            },
        }))["result"]
        assert called["isError"] is False
        embedded = next(block for block in called["content"] if block["type"] == "resource")["resource"]
        link = next(block for block in called["content"] if block["type"] == "resource_link")
        assert link["name"] == "Rechnung März.pdf"
        assert embedded["mimeType"] == "application/pdf"
        assert base64.b64decode(embedded["blob"], validate=True) == PAYLOAD
        read = _response_json(client.post(path, headers=headers, json={
            "jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": link["uri"]},
        }))["result"]
        assert read["contents"][0]["mimeType"] == "application/pdf"
        assert base64.b64decode(read["contents"][0]["blob"], validate=True) == PAYLOAD
