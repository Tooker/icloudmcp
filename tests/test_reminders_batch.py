from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging

import httpx2
from loguru import logger
from mcp_types import CallToolRequestParams
import pytest

from app.config import RemindersConfig
from app.mcp_server import create_mcp_server
from app.reminders import GoRemindersService, REMINDER_TOOLS


PRIVATE = "PRIVATE_BATCH_TITLE_NOTES_ID_OR_TOKEN"
READS = {"list_reminder_lists", "list_reminder_sections", "list_reminders"}


@pytest.fixture
def backend(monkeypatch):
    original_client = httpx2.AsyncClient
    state = {
        "sections": [],
        "reminders": [
            {"id": "a", "title": "A", "list_ref": "list", "priority": 0, "completed": False},
            {"id": "b", "title": "B", "list_ref": "list", "parent_ref": "a", "priority": 9,
             "completed": True, "assignee_id": PRIVATE},
            {"id": "c", "title": "C", "list_ref": "list", "priority": 0, "completed": False},
        ],
        "tools": set(REMINDER_TOOLS) - {"batch_update_reminders"},
        "calls": [], "sessions": 0, "writes": 0, "delay": 0,
        "fail_write": None, "failure_code": "icloud_write_failed", "bad_create_result": False,
    }

    async def handle(request):
        assert request.url.path == "/mcp"
        assert request.headers.get("authorization") == f"Bearer {PRIVATE}"
        if request.method == "GET":
            return httpx2.Response(405)
        message = json.loads(request.content)
        method = message["method"]
        if method == "notifications/initialized":
            return httpx2.Response(202)
        if method == "initialize":
            state["sessions"] += 1
            payload = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                       "serverInfo": {"name": "simulated-go", "version": "1"}}
        elif method == "tools/list":
            payload = {"tools": [{"name": name, "inputSchema": {"type": "object", "properties": {}}}
                                 for name in sorted(state["tools"])]}
        else:
            assert method == "tools/call"
            name, arguments = message["params"]["name"], message["params"]["arguments"]
            state["calls"].append((name, arguments))
            if state["delay"]:
                await asyncio.sleep(state["delay"])
            if name not in READS:
                state["writes"] += 1
                if state["writes"] == state["fail_write"]:
                    payload = {"isError": True, "content": [{"type": "text", "text": f'{state["failure_code"]}: {PRIVATE}'}]}
                    return httpx2.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": payload})
            if name == "list_reminder_lists":
                data = {"lists": [{"id": "list", "name": PRIVATE}]}
            elif name == "list_reminder_sections":
                data = {"list_id": "list", "sections": state["sections"]}
            elif name == "list_reminders":
                assert arguments["include_completed"] is True
                data = {"reminders": state["reminders"][:500], "total": len(state["reminders"])}
            elif name == "create_reminder_section":
                id = f'new-section-{state["writes"]}'
                state["sections"].append({"id": id, "title": arguments["title"], "list_id": "list"})
                data = {"id": id, "status": "created"}
            elif name == "create_reminder":
                id = f'new-reminder-{state["writes"]}'
                parent = next((item for item in state["reminders"] if item["id"] == arguments.get("parent_id")), None)
                item = {"id": id, "title": arguments["title"], "list_ref": arguments["list_id"],
                        "parent_ref": arguments.get("parent_id"), "completed": False,
                        "section_ref": parent.get("section_ref") if parent else arguments.get("section_id")}
                state["reminders"].append(item)
                data = {"id": id, "status": "created"}
                if state["bad_create_result"]:
                    data = {"status": "created"}
            elif name == "update_reminder":
                item = next(item for item in state["reminders"] if item["id"] == arguments["id"])
                for key in ("title", "due", "notes", "priority"):
                    if key in arguments:
                        item[key] = {"none": 0, "low": 9, "medium": 5, "high": 1}[arguments[key]] if key == "priority" else arguments[key]
                data = {"id": item["id"], "status": "updated", "extra": PRIVATE}
            elif name == "move_reminder":
                item = next(item for item in state["reminders"] if item["id"] == arguments["id"])
                if arguments.get("clear_parent"):
                    item["parent_ref"] = None
                elif "parent_id" in arguments:
                    # Model the backend's cycle check, even for temporary states.
                    parent = arguments["parent_id"]
                    while parent:
                        assert parent != item["id"]
                        parent = next(node for node in state["reminders"] if node["id"] == parent).get("parent_ref")
                    item["parent_ref"] = arguments["parent_id"]
                section = item.get("section_ref")
                if item.get("parent_ref"):
                    section = next(node for node in state["reminders"] if node["id"] == item["parent_ref"]).get("section_ref")
                elif arguments.get("clear_section"):
                    section = None
                elif "section_id" in arguments:
                    section = arguments["section_id"]
                affected = {item["id"]}
                while True:
                    children = {node["id"] for node in state["reminders"] if node.get("parent_ref") in affected}
                    if children <= affected:
                        break
                    affected.update(children)
                for node in state["reminders"]:
                    if node["id"] in affected:
                        node["section_ref"] = section
                data = {"id": item["id"], "status": "moved"}
            elif name == "reorder_reminders":
                parent = arguments.get("parent_id")
                section = next(node for node in state["reminders"] if node["id"] == parent).get("section_ref") if parent else arguments.get("section_id")
                siblings = [node["id"] for node in state["reminders"] if node.get("parent_ref") == parent and node.get("section_ref") == section]
                assert set(siblings) == set(arguments["reminder_ids"])
                assert len(siblings) == len(arguments["reminder_ids"])
                data = {"id": "list", "status": "reordered"}
            else:
                raise AssertionError("Batch called an unexpected tool")
            payload = {"content": [{"type": "text", "text": json.dumps(data)}], "structuredContent": data}
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": payload})

    monkeypatch.setattr("app.reminders.httpx2.AsyncClient", lambda **kwargs: original_client(transport=httpx2.MockTransport(handle), **kwargs))
    service = GoRemindersService(RemindersConfig("http://reminders:8080/mcp", PRIVATE, 1))
    return service, state


