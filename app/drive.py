"""An iCloud web protocol adapter, using administratively exported cookies.

No authenticator or password is loaded at runtime. In particular this
adapter cannot call login, requestPCS, trust or device-consent endpoints.
The read endpoints follow the reviewed pyicloud 2.7.0 Drive implementation.
"""

from __future__ import annotations

import asyncio
import base64
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.message import Message
from hashlib import sha256
from http.cookiejar import Cookie, DefaultCookiePolicy
import json
import mimetypes
from pathlib import Path
import re
from time import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from cryptography.fernet import Fernet
import httpx

from app.http_privacy import quiet_transport as _quiet_transport
from app.drive_config import DriveBackendConfig
from app.drive_errors import DriveError
from app.drive_writes import DriveWrites, WRITE_TOOLS
from app.mail_attachments import extract_attachment_text
from app.timing import measure_phase

ROOT = "FOLDER::com.apple.CloudDocs::root"
MAX_METADATA_BYTES = 8_000_000
MAX_OPERATION_BYTES = 64_000_000
READ_TOOLS = frozenset({"drive_status", "list_drive_items", "search_drive_files", "get_drive_file"})
DRIVE_TOOLS = READ_TOOLS | WRITE_TOOLS


def safe_apple_url(url: str, *, asset: bool = False) -> str:
    try:
        parsed = urlsplit(url)
        domains = ("icloud.com", "icloud.com.cn") + (("icloud-content.com", "icloud-content.com.cn") if asset else ())
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or parsed.fragment or (parsed.query and not asset)
                or any(ord(char) <= 32 or char == "\\" for char in url)
                or not any(host == domain or host.endswith("." + domain) for domain in domains)):
            raise ValueError
        return str(httpx.URL(url))
    except (ValueError, TypeError):
        raise DriveError("unsafe_target") from None


@dataclass(frozen=True, repr=False)
class DriveSession:
    account_key: str
    id_key: bytes
    drive_url: str
    document_url: str
    params: dict[str, str]
    cookies: list[dict[str, Any]]
    user_agent: str = "icloud-cruncher-drive"

    @classmethod
    def load(cls, path: Path):
        try:
            with path.open("rb") as file:
                data = file.read(1_000_001)
            if len(data) > 1_000_000:
                raise ValueError
            raw = json.loads(data)
            if raw["version"] != 1 or re.fullmatch(r"[0-9a-f]{64}", raw["account_key"]) is None:
                raise ValueError
            key = raw["id_key"].encode("ascii")
            Fernet(key)
            params = raw["params"]
            if not isinstance(params, dict) or not params.get("dsid") or len(params) > 20:
                raise ValueError
            if any(not isinstance(key, str) or not isinstance(value, str) or len(key) > 100 or len(value) > 4096 for key, value in params.items()):
                raise ValueError
            cookies = raw["cookies"]
            if not isinstance(cookies, list) or not cookies or len(cookies) > 100:
                raise ValueError
            for cookie in cookies:
                domain = cookie["domain"].lstrip(".")
                safe_apple_url("https://" + domain + "/")
                if not isinstance(cookie["name"], str) or not isinstance(cookie["value"], str):
                    raise ValueError
                if len(cookie["name"]) > 256 or len(cookie["value"]) > 32768 or not cookie["path"].startswith("/"):
                    raise ValueError
                if cookie.get("expires") is not None and type(cookie["expires"]) not in (int, float):
                    raise ValueError
                if any(key in cookie and type(cookie[key]) is not bool for key in ("host_only", "secure")):
                    raise ValueError
            agent = raw.get("user_agent", "icloud-cruncher-drive")
            if not isinstance(agent, str) or not 1 <= len(agent) <= 1024 or any(ord(char) < 32 or ord(char) > 126 for char in agent):
                raise ValueError
            return cls(raw["account_key"], key, safe_apple_url(raw["drive_url"]),
                       safe_apple_url(raw["document_url"]), params, cookies, agent)
        except DriveError:
            raise
        except Exception:
            raise DriveError("auth_required") from None

    def issue_id(self, native: str, parent: str | None = None) -> str:
        reference = [self.account_key, native]
        if parent is not None:
            reference.append(parent)
        return "di_" + Fernet(self.id_key).encrypt(json.dumps(reference).encode()).decode("ascii")

    def resolve(self, item_id: str | None) -> str:
        return self.resolve_reference(item_id)[0]

    def resolve_reference(self, item_id: str | None) -> tuple[str, str | None]:
        if item_id is None:
            return ROOT, None
        try:
            if not isinstance(item_id, str) or not item_id.startswith("di_") or len(item_id) > 4096:
                raise ValueError
            reference = json.loads(Fernet(self.id_key).decrypt(item_id[3:].encode("ascii")))
            if not isinstance(reference, list) or len(reference) not in (2, 3):
                raise ValueError
            account, native = reference[:2]
            if account != self.account_key:
                raise ValueError
            _validate_native(native)
            parent = reference[2] if len(reference) == 3 else None
            if parent is not None:
                _validate_native(parent)
                if not parent.startswith("FOLDER::"):
                    raise ValueError
            return native, parent
        except Exception:
            raise DriveError("invalid_argument") from None


