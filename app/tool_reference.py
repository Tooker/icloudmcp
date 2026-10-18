"""Export the published tool descriptions without configuration or network access.

Run: uv run python -m app.tool_reference --output docs/mcp-tools.md
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.mcp_server import create_mcp_server


async def reference():
    tools = await create_mcp_server(None).list_tools()
    parts = [
        "# MCP tool reference\n\n"
        "Generated from the same tool schemas/descriptions published by `tools/list`. "
        "Regenerate with `uv run python -m app.tool_reference --output docs/mcp-tools.md`. "
        "No configuration, credentials or network access is required.\n\n"
        "Use exact JSON parameter names and enum values. Required fields must be supplied; "
        "optional fields use the stated default when omitted. `null` is accepted only where "
        "the type includes `null`; its meaning is described per field. Nested objects reject "
        "unknown fields. JSON types are strict: strings such as `\"true\"` or `\"50\"` "
        "are not booleans or integers. Actual account/folder/sender facts must come from tool results. "
        "Numeric bounds reflect the default configuration here; tools/list publishes active configured limits. "
        "Every tool publishes outputSchema, including the shared error contract documented in "
        "[MCP errors](mcp-errors.md).\n"
    ]
    for tool in tools:
        annotations = tool.annotations
        mode = "read-only" if annotations and annotations.read_only_hint else "write"
        if annotations and annotations.destructive_hint:
            mode += ", destructive"
        parts.append(f"## `{tool.name}`\n\n{tool.title or tool.name} ({mode}).\n\n{tool.description}\n")
        parts.append("<details>\n<summary>Response JSON Schema</summary>\n\n```json\n" +
                     json.dumps(tool.output_schema, ensure_ascii=False, indent=2) + "\n```\n\n</details>\n")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    options.output.write_text(asyncio.run(reference()), encoding="utf-8")


if __name__ == "__main__":
    main()
