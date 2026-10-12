import json

from mcp_types import CallToolResult, TextContent

MESSAGES = {
    "not_configured": "Enable the private Drive backend using DRIVE_MCP_URL and DRIVE_MCP_TOKEN.",
    "auth_required": "Export a Drive session with the administrative Go drive-export command; renew the saved Go login only if expired.",
    "access_required": "Drive web access needs administrative approval on a trusted device. MCP never requests approval.",
    "invalid_argument": "Use an issued Drive ID and bounded pagination; further chunks require the first download's version.",
    "not_found": "The Drive item is unavailable to this session.",
    "lookup_incomplete": "The file could not be resolved within bounded folder coverage; list its current folder and use the newly issued ID.",
    "unsupported_item": "Shared items, app libraries and document packages are not supported by this initial Drive reader.",
    "version_changed": "The file version changed. Discard earlier chunks and start a fresh download.",
    "too_large": "Drive exceeded the configured file, folder or response size limit.",
    "unsafe_target": "Drive returned a URL outside verified Apple HTTPS services.",
    "protocol_error": "Drive returned an invalid or unsupported response.",
    "backend_unavailable": "The private Drive backend could not complete this request.",
    "backend_auth_failed": "The private Drive backend rejected its bearer token.",
    "timeout": "The total Drive operation deadline expired.",
    "conflict": "The destination name exists or the expected file version no longer matches. Refresh the folder before another action.",
    "read_only": "The selected Drive item does not allow this write.",
    "confirmation_required": "Replacing a file requires explicit confirm=true and its expected_version.",
    "snapshot_expired": "The source file snapshot is unknown or expired. Retrieve the original file again.",
    "write_failed": "Apple rejected the Drive write. Inspect the preserved write state before another action.",
    "write_uncertain": "The Drive write outcome could not be confirmed. Do not repeat automatically; inspect the returned IDs and current folder.",
}


class DriveError(Exception):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code if code in MESSAGES else "backend_unavailable"
        self.details = details or {}
        super().__init__(MESSAGES[self.code])

    def as_result(self):
        payload = {**self.details, "error": {"code": self.code, "message": str(self)}}
        return CallToolResult(isError=True, structuredContent=payload,
                              content=[TextContent(type="text", text=json.dumps(payload))])
