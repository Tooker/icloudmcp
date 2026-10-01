"""Authorized mutation regression; native test sections need separate cleanup.

The normal live smoke remains read-only. The optional private journal records
the section identity for cleanup, since MCP has no section-deletion tool.
"""

import asyncio
import os
import json
from pathlib import Path
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
    cycles = int(os.environ.get("LIVE_REMINDERS_WRITE_CYCLES", "8"))
    if not 0 <= cycles <= len(titles):
        pytest.fail("LIVE_REMINDERS_WRITE_CYCLES must be between 0 and 8")
    titles = titles[:cycles]

    async def run():
        created = set()
        removed = set()
        parent_id = None
        section_id = None
        journal = os.environ.get("LIVE_REMINDERS_WRITE_JOURNAL")

        def save_journal():
            if journal:
                path = Path(journal)
                path.write_text(json.dumps({"marker": marker, "list_id": target, "section_id": section_id, "created_ids": sorted(created), "removed_ids": sorted(removed)}))
                path.chmod(0o600)

        save_journal()
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
                    print("Write regression: discovery=true")
                    section = await invoke("create_reminder_section", {"list_id": target, "title": marker})
                    section_id = section.structured_content["id"]
                    save_journal()
                    print("Write regression: native_section=true")
                    parent = await invoke("create_reminder", {
                        "title": marker, "list_id": target, "notes": marker, "section_id": section_id, "client_request_id": str(uuid4()),
                    })
                    if parent.structured_content.get("write_status") != "succeeded":
                        raise AssertionError("Confirmed creation lacks machine-readable write status")
                    parent_id = parent.structured_content["id"]
                    created.add(parent_id)
                    anchor = await invoke("create_reminder", {"title": marker + " anchor", "list_id": target, "parent_id": parent_id, "notes": marker, "client_request_id": str(uuid4())})
                    anchor_id = anchor.structured_content["id"]
                    created.add(anchor_id)
                    save_journal()
                    for title in titles:
                        arguments = {"title": title, "list_id": target, "parent_id": parent_id,
                                     "notes": marker, "due": "2026-10-15", "priority": "high",
                                     "client_request_id": str(uuid4())}
                        result = await invoke("create_reminder", arguments)
                        rid = result.structured_content["id"]
                        created.add(rid)
                        save_journal()
                        # This deliberate replay tests keyed idempotency after a confirmed write.
                        replay = await invoke("create_reminder", arguments)
                        if replay.structured_content["id"] != rid or replay.structured_content["status"] != "already_created":
                            raise AssertionError("Keyed replay did not recover the same reminder")
                        read = await invoke("get_reminder", {"id": rid})
                        item = read.structured_content["reminder"]
                        if (item["title"] != title or item.get("notes") != marker or item.get("due") != "2026-10-15"
                                or item.get("priority") != 1 or item.get("parent_ref") != parent_id or item.get("section_ref") != section_id):
                            raise AssertionError("Creation did not preserve exact text, date, priority or parent")
                        updated = title + " (Test)"
                        await invoke("update_reminder", {"id": rid, "title": updated})
                        read = await invoke("get_reminder", {"id": rid})
                        if read.structured_content["reminder"]["title"] != updated:
                            raise AssertionError("Updated title did not roundtrip exactly")
                        await invoke("move_reminder", {"id": rid, "clear_parent": True, "clear_section": True})
                        read = await invoke("get_reminder", {"id": rid})
                        if read.structured_content["reminder"].get("parent_ref") or read.structured_content["reminder"].get("section_ref"):
                            raise AssertionError("Outdent/section clear did not roundtrip")
                        await invoke("move_reminder", {"id": rid, "parent_id": parent_id, "before_id": anchor_id})
                        await invoke("reorder_reminders", {"list_id": target, "parent_id": parent_id, "reminder_ids": [anchor_id, rid]})
                        siblings = await invoke("list_reminders", {"list_id": target, "parent_id": parent_id, "include_completed": True, "limit": 500})
                        if [node["id"] for node in siblings.structured_content["reminders"]] != [anchor_id, rid]:
                            raise AssertionError("Native sibling ordering did not roundtrip")
                        await invoke("complete_reminder", {"id": rid})
                        read = await invoke("get_reminder", {"id": rid})
                        if not read.structured_content["reminder"]["completed"]:
                            raise AssertionError("Completion was not observed")
                        await invoke("delete_reminder", {"id": rid, "confirm": True})
                        removed.add(rid)
                        save_journal()
                        absent = await invoke("get_reminder", {"id": rid}, allow_error=True)
                        if not absent.is_error or absent.structured_content.get("error_code") != "not_found":
                            raise AssertionError("Deleted reminder is still present")
                        print(f"Write regression: lifecycles={len(removed)} exact_text=true idempotency=true")
                    # Reconstruct the complete existing tree without editing old contents.
                    current = await page()
                    headings = (await invoke("list_reminder_sections", {"list_id": target})).structured_content["sections"]
                    nodes = {item["id"]: {"id": item["id"], "subtasks": []} for item in current}
                    sections = [{"id": heading["id"], "reminders": []} for heading in headings]
                    groups = {section["id"]: section["reminders"] for section in sections}
                    roots = []
                    for item in current:
                        node = nodes[item["id"]]
                        if item.get("parent_ref"):
                            nodes[item["parent_ref"]]["subtasks"].append(node)
                        else:
                            groups.get(item.get("section_ref"), roots).append(node)
                    batch_title = marker + " batch ÄÖÜ ❤️"
                    nodes[parent_id]["subtasks"].append({"title": batch_title, "notes": marker, "client_request_id": str(uuid4())})
                    arguments = {"list_id": target, "reminders": roots, "sections": sections}
                    preview = await invoke("batch_update_reminders", arguments)
                    if preview.structured_content["status"] != "preview" or preview.structured_content["completed_operations"]:
                        raise AssertionError("Batch preview performed writes")
                    if any(item["title"] == batch_title for item in await page()):
                        raise AssertionError("Preview created its planned reminder")
                    applied = await invoke("batch_update_reminders", {**arguments, "dry_run": False})
                    payload = applied.structured_content
                    if payload["status"] != "applied" or payload["completed_operations"] != payload["planned_operations"]:
                        raise AssertionError("Batch did not preserve all confirmed operation results")
                    new_ids = set(payload["ids"].values()) - set(nodes) - {heading["id"] for heading in headings}
                    if len(new_ids) != 1:
                        raise AssertionError("Batch did not return the exact created identity")
                    created.update(new_ids)
                    save_journal()
                    read = (await invoke("get_reminder", {"id": next(iter(new_ids))})).structured_content["reminder"]
                    if read["title"] != batch_title or read.get("parent_ref") != parent_id or read.get("section_ref") != section_id:
                        raise AssertionError("Batch creation did not preserve text and inherited structure")
                    print("Write regression: batch_preview=true batch_apply=true")
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
                        removed.add(rid)
                        save_journal()
                    if any(item.get("notes") == marker for item in await page()):
                        raise AssertionError("Own marked test reminders remain; inspect before retrying")
        return len(titles)

    try:
        count = asyncio.run(run())
    except AssertionError:
        raise
    except Exception as error:
        def leaf_types(item):
            if isinstance(item, BaseExceptionGroup):
                return {name for child in item.exceptions for name in leaf_types(child)}
            return {item.__class__.__name__}
        # ExceptionGroup may wrap a failed assertion on leaving the MCP transport.
        # Report types only, never arbitrary upstream exception messages.
        names = ",".join(sorted(leaf_types(error)))
        raise AssertionError(f"Live write regression failed: {names}; inspect own test markers") from None
    print(f"Live write regression passed: lifecycles={count}, reminder_cleanup=true, section_cleanup=manual")
