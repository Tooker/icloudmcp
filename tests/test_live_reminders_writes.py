"""Separately authorized mutation regression; the normal live smoke stays read-only."""

import asyncio
import os
from uuid import uuid4

from mcp import Client
import pytest

from app.reminders import quiet_transport_logs

pytestmark = pytest.mark.live


def test_live_reminders_own_marked_write_lifecycle():
    if os.environ.get("RUN_LIVE_REMINDERS_WRITE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_REMINDERS_WRITE_TESTS=1 for explicitly authorized writes")
    target = os.environ.get("LIVE_REMINDERS_WRITE_LIST_ID")
    if not target:
        pytest.fail("LIVE_REMINDERS_WRITE_LIST_ID must identify the explicitly authorized test list")
    endpoint = os.environ.get("LIVE_REMINDERS_WRITE_MCP_URL", "http://127.0.0.1:8080/mcp")
    marker = "MCPRegression-" + uuid4().hex
    titles = [
        "Rollläden im Wohnzimmer getrennt steuerbar", "Glücklich sein und sich lieben! 🥰",
        "3,43 % Sparkasse Dortmund, 10 Jahre Zinsbindung", "❤️", "ÄÖÜ äöü ß",
        "!#$%&'()*+,-./:;<=>?@[\\]^_`{|}~", "Nur noch schöne Dinge machen ❤️",
        "Alina fragen, ob sie eine Risikolebensversicherung abgeschlossen hat",
    ]

    async def run():
        created = set()
        removed = set()
        parent_id = None
        with quiet_transport_logs():
            async with Client(endpoint, mode="legacy", read_timeout_seconds=210, cache=None) as client:
                async def invoke(name, arguments, *, allow_error=False):
                    result = await client.call_tool(name, arguments)
                    if result.is_error and not allow_error:
                        code = (result.structured_content or {}).get("error_code", "unknown")
                        raise AssertionError(f"{name} failed ({code}); no automatic mutation retry")
                    return result

                async def page():
                    values, offset = [], 0
                    while True:
                        result = await invoke("list_reminders", {
                            "list_id": target, "include_completed": True, "limit": 500, "offset": offset,
                        })
                        payload = result.structured_content
                        values.extend(payload["reminders"])
                        offset = payload.get("next_offset")
                        if offset is None:
                            return values

                try:
                    lists = await invoke("list_reminder_lists", {})
                    if not any(item["id"] == target for item in lists.structured_content["lists"]):
                        raise AssertionError("Authorized list does not exist; no writes made")
                    parent = await invoke("create_reminder", {
                        "title": marker, "list_id": target, "notes": marker, "client_request_id": str(uuid4()),
                    })
                    if parent.structured_content.get("write_status") != "succeeded":
                        raise AssertionError("Confirmed creation lacks machine-readable write status")
                    parent_id = parent.structured_content["id"]
                    created.add(parent_id)
                    for title in titles:
                        arguments = {"title": title, "list_id": target, "parent_id": parent_id,
                                     "notes": marker, "due": "2026-10-15", "priority": "high",
                                     "client_request_id": str(uuid4())}
                        result = await invoke("create_reminder", arguments)
                        rid = result.structured_content["id"]
                        created.add(rid)
                        # This deliberate replay tests keyed idempotency after a confirmed write.
                        replay = await invoke("create_reminder", arguments)
                        if replay.structured_content["id"] != rid or replay.structured_content["status"] != "already_created":
                            raise AssertionError("Keyed replay did not recover the same reminder")
                        read = await invoke("get_reminder", {"id": rid})
                        item = read.structured_content["reminder"]
                        if (item["title"] != title or item.get("notes") != marker or item.get("due") != "2026-10-15"
                                or item.get("priority") != 1 or item.get("parent_ref") != parent_id):
                            raise AssertionError("Creation did not preserve exact text, date, priority or parent")
                        updated = title + " (Test)"
                        await invoke("update_reminder", {"id": rid, "title": updated})
                        read = await invoke("get_reminder", {"id": rid})
                        if read.structured_content["reminder"]["title"] != updated:
                            raise AssertionError("Updated title did not roundtrip exactly")
                        await invoke("complete_reminder", {"id": rid})
                        read = await invoke("get_reminder", {"id": rid})
                        if not read.structured_content["reminder"]["completed"]:
                            raise AssertionError("Completion was not observed")
                        await invoke("delete_reminder", {"id": rid, "confirm": True})
                        removed.add(rid)
                        absent = await invoke("get_reminder", {"id": rid}, allow_error=True)
                        if not absent.is_error or absent.structured_content.get("error_code") != "not_found":
                            raise AssertionError("Deleted reminder is still present")
                        print(f"Write regression: lifecycles={len(removed)} exact_text=true idempotency=true")
                finally:
                    # Locate uncertain creations by our random marker in notes, never title similarity.
                    own = {item["id"] for item in await page() if item.get("notes") == marker}
                    own |= created - removed
                    for rid in sorted(own, key=lambda value: value == parent_id):
                        read = await invoke("get_reminder", {"id": rid}, allow_error=True)
                        if read.is_error:
                            continue
                        if read.structured_content["reminder"].get("notes") != marker:
                            raise AssertionError("Test ownership changed; cleanup stopped")
                        await invoke("delete_reminder", {"id": rid, "confirm": True})
                    if any(item.get("notes") == marker for item in await page()):
                        raise AssertionError("Own marked test reminders remain; inspect before retrying")
        return len(titles)

    try:
        count = asyncio.run(run())
    except AssertionError:
        raise
    except Exception as error:
        raise AssertionError(f"Live write regression failed: {error.__class__.__name__}; inspect own test markers") from None
    print(f"Live write regression passed: lifecycles={count}, cleanup=true")
