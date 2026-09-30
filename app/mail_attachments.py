from __future__ import annotations

import logging
from contextvars import ContextVar
from email.message import Message
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Iterator

from pypdf import PdfReader

from app.timing import timed_phase


_extracting_pdf: ContextVar[bool] = ContextVar("extracting_mail_pdf", default=False)


class _PrivatePDFLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Parser diagnostics can include document contents. Suppress those
        # only in the worker reading an attachment, including concurrent reads.
        return not _extracting_pdf.get()


for _name, _logger in list(logging.Logger.manager.loggerDict.items()):
    if (_name == "pypdf" or _name.startswith("pypdf.")) and isinstance(_logger, logging.Logger):
        _logger.addFilter(_PrivatePDFLogFilter())


class _TextUnavailable(Exception):
    def __init__(self, status: str, message: str) -> None:
        self.status = status
        self.message = message


_MAX_TEXT_ATTACHMENT_BYTES = 10_000_000
_MAX_PDF_PAGE_STREAM_BYTES = 5_000_000
_TEXT_SUFFIXES = {".txt", ".csv", ".tsv", ".md", ".json", ".xml", ".yaml", ".yml", ".log", ".ics", ".html", ".htm", ".svg"}


def _text_chunks(part: Message, payload: bytes) -> Iterator[str]:
    content_type = part.get_content_type()
    suffix = PurePosixPath(part.get_filename() or "").suffix.casefold()
    if len(payload) > _MAX_TEXT_ATTACHMENT_BYTES:
        raise _TextUnavailable("too_large", "Attachment is too large for text extraction; use format=base64.")
    if content_type == "application/pdf" or suffix == ".pdf":
        reader = PdfReader(BytesIO(payload))
        if reader.is_encrypted and not reader.decrypt(""):
            raise _TextUnavailable("encrypted", "PDF requires a password; use format=base64 for the original file.")
        for index, page in enumerate(reader.pages):
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > _MAX_PDF_PAGE_STREAM_BYTES:
                raise _TextUnavailable("too_large", "PDF page is too large for text extraction; use format=base64.")
            if index:
                yield "\n\n"
            yield page.extract_text() or ""
    elif (
        content_type.startswith("text/")
        or content_type in {"application/json", "application/xml", "application/yaml"}
        or content_type.endswith(("+json", "+xml"))
        or suffix in _TEXT_SUFFIXES
    ):
        charset = part.get_content_charset()
        if charset is None:
            charset = "utf-16" if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            yield payload.decode(charset, errors="replace")
        except LookupError:
            yield payload.decode("utf-8", errors="replace")
    else:
        raise _TextUnavailable("unsupported", "Text extraction is supported for PDF and text files; use format=base64 for this file.")


@timed_phase("attachment_text_extract")
def extract_attachment_text(part: Message, payload: bytes, offset: int, limit: int) -> dict[str, Any]:
    """Extract a bounded text window, reading PDF pages only as far as needed."""

    token = _extracting_pdf.set(True)
    try:
        pieces: list[str] = []
        position = 0
        has_text = False
        end = offset + limit + 1
        for chunk in _text_chunks(part, payload):
            has_text = has_text or bool(chunk.strip())
            start_in_chunk = max(0, offset - position)
            end_in_chunk = max(0, end - position)
            pieces.append(chunk[start_in_chunk:end_in_chunk])
            position += len(chunk)
            if position >= end:
                break
        text = "".join(pieces)
        has_more = len(text) > limit
        return {
            "text": text[:limit],
            "text_status": "ok" if has_text else "no_text",
            "text_message": None if has_text else "No embedded text found. Scanned PDFs need OCR; use format=base64 for the original file.",
            "returned_chars": min(len(text), limit),
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        }
    except _TextUnavailable as exc:
        status, message = exc.status, exc.message
    except Exception:
        # Neither parser diagnostics nor exception chains may expose email
        # contents. Original bytes remain available even for malformed PDFs.
        status, message = "error", "Attachment text could not be extracted; use format=base64 for the original file."
    finally:
        _extracting_pdf.reset(token)
    return {
        "text": None,
        "text_status": status,
        "text_message": message,
        "returned_chars": 0,
        "has_more": False,
        "next_offset": None,
    }
