from __future__ import annotations

import base64
import json
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

from loguru import logger
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

from app.mcp_groups import grouped_tools
from app.tool_contracts import DescribedMCPServer


@dataclass(frozen=True)
class _AttachmentSnapshot:
    data: bytes
    mime_type: str
    expires_at: float


class AttachmentMCPServer(DescribedMCPServer):
    """Native mail/Drive files sharing bounded, private resource snapshots.

    Snapshots preserve exactly the file returned by the tool, even if a UID
    is later reused. Resource URIs contain only random IDs, never mail data.
    All snapshot access runs synchronously on the MCP event loop.
    """

    _RESOURCE_PREFIX = "icloud-mail://attachments/"
    _DRIVE_RESOURCE_PREFIX = "icloud-drive://files/"
    _RESOURCE_TTL_SECONDS = 900
    _MAX_RESOURCES = 64
    _MAX_RESOURCE_BYTES = 30_000_000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._attachment_resources: OrderedDict[str, _AttachmentSnapshot] = OrderedDict()
        self._attachment_resource_bytes = 0

    def _drop_snapshot(self, uri: str) -> None:
        self._attachment_resource_bytes -= len(self._attachment_resources.pop(uri).data)

    async def list_tools(self):
        return grouped_tools(await super().list_tools())

    def file_snapshot_bytes(self, uri: str) -> bytes:
        """Resolve only already-issued private snapshots for Drive upload inputs."""
        self._prune_snapshots(monotonic())
        snapshot = self._attachment_resources.get(uri)
        if snapshot is None:
            raise ResourceNotFoundError("File snapshot is unknown or expired; retrieve the original file again.")
        return snapshot.data

    def _prune_snapshots(self, now: float) -> None:
        for uri, snapshot in list(self._attachment_resources.items()):
            if snapshot.expires_at <= now:
                self._drop_snapshot(uri)

    def attachment_result(self, attachment: dict[str, Any]) -> CallToolResult:
        return self._file_result(attachment, self._RESOURCE_PREFIX, f"attachment-{attachment['attachment_id']}")

    def drive_file_result(self, file: dict[str, Any]) -> CallToolResult:
        return self._file_result(file, self._DRIVE_RESOURCE_PREFIX, "Drive file")

    def _file_result(self, attachment: dict[str, Any], prefix: str, default_name: str) -> CallToolResult:
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
        uri = prefix + str(uuid4())
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
        name = attachment["filename"] or default_name
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
        if not uri.startswith((self._RESOURCE_PREFIX, self._DRIVE_RESOURCE_PREFIX)):
            return await super().read_resource(uri, context)
        kind = "drive_file" if uri.startswith(self._DRIVE_RESOURCE_PREFIX) else "mail_attachment"
        self._prune_snapshots(monotonic())
        snapshot = self._attachment_resources.get(uri)
        if snapshot is None:
            logger.info("mcp_resource_read kind={} status=miss", kind)
            raise ResourceNotFoundError(
                "Attachment resource is unknown or expired; call get_email_attachment again."
                if kind == "mail_attachment" else "Drive resource is unknown or expired; call get_drive_file again."
            )
        logger.info("mcp_resource_read kind={} status=hit bytes={}", kind, len(snapshot.data))
        return [ReadResourceContents(content=snapshot.data, mime_type=snapshot.mime_type)]

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        templates = await super().list_resource_templates()
        return [*templates, ResourceTemplate(
            name="mail_attachment",
            title="Mail attachment",
            uri_template=self._RESOURCE_PREFIX + "{resource_id}",
            description=(
                "Original attachment snapshots returned by get_email_attachment(format=file). "
                "Use the issued URI with resources/read. Available for up to 15 minutes, "
                "until capacity eviction or service restart; request the file again on expiry."
            ),
        ), ResourceTemplate(
            name="drive_file", title="iCloud Drive file",
            uri_template=self._DRIVE_RESOURCE_PREFIX + "{resource_id}",
            description="Original Drive file snapshots from get_drive_file(format=file). Use resources/read; expires after at most 15 minutes or capacity eviction/restart.",
        )]
