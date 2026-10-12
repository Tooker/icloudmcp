import asyncio
import base64
from copy import deepcopy
from email import policy
from email.parser import BytesParser
from hashlib import sha256
import json
from dataclasses import replace

import httpx
import pytest

from app.drive import DriveSession, ICloudDriveService, ROOT
from app.drive_config import DriveBackendConfig
from app.drive_errors import DriveError
from test_drive import AppleDrive, FILE, PAYLOAD, snapshot


class AppleWrites(AppleDrive):
    """Stateful, independent Apple mutation/etag and multipart simulation."""

    def __init__(self):
        super().__init__()
        self.reserved = {}
        self.payloads = {"file-123": PAYLOAD}
        self.trashed = []
        self.next_id = 0
        self.fail = None
        self.etag_conflict = False
        self.change_original = False
        self.change_staged = False
        self.readback_fails = False

    async def __call__(self, request):
        path = request.url.path
        if path == "/signed":
            self.requests.append(request)
            assert not request.headers.get("Cookie")
            document = request.url.params["doc"]
            if self.readback_fails and document != "file-123":
                return httpx.Response(503)
            if self.change_original and document != "file-123":
                self.nodes[FILE]["etag"] = "concurrent-change"
            if self.change_staged and document != "file-123":
                self.nodes["FILE::com.apple.CloudDocs::" + document]["etag"] = "staged-change"
            return httpx.Response(200, content=self.payloads[document])
        if path == "/ws/com.apple.CloudDocs/download/by_id":
            self.requests.append(request)
            return httpx.Response(200, json={"data_token": {"url": "https://cvws.icloud-content.com/signed?doc=" + request.url.params["document_id"]}})
        if path == "/upload":
            self.requests.append(request)
            assert not request.headers.get("Cookie")
            assert not request.headers.get("Origin")
            assert "dsid" not in request.url.params
            if self.fail == "upload_bytes":
                raise httpx.ReadTimeout("PRIVATE_UPLOAD_FAILURE")
            message = BytesParser(policy=policy.default).parsebytes(
                ("Content-Type: " + request.headers["Content-Type"] + "\r\n\r\n").encode() + request.content)
            parts = list(message.iter_parts())
            assert len(parts) == 1
            data = parts[0].get_payload(decode=True)
            self.payloads[request.url.params["doc"]] = data
            return httpx.Response(200, json={"singleFile": {"size": len(data), "fileChecksum": "test-checksum",
                                                          "referenceChecksum": "test-reference", "wrappingKey": "test-key", "receipt": "test-receipt"}})
        if path in {"/createFolders", "/ws/com.apple.CloudDocs/upload/web", "/ws/com.apple.CloudDocs/update/documents", "/moveItemsToTrash", "/renameItems"}:
            self.requests.append(request)
            body = json.loads(request.content)
            if path == "/createFolders":
                self.next_id += 1
                native = "FOLDER::com.apple.CloudDocs::created-" + str(self.next_id)
                parent = self.nodes[body["destinationDrivewsId"]]
                item = {"drivewsid": native, "docwsid": native.split("::")[-1], "name": body["folders"][0]["name"],
                        "type": "FOLDER", "etag": "folder-etag", "items": [], "status": "OK"}
                self.nodes[native] = item
                parent["items"].append(item)
                return httpx.Response(200, json={"folders": [deepcopy(item)]})
            if path.endswith("/upload/web"):
                self.next_id += 1
                document = "created-" + str(self.next_id)
                self.reserved[document] = body
                return httpx.Response(200, json=[{"document_id": document, "url": "https://cvws.icloud-content.com/upload?doc=" + document}])
            if path.endswith("/update/documents"):
                assert body["command"] == "add_file" and body["allow_conflict"] is False
                document = body["document_id"]
                native = "FILE::com.apple.CloudDocs::" + document
                parent = "FOLDER::com.apple.CloudDocs::" + body["path"]["starting_document_id"]
                name, extension = body["path"]["path"].rsplit(".", 1)
                item = {"drivewsid": native, "docwsid": document, "zone": "com.apple.CloudDocs", "type": "FILE",
                        "name": name, "extension": extension, "etag": "created-etag", "size": len(self.payloads[document])}
                self.nodes[native] = item
                self.nodes[parent]["items"].append(item)
                if self.fail == "commit_file":
                    raise httpx.ReadTimeout("PRIVATE_COMMIT_FAILURE")
                return httpx.Response(200, json={"status": {"status_code": 0}, "results": [{"status": {"status_code": 0},
                    "document": {"document_id": document, "type": "FILE", "zone": "com.apple.CloudDocs"}}]})
            item = body["items"][0]
            native = item["drivewsid"]
            node = self.nodes[native]
            if item["etag"] != node["etag"] or self.etag_conflict and path == "/moveItemsToTrash":
                return httpx.Response(200, json={"items": [{"drivewsid": native, "status": "ETAG_CONFLICT"}]})
            if path == "/moveItemsToTrash":
                for folder in self.nodes.values():
                    if folder.get("type") == "FOLDER":
                        folder["items"] = [child for child in folder["items"] if child["drivewsid"] != native]
                self.trashed.append(native)
                if self.fail == "trash_original":
                    raise httpx.ReadTimeout("PRIVATE_TRASH_FAILURE")
            else:
                name = item["name"]
                if "." in name:
                    node["name"], node["extension"] = name.rsplit(".", 1)
                else:
                    node["name"] = name
                    node.pop("extension", None)
                node["etag"] = "renamed-etag"
                if self.fail == "rename_replacement" and self.trashed:
                    raise httpx.ReadTimeout("PRIVATE_RENAME_FAILURE")
            return httpx.Response(200, json={"items": [{"drivewsid": native, "status": "OK", "etag": node["etag"]}]})
        return await super().__call__(request)


