"""Tool-specific discovery steps and evidence supported by successful replies."""

from app.mcp_groups import service_for_tool


# Each entry is (workflow, result interpretation). Keep this exhaustive rather
# than substituting generic claims when a new tool has not been documented.
USAGE = {
    "list_calendars": (
        "Start here when the calendar is unknown; use returned IDs for event operations.",
        "An array of discovered calendar summaries with id and name. Missing configuration produces not_configured rather than an empty successful catalogue; backend errors do not establish that the account has no calendars.",
    ),
    "list_events": (
        "Discover calendars first when filtering by calendar. Bound the date window, then use returned calendar_id and uid for details; retain recurrence_id for occurrence deletion.",
        "An array of actual occurrences, including summary, bounds, all_day and recurrence identifiers. Results are limited by limit; an occurrence is not the series master. Do not infer complete absence beyond the queried window or result limit.",
    ),
    "get_event": (
        "Use calendar and uid from a listing to inspect the stored event before editing a series.",
        "An event summary with calendar identity, UID, description, location, bounds and recurrence metadata. This UID-based lookup does not select an individual expanded occurrence by occurrence_id.",
    ),
    "create_event": (
        "Select an existing calendar and obtain authorization for the intended event; validate date/timestamp mode and end after start.",
        "The created event summary and its UID/calendar identity. Use those identifiers for subsequent reads or updates; a successful creation is not permission to create another duplicate.",
    ),
    "update_event": (
        "Read the stored event first and provide at least one changed field. Changing bounds requires both start and end. This UID-based operation edits the stored event; it has no occurrence-only update selector.",
        "The saved event summary. Omitted/null fields preserve existing values; description/location may be cleared with empty strings. Do not claim that only one recurrence instance changed when editing a series.",
    ),
    "delete_event": (
        "Read the intended event/occurrence and obtain explicit deletion authorization. For one occurrence reuse its original recurrence_id, even if the occurrence moved; never replace a failed occurrence deletion with a series deletion.",
        "deleted=true, scope and calendar/UID identity, plus occurrence information for occurrence deletion. scope=series removes the entire series; scope=occurrence excludes only the original recurrence slot.",
    ),
    "mail_account_info": (
        "Start here before preparing mail writes to learn the configured account, endpoint and default From header; then discover actual folders with list_mailboxes.",
        "Configured host, port, account, default_mailbox, configured_drafts_mailbox and default_from_header, with explicit verification flags and can_send=false. This configuration-only result does not prove folder existence, upstream provider or send-as permissions.",
    ),
    "list_mailboxes": (
        "Discover exact folder names before selecting, moving or writing mail. For drafts prefer a native Drafts special-use flag, otherwise choose an explicitly verified existing folder.",
        "An array of name, delimiter and flags. Copy the complete name including prefixes. Folder names/flags describe mailbox organization; they do not identify the upstream provider or sender account.",
    ),
    "search_emails": (
        "Choose a mailbox from list_mailboxes and narrow filters. Pass a result's mailbox and UID to get_email; use current returned generation information where available.",
        "Newest-first header summaries with UID, mailbox, sender/recipients, subject, dates and read flags. These are not full message bodies. limit can truncate matches, so the array does not provide an exhaustive mailbox catalogue.",
    ),
    "get_email": (
        "Use mailbox-local UID from search_emails; preserve expected_uid_validity when using a generation-bound retrieval reference. Use returned attachment_id for attachment retrieval.",
        "Message headers, body text with truncation information and attachment metadata. BODY.PEEK preserves the read flag. A body signature is not a From display name; a truncated body is not the complete original message.",
    ),
    "get_email_attachment": (
        "Read get_email first to obtain the exact attachment_id. Use file for original bytes, text for extraction, or collect base64 chunks using next_offset and the same mailbox generation.",
        "file returns an embedded binary resource and a private resource link with metadata; text/base64 return bounded content and pagination information. Text extraction changes representation and may require OCR for scans; original file mode performs no conversion. A resource can expire or be evicted.",
    ),
    "create_draft": (
        "Inspect mail_account_info and list_mailboxes first, choose the exact draft folder, then supply complete recipients, subject, body and optional attachments. Set a display name through the From header only when that identity is intended.",
        "created=true, mailbox, uid (possibly null if APPENDUID is unavailable), attachment_count and submitted From fields, body_format and sent=false. Null UID does not mean creation failed: discover the stored draft through search_emails. From fields describe the submitted MIME header, not independently verified sender identity or permission to send.",
    ),
    "update_draft": (
        "Locate and read an existing non-deleted draft in the exact folder. Supply its complete replacement, including every desired recipient and attachment; omitted attachments are not retained.",
        "updated=true, old_uid, replacement uid (possibly null), mailbox, submitted From fields and old_draft_marked_deleted/old_draft_expunged. Replacement is non-atomic; failure can leave both drafts. sent=false confirms this service did not send the draft, not that another client never sent it.",
    ),
    "mark_email_read": (
        "Select the exact mailbox and message UID; specify read=true to mark read or false to mark unread.",
        "UID, mailbox and requested read state after the flag update succeeds. This updates Seen only; it does not move, delete or reply to the message.",
    ),
    "move_email": (
        "Discover both exact folder names and the source UID. Source and destination must differ. Obtain authorization before changing mailbox state.",
        "Source/destination names and source_marked_deleted/source_expunged plus moved. The implementation copies, marks the source deleted, then expunges that UID when safe. moved=false with source_marked_deleted=true can still mean the destination copy exists; do not claim nothing happened or blindly repeat. Discover the destination UID independently.",
    ),
    "delete_email": (
        "Read the exact message identity and obtain explicit confirm=true authorization. This is destructive mailbox mutation, not draft preparation.",
        "UID, mailbox, marked_deleted and expunged/deleted. If marked_deleted=true but expunged=false, the message is flagged for deletion but not confirmed permanently removed. The service never uses mailbox-wide expunge as a fallback.",
    ),
    "semantic_search_emails": (
        "Use for meaning-based discovery in the local mail/PDF index; check index progress. For current originals use the returned email/attachment retrieval arguments, including expected_uid_validity.",
        "matches with scores, excerpts, source/attachment references and index status. Excerpts are bounded derived text, scores are retrieval similarity, and no match does not prove absence from live IMAP or unindexed/scanned documents.",
    ),
    "email_search_index_status": (
        "Use before interpreting semantic search coverage or diagnosing indexing progress; this does not start an index job or fetch new mail.",
        "configured and safe local index/worker counts and state when enabled. configured=false means semantic search is disabled. Index progress does not prove complete coverage of the live mailbox.",
    ),
    "list_addressbooks": (
        "Discover address-book IDs and write permissions before selecting a Contacts collection. If multiple books are eligible, pass an explicit ID in subsequent calls.",
        "addressbooks containing account-scoped id, name and writable. Unknown permission is not confirmed write access; creation refreshes permissions.",
    ),
    "list_contacts": (
        "Select an address book, page with next_offset and retain returned contact IDs. Review coverage_complete and skipped_count before using the catalogue for duplicate or absence checks.",
        "contacts plus addressbook_id, pagination, catalogue_count and coverage information. Individual unparseable/missing entries can be skipped; a partial page/catalogue cannot establish that a contact does not exist.",
    ),
    "search_contacts": (
        "Select an address book and search names, organization, email or phone; collect matching pages and check coverage before creating a potential duplicate.",
        "Matching structured contacts, account-scoped IDs, pagination and coverage information. Matches are individual records, not merged identities or Reminders participants.",
    ),
    "get_contact": (
        "Use contact_id from Contacts list/search/create. For uncertain creation inspect this ID before considering any new write.",
        "A contact object with names, organization, labeled email/phone/address fields and supported metadata. A coverage_incomplete failure cannot establish absence. Photos, groups and arbitrary Apple extension fields are not included.",
    ),
    "create_contact": (
        "Check potential duplicates and select a writable address book. Submit one structured contact with a name or organization; creation neither edits nor merges existing records.",
        "write_status, generated contact_id/uid, addressbook_id and readback_confirmed, plus contact on successful readback. write_status=succeeded remains confirmed even if readback_confirmed=false. Preserve IDs and inspect after unknown state; never replay automatically.",
    ),
    "drive_status": (
        "Start here before Drive operations. Authentication and web-access approval, when required, are separate explicit administrative actions.",
        "configured, session_state, root_id and capabilities. ready means existing access was probed, not that every file or write is permitted. auth_required/access_required do not initiate login, approval or device notifications.",
    ),
    "list_drive_items": (
        "Use an issued folder ID or the root, collect pages with next_offset, and retain file/folder IDs and versions for later reads or replacement.",
        "items, folder_id, total, pagination and coverage_complete/skipped_count. Unsupported shared/app-library/package items can be skipped. Folder coverage is bounded and does not prove absence elsewhere in Drive.",
    ),
    "search_drive_files": (
        "Search filenames under the selected owned folder with explicit traversal budgets. For content/semantic search this tool is unsuitable; retrieve a matching original with get_drive_file.",
        "files, pagination and coverage_complete with traversal information. Depth/node limits and skipped items can make coverage incomplete; no match then does not prove the file is absent.",
    ),
    "get_drive_file": (
        "Use a regular file ID from list/search. Use file for complete original bytes. For paged extraction or base64 chunks retain the returned download version for subsequent reads; discard accumulated chunks on version_changed.",
        "File metadata, size, SHA-256 and version with native binary resource/link in file mode or bounded text/base64 content and pagination. The checksum describes original bytes, not extracted text. Private resource availability is limited by TTL, eviction and server restarts.",
    ),
    "create_drive_folder": (
        "Select an owned parent and a unique folder name; authorization must cover creation. The service refreshes permissions and complete name coverage before writing.",
        "The created folder information plus write state/confirmed IDs when provided. A failure after creation may retain folder_id and confirmed steps; preserve them and inspect the parent rather than creating another folder automatically.",
    ),
    "upload_drive_file": (
        "Choose a parent, a name not already present and exactly one content source. Existing names require explicit version-checked replace_drive_file instead. Upload stages bytes, verifies them, then conditionally renames to the requested name.",
        "item, bytes_uploaded, sha256, version and write journal. Preserve staging/created IDs, confirmed_steps and uncertain_step on failure. Upload failure can leave a staged file; do not retry or remove artifacts automatically.",
    ),
    "replace_drive_file": (
        "Read the intended file/version, obtain explicit confirmation and supply exactly one replacement content source. Replacement verifies staged bytes, moves the original to native Trash, then renames the staged file.",
        "The replacement item with a new file ID, bytes_uploaded, sha256, version and write journal. This is non-atomic; preserve original/replacement IDs, original_in_trash and confirmed/uncertain steps. original_in_trash=null means unknown, not false. Never retry or roll back automatically.",
    ),
    "list_reminder_lists": (
        "Discover exact list IDs before reading or writing reminders, sections or collaborators; a list title alone is not a stable identifier.",
        "lists containing id/name and optional structure_warnings. Warning-bearing list structure must be inspected before structural writes; successfully readable tasks do not prove valid section/order metadata.",
    ),
    "list_reminders": (
        "Select exact list/parent/section IDs and page with next_offset. Include completed tasks when preparing reorder/batch operations; use tree only as a display aid for the returned page.",
        "reminders, total, next_offset and optional tree/legend/structure_warnings. The flat records and parent_ref remain authoritative when a parent is outside the page. Priority, completion and manual order are independent.",
    ),
    "get_reminder": (
        "Use an exact reminder ID from list_reminders to inspect current notes, completion, structure and assignment before mutation.",
        "A reminder object with identity, title, completion/priority and available due/notes/list/parent/section/assignee metadata. Missing optional fields on an older backend are not proof those features never exist.",
    ),
    "create_reminder": (
        "Select a writable existing list and, if relevant, parent/section in that same list. For creation-key recovery preserve both the UUID and identical arguments; key support is checked before writes.",
        "id and status=created or already_created; newer backends may include write_status. already_created with a supported creation key recovers that existing creation and does not imply another task was inserted.",
    ),
    "update_reminder": (
        "Read the reminder and submit only supported changed nonempty fields. Use move_reminder for parent/section/order and assign_reminder for assignment; this tool does not change completion.",
        "id and status=updated, with optional write_status. Updating due/notes cannot clear them; priority=none clears priority. A successful field update is not evidence of a structure or assignee change.",
    ),
    "complete_reminder": (
        "Read the exact reminder identity and authorize marking it complete. The interface does not expose reopening a completed reminder.",
        "id and status=completed, with optional write_status. Already completed reminders remain completed; this does not delete the task or change its manual order.",
    ),
    "delete_reminder": (
        "Read the exact task and obtain explicit confirmation for permanent deletion before calling confirm=true.",
        "id and status=deleted, with optional write_status. Deletion is destructive; an error with unknown write_status requires inspection, not automatic repeat.",
    ),
    "sync_reminders": (
        "Request synchronization when a cache refresh is needed; choose incremental by default, full only for a complete refresh. This is separate from account login and access approval.",
        "Safe list/reminder counts and optional structure_warnings. Counts describe the synchronization result, not successful mutation of task contents; a full sync can take longer than the call deadline.",
    ),
    "list_reminder_participants": (
        "Use the exact reminder list ID before assigning a shared-list task. Select the returned accepted participant ID for this list, never a Contacts ID, email or inferred name match.",
        "list_id, shared and participants with id, role, permission and current-user information. Discovery is read-only and does not assign anyone or invite new participants.",
    ),
    "assign_reminder": (
        "Read the reminder and accepted participants for its own list; use participant_id to assign or clear=true to remove assignment, never both. Membership and write permissions are refreshed before writing.",
        "id and status=assigned, unassigned or unchanged, with optional write_status. unchanged means the requested assignment already matched; it does not indicate a new invitation or membership change.",
    ),
    "list_reminder_sections": (
        "Discover native section IDs for one list before moving tasks into sections or constructing a complete batch. Section headings are separate native records, not reminder titles.",
        "list_id, sections with id/title/order metadata and optional structure_warnings. Preserve the existing section order; warnings can prohibit structural writes even while ordinary tasks are readable.",
    ),
    "create_reminder_section": (
        "Select a writable list and supply the intended heading. Use the returned ID for moves or batches; this creates a native section, not a reminder.",
        "The new section id and status=created, with optional write_status. On an uncertain result inspect current sections before considering another creation.",
    ),
    "move_reminder": (
        "Read list/parent/section structure first. Move within the same list; use explicit clear flags for detaching and at most one sibling anchor. The subtree moves together and cycles are rejected.",
        "id and status=moved; order_verification=verified when the backend freshly confirms manual order. Absence of that optional field on older backends is not verified order. Preserve any uncertain write diagnostics and inspect before retrying.",
    ),
    "reorder_reminders": (
        "Read the entire target sibling group including completed tasks, then provide every sibling ID exactly once in desired order. This changes manual order, not priority/completion or section membership.",
        "id and status=reordered or unchanged, with optional order_verification. Only order_verification=verified confirms fresh order readback; an older response without it does not prove verification.",
    ),
    "batch_update_reminders": (
        "Read all pages with include_completed=true and existing native sections. Submit the complete target tree, preview with dry_run=true, review planned operations, then apply the authorized structure with dry_run=false.",
        "status=preview, applied or failed, atomic=false, operation counts, operations and path-to-ID mapping. On failure confirmed native results, created IDs and the failed/uncertain operation remain evidence of partial changes. A preview is not an applied change; never replay or roll back an uncertain batch automatically.",
    ),
}


FAILURES = {
    "calendar": "Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series.",
    "mail": "Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service.",
    "contacts": "Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation.",
    "drive": "Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically.",
    "reminders": "Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval.",
}


def usage_description(name):
    workflow, result = USAGE[name]
    failure = FAILURES[service_for_tool(name)]
    return (
        f"Workflow: {workflow}\n"
        f"Result interpretation: {result}\n"
        f"Failures and recovery: {failure} "
        "Treat MCP isError=true as an error even when confirmed partial write information is present. "
        "Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, "
        "confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. "
        "Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, "
        "while overall_write_status describes the complete call. Preserve original IDs and native content. "
        "Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. "
        "Report only facts supported by the returned fields; omitted or unknown values are not confirmation."
    )