def invoke(service, arguments):
    server = create_mcp_server(None, reminders_service=service)
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="batch_update_reminders", arguments=arguments)))


def current_tree():
    return {"list_id": "list", "reminders": [{"id": "a", "subtasks": [{"id": "b"}]}, {"id": "c"}]}


def new_tree():
    return {"list_id": "list", "reminders": [], "sections": [{"title": PRIVATE, "reminders": [
        {"title": PRIVATE, "notes": PRIVATE, "due": "2026-10-02", "subtasks": [
            {"id": "b", "subtasks": [{"id": "a", "priority": "high", "notes": PRIVATE}]},
            {"id": "c", "subtasks": [{"title": PRIVATE}]},
        ]},
    ]}]}


def test_default_preview_validates_full_tree_without_writes_and_hides_contents_in_logs(backend, caplog):
    service, state = backend
    original = deepcopy(state["reminders"])
    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        with caplog.at_level(logging.DEBUG):
            result = invoke(service, new_tree())
    finally:
        logger.remove(sink)
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "preview" and data["atomic"] is False
    assert data["planned_operations"] > 0 and data["completed_operations"] == 0
    assert state["sessions"] == 1 and state["writes"] == 0
    assert state["reminders"] == original and not state["sections"]
    assert {name for name, _ in state["calls"]} == READS
    assert PRIVATE not in "\n".join(logs) + caplog.text


def test_apply_resolves_new_ids_reverses_ancestors_and_preserves_completion_and_assignment(backend):
    service, state = backend
    result = invoke(service, {**new_tree(), "dry_run": False})
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "applied"
    assert data["completed_operations"] == data["planned_operations"] == state["writes"]
    assert state["sessions"] == 1
    ids = data["ids"]
    root = ids["sections[0].reminders[0]"]
    section = ids["sections[0]"]
    reminders = {node["id"]: node for node in state["reminders"]}
    assert reminders["b"]["parent_ref"] == root
    assert reminders["a"]["parent_ref"] == "b"
    assert reminders["c"]["parent_ref"] == root
    assert reminders[ids["sections[0].reminders[0].subtasks[1].subtasks[0]"]]["parent_ref"] == "c"
    assert all(item["section_ref"] == section for item in state["reminders"])
    assert reminders["a"]["priority"] == 1 and reminders["a"]["notes"] == PRIVATE
    assert reminders["b"]["completed"] and reminders["b"]["assignee_id"] == PRIVATE
    reorder = [(name, args) for name, args in state["calls"] if name == "reorder_reminders"]
    assert reorder == [("reorder_reminders", {"list_id": "list", "parent_id": root, "reminder_ids": ["b", "c"]})]
    update = next(operation for operation in data["operations"] if operation["tool"] == "update_reminder")
    assert update["result"]["structuredContent"]["extra"] == PRIVATE


