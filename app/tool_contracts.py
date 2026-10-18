"""Publish parameter contracts from the same schemas used for MCP validation."""

from copy import deepcopy
import json
from typing import Annotated, get_type_hints

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from app.tool_usage import usage_description
from app.mcp_errors import ToolFailure, error_result
from pydantic import Field
from app.result_schemas import SCHEMAS, VALIDATORS, safe_evidence
from app.timing import tool_trace


def numeric_bounds(tool, parameter):
    if parameter == "limit":
        maximum = 200 if tool == "list_events" else 1000 if tool == "search_emails" else 50 if tool == "semantic_search_emails" else 100000 if tool == "get_email_attachment" else 1000000 if tool == "get_drive_file" else 500
        return {"ge": 1, "le": maximum}
    if parameter == "offset":
        return {"ge": 0, **({"le": 30000000 if tool == "get_drive_file" else 20000} if "drive" in tool else {})}
    return {
        "max_body_chars": {"ge": 1, "le": 100000},
        "max_depth": {"ge": 0, "le": 10},
        "max_nodes": {"ge": 1, "le": 10000},
    }.get(parameter)


PARAMETERS = {
    "calendar": "Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.",
    "uid": "Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.",
    "title": "Title text; nonblank when creating. On updates null/omission preserves the existing title.",
    "start": "ISO 8601 timestamp for timed events, YYYY-MM-DD for all-day events. Null on list_events defaults to local midnight 30 days ago. On update supply start and end together or omit both to preserve bounds.",
    "end": "ISO 8601 timestamp or all-day exclusive YYYY-MM-DD end, after start. Null on list_events defaults to local midnight 365 days ahead. On update supply start and end together or omit both to preserve bounds.",
    "description": "Event description; null on update preserves it, empty string clears it.",
    "location": "Event location; null on update preserves it, empty string clears it.",
    "all_day": "True for date-only events; false for timed events. Null on update preserves the existing mode.",
    "timezone_name": "IANA timezone, e.g. Europe/Berlin, for naive timed timestamps or all-day/timed conversion. Null uses configured timezone. On update supply it with start/end or an all_day mode change; it does not independently change the timezone.",
    "scope": "occurrence deletes only the original recurrence slot; series deletes the complete event series. No implicit default.",
    "recurrence_id": "Exact original recurrence_id returned by list_events, preserving date/timestamp type and timezone. Required for scope=occurrence; omit for scope=series.",
    "confirm": "Explicit true authorizes this destructive operation; false does not perform it.",
    "mailbox": "Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.",
    "source_mailbox": "Exact source name from list_mailboxes; null uses configured default mailbox.",
    "destination_mailbox": "Exact existing destination name from list_mailboxes; folders are not created automatically.",
    "from_address": "Sender address filter. Null means no sender filter.",
    "to_address": "Recipient address filter. Null means no recipient filter.",
    "subject": "Subject filter. Null means no subject filter.",
    "query": "Search text; null on optional filters means no text filter.",
    "since": "Inclusive earliest IMAP date, YYYY-MM-DD; null means no lower date filter.",
    "before": "Exclusive latest IMAP date, YYYY-MM-DD; null means no upper date filter.",
    "unread_only": "True restricts results to messages without the Seen flag; false includes read and unread messages.",
    "source": "body searches message bodies; attachment searches extracted attachments; null searches both. Only indexed local snapshots are covered.",
    "max_body_chars": "Maximum returned body characters, 1..100000; a truncated body is not the complete message.",
    "expected_uid_validity": "Mailbox generation from a prior result, as a decimal string. Null omits the generation guard; a mismatch rejects a reused UID.",
    "attachment_id": "Opaque attachment ID returned by get_email for this exact UID/mailbox; not a filename or path.",
    "format": "file returns complete original bytes as native MCP resources; text extracts readable text; base64 returns original byte chunks. Only these exact values are accepted.",
    "to": "Array of recipient strings (address or RFC mailbox such as Name <person@example.com>), not a comma-separated string. May be empty if cc/bcc supplies a recipient; at least one recipient overall. No CR/LF.",
    "cc": "Optional array of visible copy recipients; null/omission means none. No CR/LF.",
    "bcc": "Optional array of blind copy recipients; null/omission means none. No CR/LF.",
    "body": "Complete draft body string. Use body_format to declare plain text or HTML. Signature text does not set the From header. Entire MIME message including encoded attachments is limited to 25000000 bytes.",
    "body_format": "Exactly plain (plain text) or html (HTML); text is invalid. Defaults to plain. Parameter name is body_format, not format.",
    "attachments": "Optional array of attachment objects; null/omission means no attachments. Each object requires filename and content_base64, with optional MIME content_type. Maximum 10000000 decoded bytes per attachment and 25000000 bytes for the entire serialized message. No local paths or external URLs.",
    "read": "True sets Seen; false clears Seen. This changes the message's read state.",
    "addressbook_id": "Exact account-scoped ID from list_addressbooks. Null uses the configured default or the sole eligible discovered book; multiple eligible books require an explicit ID. Never pass a remote URL.",
    "contact_id": "Exact account-scoped ID returned by Contacts tools; not a URL or a Reminders participant ID.",
    "contact": "Structured new contact; provide a name or organization. No vCard/URL input, no duplicate merging. Nested fields are described below.",
    "folder_id": "Opaque owned regular folder ID from Drive tools; null selects the Drive root. Shared items, app libraries and packages are unsupported.",
    "file_id": "Opaque regular file ID returned by Drive tools, never a URL or path. Replacement returns a different ID.",
    "name": "New folder name, one nonblank path component; do not include slash, backslash or control characters. Existing names are rejected.",
    "filename": "Filename, one nonblank path component without slash, backslash or control characters.",
    "content_base64": "Strict base64 of complete original file bytes, maximum 30000000 decoded bytes for Drive. Supply exactly one of content_base64, content_text or source_resource_uri.",
    "content_text": "Complete text encoded as UTF-8 (maximum 30000000 bytes). Supply exactly one of content_text, content_base64 or source_resource_uri.",
    "source_resource_uri": "Already-issued private Mail/Drive snapshot URI from this MCP server, valid up to 15 minutes subject to eviction/restart. No filesystem paths or external URLs. Supply exactly one content source.",
    "expected_version": "Exact version returned by Drive reads/listings. Required for replacement and subsequent nonzero-offset chunks; mismatches reject changed files. Discard previously collected chunks on version_changed.",
    "recursive": "True searches descendant folders within traversal bounds; false searches only the selected folder.",
    "max_depth": "Maximum descendant depth for Drive traversal, 0..10; 0 searches only the selected folder.",
    "max_nodes": "Drive traversal budget, 1..10000 nodes. Check coverage_complete; an incomplete search cannot prove absence.",
    "id": "Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.",
    "list_id": "Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.",
    "parent_id": "Exact parent reminder ID in the same list. Creation null means top-level; move null preserves parent unless clear_parent=true; reorder null selects top-level siblings; reads null omit the parent filter.",
    "section_id": "Exact section ID from list_reminder_sections in the same list. Creation null means unsectioned or inherited from parent; move null preserves section unless clear_section=true; reorder null selects unsectioned siblings; reads null omit this filter.",
    "due": "Due date YYYY-MM-DD. Null/omission leaves an existing due date unchanged or creates without a due date; clearing is unsupported.",
    "priority": "Exact string none, low, medium or high, mapped to native 0, 9, 5, 1. Null preserves existing priority or uses backend creation default. none explicitly clears priority; independent of manual order.",
    "notes": "Reminder notes. Null/omission preserves existing notes or creates without notes; clearing existing notes with an empty string is unsupported.",
    "include_completed": "True includes completed tasks. Required when preparing complete reorder/batch structures; false filters them out.",
    "view": "flat returns the flat page; tree additionally nests only subtasks present on that page. parent_ref remains authoritative if a parent is outside the page.",
    "client_request_id": "Optional UUID creation key, supported only by capable Go backends. Preserve key and identical arguments for recovery; older backends reject before writing.",
    "participant_id": "Exact accepted participant ID from list_reminder_participants for this reminder's list. Supply participant_id or clear=true, never both; not an email, name or Contacts ID.",
    "clear": "True removes the assignee; mutually exclusive with participant_id. False requires participant_id.",
    "clear_parent": "True moves to top level; mutually exclusive with parent_id. False/omission preserves parent when parent_id is omitted.",
    "clear_section": "True removes section membership; mutually exclusive with section_id. False/omission preserves membership when section_id is omitted.",
    "before_id": "Exact sibling ID in the target group to insert before; mutually exclusive with after_id. Without either anchor append to the target group.",
    "after_id": "Exact sibling ID in the target group to insert after; mutually exclusive with before_id.",
    "reminder_ids": "Array of every sibling ID exactly once in desired manual order, including completed reminders. All IDs must belong to the selected list/parent/section group.",
    "reminders": "Complete target array of unsectioned top-level reminder nodes in desired order. Include all existing tasks, including completed ones, exactly once across this array and sections. Maximum 500 total tasks, 20 task levels.",
    "sections": "Complete target array of native sections in current section order; existing sections use id, new sections omit id and require title. Append new sections only; no section rename/reorder/deletion. Maximum 100 sections; null means no sections.",
    "dry_run": "True validates/previews without writing (default); false applies sequential non-atomic writes. Preserve confirmed IDs and uncertain steps and inspect before retrying.",
    "full": "True requests full Reminders synchronization; false requests incremental synchronization. Does not perform account login/device approval.",
    "limit": "Maximum number of results for this page. See tool-specific bounds.",
    "offset": "Zero-based nonnegative pagination offset. See tool-specific bounds; advance only using returned coverage/pagination information.",
}

