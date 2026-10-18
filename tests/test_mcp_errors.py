import asyncio
from copy import deepcopy
import json

from loguru import logger
from mcp_types import CallToolRequestParams, CallToolResult, TextContent
import pytest
from pydantic import ValidationError

from app.icloud_cache import SQLiteICloudCalendarCache
from app.mcp_errors import ErrorInfo, ErrorPayload, error_result
from app.mcp_server import create_mcp_server
from app.result_schemas import VALIDATORS
from test_imap import FakeIMAP, service_with


def invoke(server, name, **arguments):
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments)))


@pytest.mark.parametrize("name, arguments", [
    ("delete_email", {"uid": "42", "confirm": "true"}),
    ("delete_email", {"uid": "42", "confirm": 1}),
    ("delete_email", {"uid": "42", "confirm": False}),
    ("search_emails", {"limit": "50"}),
    ("search_emails", {"limit": True}),
    ("list_events", {"limit": 201}),
    ("list_events", {"limit": 0}),
    ("list_events", {"limit": 1.5}),
    ("list_drive_items", {"offset": -1}),
    ("search_drive_files", {"query": "Example", "max_nodes": 10001}),
    ("get_drive_file", {"file_id": "file", "format": "text", "limit": 100001}),
    ("get_drive_file", {"file_id": "file", "offset": 1}),
    ("get_drive_file", {"file_id": "file", "format": "base64", "offset": 1}),
    ("get_email_attachment", {"uid": "42", "attachment_id": "1", "format": "file", "offset": 1}),
    ("upload_drive_file", {"filename": "example.txt"}),
    ("upload_drive_file", {"filename": "example.txt", "content_text": "x", "content_base64": "eA=="}),
    ("replace_drive_file", {"file_id": "file", "expected_version": "v", "content_text": "x", "confirm": False}),
    ("batch_update_reminders", {"list_id": "list", "reminders": [{"title": "x"}] * 501, "dry_run": False}),
])
def test_invalid_types_bounds_and_relations_never_reach_services(name, arguments):
    class ForbiddenService:
        calls = 0

        def __getattr__(self, attr):
            if attr == "config":
                raise AttributeError(attr)
            def forbidden(*args, **kwargs):
                self.calls += 1
                raise AssertionError("Input validation must precede backend access")
            return forbidden

    backend = ForbiddenService()
    server = create_mcp_server(backend, backend, reminders_service=backend, contacts_service=backend, drive_service=backend)
    result = invoke(server, name, **arguments)
    assert result.is_error is True
    info = ErrorInfo.model_validate(result.structured_content["error"])
    assert info.code in {"invalid_argument", "confirmation_required"}
    assert info.phase == "input_validation"
    assert info.write_status in {None, "not_sent"}
    assert info.automatic_retry_allowed is False
    assert backend.calls == 0


@pytest.mark.parametrize("name, arguments, service", [
    ("list_calendars", {}, "calendar"),
    ("list_events", {}, "calendar"),
    ("get_event", {"calendar": "calendar", "uid": "event"}, "calendar"),
    ("get_email", {"uid": "42"}, "mail"),
    ("get_contact", {"contact_id": "contact"}, "contacts"),
    ("get_drive_file", {"file_id": "file"}, "drive"),
    ("get_reminder", {"id": "reminder"}, "reminders"),
])
def test_missing_services_share_a_typed_error_contract(name, arguments, service):
    result = invoke(create_mcp_server(None), name, **arguments)
    assert result.is_error is True
    info = ErrorInfo.model_validate(result.structured_content["error"])
    assert info.code == "not_configured"
    assert info.service == service
    assert info.request_operation == name
    assert info.write_status is None
    assert info.request_id
    assert info.automatic_retry_allowed is False
    ErrorPayload.model_validate(result.structured_content)


class FaultyMail(FakeIMAP):
    def __init__(self, phase, outcome):
        super().__init__()
        self.phase = phase
        self.outcome = outcome

    def fail(self):
        if self.outcome == "timeout":
            raise TimeoutError("PRIVATE_UPSTREAM_MARKER")
        return "NO", [b"PRIVATE_UPSTREAM_MARKER"]

    def append(self, *args):
        if self.phase == "append":
            self.calls.append(("APPEND", args))
            return self.fail()
        return super().append(*args)

    def uid(self, command, *args):
        if command == "FETCH" and args[1] == "(UID FLAGS)":
            self.calls.append((command, args))
            return "OK", [b"1 (UID 42 FLAGS (\\Draft))"]
        if command == "COPY":
            self.calls.append((command, args))
            return "OK", [b"[COPYUID 7 42 77] copied"]
        if command == "STORE" and self.phase == "store":
            self.calls.append((command, args))
            return self.fail()
        return super().uid(command, *args)


@pytest.mark.parametrize("outcome,state,deleted", [("NO", "partial", False), ("timeout", "unknown", None)])
def test_draft_failure_preserves_created_uid_and_uncertain_step(outcome, state, deleted):
    client = FaultyMail("store", outcome)
    logs = []
    sink = logger.add(lambda message: logs.append(str(message)))
    try:
        result = invoke(create_mcp_server(None, service_with(client)), "update_draft", uid="42",
                        to=["person@example.com"], subject="PRIVATE_INPUT_MARKER", body="PRIVATE_INPUT_MARKER")
    finally:
        logger.remove(sink)
    data = result.structured_content
    assert result.is_error is True
    assert data["uid"] == "77" and data["old_uid"] == "42"
    assert data["created"] is True
    assert data["old_draft_marked_deleted"] is deleted
    assert data["confirmed_steps"] == ["append_draft"]
    assert data["write_status"] == state
    assert data["error"]["overall_write_status"] == state
    assert data["error"]["phase"] == "mark_old_draft_deleted"
    assert data["error"]["inspect_before_retry"] is True
    assert data["uncertain_step"] == ("mark_old_draft_deleted" if outcome == "timeout" else None)
    assert sum(command == "APPEND" for command, _ in client.calls) == 1
    assert not any(command == "EXPUNGE" for command, _ in client.calls)
    assert data["error"]["request_id"] in "".join(logs)
    for marker in ("PRIVATE_UPSTREAM_MARKER", "PRIVATE_INPUT_MARKER", "person@example.com"):
        assert marker not in str(result)
        assert marker not in "".join(logs)


