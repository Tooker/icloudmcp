"""Typed Drive tools shared by the main endpoint and private backend."""

import base64
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

from loguru import logger
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from app.drive_errors import DriveError
from app.drive_writes import WRITE_TOOLS, input_bytes
from app.timing import call_id, tool_trace


def register_drive_tools(server, service, *, native_files=True):
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write_annotations = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
    replace_annotations = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

    async def call(tool_name: str, **arguments):
        with tool_trace(tool_name):
            started = perf_counter()
            outcome = "cancelled"
            count = None
            logger.info("mcp_tool_start tool={} call_id={}", tool_name, call_id())
            try:
                if service is None:
                    if tool_name == "drive_status":
                        outcome = "not_configured"
                        return {"configured": False, "session_state": "not_configured", "read_only": True, "root_id": None, "capabilities": []}
                    raise DriveError("not_configured")
                if tool_name in {"upload_drive_file", "replace_drive_file"}:
                    source = arguments.pop("source_resource_uri", None)
                    if source is not None:
                        if arguments.get("content_text") is not None or arguments.get("content_base64") is not None or not isinstance(source, str):
                            raise DriveError("invalid_argument")
                        if not native_files:
                            raise DriveError("invalid_argument")
                        try:
                            data = server.file_snapshot_bytes(source)
                        except Exception:
                            raise DriveError("snapshot_expired") from None
                        arguments["content_base64"] = base64.b64encode(data).decode("ascii")
                    input_bytes(content_text=arguments.get("content_text"), content_base64=arguments.get("content_base64"))
                result = await service.call_tool(tool_name, {key: value for key, value in arguments.items() if value is not None})
                outcome = "ok"
                count = len(result["items"]) if "items" in result else len(result["files"]) if "files" in result else 1
                if tool_name == "get_drive_file" and result.get("format") == "file":
                    if not native_files:
                        # Avoid duplicating a potentially 40 MB JSON payload in
                        # both textual and structured MCP content.
                        return CallToolResult(structuredContent=result, content=[TextContent(type="text", text="Drive file downloaded.")])
                    encoded = result.get("content_base64")
                    if not isinstance(encoded, str) or len(encoded) > 40_000_000:
                        raise DriveError("protocol_error")
                    try:
                        data = base64.b64decode(encoded, validate=True)
                    except Exception:
                        raise DriveError("protocol_error") from None
                    if len(data) != result.get("size") or len(data) > 30_000_000 or sha256(data).hexdigest() != result.get("sha256"):
                        raise DriveError("protocol_error")
                    return server.drive_file_result({key: value for key, value in result.items() if key != "content_base64"} | {"content_bytes": data})
                return result
            except DriveError as error:
                outcome = error.code
                if tool_name in WRITE_TOOLS and not error.details:
                    error.details = {"operation": tool_name, "write_status": "not_started", "confirmed_steps": [], "uncertain_step": None}
                return error.as_result()
            except Exception:
                outcome = "backend_unavailable"
                return DriveError(outcome).as_result()
            finally:
                logger.info("mcp_tool_complete tool={} call_id={} outcome={} duration_ms={:.1f} result_count={}",
                            tool_name, call_id(), outcome, (perf_counter() - started) * 1000, count)

    @server.tool(annotations=annotations, description=(
        "Show safe Drive configuration, current session/access state, root_id and capabilities. "
        "Probes existing access only; never logs in or requests 2FA/ADP approval. "
        "auth_required/access_required need the separate administrative Drive CLI."
    ))
    async def drive_status() -> dict[str, Any]:
        return await call("drive_status")

    @server.tool(annotations=annotations, description=(
        "List one iCloud Drive folder by an issued folder_id; omitted means root. "
        "limit 1..500, offset pagination. IDs are opaque account-scoped references. "
        "Shared folders, app libraries and document packages are skipped; check coverage_complete/skipped_count."
    ))
    async def list_drive_items(folder_id: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await call("list_drive_items", folder_id=folder_id, limit=limit, offset=offset)

    @server.tool(annotations=annotations, description=(
        "Find files by case-insensitive filename substring under a folder. "
        "This is bounded folder traversal, not global or semantic content search. "
        "recursive=true, max_depth 0..10 (default 3), max_nodes 1..10000 (default 1000). "
        "limit 1..500; offset indexes matches. Check coverage_complete before concluding absence."
    ))
    async def search_drive_files(query: str, folder_id: str | None = None, recursive: bool = True,
                                 max_depth: int = 3, max_nodes: int = 1000, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await call("search_drive_files", query=query, folder_id=folder_id, recursive=recursive,
                          max_depth=max_depth, max_nodes=max_nodes, limit=limit, offset=offset)

    @server.tool(annotations=annotations, description=(
        "Download one Drive file by issued file_id, up to 30 MB. format=file (default) returns a complete "
        "native MCP file/resource, text extracts PDF/text, base64 returns original byte chunks. "
        "Text limit 1..100000 characters, base64 limit 1..1000000 bytes (default 20000). "
        "Pass the returned download version as expected_version on all later chunks/text pages; required "
        "for offset>0. Metadata and full-content versions are checked before exposing bytes. "
        "On version_changed discard previous chunks and restart. No arbitrary URLs or local paths accepted."
    ))
    async def get_drive_file(file_id: str, format: Literal["file", "text", "base64"] = "file",
                             offset: int = 0, limit: int = 20000, expected_version: str | None = None) -> dict[str, Any]:
        return await call("get_drive_file", file_id=file_id, format=format, offset=offset, limit=limit, expected_version=expected_version)

    @server.tool(annotations=write_annotations, title="Drive · Create folder", description=(
        "Create one named folder inside an issued folder_id (omitted=root). Refresh permissions and complete name coverage; "
        "reject collisions. Never replay a failed or uncertain write. Preserve returned folder_id even if readback fails."
    ))
    async def create_drive_folder(name: str, folder_id: str | None = None) -> dict[str, Any]:
        return await call("create_drive_folder", name=name, folder_id=folder_id)

    @server.tool(annotations=write_annotations, title="Drive · Upload file", description=(
        "Upload a new original file up to 30 MB into folder_id (omitted=root). Supply filename and exactly one of "
        "content_base64 (original bytes), content_text (UTF-8), or source_resource_uri (issued Mail/Drive snapshot). "
        "Reject existing names; never replace implicitly. Verify original bytes after activation. "
        "On failure preserve file_id/reserved_file_id and write_status; never retry automatically."
    ))
    async def upload_drive_file(filename: str, folder_id: str | None = None, content_base64: str | None = None,
                                content_text: str | None = None, source_resource_uri: str | None = None) -> dict[str, Any]:
        return await call("upload_drive_file", filename=filename, folder_id=folder_id, content_base64=content_base64,
                          content_text=content_text, source_resource_uri=source_resource_uri)

    @server.tool(annotations=replace_annotations, title="Drive · Replace file", description=(
        "Replace the contents of an owned regular file, up to 30 MB. Requires explicit confirm=true and expected_version "
        "from list_drive_items/get_drive_file. Supply exactly one of content_base64, content_text or source_resource_uri. "
        "First stage and verify new bytes, then move the original to native Trash with its fresh etag and rename the staged "
        "file to the original name. This is non-atomic and returns a NEW file ID. Preserve all IDs, original_in_trash, "
        "confirmed_steps and uncertain_step on failure. Never retry or roll back automatically."
    ))
    async def replace_drive_file(file_id: str, expected_version: str, confirm: bool = False, content_base64: str | None = None,
                                 content_text: str | None = None, source_resource_uri: str | None = None) -> dict[str, Any]:
        return await call("replace_drive_file", file_id=file_id, expected_version=expected_version, confirm=confirm,
                          content_base64=content_base64, content_text=content_text, source_resource_uri=source_resource_uri)
