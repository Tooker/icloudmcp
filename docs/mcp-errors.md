# MCP error contract

Every failed tool call returns `isError: true` and a typed `structuredContent.error`
object. Calendar, Mail, Contacts, Drive and Reminders use the same fields.
Protocol/HTTP authentication errors retain their transport-level semantics.

| Field | Meaning |
| --- | --- |
| `code` | Application-owned error code, enumerated in each tool's `outputSchema`. Never guessed from exception text. |
| `message` | Safe explanation. An upstream reason can remain unknown; no raw exception, credentials or rejected input values are echoed. |
| `service` | `calendar`, `mail`, `contacts`, `drive`, `reminders` or `unknown`. |
| `request_operation` | Tool originally called. |
| `operation` | Native failed sub-step when supplied, otherwise the tool called. |
| `request_id` | Diagnostic request ID. Existing native IDs remain preserved. |
| `phase` | Known validation/backend phase or write step; `service` when no finer phase is established. |
| `write_status` | Native affected-step status when supplied, otherwise the operation status. |
| `overall_write_status` | Overall request state: `not_sent`, `failed`, `succeeded`, `partial`, `unknown`, or `null` for reads. |
| `confirmed_steps` | Steps acknowledged by the service; this is not independent content readback. Native batch operation records remain the evidence for completed batch steps. |
| `uncertain_step` | Submitted step whose acknowledgement was not established, or `null` when no such step is recorded. An unknown overall state can exist without a precisely known step. |
| `retry_class` | `retryable_safe`, `retryable_after_read` or `not_retryable`. Existing native step-specific classification remains preserved. |
| `retryable` | Whether a manual retry can be considered with the stated prerequisites; never approval for an automatic retry. |
| `inspect_before_retry` | Inspect current state first, especially after partial or unknown changes. |
| `automatic_retry_allowed` | Always `false`. |
| `invalid_parameters` | Optional known parameter names and expected contracts. No submitted values or unknown parameter names. |

The normal error is added to valid native results rather than replacing them. Existing
root fields, native error fields, content blocks, `_meta`, created/reserved IDs,
completed batch operations and unknown backend extensions remain available.
`error.operation` and `error.write_status` can therefore refer to a failed batch
step while `request_operation` and `overall_write_status` refer to the whole batch.
A rejected/not-sent batch step does not erase earlier successful steps.
Malformed replies are handled separately: retain individually validated IDs,
write states and other declared fields, but do not echo invalid ID objects,
unknown malformed fields, validator inputs or arbitrary diagnostic text/content.
Unknown extensions and native content remain preserved for valid replies.

`unknown` and null fields never mean no change. `succeeded` can remain confirmed
even when local cache maintenance or readback fails. Native Drive root statuses
such as `not_started` or `uncertain` remain unchanged; the common overall state
normalizes these to `not_sent` or `unknown`.

## Mail example

Replacing a draft first appends the replacement and then marks the old draft
deleted. If APPEND is acknowledged with UID `77` and STORE rejects deletion,
the error retains `created=true`, `uid="77"`, `old_uid="42"`,
`confirmed_steps=["append_draft"]`, `old_draft_marked_deleted=false`,
`overall_write_status="partial"` and `inspect_before_retry=true`.
If STORE loses its acknowledgement, that flag becomes `null`, the overall state
becomes `unknown`, and `uncertain_step="mark_old_draft_deleted"` is preserved.
The caller must inspect both drafts rather than create another replacement.

COPY acknowledgements preserve the destination UID when a valid single-message
COPYUID mapping is supplied. Both mailbox caches are invalidated after any copy
attempt, including a later STORE failure. The server verifies source UID
existence before flag/move/delete; an accepted UID command alone would otherwise
not prove that a matching message existed.

UID EXPUNGE rejection retains confirmed deletion flags but reports no confirmed
expunge. Connection loss during expunge reports a null/unknown expunge outcome;
it never falls back to mailbox-wide EXPUNGE or automatically repeats the command.

## Validation and schemas

Inputs use strict JSON types: `"true"` is not `true`, and `"50"` is not `50`.
Unknown parameters, invalid enums, numeric bounds and required content-source
relationships are rejected before service access, with `phase=input_validation`
and `write_status=not_sent` for writes. Other domain constraints are validated
by the service before its mutations.

Every tool publishes a typed success/error union in `outputSchema`. Successful
native replies are validated without removing additional fields. A malformed
success reply becomes `backend_protocol_error` and retains its validated evidence;
it does not justify replaying a confirmed write. Tool names, existing successful
response shapes, private resource routes and native content are preserved.
