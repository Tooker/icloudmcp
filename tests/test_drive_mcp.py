import asyncio
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket

from fastapi.testclient import TestClient
import httpx
from loguru import logger
from mcp_types import CallToolRequestParams
import pytest
import uvicorn

from app.drive import ICloudDriveService
from app.drive_backend import create_drive_app
from app.drive_client import DriveBackendClient
from app.drive_config import DriveBackendConfig, DriveConfig, load_drive_config
from app.drive_errors import DriveError
from app.main import create_app
from app.mcp_resources import AttachmentMCPServer
from app.mcp_server import create_mcp_server
from test_drive import AppleDrive, PAYLOAD, TOKEN, snapshot
from test_live_drive import probe_original_file
from test_drive_writes import AppleWrites
from app.mcp_groups import SERVICE_META, SERVICES


def invoke(server, name, **arguments):
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments)))


def test_drive_tools_are_read_only_and_not_configured_status_is_available():
    server = create_mcp_server(None)
    names = {"drive_status", "list_drive_items", "search_drive_files", "get_drive_file"}
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in names:
        assert tools[name].annotations.read_only_hint is True
        assert tools[name].annotations.destructive_hint is False
    assert invoke(server, "drive_status").structured_content["configured"] is False
    assert invoke(server, "list_drive_items").structured_content["error"]["code"] == "not_configured"
    assert not any("approve" in name or "login" in name for name in tools)
    for name in ("create_drive_folder", "upload_drive_file", "replace_drive_file"):
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.idempotent_hint is False
    assert tools["replace_drive_file"].annotations.destructive_hint is True


def test_service_groups_preserve_names_annotations_and_stable_catalogue():
    server = create_mcp_server(None)
    first = asyncio.run(server.list_tools())
    second = asyncio.run(server.list_tools())
    assert [tool.model_dump(by_alias=True) for tool in first] == [tool.model_dump(by_alias=True) for tool in second]
    assert all(tool.meta[SERVICE_META] in SERVICES for tool in first)
    sequence = [SERVICES.index(tool.meta[SERVICE_META]) for tool in first]
    assert sequence == sorted(sequence)
    assert next(tool for tool in first if tool.name == "create_event").title.startswith("Calendar · ")
    assert next(tool for tool in first if tool.name == "upload_drive_file").model_dump(by_alias=True)["_meta"][SERVICE_META] == "drive"


def test_write_mcp_bridge_copies_original_snapshot_and_replaces_with_new_id(tmp_path):
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleWrites()
    private = create_drive_app({"DRIVE_MCP_TOKEN": TOKEN}, service=ICloudDriveService(DriveBackendConfig(path), transport=httpx.MockTransport(apple)))

    async def exercise():
        async with private.router.lifespan_context(private):
            bridge = DriveBackendClient(DriveConfig("http://drive:8080/mcp", TOKEN), transport=httpx.ASGITransport(app=private))
            server = create_mcp_server(None, drive_service=bridge)
            async def tool(tool_name, **arguments):
                reply = await server._handle_call_tool(None, CallToolRequestParams(name=tool_name, arguments=arguments))
                assert not reply.is_error
                return reply.structured_content
            folder = await tool("create_drive_folder", name="Work")
            source = server.attachment_result({"filename": "source.bin", "attachment_id": "1", "content_type": "application/octet-stream", "content_bytes": bytes(range(256))})
            uploaded = await tool("upload_drive_file", filename="original.bin", folder_id=folder["folder_id"], source_resource_uri=source.structured_content["resource_uri"])
            assert uploaded["sha256"] == sha256(bytes(range(256))).hexdigest()
            replacement = await tool("replace_drive_file", file_id=uploaded["file_id"], expected_version=uploaded["version"], confirm=True, content_text="Updated contents")
            assert replacement["original_in_trash"] is True
            assert replacement["readback_verified"] is True
            assert replacement["sha256"] == sha256(b"Updated contents").hexdigest()
            assert replacement["item"]["name"] == "original.bin"
            read = await server._handle_call_tool(None, CallToolRequestParams(name="get_drive_file", arguments={"file_id": replacement["file_id"]}))
            uri = read.structured_content["resource_uri"]
            assert (await server.read_resource(uri))[0].content == b"Updated contents"
    asyncio.run(exercise())


