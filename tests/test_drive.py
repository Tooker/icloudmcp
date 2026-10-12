import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import logging
from pathlib import Path

from cryptography.fernet import Fernet
import httpx
import pytest

from app.drive import DriveSession, ICloudDriveService, ROOT
from app.drive_config import DriveBackendConfig
from app.drive_errors import DriveError

FILE = "FILE::com.apple.CloudDocs::file-123"
FOLDER = "FOLDER::com.apple.CloudDocs::folder-123"
TOKEN = "dedicated-drive-token-0123456789abcdef"
PAYLOAD = "Private invoice Änne\nSecond line".encode()


def snapshot(path, *, key=None, account="account", cookies=None):
    raw = {"version": 1, "account_key": sha256(account.encode()).hexdigest(), "id_key": key or Fernet.generate_key().decode(),
           "drive_url": "https://p42-drivews.icloud.com", "document_url": "https://p42-docws.icloud.com",
           "params": {"dsid": "PRIVATE_ACCOUNT_ID", "clientId": "PRIVATE_CLIENT_ID"},
           "cookies": cookies or [{"name": "AUTH", "value": "PRIVATE_COOKIE", "domain": ".icloud.com", "path": "/", "expires": None}]}
    path.write_text(json.dumps(raw))
    return raw


class AppleDrive:
    def __init__(self):
        self.requests = []
        self.payload = PAYLOAD
        file = {"drivewsid": FILE, "docwsid": "file-123", "zone": "com.apple.CloudDocs", "type": "FILE", "name": "Rechnung März",
                "extension": "txt", "size": len(self.payload), "etag": "first-version", "dateModified": "2026-10-11T10:00:00Z"}
        folder = {"drivewsid": FOLDER, "docwsid": "folder-123", "type": "FOLDER", "name": "Invoices", "etag": "folder-version", "items": []}
        self.nodes = {ROOT: {"drivewsid": ROOT, "type": "FOLDER", "etag": "root-version", "items": [file, folder]},
                      FILE: file, FOLDER: folder}
        self.asset_url = "https://cvws.icloud-content.com/signed?secret=PRIVATE_SIGNED_TOKEN"
        self.asset_redirect = None
        self.status = 200
        self.delay = 0
        self.change_after_download = False
        self.package = False

    async def __call__(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if request.url.host == "cvws.icloud-content.com":
            assert not request.headers.get("Cookie")
            assert "dsid" not in request.url.params
            assert not request.headers.get("Authorization")
            assert not request.headers.get("Origin")
            if self.asset_redirect:
                return httpx.Response(302, headers={"Location": self.asset_redirect})
            if self.change_after_download:
                self.nodes[FILE]["etag"] = "replacement-version"
            return httpx.Response(200, content=self.payload)
        assert request.headers["Cookie"] == "AUTH=PRIVATE_COOKIE"
        assert request.url.params["dsid"] == "PRIVATE_ACCOUNT_ID"
        if self.status != 200:
            return httpx.Response(self.status, text="PRIVATE_REMOTE_ERROR")
        if request.url.path == "/retrieveItemDetailsInFolders":
            body = json.loads(request.content)
            assert request.method == "POST" and len(body) == 1
            native = body[0]["drivewsid"]
            # Real Apple accepts folders here, and returns 500 for FILE IDs.
            if native.startswith("FILE::"):
                return httpx.Response(500)
            if native not in self.nodes:
                return httpx.Response(200, json=[{"drivewsid": native, "status": "ID_INVALID"}])
            return httpx.Response(200, json=[deepcopy(self.nodes[native])])
        assert request.method == "GET" and request.url.path == "/ws/com.apple.CloudDocs/download/by_id"
        assert request.url.params["document_id"] == "file-123"
        return httpx.Response(200, json={"package_token" if self.package else "data_token": {"url": self.asset_url}})


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleDrive()
    config = DriveBackendConfig(path)
    service = ICloudDriveService(config, transport=httpx.MockTransport(apple))
    return service, apple, path


def run(service, name, **arguments):
    return asyncio.run(service.call_tool(name, arguments))


def file_id(path):
    return DriveSession.load(path).issue_id(FILE)


def test_status_probes_existing_access_without_authentication_or_approval(setup):
    service, apple, _ = setup
    result = run(service, "drive_status")
    assert result["session_state"] == "ready"
    assert result["read_only"] is False
    assert result["root_id"].startswith("di_")
    assert result["shared_items_supported"] is False
    assert "PRIVATE" not in str(result)
    assert len(apple.requests) == 1
    assert all("retrieveItemDetailsInFolders" in request.url.path for request in apple.requests)


def test_missing_session_does_not_contact_apple_and_reports_admin_action(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        raise AssertionError
    service = ICloudDriveService(DriveBackendConfig(tmp_path / "missing"), transport=httpx.MockTransport(handler))
    assert run(service, "drive_status")["session_state"] == "auth_required"
    with pytest.raises(DriveError) as error:
        run(service, "list_drive_items")
    assert error.value.code == "auth_required"
    assert calls == []


@pytest.mark.parametrize("status,code", [(401, "auth_required"), (421, "auth_required"), (403, "access_required"), (450, "access_required"), (503, "backend_unavailable")])
def test_expired_authentication_and_access_never_trigger_approval_or_retries(setup, status, code):
    service, apple, _ = setup
    apple.status = status
    assert run(service, "drive_status")["session_state"] == code
    assert len(apple.requests) == 1


def test_list_paginates_and_issues_opaque_account_scoped_ids(setup):
    service, apple, path = setup
    first = run(service, "list_drive_items", limit=1)
    assert first["has_more"] is True
    assert first["items"][0]["name"] == "Rechnung März.txt"
    assert FILE not in str(first)
    assert "PRIVATE_ACCOUNT_ID" not in str(first)
    second = run(service, "list_drive_items", limit=1, offset=1)
    assert second["items"][0]["type"] == "folder"
    assert second["next_offset"] is None
    assert DriveSession.load(path).resolve(first["items"][0]["id"]) == FILE
    # Issued references survive a backend restart; they do not depend on an in-memory registry.
    fresh = ICloudDriveService(service.config, transport=httpx.MockTransport(apple))
    assert run(fresh, "get_drive_file", file_id=first["items"][0]["id"], format="text")["text"] == PAYLOAD.decode()


def test_other_accounts_and_tampered_ids_never_reach_apple(setup):
    service, apple, path = setup
    identifier = file_id(path)
    raw = json.loads(path.read_text())
    snapshot(path, key=raw["id_key"], account="another-account")
    for invalid in (identifier, identifier[:-4] + "AAAA", "https://example.com/file", "/etc/passwd"):
        with pytest.raises(DriveError) as error:
            run(service, "get_drive_file", file_id=invalid)
        assert error.value.code == "invalid_argument"
    assert apple.requests == []


def test_bounded_search_reports_truncated_depth_and_node_coverage(setup):
    service, apple, _ = setup
    duplicate = deepcopy(apple.nodes[FILE])
    duplicate["drivewsid"] = "FILE::com.apple.CloudDocs::another-file"
    duplicate["name"] = "Rechnung nested"
    apple.nodes[FOLDER]["items"] = [duplicate]
    all_results = run(service, "search_drive_files", query="RECHNUNG")
    assert len(all_results["files"]) == 2
    assert all_results["coverage_complete"] is True
    depth_limited = run(service, "search_drive_files", query="Rechnung", max_depth=0)
    assert len(depth_limited["files"]) == 1
    assert depth_limited["coverage_complete"] is False
    node_limited = run(service, "search_drive_files", query="Rechnung", max_nodes=1)
    assert node_limited["coverage_complete"] is False
    assert node_limited["examined_nodes"] == 1


def test_search_handles_cycles_and_matching_pagination(setup):
    service, apple, _ = setup
    apple.nodes[FOLDER]["items"] = [deepcopy(apple.nodes[FOLDER]), deepcopy(apple.nodes[FILE])]
    result = run(service, "search_drive_files", query="Rechnung", limit=1)
    assert len(result["files"]) == 1
    assert result["examined_nodes"] == 2
    assert len(apple.requests) == 2


@pytest.mark.parametrize("change", [
    {"shareID": {"ownerRecordName": "PRIVATE_OWNER"}}, {"isPackage": True}, {"isShared": True},
    {"drivewsid": "FILE::com.apple.Pages::app-item"}, {"type": "APP_LIBRARY"},
])
def test_shared_packages_and_app_libraries_are_explicitly_skipped(setup, change):
    service, apple, _ = setup
    unsupported = {**apple.nodes[FILE], **change}
    apple.nodes[ROOT]["items"] = [unsupported]
    result = run(service, "list_drive_items")
    assert result["items"] == []
    assert result["skipped_count"] == 1
    assert result["coverage_complete"] is False


def test_native_download_is_complete_and_signed_assets_get_no_credentials(setup):
    service, apple, path = setup
    result = run(service, "get_drive_file", file_id=file_id(path))
    assert base64.b64decode(result["content_base64"]) == PAYLOAD
    assert result["format"] == "file"
    assert result["sha256"] == sha256(PAYLOAD).hexdigest()
    assert result["version"].startswith("dv_")
    assert [request.method for request in apple.requests] == ["POST", "GET", "GET", "POST"]


def test_nested_file_reference_refreshes_only_its_containing_folder(setup):
    service, apple, path = setup
    apple.nodes[FOLDER]["items"] = [apple.nodes[FILE]]
    apple.nodes[ROOT]["items"] = [apple.nodes[FOLDER]]
    folder_id = DriveSession.load(path).issue_id(FOLDER)
    item = run(service, "list_drive_items", folder_id=folder_id)["items"][0]
    assert DriveSession.load(path).resolve_reference(item["id"]) == (FILE, FOLDER)
    apple.requests.clear()
    result = run(service, "get_drive_file", file_id=item["id"], expected_version=item["version"])
    assert base64.b64decode(result["content_base64"]) == PAYLOAD
    metadata_reads = [json.loads(request.content)[0]["drivewsid"] for request in apple.requests if request.method == "POST"]
    assert metadata_reads == [FOLDER, FOLDER]


def test_legacy_file_reference_uses_fresh_bounded_folder_catalogue(setup):
    service, apple, path = setup
    apple.nodes[FOLDER]["items"] = [apple.nodes[FILE]]
    apple.nodes[ROOT]["items"] = [apple.nodes[FOLDER]]
    result = run(service, "get_drive_file", file_id=file_id(path))
    assert base64.b64decode(result["content_base64"]) == PAYLOAD
    assert all(json.loads(request.content)[0]["drivewsid"].startswith("FOLDER::")
               for request in apple.requests if request.method == "POST")


def test_incomplete_file_lookup_cannot_establish_absence(setup):
    service, apple, path = setup
    apple.nodes[ROOT]["items"] = []
    apple.nodes[ROOT]["numberOfItems"] = 2
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "lookup_incomplete"


@pytest.mark.parametrize("tool", ["list_drive_items", "search_drive_files"])
def test_file_reference_cannot_be_used_as_folder(setup, tool):
    service, apple, path = setup
    arguments = {"folder_id": file_id(path)}
    if tool == "search_drive_files":
        arguments["query"] = "invoice"
    with pytest.raises(DriveError) as error:
        run(service, tool, **arguments)
    assert error.value.code == "invalid_argument"
    assert apple.requests == []


def test_byte_chunks_require_and_check_full_content_version(setup):
    service, apple, path = setup
    identifier = file_id(path)
    first = run(service, "get_drive_file", file_id=identifier, format="base64", limit=5)
    assert base64.b64decode(first["content_base64"]) == PAYLOAD[:5]
    assert first["next_offset"] == 5
    second = run(service, "get_drive_file", file_id=identifier, format="base64", offset=5, limit=5, expected_version=first["version"])
    assert base64.b64decode(second["content_base64"]) == PAYLOAD[5:10]
    # Even an upstream mutation with an unchanged metadata ETag cannot mix chunks.
    apple.payload = b"X" * len(PAYLOAD)
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=identifier, format="base64", offset=10, expected_version=first["version"])
    assert error.value.code == "version_changed"


def test_metadata_change_mid_download_discards_all_bytes(setup):
    service, apple, path = setup
    apple.change_after_download = True
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "version_changed"


def test_expected_metadata_version_rejects_change_before_downloading(setup):
    service, apple, path = setup
    metadata = run(service, "list_drive_items")["items"][0]
    apple.nodes[FILE]["etag"] = "changed"
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=metadata["id"], expected_version=metadata["version"])
    assert error.value.code == "version_changed"
    assert not any("download/by_id" in request.url.path for request in apple.requests)


