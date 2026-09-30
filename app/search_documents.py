from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterator

from app.imap import ICloudIMAPService
from app.mail_attachments import extract_attachment_text

PIPELINE_VERSION = "mail-pdf-v1"
MAX_SOURCE_CHARS = 100_000
MAX_CHUNKS = 64
MAX_ATTACHMENTS = 20


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def html_text(text: str) -> str:
    parser = _HTMLText()
    parser.feed(text)
    return "".join(parser.parts).strip()


def utf8_prefix(text: str, maximum: int) -> str:
    return text.encode("utf-8")[:maximum].decode("utf-8", errors="ignore")


def text_chunks(text: str, prefix: str) -> Iterator[tuple[str, str]]:
    """Use a conservative byte bound below the API's 8192-token input limit.

    A byte-level tokenizer cannot have more tokens than UTF-8 bytes. This
    also avoids downloading a tokenizer at runtime on the small mail server.
    Overlap preserves context across Unicode-safe chunk boundaries.
    """
    prefix = utf8_prefix(prefix, 1000) + "\n\n"
    budget = 6500 - len(prefix.encode("utf-8"))
    start = 0
    while start < len(text):
        piece = utf8_prefix(text[start:], budget)
        if not piece:
            return
        end = start + len(piece)
        yield prefix + piece, piece
        if end >= len(text):
            return
        start = end - min(150, len(piece) // 4)


@dataclass
class PreparedMail:
    chunks: list[dict[str, Any]]
    skipped_attachments: int = 0
    truncated_sources: int = 0
    skipped_messages: int = 0


def prepare_mail(document: dict[str, Any]) -> PreparedMail:
    if document["raw_message"] is None:
        return PreparedMail([], skipped_messages=1)
    message = ICloudIMAPService._parse_message(document["raw_message"])
    body = ICloudIMAPService._message_body(message, MAX_SOURCE_CHARS)
    summary = ICloudIMAPService._message_summary(
        message, uid=document["uid"], mailbox=document["mailbox"], flags=document["summary"].get("flags", []),
    )
    header = "\n".join(f"{field}: {summary.get(field) or ''}" for field in ("subject", "from", "to", "date"))
    result = PreparedMail([], truncated_sources=int(body["body_truncated"]))

    def add(text: str, source: str, attachment_id: str | None = None, filename: str | None = None) -> None:
        prefix = header + ("\nAttachment: " + filename if filename else "")
        for embedding_text, excerpt in text_chunks(text, prefix):
            if len(result.chunks) >= MAX_CHUNKS:
                result.truncated_sources += 1
                return
            result.chunks.append({
                "embedding_text": embedding_text, "text": excerpt,
                "source": source, "attachment_id": attachment_id, "filename": filename,
            })

    content = html_text(body["body"]) if body["body_format"] == "html" else body["body"]
    # Header-only messages are still discoverable by subject/sender.
    add(content.strip() or header, "body")
    attachment_id = 0
    for part in ICloudIMAPService._message_parts(message):
        if not ICloudIMAPService._is_attachment(part):
            continue
        attachment_id += 1
        if attachment_id > MAX_ATTACHMENTS or len(result.chunks) >= MAX_CHUNKS:
            result.skipped_attachments += 1
            continue
        extracted = extract_attachment_text(part, ICloudIMAPService._part_payload(part), 0, MAX_SOURCE_CHARS)
        if extracted["text_status"] != "ok":
            result.skipped_attachments += 1
            continue
        result.truncated_sources += int(extracted["has_more"])
        text = extracted["text"]
        if part.get_content_type() == "text/html":
            text = html_text(text)
        add(text.strip(), "attachment", str(attachment_id), part.get_filename())
    return result
