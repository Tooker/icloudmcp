# Changelog

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