def test_zero_byte_files_do_not_call_document_download_api(setup):
    service, apple, path = setup
    apple.nodes[FILE]["size"] = 0
    result = run(service, "get_drive_file", file_id=file_id(path))
    assert result["size"] == 0
    assert result["content_base64"] == ""
    assert len(apple.requests) == 2


def test_text_pages_reuse_existing_extraction_and_checked_versions(setup):
    service, _, path = setup
    first = run(service, "get_drive_file", file_id=file_id(path), format="text", limit=5)
    assert first["text"] == PAYLOAD.decode()[:5]
    assert first["next_offset"] == 5
    second = run(service, "get_drive_file", file_id=file_id(path), format="text", offset=5, limit=5, expected_version=first["version"])
    assert second["text"] == PAYLOAD.decode()[5:10]


@pytest.mark.parametrize("url", [
    "https://evil.invalid/private", "https://icloud-content.com.evil.invalid/", "http://cvws.icloud-content.com/",
    "https://user:secret@cvws.icloud-content.com/", "https://cvws.icloud-content.com:444/",
])
def test_unsafe_download_urls_and_redirects_are_rejected_before_request(setup, url):
    service, apple, path = setup
    apple.asset_url = url
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "unsafe_target"
    assert len(apple.requests) == 2
    apple.asset_url = "https://cvws.icloud-content.com/signed"
    apple.asset_redirect = url
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "unsafe_target"
    assert not any(request.url.host == "evil.invalid" for request in apple.requests)


