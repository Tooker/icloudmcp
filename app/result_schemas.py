"""Typed public replies. Extra backend fields and native MCP content survive."""

from copy import deepcopy
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.drive_errors import MESSAGES as DRIVE_ERRORS
from app.mcp_errors import ErrorPayload, WriteStatus
from app.reminders_schemas import RESPONSES as REMINDERS_RESPONSES


class Reply(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, hide_input_in_errors=True)


class Calendar(Reply):
    id: str
    name: str


class CalendarsReply(Reply):
    result: list[Calendar]


class Event(Reply):
    uid: str
    calendar_id: str
    calendar_name: str
    summary: str | None
    start: str | None
    end: str | None
    all_day: bool
    description: str | None = None
    location: str | None = None
    status: str | None = None
    recurrence_rule: str | None = None
    is_recurring: bool
    series_uid: str | None = None
    recurrence_id: str | None = None
    occurrence_id: str | None = None


class EventsReply(Reply):
    result: list[Event]


class DeleteEventReply(Reply):
    deleted: Literal[True]
    scope: Literal["occurrence", "series"]
    uid: str
    calendar_id: str
    calendar_name: str
    series_uid: str | None = None
    recurrence_id: str | None = None
    occurrence_id: str | None = None
    occurrence_date: str | None = None
    affected_date: str | None = None
    already_deleted: bool | None = None


class Mailbox(Reply):
    name: str
    delimiter: str | None
    flags: list[str]


class MailboxesReply(Reply):
    result: list[Mailbox]


class MailHeader(Reply):
    uid: str
    mailbox: str
    subject: str | None
    from_header: str | None = Field(alias="from")
    to: str | None
    cc: str | None
    date: str | None
    message_id: str | None
    flags: list[str]
    read: bool
    uid_validity: str | None = None
    internal_date: str | None = None


class MailHeadersReply(Reply):
    result: list[MailHeader]


class Attachment(Reply):
    attachment_id: str
    filename: str | None
    content_type: str
    size: int = Field(ge=0)


class EmailReply(MailHeader):
    body: str
    body_truncated: bool
    body_format: Literal["plain", "html"] | None
    attachments: list[Attachment]


class FileContent(Reply):
    filename: str | None
    content_type: str
    size: int = Field(ge=0)
    format: Literal["file", "text", "base64"]
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None
    content_base64: str | None = None
    text: str | None = None
    text_status: Literal["ok", "no_text", "unsupported", "encrypted", "too_large", "error"] | None = None
    text_message: str | None = None
    returned_bytes: int | None = Field(default=None, ge=0)
    returned_chars: int | None = Field(default=None, ge=0)
    resource_uri: str | None = Field(default=None, description="Opaque private snapshot URI, absent from public routes and resources/list.")
    resource_expires_in_seconds: int | None = Field(default=None, ge=0, le=900)


class EmailAttachmentReply(FileContent):
    uid: str
    mailbox: str
    uid_validity: str
    attachment_id: str


class MailAccountReply(Reply):
    protocol: Literal["imap"]
    host: str
    port: int = Field(ge=1, le=65535)
    account: str
    default_mailbox: str
    configured_drafts_mailbox: str
    default_from_header: str
    mailbox_existence_verified: Literal[False]
    upstream_provider_verified: Literal[False]
    send_as_permissions_verified: Literal[False]
    can_send: Literal[False]


class MailJournal(Reply):
    operation: str
    phase: str
    write_status: WriteStatus
    confirmed_steps: list[str]
    uncertain_step: str | None


class DraftReply(MailJournal):
    created: bool
    mailbox: str
    uid: str | None
    subject: str
    attachment_count: int = Field(ge=0)
    from_header: str
    from_address: str
    from_name: str
    body_format: Literal["plain", "html"]
    sent: Literal[False]
    send_as_permissions_verified: Literal[False]


class UpdateDraftReply(DraftReply):
    updated: Literal[True]
    old_uid: str
    old_draft_marked_deleted: bool
    old_draft_expunged: bool


