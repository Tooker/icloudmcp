# Changelog

## Unreleased

- Merge declarative `batch_update_reminders` with typed recursive tasks and
  native sections, default preview, complete coverage validation and sequential
  application through one bounded Go MCP session.
- Preserve confirmed per-operation results and created IDs on partial failure,
  including the failed step's safe write and retry diagnostics.
- Support optional creation keys on new batch tasks; validate keys and backend
  capabilities before any writes. Never automatically replay a batch.
- Combine the local Go title/completion fixes, write confirmations and durable
  keyed creation with the native section/order implementation.

## 1.1.0 — 2026-10-01

- Native Reminders section discovery and creation through the Go backend and
  the common Python MCP endpoint.
- Tree views, section filters, inherited sections and native manual positions.
- Move existing reminders between sections or under parents, and reorder
  siblings while preserving their subtrees.
- Explain status, hierarchy, priority and ordering symbols in MCP instructions,
  tool descriptions, read results and the Go CLI's `list --legend`.
- Preserve existing CloudKit metadata and shared-owner zones; refresh write
  permissions and reject cycles, cross-list references and unsupported formats.
- Preserve safe structured write diagnostics and reject keyed creation before
  dispatch when the selected backend does not support it.
- Align application/MCP/package versions to 1.1.0 and add a local paired-source
  Docker build override with versioned image tags; pin the published Go release
  in the default deployment.
