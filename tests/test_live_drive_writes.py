"""Explicit opt-in writes confined to a freshly created test folder/file.

Creates one folder, uploads new bytes, then replaces ONLY that newly-created
file. It leaves the folder/new file and original in Trash for inspection.
Never replays, authenticates, requests approval, deletes folders or touches
pre-existing files. No names, IDs, URLs or file contents appear in output.
"""

import asyncio
from hashlib import sha256
import os
from uuid import uuid4

from mcp import Client
import pytest

from app.drive_errors import MESSAGES
from app.reminders import quiet_transport_logs
from test_live_drive import probe_original_file

pytestmark = pytest.mark.live


async def probe_write_cycle(endpoint):
    with quiet_transport_logs():
        async with asyncio.timeout(240):
            async with Client(endpoint, mode="legacy", read_timeout_seconds=100, cache=None) as client:
                status = await client.call_tool("drive_status", {})
                if status.is_error or (status.structured_content or {}).get("session_state") != "ready":
                    raise AssertionError("Drive session is not ready for the explicitly requested write test")
                async def write(tool_name, arguments):
                    result = await client.call_tool(tool_name, arguments)
                    payload = result.structured_content
                    if result.is_error or not isinstance(payload, dict) or payload.get("write_status") != "succeeded":
                        code = (payload or {}).get("error", {}).get("code") if isinstance(payload, dict) else None
                        safe_code = code if isinstance(code, str) and code in MESSAGES else "unknown"
                        raise AssertionError("Drive write test stopped without replay: " + tool_name + "; " + safe_code)
                    return payload
                folder = await write("create_drive_folder", {"name": "Codex Drive Test " + uuid4().hex[:12]})
                folder_id = folder.get("folder_id")
                if not isinstance(folder_id, str):
                    raise AssertionError("Confirmed test-folder creation did not return a usable reference")
                original = "MCP original-byte upload test\n"
                updated = "MCP replacement-byte test\nUpdated via existing Go login.\n"
                uploaded = await write("upload_drive_file", {"folder_id": folder_id, "filename": "original-byte-test.txt", "content_text": original})
                if uploaded.get("sha256") != sha256(original.encode()).hexdigest() or uploaded.get("readback_verified") is not True:
                    raise AssertionError("The newly uploaded test file failed its original-byte checksum")
                identifier, version = uploaded.get("file_id"), uploaded.get("version")
                if not isinstance(identifier, str) or not isinstance(version, str):
                    raise AssertionError("Confirmed test upload did not return a file/version reference")
                # Only replace the file created in this invocation.
                replaced = await write("replace_drive_file", {"file_id": identifier, "expected_version": version, "confirm": True, "content_text": updated})
                if (replaced.get("sha256") != sha256(updated.encode()).hexdigest() or replaced.get("readback_verified") is not True
                        or replaced.get("original_in_trash") is not True):
                    raise AssertionError("Replacement of the newly created test file was not fully verified")
                new_id = replaced.get("file_id")
                if not isinstance(new_id, str):
                    raise AssertionError("Confirmed replacement did not return its new file reference")
            readback = await probe_original_file(endpoint, new_id)
            if readback.get("original_verified") is not True or readback.get("bytes_checked") != len(updated.encode()):
                raise AssertionError("The replacement test file did not round-trip as a native MCP resource")
            return {"folders_created": 1, "files_uploaded": 1, "files_replaced": 1, "bytes_verified": len(updated.encode()),
                    "native_resource_verified": True, "original_preserved_in_trash": True, "preexisting_files_modified": 0}


def test_live_drive_write_cycle():
    if os.environ.get("RUN_LIVE_DRIVE_WRITE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_DRIVE_WRITE_TESTS=1 to explicitly create and replace one new test file")
    try:
        result = asyncio.run(probe_write_cycle(os.environ.get("LIVE_DRIVE_MCP_URL", "http://127.0.0.1:8080/mcp")))
    except AssertionError:
        raise
    except Exception as error:
        raise AssertionError("Drive write test stopped: " + type(error).__name__ + "; no replay or private details logged") from None
    print("Isolated Drive write smoke passed:", result)
