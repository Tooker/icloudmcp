# Changelog

## 1.4.0 — 2026-10-18

- Add Contacts discovery, search, reads and creation through CardDAV, with
  bounded catalogues and preserved confirmed or uncertain write state.
- Add optional private iCloud Drive access for browsing, search, downloads,
  folder creation, uploads and version-checked, non-atomic file replacement.
  Reuse the Go administrative session export for authentication and ADP access.
- Group tools by service while preserving tool names, schemas and metadata.
- Publish strict parameter contracts, typed response schemas, workflow guidance
  and a generated reference for all 45 MCP tools.
- Standardize safe tool errors while preserving valid native fields, known IDs,
  confirmed writes and uncertain steps without automatic retries.
- Journal IMAP mutation steps, verify source UIDs and invalidate affected caches
  after successful, failed or uncertain writes. Add configuration-only
  `mail_account_info` and clarify draft folder and submitted From-header behavior.

## 1.3.0 — 2026-10-01

- Merge declarative `batch_update_reminders` with typed recursive tasks and
  native sections, default preview, complete coverage validation and sequential
  application through one bounded Go MCP session.
- Preserve confirmed per-operation results and created IDs on partial failure,
  including the failed step's safe write and retry diagnostics.
- Support optional creation keys on new batch tasks; validate keys and backend
  capabilities before any writes. Never automatically replay a batch.
- Combine the local Go title/completion fixes, write confirmations and durable
  keyed creation with the native section/order implementation.
- Return complete iCloud Mail attachments up to 30 MB as native MCP resources,
  with matching bounded resource snapshots.

## 1.1.0 — 2026-10-01

- Native Reminders section discovery and creation through the Go backend and
  the common Python MCP endpoint.
- Tree views, section filters, inherited sections and native manual positions.
- Move existing reminders between sections or under parents, and reorder
  siblings while preserving their subtrees.
- Add declarative batch planning with a default read-only preview and bounded,
  sequential application preserving progress and created IDs on failure.
- Explain status, hierarchy, priority and ordering symbols in MCP instructions,
  tool descriptions, read results and the Go CLI's `list --legend`.
- Preserve existing CloudKit metadata and shared-owner zones; refresh write
  permissions and reject cycles, cross-list references and unsupported formats.
- Preserve safe structured write diagnostics and reject keyed creation before
  dispatch when the selected backend does not support it.
- Align application/MCP/package versions to 1.1.0 and add a local paired-source
  Docker build override with versioned image tags; pin the published Go release
  in the default deployment.