NESTED = {
    "display_name": "Contact's formatted display name.", "given_name": "Given/first name.",
    "family_name": "Family/last name.", "additional_name": "Additional/middle names.",
    "name_prefix": "Name prefix or honorific.", "name_suffix": "Name suffix.",
    "organization": "Organization name; sufficient instead of a person's name.",
    "emails": "Email values with optional labels, at most 50; defaults to an empty array.",
    "phones": "Phone values with optional labels, at most 50; defaults to an empty array.",
    "addresses": "Postal addresses, at most 20; defaults to an empty array. Each needs a nonblank address field.",
    "birthday": "Valid calendar date YYYY-MM-DD; null/omission means no birthday.",
    "notes": "Contact notes; empty string means no notes.",
    "value": "Nonblank email or phone value, depending on the containing array.",
    "label": "Optional free-text label (e.g. home or work); empty string means unlabeled.",
    "po_box": "Post office box.", "extended": "Extended postal address (e.g. apartment).",
    "street": "Street address.", "city": "City/locality.", "region": "State/province/region.",
    "postal_code": "Postal/ZIP code.", "country": "Country text.",
    "filename": PARAMETERS["filename"],
    "content_base64": "Strict base64 of original attachment bytes; maximum 10000000 decoded bytes. No paths or URLs.",
    "content_type": "MIME type such as application/pdf; defaults to application/octet-stream.",
    "priority": PARAMETERS["priority"],
}