@pytest.fixture
def writes(tmp_path):
    path = tmp_path / "session.json"
    snapshot(path)
    apple = AppleWrites()
    return ICloudDriveService(DriveBackendConfig(path), transport=httpx.MockTransport(apple)), apple, path


def call(service, tool_name, **arguments):
    return asyncio.run(service.call_tool(tool_name, arguments))


def original(path, apple):
    session = DriveSession.load(path)
    item = apple.nodes[FILE]
    return session.issue_id(FILE, ROOT), ICloudDriveService._metadata_version(session, item)


def test_create_folder_and_reject_duplicate_without_replaying(writes):
    service, apple, _ = writes
    result = call(service, "create_drive_folder", name="New folder")
    assert result["write_status"] == "succeeded"
    assert result["readback_verified"] is True
    assert result["item"]["name"] == "New folder"
    with pytest.raises(DriveError) as failure:
        call(service, "create_drive_folder", name="New folder")
    assert failure.value.code == "conflict"
    assert len([request for request in apple.requests if request.url.path == "/createFolders"]) == 1


@pytest.mark.parametrize("data", [b"", "Unicode Ä\ntext".encode(), bytes(range(256)) * 20])
def test_upload_preserves_original_bytes_and_activates_exact_name(writes, data):
    service, apple, _ = writes
    result = call(service, "upload_drive_file", filename="original.bin", content_base64=base64.b64encode(data).decode())
    assert result["write_status"] == "succeeded" and result["readback_verified"] is True
    assert result["item"]["name"] == "original.bin"
    assert result["sha256"] == sha256(data).hexdigest()
    assert result["bytes_uploaded"] == len(data)
    retrieved = call(service, "get_drive_file", file_id=result["item"]["id"])
    assert base64.b64decode(retrieved["content_base64"]) == data
    assert FILE not in apple.trashed


def test_replace_stages_verifies_and_preserves_original_in_native_trash(writes):
    service, apple, path = writes
    identifier, version = original(path, apple)
    result = call(service, "replace_drive_file", file_id=identifier, expected_version=version, confirm=True, content_text="Replacement Ä")
    assert result["write_status"] == "succeeded"
    assert result["original_in_trash"] is True
    assert result["atomic"] is False and result["preserves_file_id"] is False
    assert DriveSession.load(path).resolve(result["file_id"]) != FILE
    assert apple.trashed == [FILE]
    assert apple.payloads["file-123"] == PAYLOAD
    assert result["item"]["name"] == "Rechnung März.txt"
    assert result["sha256"] == sha256("Replacement Ä".encode()).hexdigest()
    phases = [request.url.path for request in apple.requests]
    assert phases.index("/signed") < phases.index("/moveItemsToTrash")


@pytest.mark.parametrize("arguments,code", [
    ({"confirm": False}, "confirmation_required"),
    ({"expected_version": "dm_" + "0" * 64}, "conflict"),
    ({"content_text": None, "content_base64": "!!!"}, "invalid_argument"),
])
def test_invalid_replace_never_starts_a_mutation(writes, arguments, code):
    service, apple, path = writes
    identifier, version = original(path, apple)
    params = {"file_id": identifier, "expected_version": version, "confirm": True, "content_text": "Replacement", **arguments}
    with pytest.raises(DriveError) as failure:
        call(service, "replace_drive_file", **params)
    assert failure.value.code == code
    assert failure.value.details["write_status"] == "not_started"
    assert not any(request.url.path in {"/upload", "/ws/com.apple.CloudDocs/upload/web", "/moveItemsToTrash"} for request in apple.requests)


@pytest.mark.parametrize("name", ["", "../file", "folder/file", "a\\b", "nul\x00name", "Ä" * 130])
def test_invalid_names_never_reach_apple(writes, name):
    service, apple, _ = writes
    with pytest.raises(DriveError) as failure:
        call(service, "upload_drive_file", filename=name, content_text="Private contents")
    assert failure.value.code == "invalid_argument"
    assert apple.requests == []