def test_write_error_preserves_backend_progress_through_both_mcp_layers(tmp_path):
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleWrites()
    apple.fail = "trash_original"
    private = create_drive_app({"DRIVE_MCP_TOKEN": TOKEN}, service=ICloudDriveService(DriveBackendConfig(path), transport=httpx.MockTransport(apple)))

    async def exercise():
        async with private.router.lifespan_context(private):
            bridge = DriveBackendClient(DriveConfig("http://drive:8080/mcp", TOKEN), transport=httpx.ASGITransport(app=private))
            server = create_mcp_server(None, drive_service=bridge)
            listed = await server._handle_call_tool(None, CallToolRequestParams(name="list_drive_items", arguments={}))
            item = listed.structured_content["items"][0]
            reply = await server._handle_call_tool(None, CallToolRequestParams(name="replace_drive_file", arguments={
                "file_id": item["id"], "expected_version": item["version"], "confirm": True, "content_text": "Replacement"}))
            assert reply.is_error
            result = reply.structured_content
            assert result["write_status"] == "uncertain"
            assert result["uncertain_step"] == "trash_original"
            assert result["original_in_trash"] is None
            assert result["file_id"].startswith("di_")
            assert "commit_file" in result["confirmed_steps"]
            assert "PRIVATE" not in str(reply)
    asyncio.run(exercise())