def parameter_description(tool, name):
    if name == "limit":
        if tool == "get_drive_file":
            return "Chunk size: text characters 1..100000, base64 decoded bytes 1..1000000. Ignored in file mode, which returns the complete file up to 30000000 bytes."
        if tool == "get_email_attachment":
            return "Chunk size 1..100000: characters for text, decoded bytes for base64. Ignored in file mode, which returns the complete attachment up to 30000000 bytes."
        maximum = 200 if tool == "list_events" else 1000 if tool == "search_emails" else 50 if tool == "semantic_search_emails" else 500
        return f"Maximum results for this page, 1..{maximum}."
    if name == "offset" and tool in {"get_drive_file", "get_email_attachment"}:
        return "Zero-based character offset for text or decoded-byte offset for base64; file requires 0. Decode each base64 chunk separately before concatenation. Drive offset is at most 30000000 and nonzero offsets require expected_version."
    if name == "offset" and "drive" in tool:
        return "Zero-based pagination offset, 0..20000; check coverage_complete and returned pagination before inferring absence."
    if tool in {"create_draft", "update_draft"}:
        if name == "from_address":
            return "Complete MIME From header, e.g. Name <person@example.com>, or a bare email address. Null defaults to the configured IMAP username. This does not verify send-as permissions. The body/signature does not set the sender name; inspect returned from_header/from_address/from_name."
        if name == "subject":
            return "Complete nonblank subject, without CR/LF. Required even when updating; drafts are replaced, not partially patched."
    if name == "query" and tool == "semantic_search_emails":
        return "Nonblank natural-language query embedded with OpenAI; searches indexed local mail/PDF text only."
    if name == "query" and tool == "search_contacts":
        return "Nonblank contact search text, at most 256 characters; case-insensitive substring of name, organization, email or phone. Phone searches ignore formatting. Inspect coverage_complete before inferring absence."
    if name == "query" and tool == "search_drive_files":
        return "Nonblank filename search text, at most 256 characters, within selected owned folders; inspect coverage_complete before inferring absence."
    return PARAMETERS[name]


