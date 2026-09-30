"""Opt-in read-only smoke test through the deployed Python MCP endpoint."""

import asyncio
import os

from mcp import Client
import pytest

from app.reminders import REMINDER_TOOLS, quiet_transport_logs


pytestmark = pytest.mark.live


def test_live_python_go_reminders_read_only():
    if os.environ.get("RUN_LIVE_REMINDERS_TESTS") != "1":
        pytest.skip("set RUN_LIVE_REMINDERS_TESTS=1 to read Reminders through the Python endpoint")

    async def smoke():
        endpoint = os.environ.get("LIVE_REMINDERS_MCP_URL", "http://127.0.0.1:8080/mcp")
        with quiet_transport_logs():
            async with asyncio.timeout(480):
                async with Client(endpoint, mode="legacy", read_timeout_seconds=210, cache=None) as client:
                    tools = await client.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert REMINDER_TOOLS | {"list_calendars", "search_emails", "get_email_attachment"} <= names
                    lists = await client.call_tool("list_reminder_lists", {})
                    assert not lists.is_error, "Reminders read failed; check the Go login or device approval."
                    active = await client.call_tool("list_reminders", {"include_completed": False, "limit": 5})
                    assert not active.is_error, "Active-reminder read failed."
                    assert isinstance(lists.structured_content.get("lists"), list)
                    page = active.structured_content
                    assert isinstance(page.get("reminders"), list)
                    assert all(not item["completed"] for item in page["reminders"])
                    sampled = 0
                    if page["reminders"]:
                        item = await client.call_tool("get_reminder", {"id": page["reminders"][0]["id"]})
                        assert not item.is_error, "Individual-reminder read failed."
                        assert isinstance(item.structured_content.get("reminder"), dict)
                        sampled = 1
                    shared_lists = participants = 0
                    for reminder_list in lists.structured_content["lists"]:
                        people = await client.call_tool("list_reminder_participants", {"list_id": reminder_list["id"]})
                        if people.is_error:
                            raise AssertionError("Shared-list participant read failed.")
                        data = people.structured_content
                        if data.get("list_id") != reminder_list["id"] or not isinstance(data.get("participants"), list):
                            raise AssertionError("Invalid participant result; no account details logged.")
                        ids = [person.get("id") for person in data["participants"]]
                        if not all(ids) or len(ids) != len(set(ids)):
                            raise AssertionError("Invalid participant identities; no account details logged.")
                        if data.get("shared"):
                            shared_lists += 1
                            participants += len(ids)
                        elif ids:
                            raise AssertionError("A private list returned collaborators.")
                    return len(lists.structured_content["lists"]), page["total"], sampled, shared_lists, participants

    try:
        lists, active, sampled, shared_lists, participants = asyncio.run(smoke())
    except AssertionError:
        raise
    except Exception as error:
        raise AssertionError(f"Live Reminders smoke failed: {error.__class__.__name__}") from None
    print(f"Read-only Python/Go smoke passed: lists={lists} shared_lists={shared_lists} participants={participants} active={active} sampled={sampled}")