@pytest.mark.parametrize("change", [
    lambda args: args["reminders"].pop(),
    lambda args: args["reminders"][0]["subtasks"].clear(),  # completed tasks must be included
    lambda args: args["reminders"].append({"id": "a"}),
    lambda args: args["reminders"].append({"id": "foreign"}),
    lambda args: args["reminders"].append({"title": "  "}),
    lambda args: args["reminders"].append({}),
    lambda args: args["reminders"][0].update(due="2026-02-30"),
    lambda args: args["reminders"][0].update(notes=""),
    lambda args: args["reminders"][0].update(title="é" * 2049),
    lambda args: args["reminders"][0].update(completed=True),
    lambda args: args["reminders"][0].update(participant_id=PRIVATE),
])
def test_invalid_target_never_writes(backend, change):
    service, state = backend
    arguments = current_tree()
    change(arguments)
    result = invoke(service, {**arguments, "dry_run": False})
    assert result.is_error
    assert state["writes"] == 0


@pytest.mark.parametrize("bad_state", ["foreign_list", "missing_parent", "cycle", "partial_page", "wrong_section_list"])
def test_invalid_live_structure_never_writes(backend, bad_state):
    service, state = backend
    if bad_state == "foreign_list":
        state["reminders"][0]["list_ref"] = "another-list"
    elif bad_state == "missing_parent":
        state["reminders"][0]["parent_ref"] = "missing"
    elif bad_state == "cycle":
        state["reminders"][0]["parent_ref"] = "b"
    elif bad_state == "partial_page":
        state["reminders"].extend({"id": f"other-{index}", "list_ref": "list"} for index in range(501))
    else:
        state["sections"] = [{"id": "s", "list_id": "another-list"}]
    result = invoke(service, {**current_tree(), "dry_run": False})
    assert result.is_error and state["writes"] == 0


@pytest.mark.parametrize("missing_tool", ["list_reminder_sections", "create_reminder_section", "move_reminder", "reorder_reminders"])
def test_missing_backend_capability_is_reported_before_any_write(backend, missing_tool):
    service, state = backend
    state["tools"].remove(missing_tool)
    result = invoke(service, {**new_tree(), "dry_run": False})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "backend_upgrade_required"
    assert state["writes"] == 0


def test_failure_keeps_completed_results_created_ids_and_uncertain_step_without_replaying(backend, caplog):
    service, state = backend
    state["fail_write"] = 4
    logs = []
    sink = logger.add(lambda message: logs.append(message.record["message"]))
    try:
        with caplog.at_level(logging.DEBUG):
            result = invoke(service, {**new_tree(), "dry_run": False})
    finally:
        logger.remove(sink)
    assert result.is_error
    data = result.structured_content
    assert data["status"] == "failed" and data["completed_operations"] == 3
    assert data["ids"]["sections[0]"].startswith("new-section-")
    assert data["ids"]["sections[0].reminders[0]"].startswith("new-reminder-")
    assert data["failed_operation"]["tool"] == "move_reminder"
    assert data["write_result_unknown"] and data["inspect_before_retry"]
    assert data["error"]["code"] == "icloud_write_failed"
    assert PRIVATE not in data["error"]["message"]
    assert state["writes"] == 4
    assert any("outcome=icloud_write_failed" in entry and "result_count=3" in entry for entry in logs)
    assert PRIVATE not in "\n".join(logs) + caplog.text


def test_unusable_create_response_stops_without_repeating_creation(backend):
    service, state = backend
    state["bad_create_result"] = True
    result = invoke(service, {**new_tree(), "dry_run": False})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "write_result_unknown"
    assert result.structured_content["failed_operation"]["tool"] == "create_reminder"
    assert state["writes"] == 3


