"""Bounded, fresh MCP sessions to our JSON-only private Drive backend."""

import asyncio
import json

import httpx

from app.http_privacy import quiet_transport as _quiet_transport
from app.drive import DRIVE_TOOLS
from app.drive_writes import WRITE_TOOLS
from app.drive_config import DriveConfig
from app.drive_errors import DriveError
from app.timing import measure_phase


class DriveBackendClient:
    def __init__(self, config: DriveConfig, *, transport=None):
        self.config = config
        self._transport = transport

    async def call_tool(self, name, arguments):
        if name not in DRIVE_TOOLS:
            raise DriveError("invalid_argument")
        dispatched = False
        headers = {"Authorization": "Bearer " + self.config.token,
                   "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        try:
            with _quiet_transport(), measure_phase("drive_mcp_call"):
                async with asyncio.timeout(self.config.timeout_seconds), httpx.AsyncClient(headers=headers, timeout=self.config.timeout_seconds,
                                             follow_redirects=False, trust_env=False, transport=self._transport) as client:
                    initialized, response_headers = await self._request(client, {
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "icloud-drive-bridge", "version": "1.0"}},
                    }, maximum=1_000_000)
                    protocol = initialized.get("result", {}).get("protocolVersion")
                    if protocol not in ("2025-06-18", "2025-11-25", "2026-07-28"):
                        raise DriveError("protocol_error")
                    client.headers["MCP-Protocol-Version"] = protocol
                    session_id = response_headers.get("mcp-session-id")
                    if session_id:
                        client.headers["Mcp-Session-Id"] = session_id
                    try:
                        await self._request(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, maximum=1_000_000, notification=True)
                        dispatched = True
                        reply, _ = await self._request(client, {
                            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        }, maximum=42_000_000 if name == "get_drive_file" else 8_000_000)
                    finally:
                        # Our backend is stateless. Stateful compatible backends
                        # can release their session; failure never replays a call.
                        if session_id:
                            try:
                                async with client.stream("DELETE", self.config.mcp_url):
                                    pass
                            except Exception:
                                pass
                    result = reply.get("result")
                    if not isinstance(result, dict) or not isinstance(result.get("structuredContent"), dict):
                        raise DriveError("protocol_error")
                    payload = result["structuredContent"]
                    if result.get("isError"):
                        error = payload.get("error")
                        details = self._write_details(payload) if name in WRITE_TOOLS else None
                        raise DriveError(error.get("code") if isinstance(error, dict) else "backend_unavailable", details)
                    return payload
        except DriveError as error:
            if name in WRITE_TOOLS and not error.details:
                error.details = self._unknown_write(name, dispatched and error.code != "backend_auth_failed", arguments)
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise DriveError("timeout", self._unknown_write(name, dispatched, arguments) if name in WRITE_TOOLS else None) from None
        except Exception:
            raise DriveError("backend_unavailable", self._unknown_write(name, dispatched, arguments) if name in WRITE_TOOLS else None) from None

    @staticmethod
    def _unknown_write(name, dispatched, arguments):
        details = {"operation": name, "write_status": "uncertain" if dispatched else "not_started",
                   "uncertain_step": "backend_call" if dispatched else None, "confirmed_steps": [], "readback_verified": False}
        if name == "replace_drive_file":
            details.update({"original_file_id": arguments.get("file_id"), "original_in_trash": None if dispatched else False,
                            "atomic": False, "preserves_file_id": False})
        return details

    @staticmethod
    def _write_details(payload):
        details = {}
        for key in ("file_id", "folder_id", "staged_file_id", "reserved_file_id", "original_file_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("di_") and len(value) <= 4096:
                details[key] = value
        for key in ("original_in_trash", "readback_verified", "atomic", "preserves_file_id"):
            if type(payload.get(key)) is bool:
                details[key] = payload[key]
        if "original_in_trash" in payload and payload["original_in_trash"] is None:
            details["original_in_trash"] = None
        if isinstance(payload.get("operation"), str) and payload["operation"] in WRITE_TOOLS:
            details["operation"] = payload["operation"]
        if isinstance(payload.get("write_status"), str) and payload["write_status"] in {"not_started", "failed", "partial", "uncertain", "succeeded"}:
            details["write_status"] = payload["write_status"]
        steps = {"create_folder", "reserve_upload", "upload_bytes", "commit_file", "rename_upload", "trash_original", "rename_replacement", "backend_call"}
        value = payload.get("confirmed_steps")
        if isinstance(value, list) and len(value) <= 16 and all(isinstance(step, str) and step in steps for step in value):
            details["confirmed_steps"] = value
        if isinstance(payload.get("uncertain_step"), str) and payload["uncertain_step"] in steps or payload.get("uncertain_step") is None:
            details["uncertain_step"] = payload.get("uncertain_step")
        return details if "write_status" in details else {}

    async def _request(self, client, message, *, maximum, notification=False):
        async with client.stream("POST", self.config.mcp_url, json=message) as response:
            if response.status_code in (401, 403):
                raise DriveError("backend_auth_failed")
            if notification:
                if response.status_code not in (200, 202, 204):
                    raise DriveError("backend_unavailable")
                return {}, response.headers
            if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("application/json"):
                raise DriveError("backend_unavailable")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > maximum:
                    raise DriveError("too_large")
                body.extend(chunk)
            try:
                reply = json.loads(body)
                if reply.get("jsonrpc") != "2.0" or reply.get("id") != message["id"] or "error" in reply:
                    raise ValueError
                return reply, response.headers
            except Exception:
                raise DriveError("protocol_error") from None