def test_unconfirmed_append_is_unknown_not_false_and_is_never_retried():
    client = FaultyMail("append", "timeout")
    result = invoke(create_mcp_server(None, service_with(client)), "create_draft",
                    to=["person@example.com"], subject="Example", body="Example")
    data = result.structured_content
    assert data["created"] is None and data["uid"] is None
    assert data["write_status"] == "unknown"
    assert data["confirmed_steps"] == []
    assert data["uncertain_step"] == "append_draft"
    assert sum(command == "APPEND" for command, _ in client.calls) == 1


def test_partial_move_preserves_copy_uid_and_invalidates_both_mailbox_caches(tmp_path):
    client = FaultyMail("store", "NO")
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite")
    mail = service_with(client, cache=cache)
    for mailbox in ("INBOX", "Archive"):
        mail.search_emails(mailbox=mailbox, since=mail._email_cache_since(), limit=1)
        mail.get_email(mailbox=mailbox, uid="42")
        assert mail._cache.get_emails(mailbox) is not None
        assert mail._cache.get_email_message(mailbox, "42", uid_validity="7") is not None
    result = invoke(create_mcp_server(None, mail), "move_email", uid="42", destination_mailbox="Archive")
    data = result.structured_content
    assert result.is_error is True
    assert data["copied"] is True and data["destination_uid"] == "77"
    assert data["source_marked_deleted"] is False
    assert data["write_status"] == "partial"
    assert data["confirmed_steps"] == ["copy_message"]
    assert sum(command == "COPY" for command, _ in client.calls) == 1
    for mailbox in ("INBOX", "Archive"):
        assert mail._cache.get_emails(mailbox) is None
        assert mail._cache.get_email_message(mailbox, "42", uid_validity="7") is None


def test_invalid_success_reply_preserves_native_fields_and_confirmed_write():
    native = {"created": True, "uid": "77", "write_status": "succeeded", "extension": {"future": True}}
    class Mail:
        def create_draft(self, **arguments):
            return deepcopy(native)
    result = invoke(create_mcp_server(None, Mail()), "create_draft", to=["person@example.com"], subject="Example", body="Example")
    assert result.is_error is True
    assert result.structured_content["created"] is True
    assert result.structured_content["uid"] == "77"
    assert result.structured_content["write_status"] == "succeeded"
    assert result.structured_content["error"]["code"] == "backend_protocol_error"
    assert result.structured_content["error"]["overall_write_status"] == "succeeded"
    assert result.structured_content["error"]["inspect_before_retry"] is True


def test_invalid_reminders_success_reply_keeps_safe_native_id_and_state():
    native = {"id": "created-id", "status": "unsupported_future_status", "write_status": "succeeded", "extension": True}
    content = [TextContent(type="text", text="native acknowledgement")]
    class Reminders:
        async def call_tool(self, name, arguments):
            return CallToolResult(structuredContent=deepcopy(native), content=content)
    result = invoke(create_mcp_server(None, reminders_service=Reminders()), "create_reminder", title="Example", list_id="list")
    assert result.is_error is True
    assert result.structured_content["id"] == "created-id"
    assert result.structured_content["write_status"] == "succeeded"
    assert "unsupported_future_status" not in str(result)
    assert result.structured_content["error"]["overall_write_status"] == "succeeded"


def test_native_batch_error_is_additive_and_overall_partial_state_is_distinct():
    native = {"status": "failed", "completed_operations": 1, "ids": {"new": "created-id"},
              "error": {"code": "icloud_write_failed", "message": "native safe message", "write_status": "not_sent",
                        "retry_class": "retryable_safe", "operation": "move_reminder", "extension": True}}
    result = error_result("batch_update_reminders", "icloud_write_failed", result=CallToolResult(structuredContent=deepcopy(native), content=[]), write=True)
    assert all(result.structured_content["error"][key] == value for key, value in native["error"].items())
    assert result.structured_content["ids"] == native["ids"]
    assert result.structured_content["error"]["overall_write_status"] == "partial"
    assert result.structured_content["error"]["inspect_before_retry"] is True
    assert result.structured_content["error"]["request_operation"] == "batch_update_reminders"


def test_every_tool_publishes_real_output_schema_and_destructive_replacements():
    tools = asyncio.run(create_mcp_server(None).list_tools())
    for tool in tools:
        assert tool.output_schema["type"] == "object"
        assert tool.output_schema["anyOf"]
        assert "ErrorInfo" in tool.output_schema["$defs"]
    for name in ("update_draft", "move_email"):
        assert next(tool for tool in tools if tool.name == name).annotations.destructive_hint is True
    limit = next(tool for tool in tools if tool.name == "list_events").input_schema["properties"]["limit"]
    assert (limit["minimum"], limit["maximum"]) == (1, 200)
