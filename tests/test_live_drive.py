"""Opt-in, content-free original-file smoke through the deployed main MCP.

Never performs authentication, requests approval or writes to iCloud. A
small owned file is sampled from at most ten folder pages; optionally select
an exact previously issued file ID through LIVE_DRIVE_FILE_ID.
"""

import asyncio
import base64
from collections import deque
from hashlib import sha256
import os

from mcp import Client
import pytest

from app.reminders import quiet_transport_logs

pytestmark = pytest.mark.live
DRIVE_TOOLS = {"drive_status", "list_drive_items", "search_drive_files", "get_drive_file"}


async def probe_original_file(endpoint: str, file_id: str | None = None) -> dict:
    with quiet_transport_logs():
        async with asyncio.timeout(180):
            async with Client(endpoint, mode="legacy", read_timeout_seconds=90, cache=None) as client:
                tools = await client.list_tools()
                if not DRIVE_TOOLS <= {tool.name for tool in tools.tools}:
                    raise AssertionError("The deployed endpoint does not advertise all Drive tools")
                status = await client.call_tool("drive_status", {})
                if status.is_error or not isinstance(status.structured_content, dict):
                    raise AssertionError("Drive status could not be read; no private response logged")
                state = status.structured_content.get("session_state")
                safe_states = {"ready", "not_configured", "auth_required", "access_required", "backend_unavailable", "backend_auth_failed", "timeout", "protocol_error", "unsafe_target", "not_found", "too_large", "unsupported_item"}
                if state not in safe_states:
                    raise AssertionError("Drive returned an unsupported session state")
                if state != "ready":
                    return {"session_state": state, "files_sampled": 0, "folders_read": 0, "original_verified": False}
                folders_read = 0
                metadata_version = None
                if file_id is None:
                    queue = deque([None])
                    seen = set()
                    while queue and folders_read < 10 and file_id is None:
                        folder = queue.popleft()
                        if folder in seen:
                            continue
                        seen.add(folder)
                        arguments = {"limit": 100}
                        if folder is not None:
                            arguments["folder_id"] = folder
                        page = await client.call_tool("list_drive_items", arguments)
                        if page.is_error or not isinstance(page.structured_content, dict):
                            raise AssertionError("Live Drive folder read failed; no folder details logged")
                        items = page.structured_content.get("items")
                        if not isinstance(items, list):
                            raise AssertionError("Live Drive returned an invalid folder page")
                        folders_read += 1
                        for item in items:
                            if not isinstance(item, dict):
                                raise AssertionError("Live Drive returned invalid item metadata")
                            size = item.get("size")
                            if item.get("type") == "file" and type(size) is int and 0 < size <= 1_000_000:
                                file_id = item.get("id")
                                metadata_version = item.get("version")
                                break
                            if item.get("type") == "folder" and len(queue) < 10:
                                queue.append(item.get("id"))
                if file_id is None:
                    return {"session_state": "ready", "files_sampled": 0, "folders_read": folders_read,
                            "original_verified": False, "sample_state": "no_small_file_in_sampled_pages"}
                arguments = {"file_id": file_id, "format": "file"}
                if metadata_version is not None:
                    arguments["expected_version"] = metadata_version
                result = await client.call_tool("get_drive_file", arguments)
                if result.is_error or not isinstance(result.structured_content, dict):
                    raise AssertionError("Live original-file download failed; no file details logged")
                metadata = result.structured_content
                embedded = next((block for block in result.content if block.type == "resource"), None)
                link = next((block for block in result.content if block.type == "resource_link"), None)
                if embedded is None or link is None or not hasattr(embedded.resource, "blob"):
                    raise AssertionError("The original file is missing native MCP binary content or its link")
                try:
                    original = base64.b64decode(embedded.resource.blob, validate=True)
                except Exception:
                    raise AssertionError("The original file has invalid transport encoding") from None
                if len(original) != metadata.get("size") or sha256(original).hexdigest() != metadata.get("sha256"):
                    raise AssertionError("Native original bytes do not match their size/checksum")
                uri = metadata.get("resource_uri")
                if not isinstance(uri, str) or not uri.startswith("icloud-drive://files/") or str(link.uri) != uri:
                    raise AssertionError("Invalid native Drive resource reference")
                snapshot = await client.read_resource(uri)
                if len(snapshot.contents) != 1 or not hasattr(snapshot.contents[0], "blob"):
                    raise AssertionError("Drive resources/read did not return original binary data")
                try:
                    snapshot_bytes = base64.b64decode(snapshot.contents[0].blob, validate=True)
                except Exception:
                    raise AssertionError("The Drive snapshot has invalid transport encoding") from None
                if snapshot_bytes != original:
                    raise AssertionError("The Drive resource differs from the original download")
                return {"session_state": "ready", "files_sampled": 1, "folders_read": folders_read,
                        "original_verified": True, "bytes_checked": len(original)}


def test_live_drive_original_file():
    if os.environ.get("RUN_LIVE_DRIVE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_DRIVE_TESTS=1 for a read-only original-file test")
    try:
        result = asyncio.run(probe_original_file(
            os.environ.get("LIVE_DRIVE_MCP_URL", "http://127.0.0.1:8080/mcp"),
            os.environ.get("LIVE_DRIVE_FILE_ID") or None,
        ))
    except AssertionError:
        raise
    except Exception as error:
        raise AssertionError(f"Live Drive smoke failed: {type(error).__name__}; no private details logged") from None
    if result["session_state"] != "ready":
        raise AssertionError("Drive is not ready: " + result["session_state"] + "; complete administrative login/approval first")
    if result["files_sampled"] == 0:
        pytest.skip("Drive access is ready; no small owned file in the bounded sample, set LIVE_DRIVE_FILE_ID")
    print("Read-only Drive original-file smoke passed: files=1 folders={} bytes={} checksum_and_resource=verified".format(
        result["folders_read"], result["bytes_checked"],
    ))