class ReadFlagReply(MailJournal):
    uid: str
    mailbox: str
    read: bool


class MoveMailReply(MailJournal):
    uid: str
    source_mailbox: str
    destination_mailbox: str
    destination_uid: str | None
    copied: bool
    moved: bool
    source_marked_deleted: bool
    source_expunged: bool


class DeleteMailReply(MailJournal):
    uid: str
    mailbox: str
    deleted: bool
    marked_deleted: bool
    expunged: bool


class AddressBook(Reply):
    id: str
    name: str
    writable: bool | None


class AddressBooksReply(Reply):
    addressbooks: list[AddressBook]


class Contact(Reply):
    id: str
    addressbook_id: str
    uid: str
    etag: str | None
    display_name: str
    given_name: str
    family_name: str
    additional_name: str
    name_prefix: str
    name_suffix: str
    organization: str
    birthday: str | None
    notes: str
    emails: list["ContactValueReply"]
    phones: list["ContactValueReply"]
    addresses: list["PostalAddressReply"]


class ContactValueReply(Reply):
    value: str
    label: str


class PostalAddressReply(Reply):
    label: str
    po_box: str
    extended: str
    street: str
    city: str
    region: str
    postal_code: str
    country: str


Contact.model_rebuild()


class ContactsReply(Reply):
    addressbook_id: str
    contacts: list[Contact]
    offset: int = Field(ge=0)
    next_offset: int | None
    has_more: bool
    coverage_complete: bool
    skipped_count: int = Field(ge=0)
    catalogue_count: int = Field(ge=0)


class ContactReply(Reply):
    contact: Contact


class CreateContactReply(Reply):
    write_status: Literal["succeeded"]
    contact_id: str
    uid: str
    addressbook_id: str
    readback_confirmed: bool
    readback_error: str | None = None
    etag: str | None = None
    contact: Contact | None = None


class DriveItem(Reply):
    id: str
    name: str
    type: Literal["file", "folder"]
    size: int | None = Field(default=None, ge=0)
    modified_at: str | None = None
    version: str | None = None


class DriveStatusReply(Reply):
    configured: bool
    session_state: Literal[tuple(sorted({"ready"} | set(DRIVE_ERRORS)))]
    root_id: str | None
    read_only: bool
    capabilities: list[Literal["list", "name_search", "download", "pdf_text", "create_folder", "upload", "replace"]]
    replacement_atomic: Literal[False] | None = None
    replacement_preserves_id: Literal[False] | None = None
    shared_items_supported: Literal[False] | None = None
    packages_supported: Literal[False] | None = None


class DrivePage(Reply):
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None
    coverage_complete: bool
    skipped_count: int = Field(ge=0)


class DriveItemsReply(DrivePage):
    folder_id: str
    items: list[DriveItem]
    total: int = Field(ge=0)


class DriveSearchReply(DrivePage):
    files: list[DriveItem]
    examined_nodes: int = Field(ge=0)


class DriveFileReply(FileContent):
    file_id: str
    version: str
    sha256: str


class DriveWriteReply(Reply):
    operation: str
    phase: str | None = None
    write_status: Literal["succeeded"]
    confirmed_steps: list[str]
    uncertain_step: None
    readback_verified: bool
    item: DriveItem
    folder_id: str | None = None
    file_id: str | None = None
    staged_file_id: str | None = None
    reserved_file_id: str | None = None
    original_file_id: str | None = None
    original_in_trash: bool | None = None
    atomic: Literal[False] | None = None
    preserves_file_id: Literal[False] | None = None
    bytes_uploaded: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    version: str | None = None


class IndexBatch(Reply):
    status: Literal["queued", "submitting", "uploaded", "validating", "in_progress", "finalizing", "completed", "failed", "expired", "cancelling", "cancelled"]
    inputs: int = Field(ge=0)
    id: str | None