def test_whole_batch_has_one_total_deadline_and_reports_inflight_write(backend):
    service, state = backend
    service.config = RemindersConfig("http://reminders:8080/mcp", PRIVATE, 0.23)
    state["delay"] = 0.04
    result = invoke(service, {**new_tree(), "dry_run": False})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "request_timeout"
    assert result.structured_content["completed_operations"] < result.structured_content["planned_operations"]
    assert result.structured_content["write_result_unknown"]
    assert state["sessions"] == 1
    assert len([name for name, _ in state["calls"] if name == "create_reminder_section"]) == 1


def test_cancellation_propagates_and_no_further_writes_are_started(backend):
    service, state = backend
    state["delay"] = 0.02

    async def run():
        task = asyncio.create_task(service.call_tool("batch_update_reminders", {**new_tree(), "dry_run": False}))
        async with asyncio.timeout(2):
            while not any(name == "create_reminder_section" for name, _ in state["calls"]):
                if task.done():
                    pytest.fail("Batch ended before the first write")
                await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert len([name for name, _ in state["calls"] if name not in READS]) == 1


def test_existing_sections_are_preserved_in_order_and_subtasks_inherit_changes(backend):
    service, state = backend
    state["sections"] = [{"id": "s1", "list_id": "list"}, {"id": "s2", "list_id": "list"}]
    state["reminders"][0]["section_ref"] = "s1"
    state["reminders"][1]["section_ref"] = "s1"
    arguments = {"list_id": "list", "reminders": [], "sections": [
        {"id": "s1", "reminders": [{"id": "c"}]},
        {"id": "s2", "reminders": [{"id": "a", "subtasks": [{"id": "b"}]}]},
    ], "dry_run": False}
    result = invoke(service, arguments)
    assert not result.is_error
    assert state["reminders"][0]["section_ref"] == "s2"
    assert state["reminders"][1]["section_ref"] == "s2"
    assert state["reminders"][2]["section_ref"] == "s1"
    assert state["writes"] == 2  # moving the parent already moves its child


def test_section_reordering_is_rejected_before_writes(backend):
    service, state = backend
    state["sections"] = [{"id": "s1", "list_id": "list"}, {"id": "s2", "list_id": "list"}]
    result = invoke(service, {**current_tree(), "sections": [{"id": "s2"}, {"id": "s1"}], "dry_run": False})
    assert result.is_error and state["writes"] == 0


@pytest.mark.parametrize("bound", ["reminders", "sections", "depth"])
def test_oversized_input_is_rejected_before_connecting(backend, bound):
    service, state = backend
    arguments = current_tree()
    if bound == "reminders":
        arguments["reminders"].extend({"title": "New"} for _ in range(501))
    elif bound == "sections":
        arguments["sections"] = [{"title": "New section"} for _ in range(101)]
    else:
        child = {"title": "New"}
        for _ in range(20):
            child = {"title": "New", "subtasks": [child]}
        arguments["reminders"].append(child)
    result = invoke(service, {**arguments, "dry_run": False})
    assert result.is_error and state["sessions"] == 0 and state["writes"] == 0


def test_empty_list_can_receive_an_entire_new_tree(backend):
    service, state = backend
    state["reminders"] = []
    result = invoke(service, {"list_id": "list", "reminders": [{"title": PRIVATE, "subtasks": [{"title": PRIVATE}]}], "dry_run": False})
    assert not result.is_error
    ids = result.structured_content["ids"]
    assert len(ids) == 2
    assert state["reminders"][1]["parent_ref"] == ids["reminders[0]"]
    assert state["writes"] == 2


def test_mcp_schema_has_recursive_typed_nodes_and_write_annotations():
    server = create_mcp_server(None)
    tool = next(tool for tool in asyncio.run(server.list_tools()) if tool.name == "batch_update_reminders")
    assert set(tool.input_schema["required"]) == {"list_id", "reminders"}
    assert tool.input_schema["properties"]["dry_run"]["default"] is True
    assert tool.input_schema["$defs"]["ReminderNode"]["properties"]["subtasks"]["items"]["$ref"]
    assert tool.annotations.destructive_hint and not tool.annotations.idempotent_hint
    assert not tool.annotations.read_only_hint