def test_package_token_is_not_silently_downloaded(setup):
    service, apple, path = setup
    apple.package = True
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "unsupported_item"


def test_size_limits_apply_before_download_and_during_streaming(setup):
    service, apple, path = setup
    service.config = replace(service.config, max_file_bytes=10)
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "too_large"
    assert len(apple.requests) == 1
    # An incorrect metadata size cannot bypass the stream bound.
    apple.nodes[FILE]["size"] = 1
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path))
    assert error.value.code == "too_large"


def test_folder_size_limit_and_total_deadline(setup):
    service, apple, _ = setup
    service.config = replace(service.config, max_folder_items=1)
    with pytest.raises(DriveError) as error:
        run(service, "list_drive_items")
    assert error.value.code == "too_large"
    service.config = replace(service.config, timeout_seconds=0.02)
    apple.delay = 0.1
    with pytest.raises(DriveError) as error:
        run(service, "list_drive_items")
    assert error.value.code == "timeout"


def test_partial_server_folder_listing_does_not_claim_complete_coverage(setup):
    service, apple, _ = setup
    apple.nodes[ROOT]["numberOfItems"] = 10
    result = run(service, "list_drive_items")
    assert result["coverage_complete"] is False
    assert result["skipped_count"] == 8
    assert run(service, "search_drive_files", query="absent")["coverage_complete"] is False