class IndexStatusReply(Reply):
    configured: bool
    source: Literal["sqlite_cached_emails"]
    model: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    worker: Literal["idle", "indexing", "waiting_batch", "retrying", "stopped"] | None = None
    embedding_mode: Literal["batch", "standard"] | None = None
    last_error: str | None = None
    batch: IndexBatch | None = None
    cached_messages: int | None = Field(default=None, ge=0)
    indexed_messages: int | None = Field(default=None, ge=0)
    indexed_chunks: int | None = Field(default=None, ge=0)
    skipped_attachments: int | None = Field(default=None, ge=0)
    truncated_sources: int | None = Field(default=None, ge=0)
    skipped_messages: int | None = Field(default=None, ge=0)
    pending_messages: int | None = Field(default=None, ge=0)


class RetrievalArguments(Reply):
    mailbox: str
    uid: str
    expected_uid_validity: str
    attachment_id: str | None = None


class RetrievalReference(Reply):
    tool: Literal["get_email", "get_email_attachment"]
    arguments: RetrievalArguments


class SemanticMatch(Reply):
    uid: str
    mailbox: str
    uid_validity: str
    subject: str | None = None
    from_header: str | None = Field(default=None, alias="from")
    to: str | None = None
    cc: str | None = None
    date: str | None = None
    message_id: str | None = None
    flags: list[str] | None = None
    read: bool | None = None
    score: float
    source: Literal["body", "attachment"]
    attachment_id: str | None
    filename: str | None
    chunk: int | None
    excerpt: str
    email: RetrievalReference
    attachment: RetrievalReference | None


class SemanticSearchReply(Reply):
    matches: list[SemanticMatch]
    index: IndexStatusReply


RESPONSES = {
    "list_calendars": CalendarsReply, "list_events": EventsReply,
    "get_event": Event, "create_event": Event, "update_event": Event, "delete_event": DeleteEventReply,
    "list_mailboxes": MailboxesReply, "mail_account_info": MailAccountReply, "search_emails": MailHeadersReply,
    "get_email": EmailReply, "get_email_attachment": EmailAttachmentReply,
    "create_draft": DraftReply, "update_draft": UpdateDraftReply,
    "mark_email_read": ReadFlagReply, "move_email": MoveMailReply, "delete_email": DeleteMailReply,
    "semantic_search_emails": SemanticSearchReply, "email_search_index_status": IndexStatusReply,
    "list_addressbooks": AddressBooksReply, "list_contacts": ContactsReply, "search_contacts": ContactsReply,
    "get_contact": ContactReply, "create_contact": CreateContactReply,
    "drive_status": DriveStatusReply, "list_drive_items": DriveItemsReply, "search_drive_files": DriveSearchReply,
    "get_drive_file": DriveFileReply, "create_drive_folder": DriveWriteReply,
    "upload_drive_file": DriveWriteReply, "replace_drive_file": DriveWriteReply,
    **REMINDERS_RESPONSES,
}
VALIDATORS = {name: TypeAdapter(model) for name, model in RESPONSES.items()}
SCHEMAS = {name: {**TypeAdapter(model | ErrorPayload).json_schema(), "type": "object"}
           for name, model in RESPONSES.items()}


def safe_evidence(name, payload):
    """Keep individually validated fields from malformed replies, never raw data.

    Valid replies retain all fields/content. For malformed replies an unknown
    extension, invalid ID object or diagnostic text is not safe write evidence.
    """
    if not isinstance(payload, dict):
        return {}
    model = RESPONSES[name]
    models = get_args(model.model_fields["root"].annotation) if "root" in model.model_fields else (model,)
    fields = {field.alias or key: field for candidate in models for key, field in candidate.model_fields.items()}
    result = {}
    for key, value in payload.items():
        field = fields.get(key)
        if field is None:
            continue
        try:
            annotation = Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
            TypeAdapter(annotation).validate_python(value, strict=True)
        except (ValidationError, ValueError, TypeError):
            continue
        result[key] = deepcopy(value)
    return result
