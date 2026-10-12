"""Bounded Drive mutations, preserving every confirmed or uncertain step.

The protocol follows reviewed pyicloud 2.7 and rclone Drive sources. Replace
stages and verifies new bytes before moving the original to native Trash.
None of these calls retries or performs authentication/device approval.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from http.cookies import SimpleCookie
import json
import mimetypes
import re
from time import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.drive_errors import DriveError

WRITE_TOOLS = frozenset({"create_drive_folder", "upload_drive_file", "replace_drive_file"})
MAX_FILE_BYTES = 30_000_000


def input_bytes(*, content_base64=None, content_text=None):
    if (content_base64 is None) == (content_text is None):
        raise DriveError("invalid_argument")
    try:
        if content_text is not None:
            if not isinstance(content_text, str) or len(content_text) > MAX_FILE_BYTES:
                raise ValueError
            data = content_text.encode("utf-8")
        else:
            if not isinstance(content_base64, str) or len(content_base64) > 40_000_000:
                raise ValueError
            data = base64.b64decode(content_base64, validate=True)
        if len(data) > MAX_FILE_BYTES:
            raise DriveError("too_large")
        return data
    except DriveError:
        raise
    except Exception:
        raise DriveError("invalid_argument") from None


def _name(value):
    try:
        encoded_size = len(value.encode("utf-8")) if isinstance(value, str) else MAX_FILE_BYTES
    except UnicodeError:
        raise DriveError("invalid_argument") from None
    if (not isinstance(value, str) or not value.strip() or value in {".", ".."}
            or encoded_size > 255
            or any(char in value for char in ("/", "\\")) or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise DriveError("invalid_argument")
    return value


def _document_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value) is None:
        raise DriveError("protocol_error")
    return value


def _writable(node):
    permissions = node.get("permissions")
    flags = node.get("file_flags")
    if (node.get("isWritable") is False or node.get("isReadOnly") is True
            or isinstance(permissions, dict) and permissions.get("canWrite") is False
            or isinstance(flags, dict) and flags.get("is_writable") is False):
        raise DriveError("read_only")


def _complete(folder):
    count = folder.get("numberOfItems")
    if count is not None and (type(count) is not int or count > len(folder["items"])):
        raise DriveError("lookup_incomplete")


def _available(folder, name, *, ignore=None):
    _complete(folder)
    for item in folder["items"]:
        if item.get("drivewsid") == ignore:
            continue
        other = item.get("name")
        extension = item.get("extension")
        if not isinstance(other, str) or extension is not None and not isinstance(extension, str):
            raise DriveError("lookup_incomplete")
        if extension:
            other += "." + extension
        if other.casefold() == name.casefold():
            raise DriveError("conflict")


def _confirm(journal, step):
    journal["confirmed_steps"].append(step)
    journal["uncertain_step"] = None


class DriveWrites:
    async def call_write_tool(self, name, arguments):
        journal = {"operation": name, "write_status": "not_started", "confirmed_steps": [],
                   "uncertain_step": None, "readback_verified": False}
        if name == "replace_drive_file":
            journal.update({"original_file_id": arguments.get("file_id"), "original_in_trash": False,
                            "atomic": False, "preserves_file_id": False})
        try:
            async with self._operation() as state:
                state.remaining_bytes = max(state.remaining_bytes, self.config.max_file_bytes * 3 + 32_000_000)
                if name == "create_drive_folder":
                    result = await self._create_folder(state, journal, **arguments)
                elif name == "upload_drive_file":
                    result = await self._upload_file(state, journal, **arguments)
                else:
                    result = await self._replace_file(state, journal, **arguments)
                journal["write_status"] = "succeeded"
                return {**deepcopy(journal), **result}
        except DriveError as error:
            if journal["uncertain_step"]:
                journal["write_status"] = "uncertain"
                if journal["uncertain_step"] == "trash_original":
                    journal["original_in_trash"] = None
            elif journal.get("file_id") or journal.get("folder_id"):
                journal["write_status"] = "partial"
            elif journal["confirmed_steps"]:
                journal["write_status"] = "failed"
            raise DriveError(error.code, deepcopy(journal)) from None

    async def _fresh_folder(self, state, folder_id=None, *, native=None):
        native = native or state.session.resolve(folder_id)
        if not native.startswith("FOLDER::"):
            raise DriveError("invalid_argument")
        folder = await self._node(state, native)
        self._children(state.session, folder)
        _complete(folder)
        _writable(folder)
        return folder

    async def _write_json(self, state, journal, step, url, *, extra_params=None, **kwargs):
        from app.drive import MAX_METADATA_BYTES, safe_apple_url
        journal["uncertain_step"] = step
        async with state.client.stream("POST", safe_apple_url(url), params={**state.session.params, **(extra_params or {})}, **kwargs) as response:
            if response.status_code in (400, 401, 403, 404, 409, 412, 421, 429, 450):
                journal["uncertain_step"] = None
                code = {401: "auth_required", 421: "auth_required", 403: "access_required", 450: "access_required",
                        409: "conflict", 412: "conflict", 404: "not_found"}.get(response.status_code, "write_failed")
                raise DriveError(code)
            if response.status_code not in (200, 201):
                raise DriveError("write_uncertain")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                state.remaining_bytes -= len(chunk)
                if len(data) + len(chunk) > MAX_METADATA_BYTES or state.remaining_bytes < 0:
                    raise DriveError("too_large")
                data.extend(chunk)
            try:
                return json.loads(data)
            except Exception:
                raise DriveError("protocol_error") from None

    @staticmethod
    def _item_ack(payload, field, native=None, journal=None):
        items = payload.get(field) if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise DriveError("protocol_error")
        item = items[0]
        status = item.get("status")
        if status != "OK":
            if status in {"ETAG_CONFLICT", "NAME_CONFLICT", "NAME_EXISTS", "ALREADY_EXISTS", "EXISTS"}:
                if journal is not None:
                    journal["uncertain_step"] = None
                raise DriveError("conflict")
            if status in {"PERMISSION_DENIED", "ACCESS_DENIED"}:
                if journal is not None:
                    journal["uncertain_step"] = None
                raise DriveError("read_only")
            raise DriveError("write_failed")
        if native is not None and item.get("drivewsid") != native:
            raise DriveError("protocol_error")
        return item

    async def _create_folder(self, state, journal, name, folder_id=None):
        from app.drive import _validate_native
        _name(name)
        folder = await self._fresh_folder(state, folder_id)
        _available(folder, name)
        result = await self._write_json(state, journal, "create_folder", state.session.drive_url.rstrip("/") + "/createFolders",
                                        json={"destinationDrivewsId": folder["drivewsid"], "folders": [
                                            {"clientId": "FOLDER::UNKNOWN_ZONE::TempId-" + str(uuid4()), "name": name}]})
        item = self._item_ack(result, "folders", journal=journal)
        _validate_native(item.get("drivewsid"))
        if item.get("type") != "FOLDER":
            raise DriveError("protocol_error")
        journal["folder_id"] = state.session.issue_id(item["drivewsid"])
        _confirm(journal, "create_folder")
        # Preserve confirmed creation if subsequent readback is unavailable.
        try:
            fresh = await self._node(state, item["drivewsid"])
            public = self._public(state.session, fresh)
            if public["name"] != name:
                raise DriveError("conflict")
            journal["readback_verified"] = True
        except DriveError as error:
            if error.code == "conflict":
                raise
            public = {"id": journal["folder_id"], "name": name, "type": "folder"}
        return {"item": public}

    async def _send_upload(self, state, journal, url, filename, data):
        from app.drive import MAX_METADATA_BYTES, safe_apple_url
        url = safe_apple_url(url, asset=True)
        journal["uncertain_step"] = "upload_bytes"
        # Content hosts outside icloud.com never receive account cookies or
        # headers. Account-service uploads retain the authoritative jar scope.
        host = urlsplit(url).hostname
        account_host = host == "icloud.com" or host.endswith(".icloud.com") or host == "icloud.com.cn" or host.endswith(".icloud.com.cn")
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, trust_env=False, follow_redirects=False,
                                     transport=self._transport) as anonymous:
            client = state.client if account_host else anonymous
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            async with client.stream("POST", url, files={filename: (filename, data, mime)}) as response:
                if response.status_code in (400, 401, 403, 409, 412, 429):
                    journal["uncertain_step"] = None
                    raise DriveError("write_failed")
                if response.status_code not in (200, 201):
                    raise DriveError("write_uncertain")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    state.remaining_bytes -= len(chunk)
                    if len(body) + len(chunk) > MAX_METADATA_BYTES or state.remaining_bytes < 0:
                        raise DriveError("too_large")
                    body.extend(chunk)
                try:
                    info = json.loads(body)["singleFile"]
                    if not isinstance(info, dict) or int(info["size"]) != len(data):
                        raise ValueError
                    for key in ("fileChecksum", "referenceChecksum", "wrappingKey"):
                        if not isinstance(info[key], str) or not info[key] or len(info[key]) > 32768:
                            raise ValueError
                    if "receipt" in info and (not isinstance(info["receipt"], str) or len(info["receipt"]) > 32768):
                        raise ValueError
                except Exception:
                    raise DriveError("protocol_error") from None
                _confirm(journal, "upload_bytes")
                return info

    async def _stage_upload(self, state, journal, filename, folder, data):
        from app.drive import safe_apple_url
        native_parent = folder["drivewsid"]
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        endpoint = state.session.document_url.rstrip("/") + "/ws/com.apple.CloudDocs/upload/web"
        probe = httpx.Request("POST", endpoint)
        state.client.cookies.set_cookie_header(probe)
        cookies = SimpleCookie()
        cookies.load(probe.headers.get("Cookie", ""))
        validation = cookies.get("X-APPLE-WEBAUTH-VALIDATE")
        token = re.search(r"\bt=([^:]+)", validation.value) if validation is not None else None
        ticket = await self._write_json(state, journal, "reserve_upload", endpoint,
                                        extra_params={"token": token.group(1)} if token else None,
                                        headers={"Content-Type": "text/plain"}, json={"filename": filename, "type": "FILE",
                                                                                   "content_type": mime, "size": len(data)})
        if not isinstance(ticket, list) or len(ticket) != 1 or not isinstance(ticket[0], dict):
            raise DriveError("protocol_error")
        document = _document_id(ticket[0].get("document_id"))
        journal["reserved_file_id"] = state.session.issue_id("FILE::com.apple.CloudDocs::" + document, native_parent)
        _confirm(journal, "reserve_upload")
        upload_url = safe_apple_url(ticket[0].get("url"), asset=True)
        info = await self._send_upload(state, journal, upload_url, filename, data)
        # Refresh permissions and collisions again just before activation.
        folder = await self._fresh_folder(state, native=native_parent)
        _available(folder, filename)
        uploaded = {"signature": info["fileChecksum"], "reference_signature": info["referenceChecksum"],
                    "wrapping_key": info["wrappingKey"], "size": len(data)}
        if info.get("receipt"):
            uploaded["receipt"] = info["receipt"]
        stamp = int(time() * 1000)
        result = await self._write_json(state, journal, "commit_file",
                                        state.session.document_url.rstrip("/") + "/ws/com.apple.CloudDocs/update/documents",
                                        headers={"Content-Type": "text/plain"}, json={
                                            "command": "add_file", "document_id": document, "create_short_guid": True,
                                            "path": {"starting_document_id": native_parent.split("::", 2)[2], "path": filename},
                                            "allow_conflict": False, "data": uploaded, "mtime": stamp, "btime": stamp,
                                            "file_flags": {"is_writable": True, "is_executable": False, "is_hidden": False}})
        try:
            results = result["results"]
            if not isinstance(results, list) or len(results) != 1:
                raise ValueError
            entry = results[0]
            statuses = (result.get("status", {}), entry.get("status", {}))
            if any(status.get("status_code") not in (0, 200) for status in statuses):
                if all(type(status.get("status_code")) is int for status in statuses):
                    journal["uncertain_step"] = None
                raise DriveError("write_failed")
            item = entry["document"]
            if item.get("zone", "com.apple.CloudDocs") != "com.apple.CloudDocs" or item.get("type") != "FILE":
                raise ValueError
            native = "FILE::com.apple.CloudDocs::" + _document_id(item["document_id"])
        except DriveError:
            raise
        except Exception:
            raise DriveError("protocol_error") from None
        journal["file_id"] = state.session.issue_id(native, native_parent)
        _confirm(journal, "commit_file")
        return native, native_parent

    async def _verify_bytes(self, state, journal, native, parent, data):
        identifier = state.session.issue_id(native, parent)
        result = await self._file(state, identifier)
        if result["sha256"] != sha256(data).hexdigest() or result["size"] != len(data):
            raise DriveError("version_changed")
        journal["readback_verified"] = True
        return result

    async def _upload_file(self, state, journal, filename, folder_id=None, content_base64=None, content_text=None):
        _name(filename)
        data = input_bytes(content_base64=content_base64, content_text=content_text)
        if len(data) > self.config.max_file_bytes:
            raise DriveError("too_large")
        folder = await self._fresh_folder(state, folder_id)
        _available(folder, filename)
        native, parent = await self._stage_upload(state, journal, "codex-upload-" + uuid4().hex + ".tmp", folder, data)
        await self._verify_bytes(state, journal, native, parent, data)
        staged = await self._file_node(state, native, parent)
        folder = await self._fresh_folder(state, native=parent)
        _available(folder, filename)
        result = await self._write_json(state, journal, "rename_upload",
                                        state.session.drive_url.rstrip("/") + "/renameItems",
                                        json={"items": [{"drivewsid": native, "etag": staged["etag"], "name": filename}]})
        self._item_ack(result, "items", native, journal)
        _confirm(journal, "rename_upload")
        journal["readback_verified"] = False
        result = await self._verify_bytes(state, journal, native, parent, data)
        fresh = await self._file_node(state, native, parent)
        public = self._public(state.session, fresh, parent)
        if public["name"] != filename:
            raise DriveError("conflict")
        return {"item": public, "bytes_uploaded": len(data),
                "sha256": result["sha256"], "version": result["version"]}

    async def _replace_file(self, state, journal, file_id, expected_version, confirm=False, content_base64=None, content_text=None):
        if confirm is not True:
            raise DriveError("confirmation_required")
        if not isinstance(expected_version, str) or re.fullmatch(r"d[mv]_[0-9a-f]{64}", expected_version) is None:
            raise DriveError("invalid_argument")
        data = input_bytes(content_base64=content_base64, content_text=content_text)
        if len(data) > self.config.max_file_bytes:
            raise DriveError("too_large")
        original_native, parent = state.session.resolve_reference(file_id)
        original = await self._file_node(state, original_native, parent)
        parent = parent or original["_parent_native"]
        _writable(original)
        before = self._metadata_version(state.session, original)
        if expected_version.startswith("dm_") and expected_version != before:
            raise DriveError("conflict")
        if expected_version.startswith("dv_"):
            await self._file(state, file_id, expected_version=expected_version)
        filename = self._public(state.session, original)["name"]
        _name(filename)
        folder = await self._fresh_folder(state, native=parent)
        _available(folder, filename, ignore=original_native)
        staged_name = "codex-replacement-" + uuid4().hex + ".tmp"
        native, parent = await self._stage_upload(state, journal, staged_name, folder, data)
        journal["staged_file_id"] = journal["file_id"]
        verified = await self._verify_bytes(state, journal, native, parent, data)
        current = await self._file_node(state, original_native, parent)
        _writable(current)
        if before != self._metadata_version(state.session, current):
            raise DriveError("conflict")
        staged = await self._file_node(state, native, parent)
        _writable(staged)
        current_version = "dv_" + sha256((self._metadata_version(state.session, staged) + sha256(data).hexdigest()).encode()).hexdigest()
        if current_version != verified["version"]:
            raise DriveError("conflict")
        folder = await self._fresh_folder(state, native=parent)
        _available(folder, filename, ignore=original_native)
        # Native etags fence both changes. Never force/retry an etag conflict.
        result = await self._write_json(state, journal, "trash_original",
                                        state.session.drive_url.rstrip("/") + "/moveItemsToTrash",
                                        json={"items": [{"drivewsid": original_native, "etag": current["etag"], "clientId": original_native}]})
        self._item_ack(result, "items", original_native, journal)
        _confirm(journal, "trash_original")
        journal["original_in_trash"] = True
        journal["readback_verified"] = False
        # A concurrent file creation must produce a collision, not another replacement.
        folder = await self._fresh_folder(state, native=parent)
        _available(folder, filename)
        result = await self._write_json(state, journal, "rename_replacement",
                                        state.session.drive_url.rstrip("/") + "/renameItems",
                                        json={"items": [{"drivewsid": native, "etag": staged["etag"], "name": filename}]})
        self._item_ack(result, "items", native, journal)
        _confirm(journal, "rename_replacement")
        result = await self._verify_bytes(state, journal, native, parent, data)
        fresh = await self._file_node(state, native, parent)
        public = self._public(state.session, fresh, parent)
        if public["name"] != filename:
            raise DriveError("version_changed")
        return {"item": public, "bytes_uploaded": len(data), "sha256": result["sha256"], "version": result["version"]}