def test_pdf_text_download_uses_the_existing_extractor(setup):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    service, apple, path = setup
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 150 Td (Drive PDF invoice) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    apple.payload = output.getvalue()
    apple.nodes[FILE].update(extension="pdf", size=len(apple.payload))
    result = run(service, "get_drive_file", file_id=file_id(path), format="text")
    assert result["text_status"] == "ok"
    assert "Drive PDF invoice" in result["text"]


@pytest.mark.parametrize("arguments", [{"limit": 0}, {"offset": -1}, {"format": "base64", "offset": 2}, {"format": "file", "offset": 2}])
def test_invalid_arguments_make_no_apple_requests(setup, arguments):
    service, apple, path = setup
    with pytest.raises(DriveError) as error:
        run(service, "get_drive_file", file_id=file_id(path), **arguments)
    assert error.value.code == "invalid_argument"
    assert apple.requests == []


def test_transport_logs_never_include_cookies_urls_or_file_contents(setup, caplog):
    service, _, path = setup
    with caplog.at_level(logging.DEBUG):
        run(service, "get_drive_file", file_id=file_id(path), format="text")
    for marker in ("PRIVATE", "Rechnung", "Änne", "file-123", "signed?secret"):
        assert marker not in caplog.text


def test_exported_user_agent_is_preserved_for_session_binding(setup):
    service, apple, path = setup
    raw = json.loads(path.read_text())
    raw["user_agent"] = "Administrative-login-user-agent"
    path.write_text(json.dumps(raw))
    run(service, "drive_status")
    assert apple.requests[0].headers["User-Agent"] == "Administrative-login-user-agent"


def test_go_export_cookie_scope_does_not_expand_host_only_cookies(setup):
    service, _, path = setup
    raw = json.loads(path.read_text())
    raw["cookies"] = [{"name": "host-only", "value": "private", "domain": "p42-drivews.icloud.com", "path": "/",
                       "expires": None, "secure": True, "host_only": True}]
    path.write_text(json.dumps(raw))
    captured = []

    def capture(request):
        captured.append(bool(request.headers.get("cookie")))
        return httpx.Response(200)

    service._transport = httpx.MockTransport(capture)

    async def inspect_scope():
        async with service._operation() as state:
            await state.client.get("https://p42-drivews.icloud.com/")
            await state.client.get("https://sub.p42-drivews.icloud.com/")
            await state.client.get("https://p42-docws.icloud.com/")
            return tuple(captured)

    assert asyncio.run(inspect_scope()) == (True, False, False)