def type_contract(schema):
    """Describe JSON types/defaults/enums without copying example or input values."""
    if "$ref" in schema:
        result = schema["$ref"].rsplit("/", 1)[-1]
    elif "anyOf" in schema:
        result = " | ".join(type_contract(part) for part in schema["anyOf"])
    elif schema.get("type") == "array":
        result = "array<" + type_contract(schema.get("items", {})) + ">"
    else:
        result = schema.get("type", "object")
    if "enum" in schema:
        result += "; enum=" + json.dumps(schema["enum"], ensure_ascii=False)
    if "const" in schema:
        result += "; const=" + json.dumps(schema["const"], ensure_ascii=False)
    if "default" in schema:
        result += "; default=" + json.dumps(schema["default"], ensure_ascii=False)
    for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern"):
        if key in schema:
            result += f"; {key}=" + json.dumps(schema[key], ensure_ascii=False)
    return result


def described_tool(tool, *, private_backend=False):
    schema = deepcopy(tool.input_schema)
    schema["additionalProperties"] = False
    if tool.name == "get_drive_file":
        schema.setdefault("allOf", []).append({
            "if": {"properties": {"format": {"const": "base64"}}, "required": ["format"]},
            "else": {"properties": {"limit": {"maximum": 100000}}},
        })
        schema["allOf"].append({
            "if": {"properties": {"offset": {"exclusiveMinimum": 0}}, "required": ["offset"]},
            "then": {"required": ["expected_version"], "properties": {"expected_version": {"type": "string", "minLength": 1}}},
        })
    if tool.name in {"get_drive_file", "get_email_attachment"}:
        schema.setdefault("allOf", []).append({
            "if": {"properties": {"format": {"const": "file"}}},
            "then": {"properties": {"offset": {"const": 0}}},
        })
    if tool.name in {"upload_drive_file", "replace_drive_file"}:
        sources = ("content_text", "content_base64", "source_resource_uri")
        schema["oneOf"] = [{"required": [chosen], "properties": {
            key: {"type": "string" if key == chosen else "null"} for key in sources
        }} for chosen in sources if not private_backend or chosen != "source_resource_uri"]
        if private_backend:
            schema["properties"]["source_resource_uri"] = {
                "type": "null", "default": None,
                "description": "Private backend accepts bytes/text only. The common server resolves snapshot URIs before forwarding uploads; omit this parameter here.",
            }
    lines = ["Parameters (JSON; use exact names and enum values; no unknown fields):"]
    for name, field in schema.get("properties", {}).items():
        field.setdefault("description", parameter_description(tool.name, name))
        required = "required" if name in schema.get("required", []) else "optional"
        lines.append(f"- {name}: {type_contract(field)}; {required}. {field['description']}")
    if not schema.get("properties"):
        lines.append("- No parameters; pass {}.")
    for model, definition in schema.get("$defs", {}).items():
        lines.append(f"Nested object {model}:")
        for name, field in definition.get("properties", {}).items():
            if not field.get("description"):
                field["description"] = NESTED[name]
            required = "required" if name in definition.get("required", []) else "optional"
            lines.append(f"- {name}: {type_contract(field)}; {required}. {field['description']}")
    description = (tool.description or "") + "\n\n" + usage_description(tool.name) + "\n\n" + "\n".join(lines)
    if private_backend and tool.name == "get_drive_file":
        description += "\nPrivate backend transport: file mode returns original bytes as structured content_base64; the common public MCP server supplies the embedded resource, snapshot link and resources/read described above."
    return tool.model_copy(update={"input_schema": schema, "description": description, "output_schema": deepcopy(SCHEMAS[tool.name])})


