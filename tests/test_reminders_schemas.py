"""Wire contracts must preserve native results and mutation evidence."""

import asyncio
import json

from mcp_types import CallToolRequestParams
from jsonschema import Draft202012Validator

from app.mcp_server import create_mcp_server
from app.reminders import REMINDER_TOOLS, RemindersError
from app.reminders_schemas import VALIDATORS
from tests.test_reminders import PRIVATE, simulated_go


def test_every_reminders_tool_publishes_success_and_error_contracts():
    server = create_mcp_server(None)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(VALIDATORS) == REMINDER_TOOLS
    for name in REMINDER_TOOLS:
        schema = tools[name].output_schema
        assert schema["type"] == "object"
        Draft202012Validator.check_schema(schema)
        assert len(schema["anyOf"]) == 2
        error = schema["$defs"]["ReminderError"]
        assert "error_code" in error["required"]
        assert set(error["properties"]["write_status"]["anyOf"][0]["enum"]) == {"not_sent", "failed", "succeeded", "unknown"}
        VALIDATORS[name].validate_python(RemindersError("not_configured").details)
        Draft202012Validator(schema).validate(RemindersError("not_configured").details)
    page_defs = tools["list_reminders"].output_schema["$defs"]
    assert page_defs["ReminderTree"]["properties"]["subtasks"]["items"]["$ref"].endswith("/ReminderTree")
    assert "list_id" in page_defs["StructureWarning"]["required"]
    batch_defs = tools["batch_update_reminders"].output_schema["$defs"]
    assert "BatchNativeResult" in batch_defs
    assert "structuredContent" in batch_defs["BatchNativeResult"]["required"]
    assert "failed_operation" in batch_defs["BatchResult"]["properties"]
    assert "order_verification" in tools["move_reminder"].output_schema["$defs"]["MoveResult"]["properties"]
    assert "order_verification" in tools["reorder_reminders"].output_schema["$defs"]["ReorderResult"]["properties"]
    for name in ("move_reminder", "reorder_reminders"):
        VALIDATORS[name].validate_python(RemindersError("upstream_mismatch", write_status="succeeded",
                                                       order_verification="mismatch", retry_class="retryable_after_read").details)


def test_success_validation_preserves_future_fields_and_native_content(monkeypatch):
    data = {"id": "exact-id", "status": "created", "write_status": "succeeded", "future": {"native": PRIVATE}}
    native = {"content": [{"type": "text", "text": PRIVATE}], "structuredContent": data}
    service, _ = simulated_go(monkeypatch, result=native)
    result = asyncio.run(create_mcp_server(None, reminders_service=service)._handle_call_tool(
        None, CallToolRequestParams(name="create_reminder", arguments={"list_id": "list", "title": PRIVATE}),
    ))
    assert not result.is_error
    assert result.structured_content == data
    assert result.content[0].text == PRIVATE


def test_invalid_success_does_not_hide_confirmed_commit_or_expose_validation_input(monkeypatch):
    service, messages = simulated_go(monkeypatch, result={
        "content": [{"type": "text", "text": PRIVATE}],
        "structuredContent": {"status": "created", "write_status": "succeeded", "id": {"secret": PRIVATE}},
    })
    result = asyncio.run(create_mcp_server(None, reminders_service=service)._handle_call_tool(
        None, CallToolRequestParams(name="create_reminder", arguments={"list_id": "list", "title": PRIVATE}),
    ))
    assert result.is_error
    assert result.structured_content["error_code"] == "backend_protocol_error"
    assert result.structured_content["write_status"] == "succeeded"
    assert result.structured_content["retry_class"] == "retryable_after_read"
    assert PRIVATE not in json.dumps(result.model_dump(by_alias=True))
    assert len([item for item in messages if item["method"] == "tools/call"]) == 1
