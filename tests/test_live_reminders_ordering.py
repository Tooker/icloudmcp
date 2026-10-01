"""Authorized ordering regression with delta/full sync and own-marker cleanup."""

import asyncio
import os
from uuid import uuid4

from mcp import Client
import pytest

from app.reminders import quiet_transport_logs


pytestmark = pytest.mark.live


def test_live_ordering_top_level_and_children_survive_sync():
    if os.environ.get("RUN_LIVE_REMINDERS_WRITE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_REMINDERS_WRITE_TESTS=1 for authorized writes")
    target = os.environ.get("LIVE_REMINDERS_WRITE_LIST_ID")
    if not target:
        pytest.fail("LIVE_REMINDERS_WRITE_LIST_ID must identify the authorized list")
    marker = "MCPOrdering-" + uuid4().hex
    endpoint = os.environ.get("LIVE_REMINDERS_MCP_URL", "http://127.0.0.1:8080/mcp")

    async def run():
        with quiet_transport_logs():
            async with asyncio.timeout(600):
                async with Client(endpoint, mode="legacy", read_timeout_seconds=210, cache=None) as client:
                    async def invoke(name, args):
                        result = await client.call_tool(name, args)
                        if result.is_error:
                            raise AssertionError("Ordering regression stopped; inspect own markers before retrying")
                        if name in {"move_reminder", "reorder_reminders"}:
                            assert result.structured_content.get("write_status") == "succeeded"
                            assert result.structured_content.get("order_verification") == "verified"
                        return result.structured_content

                    async def page():
                        data = await invoke("list_reminders", {"list_id": target, "include_completed": True, "view": "tree", "limit": 500})
                        assert data.get("next_offset") is None and not data.get("structure_warnings")
                        return data["reminders"]

                    async def check(parent, wanted, *, full=False):
                        await invoke("sync_reminders", {"full": full})
                        items = await page()
                        siblings = [r for r in items if r.get("parent_ref") == parent and not r.get("section_ref")]
                        assert [r["id"] for r in siblings] == wanted, "Requested sibling order did not survive sync"
                        assert all(r["sort_index"] >= 0 for r in siblings)
                        assert len({r["sort_index"] for r in siblings}) == len(siblings)

                    async def create(label, parent=None):
                        args = {"list_id": target, "title": marker + " " + label, "notes": marker, "client_request_id": str(uuid4())}
                        if parent:
                            args["parent_id"] = parent
                        return (await invoke("create_reminder", args))["id"]

                    original = await page()
                    baseline = [r["id"] for r in original if not r.get("parent_ref") and not r.get("section_ref")]
                    preserved_fields = ("id", "title", "notes", "due", "priority", "completed", "parent_ref", "section_ref")
                    before = {r["id"]: {k: r.get(k) for k in preserved_fields} for r in original}
                    parent = None
                    try:
                        parent = await create("Parent")
                        roots = [await create(label) for label in ("A", "B", "C")]
                        children = [await create("Child " + label, parent) for label in ("A", "B", "C")]
                        print("Ordering regression: own_reminders_created=7", flush=True)
                        a, b, c = roots
                        target_order = baseline + [parent, c, a, b]
                        await invoke("reorder_reminders", {"list_id": target, "reminder_ids": target_order})
                        await check(None, target_order)
                        await invoke("move_reminder", {"id": b, "before_id": c})
                        await check(None, baseline + [parent, b, c, a])
                        await invoke("move_reminder", {"id": b, "clear_parent": True})
                        await check(None, target_order)
                        print("Ordering regression: top_level_reorder=true before=true append=true", flush=True)
                        ca, cb, cc = children
                        await invoke("reorder_reminders", {"list_id": target, "parent_id": parent, "reminder_ids": [cc, ca, cb]})
                        await check(parent, [cc, ca, cb])
                        await invoke("move_reminder", {"id": cb, "before_id": cc})
                        await check(parent, [cb, cc, ca])
                        await invoke("move_reminder", {"id": cb, "after_id": ca})
                        await check(parent, [cc, ca, cb], full=True)
                        await check(None, target_order)
                        print("Ordering regression: children_reorder=true before=true after=true full_sync=true", flush=True)
                    finally:
                        own = [r for r in await page() if r.get("notes") == marker]
                        own.sort(key=lambda r: r.get("depth", 0), reverse=True)
                        for item in own:
                            fresh = (await invoke("get_reminder", {"id": item["id"]}))["reminder"]
                            assert fresh.get("notes") == marker and fresh.get("list_ref") == target
                            await invoke("delete_reminder", {"id": item["id"], "confirm": True})
                        assert not any(r.get("notes") == marker for r in await page())
                    await check(None, baseline)
                    after = {r["id"]: {k: r.get(k) for k in preserved_fields} for r in await page()}
                    assert after == before, "Ordering test altered existing reminder contents or hierarchy"

    def leaf_types(error):
        if isinstance(error, BaseExceptionGroup):
            return {name for child in error.exceptions for name in leaf_types(child)}
        return {type(error).__name__}

    try:
        asyncio.run(run())
    except BaseException as error:
        names = ",".join(sorted(leaf_types(error)))
        raise AssertionError(f"Live ordering regression stopped: {names}; inspect own markers") from None
    print("Ordering regression passed: top_level=true children=true before=true after=true append=true delta_sync=true full_sync=true cleanup=true")