def test_collision_and_readonly_permissions_block_upload_before_reservation(writes):
    service, apple, _ = writes
    with pytest.raises(DriveError) as failure:
        call(service, "upload_drive_file", filename="Rechnung März.txt", content_text="Replacement")
    assert failure.value.code == "conflict"
    apple.nodes[ROOT]["isWritable"] = False
    with pytest.raises(DriveError) as failure:
        call(service, "upload_drive_file", filename="new.txt", content_text="new")
    assert failure.value.code == "read_only"
    assert not apple.reserved


@pytest.mark.parametrize("step", ["upload_bytes", "commit_file", "trash_original", "rename_replacement"])
def test_uncertain_write_keeps_ids_steps_and_never_replays(writes, step):
    service, apple, path = writes
    identifier, version = original(path, apple)
    apple.fail = step
    with pytest.raises(DriveError) as failure:
        call(service, "replace_drive_file", file_id=identifier, expected_version=version, confirm=True, content_text="Replacement")
    details = failure.value.details
    assert details["write_status"] == "uncertain"
    assert details["uncertain_step"] == step
    assert details["reserved_file_id"].startswith("di_")
    assert "PRIVATE" not in str(failure.value)
    if step in {"trash_original", "rename_replacement"}:
        assert details["file_id"].startswith("di_")
        assert "commit_file" in details["confirmed_steps"]
        assert details["original_in_trash"] is (None if step == "trash_original" else True)
    assert len(apple.reserved) == 1
    assert len([request for request in apple.requests if request.url.path == "/moveItemsToTrash"]) <= 1


@pytest.mark.parametrize("kind", ["metadata", "native_etag", "staged_metadata"])
def test_concurrent_changes_preserve_original_and_confirmed_staging(writes, kind):
    service, apple, path = writes
    identifier, version = original(path, apple)
    apple.change_original = kind == "metadata"
    apple.etag_conflict = kind == "native_etag"
    apple.change_staged = kind == "staged_metadata"
    with pytest.raises(DriveError) as failure:
        call(service, "replace_drive_file", file_id=identifier, expected_version=version, confirm=True, content_text="Replacement")
    assert failure.value.code in {"conflict", "version_changed"}
    assert failure.value.details["write_status"] == "partial"
    assert failure.value.details["file_id"].startswith("di_")
    assert failure.value.details["original_in_trash"] is False
    assert apple.trashed == []


def test_failed_staged_readback_never_removes_original(writes):
    service, apple, path = writes
    identifier, version = original(path, apple)
    apple.readback_fails = True
    with pytest.raises(DriveError) as failure:
        call(service, "replace_drive_file", file_id=identifier, expected_version=version, confirm=True, content_text="Replacement")
    assert failure.value.details["write_status"] == "partial"
    assert failure.value.details["readback_verified"] is False
    assert apple.trashed == []


def test_size_and_partial_folder_coverage_block_all_mutations(writes):
    service, apple, _ = writes
    service.config = replace(service.config, max_file_bytes=5)
    with pytest.raises(DriveError) as failure:
        call(service, "upload_drive_file", filename="new.txt", content_text="Longer than five")
    assert failure.value.code == "too_large"
    assert apple.requests == []
    apple.nodes[ROOT]["numberOfItems"] = len(apple.nodes[ROOT]["items"]) + 1
    with pytest.raises(DriveError) as failure:
        call(service, "create_drive_folder", name="New folder")
    assert failure.value.code == "lookup_incomplete"
    assert not any(request.url.path == "/createFolders" for request in apple.requests)


def test_foreign_upload_url_never_receives_bytes_and_keeps_reservation(writes):
    service, apple, _ = writes
    async def transport(request):
        if request.url.path.endswith("/upload/web"):
            apple.requests.append(request)
            return httpx.Response(200, json=[{"document_id": "reserved", "url": "https://evil.invalid/upload"}])
        return await apple(request)
    service._transport = httpx.MockTransport(transport)
    with pytest.raises(DriveError) as failure:
        call(service, "upload_drive_file", filename="new.txt", content_text="Original bytes")
    assert failure.value.code == "unsafe_target"
    assert failure.value.details["reserved_file_id"].startswith("di_")
    assert failure.value.details["confirmed_steps"] == ["reserve_upload"]
    assert all(request.url.host != "evil.invalid" for request in apple.requests)


def test_confirmed_folder_creation_survives_readback_failure(writes):
    service, apple, _ = writes
    async def transport(request):
        if request.url.path == "/retrieveItemDetailsInFolders" and "created-" in request.content.decode():
            return httpx.Response(503)
        return await apple(request)
    service._transport = httpx.MockTransport(transport)
    result = call(service, "create_drive_folder", name="New folder")
    assert result["write_status"] == "succeeded"
    assert result["confirmed_steps"] == ["create_folder"]
    assert result["folder_id"].startswith("di_")
    assert result["readback_verified"] is False
