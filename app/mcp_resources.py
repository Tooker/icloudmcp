from __future__ import annotations

import base64
import json
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from mcp.server.mcpserver.server import ReadResourceContents
from mcp_types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ResourceLink,
    ResourceTemplate,
    TextContent,
)


@dataclass(frozen=True)
class _AttachmentSnapshot:
    data: bytes
    mime_type: str
    expires_at: float


class AttachmentMCPServer(MCPServer):
    """Native attachment results with bounded, private resource snapshots.

    Snapshots preserve exactly the file returned by the tool, even if a UID
    is later reused. Resource URIs contain only random IDs, never mail data.
    All snapshot access runs synchronously on the MCP event loop.
    """

    _RESOURCE_PREFIX = "icloud-mail://attachments/"
    _RESOURCE_TTL_SECONDS = 900
    _MAX_RESOURCES = 64
    _MAX_RESOURCE_BYTES = 25_000_000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._attachment_resources: OrderedDict[str, _AttachmentSnapshot] = OrderedDict()
        self._attachment_resource_bytes = 0

    def _drop_snapshot(self, uri: str) -> None:
        self._attachment_resource_bytes -= len(self._attachment_resources.pop(uri).data)

    def _prune_snapshots(self, now: float) -> None:
        for uri, snapshot in list(self._attachment_resources.items()):
            if snapshot.expires_at <= now:
                self._drop_snapshot(uri)

    def attachment_result(self, attachment: dict[str, Any]) -> CallToolResult:
        payload = attachment["content_bytes"]
        if not isinstance(payload, bytes) or len(payload) > self._MAX_RESOURCE_BYTES:
            raise ValueError("Attachment is too large for a native resource; use format=base64.")
        now = monotonic()
        self._prune_snapshots(now)
        while self._attachment_resources and (
            len(self._attachment_resources) >= self._MAX_RESOURCES
            or self._attachment_resource_bytes + len(payload) > self._MAX_RESOURCE_BYTES
        ):
            self._drop_snapshot(next(iter(self._attachment_resources)))
        uri = self._RESOURCE_PREFIX + str(uuid4())
        mime_type = attachment["content_type"]
        self._attachment_resources[uri] = _AttachmentSnapshot(
            payload, mime_type, now + self._RESOURCE_TTL_SECONDS,
        )
        self._attachment_resource_bytes += len(payload)
        metadata = {key: value for key, value in attachment.items() if key != "content_bytes"}
        metadata.update({
            "resource_uri": uri,
            "resource_expires_in_seconds": self._RESOURCE_TTL_SECONDS,
        })
        name = attachment["filename"] or f"attachment-{attachment['attachment_id']}"
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False)),
                ResourceLink(type="resource_link", uri=uri, name=name, mime_type=mime_type, size=len(payload)),
                EmbeddedResource(type="resource", resource=BlobResourceContents(
                    uri=uri, mime_type=mime_type, blob=base64.b64encode(payload).decode("ascii"),
                )),
            ],
            structured_content=metadata,
        )

    async def read_resource(self, uri, context=None):
        uri = str(uri)
        if not uri.startswith(self._RESOURCE_PREFIX):
            return await super().read_resource(uri, context)
        self._prune_snapshots(monotonic())
        snapshot = self._attachment_resources.get(uri)
        if snapshot is None:
            logger.info("mcp_resource_read kind=mail_attachment status=miss")
            raise ResourceNotFoundError(
                "Attachment resource is unknown or expired; call get_email_attachment again."
            )
        logger.info("mcp_resource_read kind=mail_attachment status=hit bytes={}", len(snapshot.data))
        return [ReadResourceContents(content=snapshot.data, mime_type=snapshot.mime_type)]

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        templates = await super().list_resource_templates()
        return [*templates, ResourceTemplate(
            name="mail_attachment",
            title="iCloud Mail attachment",
            uri_template=self._RESOURCE_PREFIX + "{resource_id}",
            description=(
                "Original attachment snapshots returned by get_email_attachment(format=file). "
                "Use the issued URI with resources/read. Available for up to 15 minutes, "
                "until capacity eviction or service restart; request the file again on expiry."
            ),
        )]
