"""Typed contacts tools and content-free MCP diagnostics."""

from time import perf_counter
from typing import Any
import json

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from app.contacts import ContactsError, ICloudContactsService
from app.contacts_schemas import ContactInput
from app.timing import call_id, tool_trace


def register_contacts_tools(server: MCPServer, service: ICloudContactsService | None) -> None:
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    async def call(name: str, **arguments: Any) -> dict[str, Any] | CallToolResult:
        with tool_trace(name):
            started = perf_counter()
            outcome = "cancelled"
            count = None
            status = None
            logger.info("mcp_tool_start tool={} call_id={}", name, call_id())
            try:
                if service is None:
                    raise ContactsError("not_configured", **({"write_status": "not_sent"} if name == "create_contact" else {}))
                result = await getattr(service, name)(**arguments)
                status = result.get("write_status")
                outcome = "ok"
                count = len(result["contacts"]) if "contacts" in result else len(result["addressbooks"]) if "addressbooks" in result else 1
                return result
            except ContactsError as error:
                outcome = error.code
                status = error.details.get("write_status")
                payload = error.payload()
                return CallToolResult(
                    isError=True, structuredContent=payload,
                    content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
                )
            except Exception:
                # Service handles transport errors and preserves write state.
                # Never log an exception, which may contain URLs or card text.
                outcome = "backend_unavailable"
                status = "unknown" if name == "create_contact" else None
                payload = ContactsError(outcome, **({"write_status": status} if status else {})).payload()
                return CallToolResult(isError=True, structuredContent=payload,
                                      content=[TextContent(type="text", text=json.dumps(payload))])
            finally:
                logger.info(
                    "mcp_tool_complete tool={} call_id={} outcome={} duration_ms={:.1f} result_count={} write_status={}",
                    name, call_id(), outcome, (perf_counter() - started) * 1000, count, status,
                )

    @server.tool(annotations=read, description=(
        "List iCloud CardDAV address books with exact IDs and current creation permissions. "
        "writable=null means the server did not report privileges. IDs are scoped to this account."
    ))
    async def list_addressbooks() -> dict[str, Any]:
        return await call("list_addressbooks")

    @server.tool(annotations=read, description=(
        "List a bounded page of contacts from one exact addressbook_id. Omit the ID only when there is "
        "one address book or a configured default. limit is 1..500; offset indexes the resource catalogue. "
        "Check coverage_complete and skipped_count; an incomplete result cannot establish absence. "
        "No contact photos, groups or arbitrary Apple extension fields are returned."
    ))
    async def list_contacts(addressbook_id: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await call("list_contacts", addressbook_id=addressbook_id, limit=limit, offset=offset)

    @server.tool(annotations=read, description=(
        "Search one address book by case-insensitive substring of names, organization, email or phone. "
        "Numeric phone searches ignore formatting. Scans a bounded catalogue; results are separate contacts, "
        "never merged. limit is 1..500; offset indexes matching contacts. Check coverage_complete before "
        "concluding that a person or possible duplicate does not exist."
    ))
    async def search_contacts(query: str, addressbook_id: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await call("search_contacts", query=query, addressbook_id=addressbook_id, limit=limit, offset=offset)

    @server.tool(annotations=read, description=(
        "Read a contact by an exact contact_id from list/search/create, including labelled emails, phones, "
        "postal addresses, structured name, organization, birthday, notes, UID and ETag. Use this to reconcile "
        "an uncertain creation. IDs remain valid across service restarts for the same account and resource."
    ))
    async def get_contact(contact_id: str) -> dict[str, Any]:
        return await call("get_contact", contact_id=contact_id)

    @server.tool(annotations=write, description=(
        "Create one iCloud contact from structured contact fields in an exact addressbook_id, after user approval. "
        "A name or organization is required. Emails, phones and addresses accept labels; birthday is YYYY-MM-DD. "
        "Creates a fresh UID using If-None-Match:* and never overwrites or merges. No automatic retries. "
        "write_status=succeeded confirms creation even when readback_confirmed=false. On unknown or succeeded "
        "errors preserve contact_id and UID and use get_contact to inspect the result before any further creation. "
        "Never turn a Contacts ID into a Reminders participant ID."
    ))
    async def create_contact(contact: ContactInput, addressbook_id: str | None = None) -> dict[str, Any]:
        return await call("create_contact", contact=contact, addressbook_id=addressbook_id)
