"""Validate and apply a declarative Reminders tree through existing Go tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any, Literal, TYPE_CHECKING
from uuid import UUID

from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.reminders import RemindersError
from app.timing import measure_phase

if TYPE_CHECKING:
    from app.reminders import GoRemindersService


MAX_REMINDERS = 500
MAX_SECTIONS = 100
MAX_DEPTH = 20


class ReminderNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    id: str | None = Field(default=None, description="Exact existing reminder ID; omit to create a new reminder with title.")
    client_request_id: str | None = Field(default=None, description="Optional UUID idempotency key for a new reminder; preserve it when recovering that creation.")
    title: str | None = Field(default=None, description="Required for a new reminder; changes an existing title when supplied.")
    due: str | None = Field(default=None, description="YYYY-MM-DD; omit to preserve an existing due date. Clearing is unsupported.")
    priority: Literal["none", "low", "medium", "high"] | None = None
    notes: str | None = Field(default=None, description="Nonempty notes; omit to preserve existing notes.")
    subtasks: list[ReminderNode] = Field(default_factory=list, description="Children in desired manual order; section is inherited.")


class ReminderSection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    id: str | None = Field(default=None, description="Exact existing section ID; omit to create a new section with title.")
    title: str | None = Field(default=None, description="Heading for a new section. Renaming existing sections is unsupported.")
    reminders: list[ReminderNode] = Field(default_factory=list, description="Top-level reminders in this section, in desired order.")


class BatchStructure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    list_id: str
    reminders: list[ReminderNode]
    sections: list[ReminderSection] = Field(default_factory=list)
    dry_run: bool = True


@dataclass(frozen=True)
class Reference:
    path: str


@dataclass
class Operation:
    tool: str
    target: str
    arguments: dict[str, Any]
    creates: bool = False

    def summary(self) -> dict[str, Any]:
        # Paths identify input nodes without copying titles, notes or payloads.
        return {"tool": self.tool, "target": self.target}


def _invalid() -> None:
    raise RemindersError("invalid_argument")


def _title(value: str | None) -> None:
    if value is not None and (not value.strip() or len(value.encode("utf-8")) > 4096):
        _invalid()


def _flatten(structure: BatchStructure) -> list[tuple[str, ReminderNode, str, str]]:
    """Validate all input before connecting, then flatten parent-first."""
    if not structure.list_id.strip() or len(structure.sections) > MAX_SECTIONS:
        _invalid()
    nodes: list[tuple[str, ReminderNode, str, str]] = []
    ids: set[str] = set()
    section_ids: set[str] = set()
    request_ids: set[UUID] = set()

    def visit(items: list[ReminderNode], prefix: str, parent: str, section: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            _invalid()
        for index, node in enumerate(items):
            path = f"{prefix}[{index}]"
            if len(nodes) >= MAX_REMINDERS:
                _invalid()
            _title(node.title)
            if node.id is None:
                if node.title is None:
                    _invalid()
                if node.client_request_id is not None:
                    try:
                        key = UUID(node.client_request_id)
                    except ValueError:
                        _invalid()
                    if key in request_ids:
                        _invalid()
                    request_ids.add(key)
            elif not node.id.strip() or node.id in ids:
                _invalid()
            else:
                ids.add(node.id)
                if node.client_request_id is not None:
                    _invalid()
            if node.notes == "":
                _invalid()
            if node.due is not None:
                try:
                    if len(node.due) != 10 or date.fromisoformat(node.due).isoformat() != node.due:
                        _invalid()
                except ValueError:
                    _invalid()
            nodes.append((path, node, parent, section))
            if node.subtasks:
                visit(node.subtasks, f"{path}.subtasks", path, section, depth + 1)

    visit(structure.reminders, "reminders", "", "", 1)
    new_section_seen = False
    for index, section in enumerate(structure.sections):
        _title(section.title)
        if section.id is None:
            new_section_seen = True
            if section.title is None:
                _invalid()
        elif not section.id.strip() or section.id in section_ids or section.title is not None or new_section_seen:
            _invalid()
        else:
            section_ids.add(section.id)
        path = f"sections[{index}]"
        visit(section.reminders, f"{path}.reminders", "", path, 1)
    return nodes


def _items(result: CallToolResult, key: str) -> list[dict[str, Any]]:
    data = result.structured_content
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise RemindersError("backend_unavailable")
    items = data[key]
    if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in items):
        raise RemindersError("backend_unavailable")
    if len({item["id"] for item in items}) != len(items):
        raise RemindersError("backend_unavailable")
    return items


def _plan(
    structure: BatchStructure, nodes: list[tuple[str, ReminderNode, str, str]],
    current: list[dict[str, Any]], sections: list[dict[str, Any]],
) -> tuple[list[Operation], dict[str, str]]:
    by_id = {item["id"]: item for item in current}
    # Complete coverage includes completed tasks; omission never means deletion.
    if {node.id for _, node, _, _ in nodes if node.id is not None} != set(by_id):
        _invalid()
    if [section.id for section in structure.sections if section.id is not None] != [item["id"] for item in sections]:
        _invalid()
    if any(item.get("list_ref") != structure.list_id for item in current):
        _invalid()
    if any(item.get("list_id") != structure.list_id for item in sections):
        _invalid()
    identities = {path: node.id for path, node, _, _ in nodes if node.id is not None}
    identities.update({f"sections[{index}]": section.id for index, section in enumerate(structure.sections) if section.id is not None})
    paths = {id: path for path, id in identities.items()}
    section_ids = {item["id"] for item in sections}
    parents: dict[str, str] = {}
    memberships: dict[str, str] = {}
    for item in current:
        parent, section = item.get("parent_ref") or "", item.get("section_ref") or ""
        if (parent and parent not in by_id) or (section and section not in section_ids):
            raise RemindersError("unsupported_structure")
        path = paths[item["id"]]
        parents[path], memberships[path] = paths.get(parent, ""), paths.get(section, "")
    # Reject malformed live cycles before any mutations.
    for path in parents:
        seen: set[str] = set()
        cursor = path
        while cursor:
            if cursor in seen or cursor not in parents:
                raise RemindersError("unsupported_structure")
            seen.add(cursor)
            cursor = parents[cursor]

    operations: list[Operation] = []
    for index, section in enumerate(structure.sections):
        if section.id is None:
            operations.append(Operation("create_reminder_section", f"sections[{index}]", {
                "list_id": structure.list_id, "title": section.title,
            }, creates=True))
    # Detach changing parents first, allowing reversals of ancestor relationships.
    for path, node, parent, _ in nodes:
        if node.id is not None and parents[path] and parents[path] != parent:
            operations.append(Operation("move_reminder", path, {"id": Reference(path), "clear_parent": True}))
            parents[path] = ""
    groups: dict[tuple[str, str], list[Reference]] = {}
    for path, node, parent, section in nodes:
        fields = node.model_dump(exclude_none=True, exclude={"id", "subtasks"})
        if node.id is None:
            arguments = {**fields, "list_id": structure.list_id}
            if parent:
                arguments["parent_id"] = Reference(parent)
            elif section:
                arguments["section_id"] = Reference(section)
            operations.append(Operation("create_reminder", path, arguments, creates=True))
            parents[path], memberships[path] = parent, section
        else:
            item = by_id[node.id]
            priority = {0: "none", 9: "low", 5: "medium", 1: "high"}.get(item.get("priority"))
            changed = {key: value for key, value in fields.items() if value != (priority if key == "priority" else item.get(key))}
            if changed:
                operations.append(Operation("update_reminder", path, {"id": Reference(path), **changed}))
            if parents[path] != parent or memberships[path] != section:
                arguments = {"id": Reference(path)}
                arguments.update({"parent_id": Reference(parent)} if parent else {"clear_parent": True})
                if not parent:
                    arguments.update({"section_id": Reference(section)} if section else {"clear_section": True})
                operations.append(Operation("move_reminder", path, arguments))
                parents[path] = parent
                # Go keeps the moved subtree together and propagates its section.
                affected = {path}
                while True:
                    children = {child for child, owner in parents.items() if owner in affected}
                    if children <= affected:
                        break
                    affected.update(children)
                for child in affected:
                    memberships[child] = section
        groups.setdefault((parent, section), []).append(Reference(path))
    for (parent, section), siblings in groups.items():
        if len(siblings) < 2:
            continue
        arguments = {"list_id": structure.list_id, "reminder_ids": siblings}
        if parent:
            arguments["parent_id"] = Reference(parent)
        elif section:
            arguments["section_id"] = Reference(section)
        operations.append(Operation("reorder_reminders", parent or section or "reminders", arguments))
    return operations, identities


def _resolve(value: Any, identities: dict[str, str]) -> Any:
    if isinstance(value, Reference):
        return identities[value.path]
    if isinstance(value, list):
        return [_resolve(item, identities) for item in value]
    return value


async def run_batch(service: GoRemindersService, arguments: dict[str, Any]) -> CallToolResult:
    try:
        structure = BatchStructure.model_validate(arguments)
        nodes = _flatten(structure)
    except ValidationError:
        raise RemindersError("invalid_argument") from None

    operations: list[Operation] = []
    identities: dict[str, str] = {}
    completed: list[dict[str, Any]] = []
    pending: Operation | None = None
    failure: RemindersError | None = None
    try:
        async with service.tool_session() as session:
            # Discovery is read-only. Missing structural tools fail before writes.
            tools = await service.discover(session)
            names = set(tools)
            if not {"list_reminder_lists", "list_reminder_sections", "list_reminders"} <= names:
                raise RemindersError("backend_upgrade_required")
            lists = _items(await service.invoke(session, "list_reminder_lists", {}), "lists")
            if structure.list_id not in {item["id"] for item in lists}:
                raise RemindersError("not_found")
            sections = _items(await service.invoke(session, "list_reminder_sections", {"list_id": structure.list_id}), "sections")
            page = await service.invoke(session, "list_reminders", {
                "list_id": structure.list_id, "include_completed": True, "limit": MAX_REMINDERS, "offset": 0,
            })
            current = _items(page, "reminders")
            if page.structured_content.get("total") != len(current) or page.structured_content.get("next_offset") is not None:
                _invalid()
            with measure_phase("reminders_batch_plan"):
                operations, identities = _plan(structure, nodes, current, sections)
            if not {operation.tool for operation in operations} <= names:
                raise RemindersError("backend_upgrade_required")
            for operation in operations:
                if operation.tool == "create_reminder" and "client_request_id" in operation.arguments:
                    service._validate(operation.tool, operation.arguments, session.request_id)
                    if "client_request_id" not in tools[operation.tool].input_schema.get("properties", {}):
                        raise RemindersError("unsupported_backend", operation=operation.tool,
                                             request_id=session.request_id, write_status="not_sent")
            if not structure.dry_run:
                for operation in operations:
                    resolved = {key: _resolve(value, identities) for key, value in operation.arguments.items()}
                    pending = operation
                    result = await service.invoke(session, operation.tool, resolved)
                    if operation.creates:
                        data = result.structured_content
                        id = data.get("id") if isinstance(data, dict) else None
                        if not isinstance(id, str) or not id or id in identities.values():
                            raise RemindersError("write_result_unknown", operation=operation.tool,
                                                 request_id=session.request_id, write_status="unknown",
                                                 retry_class="retryable_after_read")
                        identities[operation.target] = id
                    completed.append({**operation.summary(), "result": result.model_dump(by_alias=True, exclude_none=True)})
                    pending = None
    except RemindersError as error:
        failure = error

    payload: dict[str, Any] = {
        "list_id": structure.list_id,
        "status": "failed" if failure else "preview" if structure.dry_run else "applied",
        "dry_run": structure.dry_run,
        "atomic": False,
        "planned_operations": len(operations),
        "completed_operations": len(completed),
        "operations": completed if not structure.dry_run else [operation.summary() for operation in operations],
        "ids": identities,
    }
    if failure:
        failure.details.setdefault("operation", pending.tool if pending else "batch_update_reminders")
        failure.details.setdefault("write_status", "unknown" if pending else "not_sent")
        payload["error"] = {**failure.details, "code": failure.code, "message": str(failure)}
        payload["failed_operation"] = pending.summary() if pending else None
        payload["write_result_unknown"] = pending is not None and failure.details.get("write_status", "unknown") == "unknown"
        payload["inspect_before_retry"] = bool(completed) or pending is not None
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload, is_error=failure is not None,
    )