class DescribedMCPServer(MCPServer):
    def add_tool(self, fn, name=None, **kwargs):
        tool_name = name or fn.__name__
        hints = get_type_hints(fn, include_extras=True)
        for parameter, annotation in hints.items():
            bounds = getattr(self, "numeric_bound_overrides", {}).get((tool_name, parameter), numeric_bounds(tool_name, parameter))
            if bounds:
                fn.__annotations__[parameter] = Annotated[annotation, Field(**bounds)]
            if tool_name == "batch_update_reminders" and parameter in {"reminders", "sections"}:
                fn.__annotations__[parameter] = Annotated[annotation, Field(max_length=500 if parameter == "reminders" else 100)]
        super().add_tool(fn, name=name, **kwargs)

    async def list_tools(self):
        return [described_tool(tool, private_backend=getattr(self, "private_backend", False)) for tool in await super().list_tools()]

    async def call_tool(self, name, arguments, context=None):
        with tool_trace(name if self._tool_manager.get_tool(name) else "unknown_tool"):
            return await self._call_described_tool(name, arguments, context)

    async def _call_described_tool(self, name, arguments, context=None):
        tool = self._tool_manager.get_tool(name)
        if tool is None:
            return error_result("unknown_tool", "unknown_tool", phase="input_validation", before_call=True)
        write = not (tool.annotations and tool.annotations.read_only_hint)
        if name == "batch_update_reminders" and isinstance(arguments, dict) and arguments.get("dry_run", True) is True:
            write = False
        properties = tool.parameters.get("properties", {})
        if not isinstance(arguments, dict) or set(arguments) - set(properties):
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True, write=write,
                                message="Unknown parameter or invalid argument object. Use the exact names in inputSchema; no remote request was made.")
        try:
            tool.fn_metadata.arg_model.model_validate(arguments, strict=True)
        except ValidationError as exc:
            fields = set()
            for issue in exc.errors(include_input=False, include_context=False, include_url=False):
                if issue["loc"] and issue["loc"][0] in properties:
                    fields.add(issue["loc"][0])
            details = [{"parameter": field, "expected": type_contract(properties[field]),
                        "description": parameter_description(name, field)} for field in sorted(fields)]
            explanation = " ".join(f"{item['parameter']}: {item['expected']}. {item['description']}" for item in details)
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True, write=write,
                                details={"invalid_parameters": details},
                                message="Invalid parameters; no remote request was made. " + explanation)
        if name == "get_drive_file" and arguments.get("format", "file") != "base64" and arguments.get("limit", 20000) > 100000:
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True, write=write,
                                message="Invalid parameters; no remote request was made. text/file limit must be 1..100000.")
        if name in {"get_email_attachment", "get_drive_file"} and arguments.get("format", "file") == "file" and arguments.get("offset", 0) != 0:
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True,
                                message="Invalid parameters; no remote request was made. format=file requires offset=0.")
        if name == "get_drive_file" and arguments.get("offset", 0) > 0 and not arguments.get("expected_version"):
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True,
                                message="Invalid parameters; no remote request was made. Subsequent chunks require expected_version.")
        if name in {"upload_drive_file", "replace_drive_file"} and sum(arguments.get(key) is not None for key in ("content_text", "content_base64", "source_resource_uri")) != 1:
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True, write=write,
                                message="Invalid parameters; no remote request was made. Supply exactly one of content_text, content_base64 or source_resource_uri.")
        if getattr(self, "private_backend", False) and arguments.get("source_resource_uri") is not None:
            return error_result(name, "invalid_argument", phase="input_validation", before_call=True, write=write,
                                message="Invalid parameters; no remote request was made. Snapshot URIs must be resolved by the common server before forwarding bytes to this private backend.")
        if name in {"delete_event", "delete_email", "delete_reminder", "replace_drive_file"} and arguments.get("confirm", False) is not True:
            return error_result(name, "confirmation_required", phase="input_validation", before_call=True, write=write)
        try:
            result = await super().call_tool(name, arguments, context)
        except ToolError as exc:
            failure = exc
            for _ in range(8):
                if isinstance(failure, ToolFailure):
                    return error_result(name, failure.code, details=failure.details, phase=failure.phase,
                                        message=failure.public_message, write=write)
                if failure.__cause__ is None:
                    break
                failure = failure.__cause__
            return error_result(name, "service_error", write=write)
        if result.is_error:
            payload = result.structured_content if isinstance(result.structured_content, dict) else {}
            native = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            return error_result(name, native.get("code") or payload.get("error_code") or "service_error",
                                result=result, phase=payload.get("phase") or payload.get("uncertain_step") or "service", write=write)
        try:
            VALIDATORS[name].validate_python(result.structured_content, strict=True)
        except ValidationError:
            return error_result(name, "backend_protocol_error", details=safe_evidence(name, result.structured_content),
                                phase="response_validation", write=write)
        return result