def _validate_native(native: str):
    if not isinstance(native, str) or re.fullmatch(r"(?:FILE|FOLDER)::com\.apple\.CloudDocs::[A-Za-z0-9_-]{1,256}", native) is None:
        raise DriveError("unsupported_item")


@dataclass
class _Operation:
    session: DriveSession
    client: httpx.AsyncClient
    remaining_bytes: int = MAX_OPERATION_BYTES


class ICloudDriveService(DriveWrites):
    def __init__(self, config: DriveBackendConfig, *, transport=None):
        self.config = config
        self._transport = transport

    @asynccontextmanager
    async def _operation(self):
        try:
            with _quiet_transport(), measure_phase("drive_service"):
                async with asyncio.timeout(self.config.timeout_seconds):
                    async with self._session_operation() as state:
                        yield state
        except DriveError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise DriveError("timeout") from None
        except Exception:
            raise DriveError("backend_unavailable") from None

    @asynccontextmanager
    async def _session_operation(self):
        session = await asyncio.to_thread(DriveSession.load, self.config.session_path)
        cookies = httpx.Cookies()
        cookies.jar.set_policy(DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
        for cookie in session.cookies:
            if cookie.get("expires") is not None and cookie["expires"] <= time():
                continue
            domain = cookie["domain"]
            host_only = cookie.get("host_only", False)
            cookies.jar.set_cookie(Cookie(
                0, cookie["name"], cookie["value"], None, False, domain,
                not host_only, domain.startswith("."), cookie["path"], True,
                cookie.get("secure", True), cookie.get("expires"), cookie.get("expires") is None,
                None, None, {},
            ))
        if not cookies:
            raise DriveError("auth_required")
        home = "https://www.icloud.com.cn" if urlsplit(session.drive_url).hostname.endswith(".com.cn") else "https://www.icloud.com"

        async def scoped_cookies(request):
            # HTTPX copies jars while merging request cookies and does not
            # retain a custom host-only policy in those copies. Apply the
            # authoritative scoped jar immediately before transmission.
            request.headers.pop("Cookie", None)
            client.cookies.set_cookie_header(request)

        async with httpx.AsyncClient(
            cookies=cookies, headers={"Origin": home, "Referer": home + "/", "User-Agent": session.user_agent, "Accept-Encoding": "identity"},
            timeout=self.config.timeout_seconds, trust_env=False, follow_redirects=False, transport=self._transport,
            event_hooks={"request": [scoped_cookies]},
        ) as client:
            client.cookies.jar.set_policy(DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
            yield _Operation(session, client)

    async def _response(self, state, client, method, url, *, maximum, **kwargs):
        with measure_phase("drive_request"):
            async with client.stream(method, url, **kwargs) as response:
                return await self._consume(state, response, maximum)

    @staticmethod
    async def _consume(state, response, maximum):
        if response.status_code in (401, 421):
            raise DriveError("auth_required")
        if response.status_code in (403, 450):
            raise DriveError("access_required")
        if response.status_code == 404:
            raise DriveError("not_found")
        if response.status_code != 200:
            raise DriveError("backend_unavailable")
        result = bytearray()
        async for chunk in response.aiter_bytes():
            state.remaining_bytes -= len(chunk)
            if len(result) + len(chunk) > maximum or state.remaining_bytes < 0:
                raise DriveError("too_large")
            result.extend(chunk)
        return bytes(result)

    async def _download(self, state, url):
        # Only a signed asset URL reaches this cookie-free client.
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, trust_env=False, follow_redirects=False,
                                     transport=self._transport, headers={"Accept-Encoding": "identity"}) as anonymous:
            for attempt in range(4):
                with measure_phase("drive_download"):
                    async with anonymous.stream("GET", safe_apple_url(url, asset=True)) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if attempt == 3 or not location:
                                raise DriveError("protocol_error")
                            url = safe_apple_url(urljoin(url, location), asset=True)
                            continue
                        return await self._consume(state, response, self.config.max_file_bytes)
        raise DriveError("protocol_error")

    async def _json(self, state, method, url, *, document_id=None, **kwargs):
        params = dict(state.session.params)
        if document_id is not None:
            params["document_id"] = document_id
        data = await self._response(state, state.client, method, safe_apple_url(url),
                                    maximum=MAX_METADATA_BYTES, params=params, **kwargs)
        try:
            return json.loads(data)
        except Exception:
            raise DriveError("protocol_error") from None

    async def _node(self, state, native):
        _validate_native(native)
        if not native.startswith("FOLDER::"):
            raise DriveError("invalid_argument")
        nodes = await self._json(state, "POST", state.session.drive_url.rstrip("/") + "/retrieveItemDetailsInFolders",
                                 json=[{"drivewsid": native, "partialData": False}])
        if not isinstance(nodes, list) or len(nodes) != 1 or not isinstance(nodes[0], dict):
            raise DriveError("protocol_error")
        node = nodes[0]
        status = node.get("status")
        if status in ("ID_INVALID", "NOT_FOUND"):
            raise DriveError("not_found")
        if status in ("ACCESS_DENIED", "PERMISSION_DENIED"):
            raise DriveError("access_required")
        if status not in (None, "OK") or node.get("drivewsid") != native:
            raise DriveError("protocol_error")
        self._supported(node)
        return node

    @staticmethod
    def _supported(node):
        _validate_native(node.get("drivewsid"))
        if (node.get("type") not in ("FILE", "FOLDER") or node.get("zone", "com.apple.CloudDocs") != "com.apple.CloudDocs"
                or any(node.get(key) for key in ("share", "shareID", "isShared", "isPackage", "isAppLibrary", "owner"))):
            raise DriveError("unsupported_item")

    @staticmethod
    def _metadata_version(session, node):
        etag = node.get("etag")
        if not isinstance(etag, str) or not etag or len(etag) > 512:
            raise DriveError("protocol_error")
        identity = [session.account_key, node["drivewsid"], etag, node.get("size"), node.get("dateModified"), node.get("docwsid")]
        return "dm_" + sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def _public(self, session, node, parent=None):
        self._supported(node)
        name = node.get("name", "root" if node["drivewsid"] == ROOT else "")
        extension = node.get("extension")
        if not isinstance(name, str) or len(name) > 4096 or (extension is not None and not isinstance(extension, str)):
            raise DriveError("protocol_error")
        if extension:
            name += "." + extension
        size = node.get("size")
        if size is not None:
            try:
                size = int(size)
                if size < 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise DriveError("protocol_error") from None
        modified = node.get("dateModified") or node.get("dateChanged")
        if modified is not None and (not isinstance(modified, str) or len(modified) > 128):
            raise DriveError("protocol_error")
        return {"id": session.issue_id(node["drivewsid"], parent if node["type"] == "FILE" else None), "name": name, "type": node["type"].lower(),
                "size": size, "modified_at": modified,
                "version": self._metadata_version(session, node) if node.get("etag") else None}

    def _children(self, session, folder):
        items = folder.get("items")
        if folder.get("type") != "FOLDER":
            raise DriveError("invalid_argument")
        if not isinstance(items, list) or len(items) > self.config.max_folder_items:
            raise DriveError("too_large" if isinstance(items, list) else "protocol_error")
        result = []
        skipped = 0
        reported_count = folder.get("numberOfItems")
        if reported_count is not None:
            if type(reported_count) is not int or reported_count < 0:
                raise DriveError("protocol_error")
            skipped = max(0, reported_count - len(items))
        for item in items:
            if not isinstance(item, dict):
                raise DriveError("protocol_error")
            try:
                result.append((item, self._public(session, item, folder["drivewsid"])))
            except DriveError as error:
                if error.code != "unsupported_item":
                    raise
                skipped += 1
        return sorted(result, key=lambda pair: pair[0]["drivewsid"]), skipped

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        if name not in DRIVE_TOOLS:
            raise DriveError("invalid_argument")
        if name in WRITE_TOOLS:
            return await self.call_write_tool(name, arguments)
        if name == "drive_status":
            try:
                async with self._operation() as state:
                    await self._node(state, ROOT)
                    return self._status("ready", state.session.issue_id(ROOT))
            except DriveError as error:
                return self._status(error.code)
        async with self._operation() as state:
            if name == "list_drive_items":
                return await self._list(state, **arguments)
            if name == "search_drive_files":
                return await self._search(state, **arguments)
            return await self._file(state, **arguments)

    @staticmethod
    def _status(status, root_id=None):
        return {"configured": True, "session_state": status, "root_id": root_id, "read_only": False,
                "capabilities": ["list", "name_search", "download", "pdf_text", "create_folder", "upload", "replace"],
                "replacement_atomic": False, "replacement_preserves_id": False,
                "shared_items_supported": False, "packages_supported": False}

    @staticmethod
    def _pagination(limit, offset):
        if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or not 0 <= offset <= 20000:
            raise DriveError("invalid_argument")

    async def _list(self, state, folder_id=None, limit=100, offset=0):
        self._pagination(limit, offset)
        native = state.session.resolve(folder_id)
        if not native.startswith("FOLDER::"):
            raise DriveError("invalid_argument")
        folder = await self._node(state, native)
        items, skipped = self._children(state.session, folder)
        more = offset + limit < len(items)
        return {"folder_id": folder_id or state.session.issue_id(native), "items": [public for _, public in items[offset:offset + limit]],
                "has_more": more, "next_offset": offset + limit if more else None, "coverage_complete": skipped == 0,
                "skipped_count": skipped, "total": len(items), "offset": offset}

    async def _search(self, state, query, folder_id=None, recursive=True, max_depth=3, max_nodes=1000, limit=100, offset=0):
        self._pagination(limit, offset)
        if (not isinstance(query, str) or not query.strip() or len(query) > 256 or type(recursive) is not bool
                or type(max_depth) is not int or not 0 <= max_depth <= 10 or type(max_nodes) is not int or not 1 <= max_nodes <= 10000):
            raise DriveError("invalid_argument")
        queue = deque([(state.session.resolve(folder_id), 0)])
        visited = set()
        examined = set()
        matches = []
        complete = True
        skipped = 0
        while queue:
            native, depth = queue.popleft()
            if native in visited:
                continue
            visited.add(native)
            children, missing = self._children(state.session, await self._node(state, native))
            skipped += missing
            complete = complete and missing == 0
            for node, public in children:
                identifier = node["drivewsid"]
                if identifier in examined:
                    continue
                if len(examined) >= max_nodes:
                    complete = False
                    queue.clear()
                    break
                examined.add(identifier)
                if public["type"] == "file" and query.strip().casefold() in public["name"].casefold():
                    matches.append(public)
                if recursive and public["type"] == "folder":
                    if depth < max_depth:
                        queue.append((identifier, depth + 1))
                    else:
                        complete = False
        more = offset + limit < len(matches)
        return {"files": matches[offset:offset + limit], "coverage_complete": complete,
                "skipped_count": skipped, "examined_nodes": len(examined), "has_more": more,
                "next_offset": offset + limit if more else None, "offset": offset}

    async def _file_node(self, state, native, parent):
        # Apple's retrieveItemDetailsInFolders endpoint accepts folders;
        # FILE IDs return HTTP 500. Refresh the containing folder instead.
        # Earlier references omitted that hint, so resolve them through a
        # bounded fresh catalogue without retaining names or metadata.
        if not native.startswith("FILE::"):
            raise DriveError("unsupported_item")
        queue = deque([parent or ROOT])
        visited = set()
        examined = 0
        incomplete = False
        while queue and len(visited) < 32:
            folder_id = queue.popleft()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            folder = await self._node(state, folder_id)
            children, skipped = self._children(state.session, folder)
            incomplete = incomplete or skipped > 0
            examined += len(children)
            if examined > 10000:
                raise DriveError("lookup_incomplete")
            # Resolve an explicitly unsupported matching item as such.
            for item in folder["items"]:
                if item.get("drivewsid") == native:
                    self._supported(item)
                    return {**item, "_parent_native": folder_id}
            if parent is not None:
                break
            for node, public in children:
                if public["type"] == "folder" and node["drivewsid"] not in visited:
                    if len(queue) < 32:
                        queue.append(node["drivewsid"])
                    else:
                        incomplete = True
        if queue or incomplete:
            raise DriveError("lookup_incomplete")
        raise DriveError("not_found")

    async def _file(self, state, file_id, format="file", offset=0, limit=20000, expected_version=None):
        if (format not in ("file", "text", "base64") or type(offset) is not int or offset < 0 or offset > 30_000_000
                or type(limit) is not int or not 1 <= limit <= (1_000_000 if format == "base64" else 100_000)
                or (format == "file" and offset != 0) or (offset > 0 and (not isinstance(expected_version, str) or not expected_version.startswith("dv_")))):
            raise DriveError("invalid_argument")
        if expected_version is not None and re.fullmatch(r"d[mv]_[0-9a-f]{64}", expected_version) is None:
            raise DriveError("invalid_argument")
        native, parent = state.session.resolve_reference(file_id)
        node = await self._file_node(state, native, parent)
        public = self._public(state.session, node)
        if public["type"] != "file" or public["size"] is None:
            raise DriveError("unsupported_item")
        before = self._metadata_version(state.session, node)
        if expected_version is not None and expected_version.startswith("dm_") and expected_version != before:
            raise DriveError("version_changed")
        if public["size"] > self.config.max_file_bytes:
            raise DriveError("too_large")
        data = b""
        if public["size"]:
            document = node.get("docwsid")
            if not isinstance(document, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", document):
                raise DriveError("protocol_error")
            token = await self._json(state, "GET", state.session.document_url.rstrip("/") + "/ws/com.apple.CloudDocs/download/by_id",
                                     document_id=document)
            asset = token.get("data_token") if isinstance(token, dict) else None
            if not isinstance(asset, dict) or not isinstance(asset.get("url"), str):
                raise DriveError("unsupported_item")
            url = safe_apple_url(asset["url"], asset=True)
            data = await self._download(state, url)
        after = await self._file_node(state, native, parent)
        if before != self._metadata_version(state.session, after) or len(data) != public["size"]:
            raise DriveError("version_changed")
        digest = sha256(data).hexdigest()
        version = "dv_" + sha256((before + digest).encode()).hexdigest()
        if expected_version is not None and expected_version.startswith("dv_") and expected_version != version:
            raise DriveError("version_changed")
        mime = mimetypes.guess_type(public["name"])[0] or "application/octet-stream"
        metadata = {"file_id": file_id, "filename": public["name"], "size": len(data), "content_type": mime,
                    "version": version, "sha256": digest, "format": format, "offset": offset}
        if format == "file":
            return {**metadata, "content_base64": base64.b64encode(data).decode("ascii"),
                    "returned_bytes": len(data), "has_more": False, "next_offset": None}
        if format == "base64":
            chunk = data[offset:offset + limit]
            more = offset + len(chunk) < len(data)
            return {**metadata, "content_base64": base64.b64encode(chunk).decode("ascii"),
                    "returned_bytes": len(chunk), "has_more": more, "next_offset": offset + len(chunk) if more else None}
        part = Message()
        part["Content-Type"] = mime
        part.add_header("Content-Disposition", "attachment", filename=public["name"])
        extracted = await asyncio.to_thread(extract_attachment_text, part, data, offset, limit)
        return {**metadata, **extracted}