def test_expired_or_ambiguous_upload_source_never_reaches_backend():
    class NeverCalled:
        async def call_tool(self, name, arguments):
            raise AssertionError("Invalid upload sources must not reach the backend")
    server = create_mcp_server(None, drive_service=NeverCalled())
    expired = invoke(server, "upload_drive_file", filename="file.txt", source_resource_uri="icloud-drive://files/expired")
    assert expired.structured_content["error"]["code"] == "snapshot_expired"
    assert expired.structured_content["write_status"] == "not_started"
    ambiguous = invoke(server, "upload_drive_file", filename="file.txt", source_resource_uri="icloud-drive://files/expired", content_text="new")
    assert ambiguous.structured_content["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize("binary", [False, True])
def test_full_python_bridge_private_mcp_apple_path_and_native_resources(tmp_path, monkeypatch, binary):
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleDrive()
    payload = bytes(range(256)) * 1024 if binary else PAYLOAD
    apple.payload = payload
    from test_drive import FILE
    apple.nodes[FILE]["size"] = len(payload)
    if binary:
        apple.nodes[FILE]["extension"] = "bin"

    def unexpected_conversion(*args, **kwargs):
        raise AssertionError("Original file downloads must never invoke text conversion")

    monkeypatch.setattr("app.drive.extract_attachment_text", unexpected_conversion)
    provider = ICloudDriveService(DriveBackendConfig(path), transport=httpx.MockTransport(apple))
    private = create_drive_app({"DRIVE_MCP_TOKEN": TOKEN}, service=provider)

    async def full_path():
        async with private.router.lifespan_context(private):
            bridge = DriveBackendClient(DriveConfig("http://drive:8080/mcp", TOKEN), transport=httpx.ASGITransport(app=private))
            public = create_mcp_server(None, drive_service=bridge)
            params = CallToolRequestParams(name="list_drive_items", arguments={})
            listed = await public._handle_call_tool(None, params)
            assert not listed.is_error
            identifier = listed.structured_content["items"][0]["id"]
            result = await public._handle_call_tool(None, CallToolRequestParams(name="get_drive_file", arguments={"file_id": identifier}))
            assert not result.is_error
            uri = result.structured_content["resource_uri"]
            assert uri.startswith("icloud-drive://files/")
            embedded = next(item for item in result.content if item.type == "resource")
            assert base64.b64decode(embedded.resource.blob) == payload
            assert (await public.read_resource(uri))[0].content == payload
            assert result.structured_content["sha256"] == sha256(payload).hexdigest()
            assert await public.list_resources() == []
            assert "content_base64" not in result.structured_content
            return result

    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        result = asyncio.run(full_path())
    finally:
        logger.remove(sink)
    text = "\n".join(logs)
    assert "mcp_tool_complete tool=get_drive_file" in text
    assert "drive_mcp_call" in text
    for marker in ("PRIVATE", "Rechnung", "file-123", result.structured_content["file_id"]):
        assert marker not in text


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_backend_requires_bearer_token_and_has_no_other_routes(tmp_path, path):
    private = create_drive_app({"DRIVE_MCP_TOKEN": TOKEN, "DRIVE_SESSION_PATH": str(tmp_path / "missing")})
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(private) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        for other in ("/", "/login", "/files", "/mcp/other"):
            assert client.get(other).status_code == 404
        assert client.post(path, json=initialize, headers=headers).status_code == 401
        assert client.post(path, json=initialize, headers={**headers, "Authorization": "Bearer wrong"}).status_code == 401
        assert client.post(path, json=initialize, headers={**headers, "Authorization": "Bearer " + TOKEN}).status_code == 200


def test_backend_failure_does_not_block_main_startup(tmp_path):
    app = create_app(tmp_path / "missing", environ={"DRIVE_MCP_URL": "http://drive:8080/mcp", "DRIVE_MCP_TOKEN": TOKEN})
    assert app.state.drive_service is not None
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


def test_mail_and_drive_share_snapshot_capacity_and_eviction(monkeypatch):
    server = AttachmentMCPServer("test")
    monkeypatch.setattr(server, "_MAX_RESOURCE_BYTES", 6)
    mail = server.attachment_result({"filename": "mail.txt", "attachment_id": "1", "content_type": "text/plain", "content_bytes": b"1234"})
    drive = server.drive_file_result({"filename": "drive.txt", "content_type": "text/plain", "content_bytes": b"5678"})
    assert server._attachment_resource_bytes == 4
    assert mail.structured_content["resource_uri"] not in server._attachment_resources
    assert drive.structured_content["resource_uri"] in server._attachment_resources
    templates = asyncio.run(server.list_resource_templates())
    assert {template.name for template in templates} == {"mail_attachment", "drive_file"}


def test_bridge_sanitizes_errors_and_never_retries(tmp_path):
    messages = []
    async def handler(request):
        message = json.loads(request.content)
        messages.append(message)
        if message["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18"}
        elif message["method"] == "notifications/initialized":
            return httpx.Response(202)
        else:
            result = {"isError": True, "structuredContent": {"error": {"code": "access_required", "message": "PRIVATE_ERROR"}},
                      "content": [{"type": "text", "text": "PRIVATE_ERROR"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})
    bridge = DriveBackendClient(DriveConfig("http://drive:8080/mcp", TOKEN), transport=httpx.MockTransport(handler))
    result = invoke(create_mcp_server(None, drive_service=bridge), "list_drive_items")
    assert result.is_error
    assert result.structured_content["error"]["code"] == "access_required"
    assert "PRIVATE_ERROR" not in str(result)
    assert len([message for message in messages if message["method"] == "tools/call"]) == 1


@pytest.mark.parametrize("env", [
    {"DRIVE_MCP_URL": "https://user:secret@example.com/mcp", "DRIVE_MCP_TOKEN": TOKEN},
    {"DRIVE_MCP_URL": "http://drive:8080/other", "DRIVE_MCP_TOKEN": TOKEN},
    {"DRIVE_MCP_URL": "http://drive:8080/mcp", "DRIVE_MCP_TOKEN": "short"},
    {"DRIVE_MCP_URL": "http://drive:8080/mcp", "DRIVE_MCP_TOKEN": TOKEN, "REMINDERS_MCP_TOKEN": TOKEN},
])
def test_drive_configuration_rejects_invalid_endpoints_and_token_reuse(env):
    with pytest.raises(ValueError):
        load_drive_config(env)


def test_drive_configuration_has_no_apple_password_fallback():
    assert load_drive_config({"ICLOUD_USERNAME": "user", "ICLOUD_APP_PASSWORD": "password"}) is None


def test_original_file_smoke_uses_real_http_mcp_client_and_resource_read(tmp_path):
    """Exercise the live probe over loopback HTTP with a simulated Apple source."""
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleDrive()
    from test_drive import FILE
    binary = bytes(range(256)) * 1024
    apple.payload = binary
    apple.nodes[FILE].update(size=len(binary), extension="bin")
    provider = ICloudDriveService(DriveBackendConfig(path), transport=httpx.MockTransport(apple))
    private = create_drive_app({"DRIVE_MCP_TOKEN": TOKEN}, service=provider)

    async def smoke():
        async with private.router.lifespan_context(private):
            bridge = DriveBackendClient(DriveConfig("http://drive:8080/mcp", TOKEN), transport=httpx.ASGITransport(app=private))
            app = create_app(tmp_path / "missing.yaml", environ={}, drive_service=bridge)
            connection = socket.socket()
            connection.bind(("127.0.0.1", 0))
            port = connection.getsockname()[1]
            web = uvicorn.Server(uvicorn.Config(app, access_log=False, log_config=None, ws="none"))
            task = asyncio.create_task(web.serve(sockets=[connection]))
            try:
                async with asyncio.timeout(20):
                    while not web.started:
                        if task.done():
                            await task
                            raise AssertionError("Local MCP test server stopped before startup")
                        await asyncio.sleep(0.01)
                    return await probe_original_file(f"http://127.0.0.1:{port}/mcp")
            finally:
                web.should_exit = True
                await asyncio.wait_for(task, timeout=5)
                connection.close()

    result = asyncio.run(smoke())
    assert result["session_state"] == "ready"
    assert result["original_verified"] is True
    assert result["files_sampled"] == 1
    assert result["bytes_checked"] == len(binary)
