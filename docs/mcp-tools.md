# MCP tool reference

Generated from the same tool schemas/descriptions published by `tools/list`. Regenerate with `uv run python -m app.tool_reference --output docs/mcp-tools.md`. No configuration, credentials or network access is required.

Use exact JSON parameter names and enum values. Required fields must be supplied; optional fields use the stated default when omitted. `null` is accepted only where the type includes `null`; its meaning is described per field. Nested objects reject unknown fields. JSON types are strict: strings such as `"true"` or `"50"` are not booleans or integers. Actual account/folder/sender facts must come from tool results. Numeric bounds reflect the default configuration here; tools/list publishes active configured limits. Every tool publishes outputSchema, including the shared error contract documented in [MCP errors](mcp-errors.md).

## `create_event`

Calendar · Create an iCloud calendar event (write).

Create a VEVENT in iCloud. This changes external state. For timed events use ISO 8601 timestamps; for all-day events set all_day=true and use YYYY-MM-DD. If calendar is omitted, the configured default is used or the account must have exactly one calendar.

Workflow: Select an existing calendar and obtain authorization for the intended event; validate date/timestamp mode and end after start.
Result interpretation: The created event summary and its UID/calendar identity. Use those identifiers for subsequent reads or updates; a successful creation is not permission to create another duplicate.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- title: string; required. Title text; nonblank when creating. On updates null/omission preserves the existing title.
- start: string; required. ISO 8601 timestamp for timed events, YYYY-MM-DD for all-day events. Null on list_events defaults to local midnight 30 days ago. On update supply start and end together or omit both to preserve bounds.
- end: string; required. ISO 8601 timestamp or all-day exclusive YYYY-MM-DD end, after start. Null on list_events defaults to local midnight 365 days ahead. On update supply start and end together or omit both to preserve bounds.
- calendar: string | null; default=null; optional. Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.
- description: string | null; default=null; optional. Event description; null on update preserves it, empty string clears it.
- location: string | null; default=null; optional. Event location; null on update preserves it, empty string clears it.
- all_day: boolean; default=false; optional. True for date-only events; false for timed events. Null on update preserves the existing mode.
- timezone_name: string | null; default=null; optional. IANA timezone, e.g. Europe/Berlin, for naive timed timestamps or all-day/timed conversion. Null uses configured timezone. On update supply it with start/end or an all_day mode change; it does not independently change the timezone.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "Event": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "calendar_id": {
          "title": "Calendar Id",
          "type": "string"
        },
        "calendar_name": {
          "title": "Calendar Name",
          "type": "string"
        },
        "summary": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Summary"
        },
        "start": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "End"
        },
        "all_day": {
          "title": "All Day",
          "type": "boolean"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "location": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Location"
        },
        "status": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Status"
        },
        "recurrence_rule": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Rule"
        },
        "is_recurring": {
          "title": "Is Recurring",
          "type": "boolean"
        },
        "series_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Series Uid"
        },
        "recurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Id"
        },
        "occurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Id"
        }
      },
      "required": [
        "uid",
        "calendar_id",
        "calendar_name",
        "summary",
        "start",
        "end",
        "all_day",
        "is_recurring"
      ],
      "title": "Event",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/Event"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `delete_event`

Calendar · Delete an iCloud calendar event (write, destructive).

Permanently delete one occurrence or an entire event/series from iCloud. scope is required: occurrence requires the exact recurrence_id from list_events; series deletes the entire event/series and must omit recurrence_id. A UID alone identifies the series. Never use scope=series for requests to delete only one day. This is destructive and requires confirm=true in addition to the client's approval flow.

Workflow: Read the intended event/occurrence and obtain explicit deletion authorization. For one occurrence reuse its original recurrence_id, even if the occurrence moved; never replace a failed occurrence deletion with a series deletion.
Result interpretation: deleted=true, scope and calendar/UID identity, plus occurrence information for occurrence deletion. scope=series removes the entire series; scope=occurrence excludes only the original recurrence slot.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- calendar: string; required. Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- confirm: boolean; required. Explicit true authorizes this destructive operation; false does not perform it.
- scope: string; enum=["occurrence", "series"]; required. occurrence deletes only the original recurrence slot; series deletes the complete event series. No implicit default.
- recurrence_id: string | null; default=null; optional. Exact original recurrence_id returned by list_events, preserving date/timestamp type and timezone. Required for scope=occurrence; omit for scope=series.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DeleteEventReply": {
      "additionalProperties": true,
      "properties": {
        "deleted": {
          "const": true,
          "title": "Deleted",
          "type": "boolean"
        },
        "scope": {
          "enum": [
            "occurrence",
            "series"
          ],
          "title": "Scope",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "calendar_id": {
          "title": "Calendar Id",
          "type": "string"
        },
        "calendar_name": {
          "title": "Calendar Name",
          "type": "string"
        },
        "series_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Series Uid"
        },
        "recurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Id"
        },
        "occurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Id"
        },
        "occurrence_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Date"
        },
        "affected_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Affected Date"
        },
        "already_deleted": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Already Deleted"
        }
      },
      "required": [
        "deleted",
        "scope",
        "uid",
        "calendar_id",
        "calendar_name"
      ],
      "title": "DeleteEventReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DeleteEventReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_event`

Calendar · Get an iCloud calendar event (read-only).

Fetch one event by its UID from the selected iCloud calendar.

Workflow: Use calendar and uid from a listing to inspect the stored event before editing a series.
Result interpretation: An event summary with calendar identity, UID, description, location, bounds and recurrence metadata. This UID-based lookup does not select an individual expanded occurrence by occurrence_id.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- calendar: string; required. Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "Event": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "calendar_id": {
          "title": "Calendar Id",
          "type": "string"
        },
        "calendar_name": {
          "title": "Calendar Name",
          "type": "string"
        },
        "summary": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Summary"
        },
        "start": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "End"
        },
        "all_day": {
          "title": "All Day",
          "type": "boolean"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "location": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Location"
        },
        "status": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Status"
        },
        "recurrence_rule": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Rule"
        },
        "is_recurring": {
          "title": "Is Recurring",
          "type": "boolean"
        },
        "series_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Series Uid"
        },
        "recurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Id"
        },
        "occurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Id"
        }
      },
      "required": [
        "uid",
        "calendar_id",
        "calendar_name",
        "summary",
        "start",
        "end",
        "all_day",
        "is_recurring"
      ],
      "title": "Event",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/Event"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_calendars`

Calendar · List iCloud calendars (read-only).

List the iCloud calendars available to the configured Apple Account.

Workflow: Start here when the calendar is unknown; use returned IDs for event operations.
Result interpretation: An array of discovered calendar summaries with id and name. Missing configuration produces not_configured rather than an empty successful catalogue; backend errors do not establish that the account has no calendars.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Calendar": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        }
      },
      "required": [
        "id",
        "name"
      ],
      "title": "Calendar",
      "type": "object"
    },
    "CalendarsReply": {
      "additionalProperties": true,
      "properties": {
        "result": {
          "items": {
            "$ref": "#/$defs/Calendar"
          },
          "title": "Result",
          "type": "array"
        }
      },
      "required": [
        "result"
      ],
      "title": "CalendarsReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/CalendarsReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_events`

Calendar · List iCloud calendar events (read-only).

List events in one calendar or across all calendars. By default, return events from 30 days in the past through 365 days in the future. Use ISO 8601 start/end filters for a narrower range (end exclusive) and query for summary, description, or location text. Recurring events are expanded with their actual occurrence start/end, series_uid, occurrence_id and recurrence_id. Use that recurrence_id unchanged to delete one occurrence; it identifies the original slot even when an occurrence has moved.

Workflow: Discover calendars first when filtering by calendar. Bound the date window, then use returned calendar_id and uid for details; retain recurrence_id for occurrence deletion.
Result interpretation: An array of actual occurrences, including summary, bounds, all_day and recurrence identifiers. Results are limited by limit; an occurrence is not the series master. Do not infer complete absence beyond the queried window or result limit.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- calendar: string | null; default=null; optional. Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.
- start: string | null; default=null; optional. ISO 8601 timestamp for timed events, YYYY-MM-DD for all-day events. Null on list_events defaults to local midnight 30 days ago. On update supply start and end together or omit both to preserve bounds.
- end: string | null; default=null; optional. ISO 8601 timestamp or all-day exclusive YYYY-MM-DD end, after start. Null on list_events defaults to local midnight 365 days ahead. On update supply start and end together or omit both to preserve bounds.
- query: string | null; default=null; optional. Search text; null on optional filters means no text filter.
- limit: integer; default=50; minimum=1; maximum=200; optional. Maximum results for this page, 1..200.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "Event": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "calendar_id": {
          "title": "Calendar Id",
          "type": "string"
        },
        "calendar_name": {
          "title": "Calendar Name",
          "type": "string"
        },
        "summary": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Summary"
        },
        "start": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "End"
        },
        "all_day": {
          "title": "All Day",
          "type": "boolean"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "location": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Location"
        },
        "status": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Status"
        },
        "recurrence_rule": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Rule"
        },
        "is_recurring": {
          "title": "Is Recurring",
          "type": "boolean"
        },
        "series_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Series Uid"
        },
        "recurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Id"
        },
        "occurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Id"
        }
      },
      "required": [
        "uid",
        "calendar_id",
        "calendar_name",
        "summary",
        "start",
        "end",
        "all_day",
        "is_recurring"
      ],
      "title": "Event",
      "type": "object"
    },
    "EventsReply": {
      "additionalProperties": true,
      "properties": {
        "result": {
          "items": {
            "$ref": "#/$defs/Event"
          },
          "title": "Result",
          "type": "array"
        }
      },
      "required": [
        "result"
      ],
      "title": "EventsReply",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/EventsReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `update_event`

Calendar · Update an iCloud calendar event (write).

Update only the supplied fields of an existing event. This changes external state. Pass description or location as an empty string to clear it; start and end must be supplied together.

Workflow: Read the stored event first and provide at least one changed field. Changing bounds requires both start and end. This UID-based operation edits the stored event; it has no occurrence-only update selector.
Result interpretation: The saved event summary. Omitted/null fields preserve existing values; description/location may be cleared with empty strings. Do not claim that only one recurrence instance changed when editing a series.
Failures and recovery: Missing configuration, authentication, unavailable calendars/events and invalid date combinations can fail the call. Never invent an upstream cause. Inspect current state after a failed write before repeating it; recurrence deletion must never fall back to deleting the series. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- calendar: string; required. Exact calendar ID or name returned by list_calendars. On list_events null/omission searches all available calendars, even when a default is configured for writes.
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- title: string | null; default=null; optional. Title text; nonblank when creating. On updates null/omission preserves the existing title.
- start: string | null; default=null; optional. ISO 8601 timestamp for timed events, YYYY-MM-DD for all-day events. Null on list_events defaults to local midnight 30 days ago. On update supply start and end together or omit both to preserve bounds.
- end: string | null; default=null; optional. ISO 8601 timestamp or all-day exclusive YYYY-MM-DD end, after start. Null on list_events defaults to local midnight 365 days ahead. On update supply start and end together or omit both to preserve bounds.
- description: string | null; default=null; optional. Event description; null on update preserves it, empty string clears it.
- location: string | null; default=null; optional. Event location; null on update preserves it, empty string clears it.
- all_day: boolean | null; default=null; optional. True for date-only events; false for timed events. Null on update preserves the existing mode.
- timezone_name: string | null; default=null; optional. IANA timezone, e.g. Europe/Berlin, for naive timed timestamps or all-day/timed conversion. Null uses configured timezone. On update supply it with start/end or an all_day mode change; it does not independently change the timezone.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "Event": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "calendar_id": {
          "title": "Calendar Id",
          "type": "string"
        },
        "calendar_name": {
          "title": "Calendar Name",
          "type": "string"
        },
        "summary": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Summary"
        },
        "start": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "End"
        },
        "all_day": {
          "title": "All Day",
          "type": "boolean"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "location": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Location"
        },
        "status": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Status"
        },
        "recurrence_rule": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Rule"
        },
        "is_recurring": {
          "title": "Is Recurring",
          "type": "boolean"
        },
        "series_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Series Uid"
        },
        "recurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Recurrence Id"
        },
        "occurrence_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Occurrence Id"
        }
      },
      "required": [
        "uid",
        "calendar_id",
        "calendar_name",
        "summary",
        "start",
        "end",
        "all_day",
        "is_recurring"
      ],
      "title": "Event",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/Event"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `create_draft`

Mail · Create a draft in the connected mail account (write).

Create a draft in the connected IMAP account. First inspect mail_account_info and list_mailboxes, then pass the exact existing draft mailbox name, preferably marked with the native Drafts special-use flag. body_format is exactly plain or html (not text). Optional attachments are structured base64 objects. The returned from_header/from_address/from_name describe the MIME header actually submitted; body signatures do not set sender identity, and send-as authorization is not verified. Never claim a provider based on folder names. Nothing is sent. A failure after submission can leave a draft behind: inspect the mailbox before any retry.

Workflow: Inspect mail_account_info and list_mailboxes first, choose the exact draft folder, then supply complete recipients, subject, body and optional attachments. Set a display name through the From header only when that identity is intended.
Result interpretation: created=true, mailbox, uid (possibly null if APPENDUID is unavailable), attachment_count and submitted From fields, body_format and sent=false. Null UID does not mean creation failed: discover the stored draft through search_emails. From fields describe the submitted MIME header, not independently verified sender identity or permission to send.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- to: array<string>; required. Array of recipient strings (address or RFC mailbox such as Name <person@example.com>), not a comma-separated string. May be empty if cc/bcc supplies a recipient; at least one recipient overall. No CR/LF.
- subject: string; required. Complete nonblank subject, without CR/LF. Required even when updating; drafts are replaced, not partially patched.
- body: string; required. Complete draft body string. Use body_format to declare plain text or HTML. Signature text does not set the From header. Entire MIME message including encoded attachments is limited to 25000000 bytes.
- cc: array<string> | null; default=null; optional. Optional array of visible copy recipients; null/omission means none. No CR/LF.
- bcc: array<string> | null; default=null; optional. Optional array of blind copy recipients; null/omission means none. No CR/LF.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- body_format: string; enum=["plain", "html"]; default="plain"; optional. Exactly plain (plain text) or html (HTML); text is invalid. Defaults to plain. Parameter name is body_format, not format.
- attachments: array<DraftAttachment> | null; default=null; optional. Optional array of attachment objects; null/omission means no attachments. Each object requires filename and content_base64, with optional MIME content_type. Maximum 10000000 decoded bytes per attachment and 25000000 bytes for the entire serialized message. No local paths or external URLs.
- from_address: string | null; default=null; optional. Complete MIME From header, e.g. Name <person@example.com>, or a bare email address. Null defaults to the configured IMAP username. This does not verify send-as permissions. The body/signature does not set the sender name; inspect returned from_header/from_address/from_name.
Nested object DraftAttachment:
- filename: string; minLength=1; required. Filename, one nonblank path component without slash, backslash or control characters.
- content_base64: string; minLength=1; required. Strict base64 of original attachment bytes; maximum 10000000 decoded bytes. No paths or URLs.
- content_type: string; default="application/octet-stream"; optional. MIME type such as application/pdf; defaults to application/octet-stream.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DraftReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "enum": [
            "not_sent",
            "failed",
            "succeeded",
            "partial",
            "unknown"
          ],
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "created": {
          "title": "Created",
          "type": "boolean"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uid"
        },
        "subject": {
          "title": "Subject",
          "type": "string"
        },
        "attachment_count": {
          "minimum": 0,
          "title": "Attachment Count",
          "type": "integer"
        },
        "from_header": {
          "title": "From Header",
          "type": "string"
        },
        "from_address": {
          "title": "From Address",
          "type": "string"
        },
        "from_name": {
          "title": "From Name",
          "type": "string"
        },
        "body_format": {
          "enum": [
            "plain",
            "html"
          ],
          "title": "Body Format",
          "type": "string"
        },
        "sent": {
          "const": false,
          "title": "Sent",
          "type": "boolean"
        },
        "send_as_permissions_verified": {
          "const": false,
          "title": "Send As Permissions Verified",
          "type": "boolean"
        }
      },
      "required": [
        "operation",
        "phase",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "created",
        "mailbox",
        "uid",
        "subject",
        "attachment_count",
        "from_header",
        "from_address",
        "from_name",
        "body_format",
        "sent",
        "send_as_permissions_verified"
      ],
      "title": "DraftReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DraftReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `delete_email`

Mail · Delete a message from the connected mail account (write, destructive).

Delete one email by marking it Deleted and expunging it when safe. This is destructive and requires confirm=true in addition to the client's approval flow.

Workflow: Read the exact message identity and obtain explicit confirm=true authorization. This is destructive mailbox mutation, not draft preparation.
Result interpretation: UID, mailbox, marked_deleted and expunged/deleted. If marked_deleted=true but expunged=false, the message is flagged for deletion but not confirmed permanently removed. The service never uses mailbox-wide expunge as a fallback.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- confirm: boolean; required. Explicit true authorizes this destructive operation; false does not perform it.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DeleteMailReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "enum": [
            "not_sent",
            "failed",
            "succeeded",
            "partial",
            "unknown"
          ],
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "deleted": {
          "title": "Deleted",
          "type": "boolean"
        },
        "marked_deleted": {
          "title": "Marked Deleted",
          "type": "boolean"
        },
        "expunged": {
          "title": "Expunged",
          "type": "boolean"
        }
      },
      "required": [
        "operation",
        "phase",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "uid",
        "mailbox",
        "deleted",
        "marked_deleted",
        "expunged"
      ],
      "title": "DeleteMailReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DeleteMailReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `email_search_index_status`

Mail · Check mail search index progress (read-only).

Return local mail index counts, model, worker state and omitted/truncated counts without reading iCloud or calling OpenAI.

Workflow: Use before interpreting semantic search coverage or diagnosing indexing progress; this does not start an index job or fetch new mail.
Result interpretation: configured and safe local index/worker counts and state when enabled. configured=false means semantic search is disabled. Index progress does not prove complete coverage of the live mailbox.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "IndexBatch": {
      "additionalProperties": true,
      "properties": {
        "status": {
          "enum": [
            "queued",
            "submitting",
            "uploaded",
            "validating",
            "in_progress",
            "finalizing",
            "completed",
            "failed",
            "expired",
            "cancelling",
            "cancelled"
          ],
          "title": "Status",
          "type": "string"
        },
        "inputs": {
          "minimum": 0,
          "title": "Inputs",
          "type": "integer"
        },
        "id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Id"
        }
      },
      "required": [
        "status",
        "inputs",
        "id"
      ],
      "title": "IndexBatch",
      "type": "object"
    },
    "IndexStatusReply": {
      "additionalProperties": true,
      "properties": {
        "configured": {
          "title": "Configured",
          "type": "boolean"
        },
        "source": {
          "const": "sqlite_cached_emails",
          "title": "Source",
          "type": "string"
        },
        "model": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model"
        },
        "dimensions": {
          "anyOf": [
            {
              "minimum": 1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Dimensions"
        },
        "worker": {
          "anyOf": [
            {
              "enum": [
                "idle",
                "indexing",
                "waiting_batch",
                "retrying",
                "stopped"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Worker"
        },
        "embedding_mode": {
          "anyOf": [
            {
              "enum": [
                "batch",
                "standard"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Embedding Mode"
        },
        "last_error": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Last Error"
        },
        "batch": {
          "anyOf": [
            {
              "$ref": "#/$defs/IndexBatch"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "cached_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Cached Messages"
        },
        "indexed_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Indexed Messages"
        },
        "indexed_chunks": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Indexed Chunks"
        },
        "skipped_attachments": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Skipped Attachments"
        },
        "truncated_sources": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Truncated Sources"
        },
        "skipped_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Skipped Messages"
        },
        "pending_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pending Messages"
        }
      },
      "required": [
        "configured",
        "source"
      ],
      "title": "IndexStatusReply",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/IndexStatusReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_email`

Mail · Read a message from the connected mail account (read-only).

Read one email by its mailbox-local IMAP UID. The message is fetched with BODY.PEEK so reading it does not mark it read. Attachments include metadata and attachment_id; call get_email_attachment with that ID to retrieve the original file as a native MCP resource, or use format=text for PDF/text contents.

Workflow: Use mailbox-local UID from search_emails; preserve expected_uid_validity when using a generation-bound retrieval reference. Use returned attachment_id for attachment retrieval.
Result interpretation: Message headers, body text with truncation information and attachment metadata. BODY.PEEK preserves the read flag. A body signature is not a From display name; a truncated body is not the complete original message.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- max_body_chars: integer; default=20000; minimum=1; maximum=100000; optional. Maximum returned body characters, 1..100000; a truncated body is not the complete message.
- expected_uid_validity: string | null; default=null; optional. Mailbox generation from a prior result, as a decimal string. Null omits the generation guard; a mismatch rejects a reused UID.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Attachment": {
      "additionalProperties": true,
      "properties": {
        "attachment_id": {
          "title": "Attachment Id",
          "type": "string"
        },
        "filename": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Filename"
        },
        "content_type": {
          "title": "Content Type",
          "type": "string"
        },
        "size": {
          "minimum": 0,
          "title": "Size",
          "type": "integer"
        }
      },
      "required": [
        "attachment_id",
        "filename",
        "content_type",
        "size"
      ],
      "title": "Attachment",
      "type": "object"
    },
    "EmailReply": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "subject": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Subject"
        },
        "from": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "From"
        },
        "to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "To"
        },
        "cc": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Cc"
        },
        "date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Date"
        },
        "message_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Message Id"
        },
        "flags": {
          "items": {
            "type": "string"
          },
          "title": "Flags",
          "type": "array"
        },
        "read": {
          "title": "Read",
          "type": "boolean"
        },
        "uid_validity": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Uid Validity"
        },
        "internal_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Internal Date"
        },
        "body": {
          "title": "Body",
          "type": "string"
        },
        "body_truncated": {
          "title": "Body Truncated",
          "type": "boolean"
        },
        "body_format": {
          "anyOf": [
            {
              "enum": [
                "plain",
                "html"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Body Format"
        },
        "attachments": {
          "items": {
            "$ref": "#/$defs/Attachment"
          },
          "title": "Attachments",
          "type": "array"
        }
      },
      "required": [
        "uid",
        "mailbox",
        "subject",
        "from",
        "to",
        "cc",
        "date",
        "message_id",
        "flags",
        "read",
        "body",
        "body_truncated",
        "body_format",
        "attachments"
      ],
      "title": "EmailReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/EmailReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_email_attachment`

Mail · Read an attachment from the connected mail account (read-only).

Read an attachment using uid, mailbox and attachment_id from get_email. Default format=file returns the COMPLETE original attachment as an embedded binary MCP resource and resource link, with filename and MIME type (up to 30 MB). File mode requires offset=0 and ignores limit; resource links can be read through resources/read for up to 15 minutes, until capacity eviction or service restart. Use format=text to extract readable PDF/text content; scanned PDFs without embedded text need OCR. Use format=base64 for bounded original byte chunks. offset/limit count characters for text and decoded bytes for base64 (limit 1–100000). Follow next_offset while has_more=true; decode each base64 chunk separately before concatenating bytes. Reads use BODY.PEEK and never mark mail read.

Workflow: Read get_email first to obtain the exact attachment_id. Use file for original bytes, text for extraction, or collect base64 chunks using next_offset and the same mailbox generation.
Result interpretation: file returns an embedded binary resource and a private resource link with metadata; text/base64 return bounded content and pagination information. Text extraction changes representation and may require OCR for scans; original file mode performs no conversion. A resource can expire or be evicted.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- attachment_id: string; required. Opaque attachment ID returned by get_email for this exact UID/mailbox; not a filename or path.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- format: string; enum=["file", "text", "base64"]; default="file"; optional. file returns complete original bytes as native MCP resources; text extracts readable text; base64 returns original byte chunks. Only these exact values are accepted.
- offset: integer; default=0; minimum=0; optional. Zero-based character offset for text or decoded-byte offset for base64; file requires 0. Decode each base64 chunk separately before concatenation. Drive offset is at most 30000000 and nonzero offsets require expected_version.
- limit: integer; default=20000; minimum=1; maximum=100000; optional. Chunk size 1..100000: characters for text, decoded bytes for base64. Ignored in file mode, which returns the complete attachment up to 30000000 bytes.
- expected_uid_validity: string | null; default=null; optional. Mailbox generation from a prior result, as a decimal string. Null omits the generation guard; a mismatch rejects a reused UID.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "EmailAttachmentReply": {
      "additionalProperties": true,
      "properties": {
        "filename": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Filename"
        },
        "content_type": {
          "title": "Content Type",
          "type": "string"
        },
        "size": {
          "minimum": 0,
          "title": "Size",
          "type": "integer"
        },
        "format": {
          "enum": [
            "file",
            "text",
            "base64"
          ],
          "title": "Format",
          "type": "string"
        },
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "content_base64": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Content Base64"
        },
        "text": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text"
        },
        "text_status": {
          "anyOf": [
            {
              "enum": [
                "ok",
                "no_text",
                "unsupported",
                "encrypted",
                "too_large",
                "error"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text Status"
        },
        "text_message": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text Message"
        },
        "returned_bytes": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Returned Bytes"
        },
        "returned_chars": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Returned Chars"
        },
        "resource_uri": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Opaque private snapshot URI, absent from public routes and resources/list.",
          "title": "Resource Uri"
        },
        "resource_expires_in_seconds": {
          "anyOf": [
            {
              "maximum": 900,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Resource Expires In Seconds"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "uid_validity": {
          "title": "Uid Validity",
          "type": "string"
        },
        "attachment_id": {
          "title": "Attachment Id",
          "type": "string"
        }
      },
      "required": [
        "filename",
        "content_type",
        "size",
        "format",
        "offset",
        "has_more",
        "next_offset",
        "uid",
        "mailbox",
        "uid_validity",
        "attachment_id"
      ],
      "title": "EmailAttachmentReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/EmailAttachmentReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_mailboxes`

Mail · List mailboxes in the connected account (read-only).

List exact available IMAP mailbox names, delimiter and native flags in the connected account. Prefer a folder marked with the Drafts special-use flag for drafts. If no such flag exists, select a verified folder name; never assume Drafts exists. Folder labels such as Gmail do not prove the provider or sender identity; inspect mail_account_info for the configured endpoint.

Workflow: Discover exact folder names before selecting, moving or writing mail. For drafts prefer a native Drafts special-use flag, otherwise choose an explicitly verified existing folder.
Result interpretation: An array of name, delimiter and flags. Copy the complete name including prefixes. Folder names/flags describe mailbox organization; they do not identify the upstream provider or sender account.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "Mailbox": {
      "additionalProperties": true,
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "delimiter": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Delimiter"
        },
        "flags": {
          "items": {
            "type": "string"
          },
          "title": "Flags",
          "type": "array"
        }
      },
      "required": [
        "name",
        "delimiter",
        "flags"
      ],
      "title": "Mailbox",
      "type": "object"
    },
    "MailboxesReply": {
      "additionalProperties": true,
      "properties": {
        "result": {
          "items": {
            "$ref": "#/$defs/Mailbox"
          },
          "title": "Result",
          "type": "array"
        }
      },
      "required": [
        "result"
      ],
      "title": "MailboxesReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/MailboxesReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `mail_account_info`

Mail · Inspect configured mail account (read-only).

Read the configured IMAP endpoint, account, default mailbox, configured draft folder and default From header. No network request is made; configured folder names do not prove that those folders exist. Use list_mailboxes to discover exact available folders and native special-use flags before draft writes. An IMAP mirror may expose folders from another provider: neither folder names nor the From address prove the upstream provider. Credentials are never returned. This service stores drafts but cannot send mail or verify send-as permissions.

Workflow: Start here before preparing mail writes to learn the configured account, endpoint and default From header; then discover actual folders with list_mailboxes.
Result interpretation: Configured host, port, account, default_mailbox, configured_drafts_mailbox and default_from_header, with explicit verification flags and can_send=false. This configuration-only result does not prove folder existence, upstream provider or send-as permissions.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "MailAccountReply": {
      "additionalProperties": true,
      "properties": {
        "protocol": {
          "const": "imap",
          "title": "Protocol",
          "type": "string"
        },
        "host": {
          "title": "Host",
          "type": "string"
        },
        "port": {
          "maximum": 65535,
          "minimum": 1,
          "title": "Port",
          "type": "integer"
        },
        "account": {
          "title": "Account",
          "type": "string"
        },
        "default_mailbox": {
          "title": "Default Mailbox",
          "type": "string"
        },
        "configured_drafts_mailbox": {
          "title": "Configured Drafts Mailbox",
          "type": "string"
        },
        "default_from_header": {
          "title": "Default From Header",
          "type": "string"
        },
        "mailbox_existence_verified": {
          "const": false,
          "title": "Mailbox Existence Verified",
          "type": "boolean"
        },
        "upstream_provider_verified": {
          "const": false,
          "title": "Upstream Provider Verified",
          "type": "boolean"
        },
        "send_as_permissions_verified": {
          "const": false,
          "title": "Send As Permissions Verified",
          "type": "boolean"
        },
        "can_send": {
          "const": false,
          "title": "Can Send",
          "type": "boolean"
        }
      },
      "required": [
        "protocol",
        "host",
        "port",
        "account",
        "default_mailbox",
        "configured_drafts_mailbox",
        "default_from_header",
        "mailbox_existence_verified",
        "upstream_provider_verified",
        "send_as_permissions_verified",
        "can_send"
      ],
      "title": "MailAccountReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/MailAccountReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `mark_email_read`

Mail · Mark a message read or unread (write).

Change the Seen flag of one email. This changes external mail state.

Workflow: Select the exact mailbox and message UID; specify read=true to mark read or false to mark unread.
Result interpretation: UID, mailbox and requested read state after the flag update succeeds. This updates Seen only; it does not move, delete or reply to the message.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- read: boolean; default=true; optional. True sets Seen; false clears Seen. This changes the message's read state.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReadFlagReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "enum": [
            "not_sent",
            "failed",
            "succeeded",
            "partial",
            "unknown"
          ],
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "read": {
          "title": "Read",
          "type": "boolean"
        }
      },
      "required": [
        "operation",
        "phase",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "uid",
        "mailbox",
        "read"
      ],
      "title": "ReadFlagReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ReadFlagReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `move_email`

Mail · Move a message in the connected mail account (write, destructive).

Copy an email to another mailbox and mark the source for deletion. This changes external mail state and requires client approval.

Workflow: Discover both exact folder names and the source UID. Source and destination must differ. Obtain authorization before changing mailbox state.
Result interpretation: Source/destination names and source_marked_deleted/source_expunged plus moved. The implementation copies, marks the source deleted, then expunges that UID when safe. moved=false with source_marked_deleted=true can still mean the destination copy exists; do not claim nothing happened or blindly repeat. Discover the destination UID independently.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- destination_mailbox: string; required. Exact existing destination name from list_mailboxes; folders are not created automatically.
- source_mailbox: string | null; default=null; optional. Exact source name from list_mailboxes; null uses configured default mailbox.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "MoveMailReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "enum": [
            "not_sent",
            "failed",
            "succeeded",
            "partial",
            "unknown"
          ],
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "source_mailbox": {
          "title": "Source Mailbox",
          "type": "string"
        },
        "destination_mailbox": {
          "title": "Destination Mailbox",
          "type": "string"
        },
        "destination_uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Destination Uid"
        },
        "copied": {
          "title": "Copied",
          "type": "boolean"
        },
        "moved": {
          "title": "Moved",
          "type": "boolean"
        },
        "source_marked_deleted": {
          "title": "Source Marked Deleted",
          "type": "boolean"
        },
        "source_expunged": {
          "title": "Source Expunged",
          "type": "boolean"
        }
      },
      "required": [
        "operation",
        "phase",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "uid",
        "source_mailbox",
        "destination_mailbox",
        "destination_uid",
        "copied",
        "moved",
        "source_marked_deleted",
        "source_expunged"
      ],
      "title": "MoveMailReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/MoveMailReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `search_emails`

Mail · Search the connected mail account (read-only).

Search the connected IMAP account by sender, recipient, subject, text, ISO dates, or unread status. Results contain headers only; use get_email to read a message body.

Workflow: Choose a mailbox from list_mailboxes and narrow filters. Pass a result's mailbox and UID to get_email; use current returned generation information where available.
Result interpretation: Newest-first header summaries with UID, mailbox, sender/recipients, subject, dates and read flags. These are not full message bodies. limit can truncate matches, so the array does not provide an exhaustive mailbox catalogue.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- from_address: string | null; default=null; optional. Sender address filter. Null means no sender filter.
- to_address: string | null; default=null; optional. Recipient address filter. Null means no recipient filter.
- subject: string | null; default=null; optional. Subject filter. Null means no subject filter.
- query: string | null; default=null; optional. Search text; null on optional filters means no text filter.
- since: string | null; default=null; optional. Inclusive earliest IMAP date, YYYY-MM-DD; null means no lower date filter.
- before: string | null; default=null; optional. Exclusive latest IMAP date, YYYY-MM-DD; null means no upper date filter.
- unread_only: boolean; default=false; optional. True restricts results to messages without the Seen flag; false includes read and unread messages.
- limit: integer; default=50; minimum=1; maximum=1000; optional. Maximum results for this page, 1..1000.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "MailHeader": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "subject": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Subject"
        },
        "from": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "From"
        },
        "to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "To"
        },
        "cc": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Cc"
        },
        "date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Date"
        },
        "message_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Message Id"
        },
        "flags": {
          "items": {
            "type": "string"
          },
          "title": "Flags",
          "type": "array"
        },
        "read": {
          "title": "Read",
          "type": "boolean"
        },
        "uid_validity": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Uid Validity"
        },
        "internal_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Internal Date"
        }
      },
      "required": [
        "uid",
        "mailbox",
        "subject",
        "from",
        "to",
        "cc",
        "date",
        "message_id",
        "flags",
        "read"
      ],
      "title": "MailHeader",
      "type": "object"
    },
    "MailHeadersReply": {
      "additionalProperties": true,
      "properties": {
        "result": {
          "items": {
            "$ref": "#/$defs/MailHeader"
          },
          "title": "Result",
          "type": "array"
        }
      },
      "required": [
        "result"
      ],
      "title": "MailHeadersReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/MailHeadersReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `semantic_search_emails`

Mail · Search mail and attachments by meaning (read-only).

Search the local SQLite mail snapshots by meaning, including extracted PDF/text attachments. The query is embedded with OpenAI; matching text excerpts come from the local Qdrant index. This covers cached mail only, not a live or complete IMAP search. Results include mailbox, uid, uid_validity, score, source and attachment_id. Use get_email/get_email_attachment to retrieve the current original; snapshots may be older than the live mailbox. source may be body or attachment. Scans need OCR and are skipped. The response includes indexing progress and omitted/truncated source counts.

Workflow: Use for meaning-based discovery in the local mail/PDF index; check index progress. For current originals use the returned email/attachment retrieval arguments, including expected_uid_validity.
Result interpretation: matches with scores, excerpts, source/attachment references and index status. Excerpts are bounded derived text, scores are retrieval similarity, and no match does not prove absence from live IMAP or unindexed/scanned documents.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- query: string; required. Nonblank natural-language query embedded with OpenAI; searches indexed local mail/PDF text only.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- source: string; enum=["body", "attachment"] | null; default=null; optional. body searches message bodies; attachment searches extracted attachments; null searches both. Only indexed local snapshots are covered.
- limit: integer; default=10; minimum=1; maximum=50; optional. Maximum results for this page, 1..50.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "IndexBatch": {
      "additionalProperties": true,
      "properties": {
        "status": {
          "enum": [
            "queued",
            "submitting",
            "uploaded",
            "validating",
            "in_progress",
            "finalizing",
            "completed",
            "failed",
            "expired",
            "cancelling",
            "cancelled"
          ],
          "title": "Status",
          "type": "string"
        },
        "inputs": {
          "minimum": 0,
          "title": "Inputs",
          "type": "integer"
        },
        "id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Id"
        }
      },
      "required": [
        "status",
        "inputs",
        "id"
      ],
      "title": "IndexBatch",
      "type": "object"
    },
    "IndexStatusReply": {
      "additionalProperties": true,
      "properties": {
        "configured": {
          "title": "Configured",
          "type": "boolean"
        },
        "source": {
          "const": "sqlite_cached_emails",
          "title": "Source",
          "type": "string"
        },
        "model": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model"
        },
        "dimensions": {
          "anyOf": [
            {
              "minimum": 1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Dimensions"
        },
        "worker": {
          "anyOf": [
            {
              "enum": [
                "idle",
                "indexing",
                "waiting_batch",
                "retrying",
                "stopped"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Worker"
        },
        "embedding_mode": {
          "anyOf": [
            {
              "enum": [
                "batch",
                "standard"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Embedding Mode"
        },
        "last_error": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Last Error"
        },
        "batch": {
          "anyOf": [
            {
              "$ref": "#/$defs/IndexBatch"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "cached_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Cached Messages"
        },
        "indexed_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Indexed Messages"
        },
        "indexed_chunks": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Indexed Chunks"
        },
        "skipped_attachments": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Skipped Attachments"
        },
        "truncated_sources": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Truncated Sources"
        },
        "skipped_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Skipped Messages"
        },
        "pending_messages": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pending Messages"
        }
      },
      "required": [
        "configured",
        "source"
      ],
      "title": "IndexStatusReply",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "RetrievalArguments": {
      "additionalProperties": true,
      "properties": {
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "expected_uid_validity": {
          "title": "Expected Uid Validity",
          "type": "string"
        },
        "attachment_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Attachment Id"
        }
      },
      "required": [
        "mailbox",
        "uid",
        "expected_uid_validity"
      ],
      "title": "RetrievalArguments",
      "type": "object"
    },
    "RetrievalReference": {
      "additionalProperties": true,
      "properties": {
        "tool": {
          "enum": [
            "get_email",
            "get_email_attachment"
          ],
          "title": "Tool",
          "type": "string"
        },
        "arguments": {
          "$ref": "#/$defs/RetrievalArguments"
        }
      },
      "required": [
        "tool",
        "arguments"
      ],
      "title": "RetrievalReference",
      "type": "object"
    },
    "SemanticMatch": {
      "additionalProperties": true,
      "properties": {
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "uid_validity": {
          "title": "Uid Validity",
          "type": "string"
        },
        "subject": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Subject"
        },
        "from": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "From"
        },
        "to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "To"
        },
        "cc": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Cc"
        },
        "date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Date"
        },
        "message_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Message Id"
        },
        "flags": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Flags"
        },
        "read": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Read"
        },
        "score": {
          "title": "Score",
          "type": "number"
        },
        "source": {
          "enum": [
            "body",
            "attachment"
          ],
          "title": "Source",
          "type": "string"
        },
        "attachment_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Attachment Id"
        },
        "filename": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Filename"
        },
        "chunk": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Chunk"
        },
        "excerpt": {
          "title": "Excerpt",
          "type": "string"
        },
        "email": {
          "$ref": "#/$defs/RetrievalReference"
        },
        "attachment": {
          "anyOf": [
            {
              "$ref": "#/$defs/RetrievalReference"
            },
            {
              "type": "null"
            }
          ]
        }
      },
      "required": [
        "uid",
        "mailbox",
        "uid_validity",
        "score",
        "source",
        "attachment_id",
        "filename",
        "chunk",
        "excerpt",
        "email",
        "attachment"
      ],
      "title": "SemanticMatch",
      "type": "object"
    },
    "SemanticSearchReply": {
      "additionalProperties": true,
      "properties": {
        "matches": {
          "items": {
            "$ref": "#/$defs/SemanticMatch"
          },
          "title": "Matches",
          "type": "array"
        },
        "index": {
          "$ref": "#/$defs/IndexStatusReply"
        }
      },
      "required": [
        "matches",
        "index"
      ],
      "title": "SemanticSearchReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/SemanticSearchReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `update_draft`

Mail · Replace a draft in the connected mail account (write, destructive).

Replace an existing draft with new recipients, subject, body, and optional base64-encoded attachments. The old draft is marked deleted when safe. Nothing is sent; send the resulting draft manually from a mail client. This is a complete replacement, not a partial patch: supply all recipients, subject, body and desired attachments. First discover the exact mailbox and UID with list_mailboxes/search_emails/get_email. body_format accepts plain or html. An append may succeed before deleting the old draft fails; never blindly retry. Inspect the mailbox first. Returned From fields describe the submitted MIME header; body signatures do not set the sender name.

Workflow: Locate and read an existing non-deleted draft in the exact folder. Supply its complete replacement, including every desired recipient and attachment; omitted attachments are not retained.
Result interpretation: updated=true, old_uid, replacement uid (possibly null), mailbox, submitted From fields and old_draft_marked_deleted/old_draft_expunged. Replacement is non-atomic; failure can leave both drafts. sent=false confirms this service did not send the draft, not that another client never sent it.
Failures and recovery: Use only returned safe diagnostics: some failures expose an operation/category but the server's exact reason can remain unavailable. Refresh folder/message discovery for mailbox or UID problems. Writes may partly succeed before failure; inspect both affected folders/drafts before retrying. Do not claim messages were sent by this service. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- uid: string; required. Exact UID from the relevant listing. Mail UIDs are decimal strings local to one mailbox; calendar UIDs identify a series.
- to: array<string>; required. Array of recipient strings (address or RFC mailbox such as Name <person@example.com>), not a comma-separated string. May be empty if cc/bcc supplies a recipient; at least one recipient overall. No CR/LF.
- subject: string; required. Complete nonblank subject, without CR/LF. Required even when updating; drafts are replaced, not partially patched.
- body: string; required. Complete draft body string. Use body_format to declare plain text or HTML. Signature text does not set the From header. Entire MIME message including encoded attachments is limited to 25000000 bytes.
- cc: array<string> | null; default=null; optional. Optional array of visible copy recipients; null/omission means none. No CR/LF.
- bcc: array<string> | null; default=null; optional. Optional array of blind copy recipients; null/omission means none. No CR/LF.
- mailbox: string | null; default=null; optional. Exact IMAP mailbox name from list_mailboxes, including prefixes/case. Null uses configured default mailbox; draft tools use configured drafts_mailbox. Discover and pass the real draft folder before writing; do not infer the provider from folder names.
- body_format: string; enum=["plain", "html"]; default="plain"; optional. Exactly plain (plain text) or html (HTML); text is invalid. Defaults to plain. Parameter name is body_format, not format.
- attachments: array<DraftAttachment> | null; default=null; optional. Optional array of attachment objects; null/omission means no attachments. Each object requires filename and content_base64, with optional MIME content_type. Maximum 10000000 decoded bytes per attachment and 25000000 bytes for the entire serialized message. No local paths or external URLs.
- from_address: string | null; default=null; optional. Complete MIME From header, e.g. Name <person@example.com>, or a bare email address. Null defaults to the configured IMAP username. This does not verify send-as permissions. The body/signature does not set the sender name; inspect returned from_header/from_address/from_name.
Nested object DraftAttachment:
- filename: string; minLength=1; required. Filename, one nonblank path component without slash, backslash or control characters.
- content_base64: string; minLength=1; required. Strict base64 of original attachment bytes; maximum 10000000 decoded bytes. No paths or URLs.
- content_type: string; default="application/octet-stream"; optional. MIME type such as application/pdf; defaults to application/octet-stream.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "UpdateDraftReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "enum": [
            "not_sent",
            "failed",
            "succeeded",
            "partial",
            "unknown"
          ],
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "created": {
          "title": "Created",
          "type": "boolean"
        },
        "mailbox": {
          "title": "Mailbox",
          "type": "string"
        },
        "uid": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uid"
        },
        "subject": {
          "title": "Subject",
          "type": "string"
        },
        "attachment_count": {
          "minimum": 0,
          "title": "Attachment Count",
          "type": "integer"
        },
        "from_header": {
          "title": "From Header",
          "type": "string"
        },
        "from_address": {
          "title": "From Address",
          "type": "string"
        },
        "from_name": {
          "title": "From Name",
          "type": "string"
        },
        "body_format": {
          "enum": [
            "plain",
            "html"
          ],
          "title": "Body Format",
          "type": "string"
        },
        "sent": {
          "const": false,
          "title": "Sent",
          "type": "boolean"
        },
        "send_as_permissions_verified": {
          "const": false,
          "title": "Send As Permissions Verified",
          "type": "boolean"
        },
        "updated": {
          "const": true,
          "title": "Updated",
          "type": "boolean"
        },
        "old_uid": {
          "title": "Old Uid",
          "type": "string"
        },
        "old_draft_marked_deleted": {
          "title": "Old Draft Marked Deleted",
          "type": "boolean"
        },
        "old_draft_expunged": {
          "title": "Old Draft Expunged",
          "type": "boolean"
        }
      },
      "required": [
        "operation",
        "phase",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "created",
        "mailbox",
        "uid",
        "subject",
        "attachment_count",
        "from_header",
        "from_address",
        "from_name",
        "body_format",
        "sent",
        "send_as_permissions_verified",
        "updated",
        "old_uid",
        "old_draft_marked_deleted",
        "old_draft_expunged"
      ],
      "title": "UpdateDraftReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/UpdateDraftReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `create_contact`

Contacts · Create contact (write).

Create one iCloud contact from structured contact fields in an exact addressbook_id, after user approval. A name or organization is required. Emails, phones and addresses accept labels; birthday is YYYY-MM-DD. Creates a fresh UID using If-None-Match:* and never overwrites or merges. No automatic retries. write_status=succeeded confirms creation even when readback_confirmed=false. On unknown or succeeded errors preserve contact_id and UID and use get_contact to inspect the result before any further creation. Never turn a Contacts ID into a Reminders participant ID.

Workflow: Check potential duplicates and select a writable address book. Submit one structured contact with a name or organization; creation neither edits nor merges existing records.
Result interpretation: write_status, generated contact_id/uid, addressbook_id and readback_confirmed, plus contact on successful readback. write_status=succeeded remains confirmed even if readback_confirmed=false. Preserve IDs and inspect after unknown state; never replay automatically.
Failures and recovery: Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- contact: ContactInput; required. Structured new contact; provide a name or organization. No vCard/URL input, no duplicate merging. Nested fields are described below.
- addressbook_id: string | null; default=null; optional. Exact account-scoped ID from list_addressbooks. Null uses the configured default or the sole eligible discovered book; multiple eligible books require an explicit ID. Never pass a remote URL.
Nested object ContactInput:
- display_name: string; default=""; maxLength=16384; optional. Contact's formatted display name.
- given_name: string; default=""; maxLength=16384; optional. Given/first name.
- family_name: string; default=""; maxLength=16384; optional. Family/last name.
- additional_name: string; default=""; maxLength=16384; optional. Additional/middle names.
- name_prefix: string; default=""; maxLength=16384; optional. Name prefix or honorific.
- name_suffix: string; default=""; maxLength=16384; optional. Name suffix.
- organization: string; default=""; maxLength=16384; optional. Organization name; sufficient instead of a person's name.
- emails: array<ContactValue>; maxItems=50; optional. Email values with optional labels, at most 50; defaults to an empty array.
- phones: array<ContactValue>; maxItems=50; optional. Phone values with optional labels, at most 50; defaults to an empty array.
- addresses: array<PostalAddress>; maxItems=20; optional. Postal addresses, at most 20; defaults to an empty array. Each needs a nonblank address field.
- birthday: string; pattern="^\\d{4}-\\d{2}-\\d{2}$" | null; default=null; optional. Valid calendar date YYYY-MM-DD; null/omission means no birthday.
- notes: string; default=""; maxLength=16384; optional. Contact notes; empty string means no notes.
Nested object ContactValue:
- value: string; minLength=1; maxLength=1024; required. Nonblank email or phone value, depending on the containing array.
- label: string; default=""; maxLength=80; optional. Optional free-text label (e.g. home or work); empty string means unlabeled.
Nested object PostalAddress:
- label: string; default=""; maxLength=80; optional. Optional free-text label (e.g. home or work); empty string means unlabeled.
- po_box: string; default=""; maxLength=16384; optional. Post office box.
- extended: string; default=""; maxLength=16384; optional. Extended postal address (e.g. apartment).
- street: string; default=""; maxLength=16384; optional. Street address.
- city: string; default=""; maxLength=16384; optional. City/locality.
- region: string; default=""; maxLength=16384; optional. State/province/region.
- postal_code: string; default=""; maxLength=16384; optional. Postal/ZIP code.
- country: string; default=""; maxLength=16384; optional. Country text.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Contact": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "etag": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Etag"
        },
        "display_name": {
          "title": "Display Name",
          "type": "string"
        },
        "given_name": {
          "title": "Given Name",
          "type": "string"
        },
        "family_name": {
          "title": "Family Name",
          "type": "string"
        },
        "additional_name": {
          "title": "Additional Name",
          "type": "string"
        },
        "name_prefix": {
          "title": "Name Prefix",
          "type": "string"
        },
        "name_suffix": {
          "title": "Name Suffix",
          "type": "string"
        },
        "organization": {
          "title": "Organization",
          "type": "string"
        },
        "birthday": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Birthday"
        },
        "notes": {
          "title": "Notes",
          "type": "string"
        },
        "emails": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Emails",
          "type": "array"
        },
        "phones": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Phones",
          "type": "array"
        },
        "addresses": {
          "items": {
            "$ref": "#/$defs/PostalAddressReply"
          },
          "title": "Addresses",
          "type": "array"
        }
      },
      "required": [
        "id",
        "addressbook_id",
        "uid",
        "etag",
        "display_name",
        "given_name",
        "family_name",
        "additional_name",
        "name_prefix",
        "name_suffix",
        "organization",
        "birthday",
        "notes",
        "emails",
        "phones",
        "addresses"
      ],
      "title": "Contact",
      "type": "object"
    },
    "ContactValueReply": {
      "additionalProperties": true,
      "properties": {
        "value": {
          "title": "Value",
          "type": "string"
        },
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "value",
        "label"
      ],
      "title": "ContactValueReply",
      "type": "object"
    },
    "CreateContactReply": {
      "additionalProperties": true,
      "properties": {
        "write_status": {
          "const": "succeeded",
          "title": "Write Status",
          "type": "string"
        },
        "contact_id": {
          "title": "Contact Id",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "readback_confirmed": {
          "title": "Readback Confirmed",
          "type": "boolean"
        },
        "readback_error": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Readback Error"
        },
        "etag": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Etag"
        },
        "contact": {
          "anyOf": [
            {
              "$ref": "#/$defs/Contact"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        }
      },
      "required": [
        "write_status",
        "contact_id",
        "uid",
        "addressbook_id",
        "readback_confirmed"
      ],
      "title": "CreateContactReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "PostalAddressReply": {
      "additionalProperties": true,
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        },
        "po_box": {
          "title": "Po Box",
          "type": "string"
        },
        "extended": {
          "title": "Extended",
          "type": "string"
        },
        "street": {
          "title": "Street",
          "type": "string"
        },
        "city": {
          "title": "City",
          "type": "string"
        },
        "region": {
          "title": "Region",
          "type": "string"
        },
        "postal_code": {
          "title": "Postal Code",
          "type": "string"
        },
        "country": {
          "title": "Country",
          "type": "string"
        }
      },
      "required": [
        "label",
        "po_box",
        "extended",
        "street",
        "city",
        "region",
        "postal_code",
        "country"
      ],
      "title": "PostalAddressReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/CreateContactReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_contact`

Contacts · Get contact (read-only).

Read a contact by an exact contact_id from list/search/create, including labelled emails, phones, postal addresses, structured name, organization, birthday, notes, UID and ETag. Use this to reconcile an uncertain creation. IDs remain valid across service restarts for the same account and resource.

Workflow: Use contact_id from Contacts list/search/create. For uncertain creation inspect this ID before considering any new write.
Result interpretation: A contact object with names, organization, labeled email/phone/address fields and supported metadata. A coverage_incomplete failure cannot establish absence. Photos, groups and arbitrary Apple extension fields are not included.
Failures and recovery: Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- contact_id: string; required. Exact account-scoped ID returned by Contacts tools; not a URL or a Reminders participant ID.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Contact": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "etag": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Etag"
        },
        "display_name": {
          "title": "Display Name",
          "type": "string"
        },
        "given_name": {
          "title": "Given Name",
          "type": "string"
        },
        "family_name": {
          "title": "Family Name",
          "type": "string"
        },
        "additional_name": {
          "title": "Additional Name",
          "type": "string"
        },
        "name_prefix": {
          "title": "Name Prefix",
          "type": "string"
        },
        "name_suffix": {
          "title": "Name Suffix",
          "type": "string"
        },
        "organization": {
          "title": "Organization",
          "type": "string"
        },
        "birthday": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Birthday"
        },
        "notes": {
          "title": "Notes",
          "type": "string"
        },
        "emails": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Emails",
          "type": "array"
        },
        "phones": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Phones",
          "type": "array"
        },
        "addresses": {
          "items": {
            "$ref": "#/$defs/PostalAddressReply"
          },
          "title": "Addresses",
          "type": "array"
        }
      },
      "required": [
        "id",
        "addressbook_id",
        "uid",
        "etag",
        "display_name",
        "given_name",
        "family_name",
        "additional_name",
        "name_prefix",
        "name_suffix",
        "organization",
        "birthday",
        "notes",
        "emails",
        "phones",
        "addresses"
      ],
      "title": "Contact",
      "type": "object"
    },
    "ContactReply": {
      "additionalProperties": true,
      "properties": {
        "contact": {
          "$ref": "#/$defs/Contact"
        }
      },
      "required": [
        "contact"
      ],
      "title": "ContactReply",
      "type": "object"
    },
    "ContactValueReply": {
      "additionalProperties": true,
      "properties": {
        "value": {
          "title": "Value",
          "type": "string"
        },
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "value",
        "label"
      ],
      "title": "ContactValueReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "PostalAddressReply": {
      "additionalProperties": true,
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        },
        "po_box": {
          "title": "Po Box",
          "type": "string"
        },
        "extended": {
          "title": "Extended",
          "type": "string"
        },
        "street": {
          "title": "Street",
          "type": "string"
        },
        "city": {
          "title": "City",
          "type": "string"
        },
        "region": {
          "title": "Region",
          "type": "string"
        },
        "postal_code": {
          "title": "Postal Code",
          "type": "string"
        },
        "country": {
          "title": "Country",
          "type": "string"
        }
      },
      "required": [
        "label",
        "po_box",
        "extended",
        "street",
        "city",
        "region",
        "postal_code",
        "country"
      ],
      "title": "PostalAddressReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ContactReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_addressbooks`

Contacts · List addressbooks (read-only).

List iCloud CardDAV address books with exact IDs and current creation permissions. writable=null means the server did not report privileges. IDs are scoped to this account.

Workflow: Discover address-book IDs and write permissions before selecting a Contacts collection. If multiple books are eligible, pass an explicit ID in subsequent calls.
Result interpretation: addressbooks containing account-scoped id, name and writable. Unknown permission is not confirmed write access; creation refreshes permissions.
Failures and recovery: Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "AddressBook": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "writable": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "title": "Writable"
        }
      },
      "required": [
        "id",
        "name",
        "writable"
      ],
      "title": "AddressBook",
      "type": "object"
    },
    "AddressBooksReply": {
      "additionalProperties": true,
      "properties": {
        "addressbooks": {
          "items": {
            "$ref": "#/$defs/AddressBook"
          },
          "title": "Addressbooks",
          "type": "array"
        }
      },
      "required": [
        "addressbooks"
      ],
      "title": "AddressBooksReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/AddressBooksReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_contacts`

Contacts · List contacts (read-only).

List a bounded page of contacts from one exact addressbook_id. Omit the ID only when there is one address book or a configured default. limit is 1..500; offset indexes the resource catalogue. Check coverage_complete and skipped_count; an incomplete result cannot establish absence. No contact photos, groups or arbitrary Apple extension fields are returned.

Workflow: Select an address book, page with next_offset and retain returned contact IDs. Review coverage_complete and skipped_count before using the catalogue for duplicate or absence checks.
Result interpretation: contacts plus addressbook_id, pagination, catalogue_count and coverage information. Individual unparseable/missing entries can be skipped; a partial page/catalogue cannot establish that a contact does not exist.
Failures and recovery: Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- addressbook_id: string | null; default=null; optional. Exact account-scoped ID from list_addressbooks. Null uses the configured default or the sole eligible discovered book; multiple eligible books require an explicit ID. Never pass a remote URL.
- limit: integer; default=100; minimum=1; maximum=500; optional. Maximum results for this page, 1..500.
- offset: integer; default=0; minimum=0; maximum=5000; optional. Zero-based nonnegative pagination offset. See tool-specific bounds; advance only using returned coverage/pagination information.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Contact": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "etag": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Etag"
        },
        "display_name": {
          "title": "Display Name",
          "type": "string"
        },
        "given_name": {
          "title": "Given Name",
          "type": "string"
        },
        "family_name": {
          "title": "Family Name",
          "type": "string"
        },
        "additional_name": {
          "title": "Additional Name",
          "type": "string"
        },
        "name_prefix": {
          "title": "Name Prefix",
          "type": "string"
        },
        "name_suffix": {
          "title": "Name Suffix",
          "type": "string"
        },
        "organization": {
          "title": "Organization",
          "type": "string"
        },
        "birthday": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Birthday"
        },
        "notes": {
          "title": "Notes",
          "type": "string"
        },
        "emails": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Emails",
          "type": "array"
        },
        "phones": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Phones",
          "type": "array"
        },
        "addresses": {
          "items": {
            "$ref": "#/$defs/PostalAddressReply"
          },
          "title": "Addresses",
          "type": "array"
        }
      },
      "required": [
        "id",
        "addressbook_id",
        "uid",
        "etag",
        "display_name",
        "given_name",
        "family_name",
        "additional_name",
        "name_prefix",
        "name_suffix",
        "organization",
        "birthday",
        "notes",
        "emails",
        "phones",
        "addresses"
      ],
      "title": "Contact",
      "type": "object"
    },
    "ContactValueReply": {
      "additionalProperties": true,
      "properties": {
        "value": {
          "title": "Value",
          "type": "string"
        },
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "value",
        "label"
      ],
      "title": "ContactValueReply",
      "type": "object"
    },
    "ContactsReply": {
      "additionalProperties": true,
      "properties": {
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "contacts": {
          "items": {
            "$ref": "#/$defs/Contact"
          },
          "title": "Contacts",
          "type": "array"
        },
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "coverage_complete": {
          "title": "Coverage Complete",
          "type": "boolean"
        },
        "skipped_count": {
          "minimum": 0,
          "title": "Skipped Count",
          "type": "integer"
        },
        "catalogue_count": {
          "minimum": 0,
          "title": "Catalogue Count",
          "type": "integer"
        }
      },
      "required": [
        "addressbook_id",
        "contacts",
        "offset",
        "next_offset",
        "has_more",
        "coverage_complete",
        "skipped_count",
        "catalogue_count"
      ],
      "title": "ContactsReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "PostalAddressReply": {
      "additionalProperties": true,
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        },
        "po_box": {
          "title": "Po Box",
          "type": "string"
        },
        "extended": {
          "title": "Extended",
          "type": "string"
        },
        "street": {
          "title": "Street",
          "type": "string"
        },
        "city": {
          "title": "City",
          "type": "string"
        },
        "region": {
          "title": "Region",
          "type": "string"
        },
        "postal_code": {
          "title": "Postal Code",
          "type": "string"
        },
        "country": {
          "title": "Country",
          "type": "string"
        }
      },
      "required": [
        "label",
        "po_box",
        "extended",
        "street",
        "city",
        "region",
        "postal_code",
        "country"
      ],
      "title": "PostalAddressReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ContactsReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `search_contacts`

Contacts · Search contacts (read-only).

Search one address book by case-insensitive substring of names, organization, email or phone. Numeric phone searches ignore formatting. Scans a bounded catalogue; results are separate contacts, never merged. limit is 1..500; offset indexes matching contacts. Check coverage_complete before concluding that a person or possible duplicate does not exist.

Workflow: Select an address book and search names, organization, email or phone; collect matching pages and check coverage before creating a potential duplicate.
Result interpretation: Matching structured contacts, account-scoped IDs, pagination and coverage information. Matches are individual records, not merged identities or Reminders participants.
Failures and recovery: Errors expose application-owned error.code and may retain write_status/IDs. coverage_incomplete is not not_found. On failed creation keep generated IDs/UID and confirmed state; inspect get_contact and never replay automatically. Failed readback does not undo confirmed creation. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- query: string; required. Nonblank contact search text, at most 256 characters; case-insensitive substring of name, organization, email or phone. Phone searches ignore formatting. Inspect coverage_complete before inferring absence.
- addressbook_id: string | null; default=null; optional. Exact account-scoped ID from list_addressbooks. Null uses the configured default or the sole eligible discovered book; multiple eligible books require an explicit ID. Never pass a remote URL.
- limit: integer; default=100; minimum=1; maximum=500; optional. Maximum results for this page, 1..500.
- offset: integer; default=0; minimum=0; maximum=5000; optional. Zero-based nonnegative pagination offset. See tool-specific bounds; advance only using returned coverage/pagination information.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Contact": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "uid": {
          "title": "Uid",
          "type": "string"
        },
        "etag": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Etag"
        },
        "display_name": {
          "title": "Display Name",
          "type": "string"
        },
        "given_name": {
          "title": "Given Name",
          "type": "string"
        },
        "family_name": {
          "title": "Family Name",
          "type": "string"
        },
        "additional_name": {
          "title": "Additional Name",
          "type": "string"
        },
        "name_prefix": {
          "title": "Name Prefix",
          "type": "string"
        },
        "name_suffix": {
          "title": "Name Suffix",
          "type": "string"
        },
        "organization": {
          "title": "Organization",
          "type": "string"
        },
        "birthday": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Birthday"
        },
        "notes": {
          "title": "Notes",
          "type": "string"
        },
        "emails": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Emails",
          "type": "array"
        },
        "phones": {
          "items": {
            "$ref": "#/$defs/ContactValueReply"
          },
          "title": "Phones",
          "type": "array"
        },
        "addresses": {
          "items": {
            "$ref": "#/$defs/PostalAddressReply"
          },
          "title": "Addresses",
          "type": "array"
        }
      },
      "required": [
        "id",
        "addressbook_id",
        "uid",
        "etag",
        "display_name",
        "given_name",
        "family_name",
        "additional_name",
        "name_prefix",
        "name_suffix",
        "organization",
        "birthday",
        "notes",
        "emails",
        "phones",
        "addresses"
      ],
      "title": "Contact",
      "type": "object"
    },
    "ContactValueReply": {
      "additionalProperties": true,
      "properties": {
        "value": {
          "title": "Value",
          "type": "string"
        },
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "value",
        "label"
      ],
      "title": "ContactValueReply",
      "type": "object"
    },
    "ContactsReply": {
      "additionalProperties": true,
      "properties": {
        "addressbook_id": {
          "title": "Addressbook Id",
          "type": "string"
        },
        "contacts": {
          "items": {
            "$ref": "#/$defs/Contact"
          },
          "title": "Contacts",
          "type": "array"
        },
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "coverage_complete": {
          "title": "Coverage Complete",
          "type": "boolean"
        },
        "skipped_count": {
          "minimum": 0,
          "title": "Skipped Count",
          "type": "integer"
        },
        "catalogue_count": {
          "minimum": 0,
          "title": "Catalogue Count",
          "type": "integer"
        }
      },
      "required": [
        "addressbook_id",
        "contacts",
        "offset",
        "next_offset",
        "has_more",
        "coverage_complete",
        "skipped_count",
        "catalogue_count"
      ],
      "title": "ContactsReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "PostalAddressReply": {
      "additionalProperties": true,
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        },
        "po_box": {
          "title": "Po Box",
          "type": "string"
        },
        "extended": {
          "title": "Extended",
          "type": "string"
        },
        "street": {
          "title": "Street",
          "type": "string"
        },
        "city": {
          "title": "City",
          "type": "string"
        },
        "region": {
          "title": "Region",
          "type": "string"
        },
        "postal_code": {
          "title": "Postal Code",
          "type": "string"
        },
        "country": {
          "title": "Country",
          "type": "string"
        }
      },
      "required": [
        "label",
        "po_box",
        "extended",
        "street",
        "city",
        "region",
        "postal_code",
        "country"
      ],
      "title": "PostalAddressReply",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ContactsReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `create_drive_folder`

Drive · Create folder (write).

Create one named folder inside an issued folder_id (omitted=root). Refresh permissions and complete name coverage; reject collisions. Never replay a failed or uncertain write. Preserve returned folder_id even if readback fails.

Workflow: Select an owned parent and a unique folder name; authorization must cover creation. The service refreshes permissions and complete name coverage before writing.
Result interpretation: The created folder information plus write state/confirmed IDs when provided. A failure after creation may retain folder_id and confirmed steps; preserve them and inspect the parent rather than creating another folder automatically.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- name: string; required. New folder name, one nonblank path component; do not include slash, backslash or control characters. Existing names are rejected.
- folder_id: string | null; default=null; optional. Opaque owned regular folder ID from Drive tools; null selects the Drive root. Shared items, app libraries and packages are unsupported.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveItem": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "type": {
          "enum": [
            "file",
            "folder"
          ],
          "title": "Type",
          "type": "string"
        },
        "size": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "modified_at": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified At"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "id",
        "name",
        "type"
      ],
      "title": "DriveItem",
      "type": "object"
    },
    "DriveWriteReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Phase"
        },
        "write_status": {
          "const": "succeeded",
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "title": "Uncertain Step",
          "type": "null"
        },
        "readback_verified": {
          "title": "Readback Verified",
          "type": "boolean"
        },
        "item": {
          "$ref": "#/$defs/DriveItem"
        },
        "folder_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Folder Id"
        },
        "file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "File Id"
        },
        "staged_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Staged File Id"
        },
        "reserved_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reserved File Id"
        },
        "original_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original File Id"
        },
        "original_in_trash": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original In Trash"
        },
        "atomic": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Atomic"
        },
        "preserves_file_id": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Preserves File Id"
        },
        "bytes_uploaded": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Bytes Uploaded"
        },
        "sha256": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sha256"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "operation",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "readback_verified",
        "item"
      ],
      "title": "DriveWriteReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveWriteReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `drive_status`

Drive · Drive status (read-only).

Show safe Drive configuration, current session/access state, root_id and capabilities. Probes existing access only; never logs in or requests 2FA/ADP approval. auth_required/access_required need the separate administrative Drive CLI.

Workflow: Start here before Drive operations. Authentication and web-access approval, when required, are separate explicit administrative actions.
Result interpretation: configured, session_state, root_id and capabilities. ready means existing access was probed, not that every file or write is permitted. auth_required/access_required do not initiate login, approval or device notifications.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveStatusReply": {
      "additionalProperties": true,
      "properties": {
        "configured": {
          "title": "Configured",
          "type": "boolean"
        },
        "session_state": {
          "enum": [
            "access_required",
            "auth_required",
            "backend_auth_failed",
            "backend_unavailable",
            "confirmation_required",
            "conflict",
            "invalid_argument",
            "lookup_incomplete",
            "not_configured",
            "not_found",
            "protocol_error",
            "read_only",
            "ready",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unsafe_target",
            "unsupported_item",
            "version_changed",
            "write_failed",
            "write_uncertain"
          ],
          "title": "Session State",
          "type": "string"
        },
        "root_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Root Id"
        },
        "read_only": {
          "title": "Read Only",
          "type": "boolean"
        },
        "capabilities": {
          "items": {
            "enum": [
              "list",
              "name_search",
              "download",
              "pdf_text",
              "create_folder",
              "upload",
              "replace"
            ],
            "type": "string"
          },
          "title": "Capabilities",
          "type": "array"
        },
        "replacement_atomic": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Replacement Atomic"
        },
        "replacement_preserves_id": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Replacement Preserves Id"
        },
        "shared_items_supported": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Shared Items Supported"
        },
        "packages_supported": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Packages Supported"
        }
      },
      "required": [
        "configured",
        "session_state",
        "root_id",
        "read_only",
        "capabilities"
      ],
      "title": "DriveStatusReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveStatusReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_drive_file`

Drive · Get drive file (read-only).

Download one Drive file by issued file_id, up to 30 MB. format=file (default) returns a complete native MCP file/resource, text extracts PDF/text, base64 returns original byte chunks. Text limit 1..100000 characters, base64 limit 1..1000000 bytes (default 20000). Pass the returned download version as expected_version on all later chunks/text pages; required for offset>0. Metadata and full-content versions are checked before exposing bytes. On version_changed discard previous chunks and restart. No arbitrary URLs or local paths accepted.

Workflow: Use a regular file ID from list/search. Use file for complete original bytes. For paged extraction or base64 chunks retain the returned download version for subsequent reads; discard accumulated chunks on version_changed.
Result interpretation: File metadata, size, SHA-256 and version with native binary resource/link in file mode or bounded text/base64 content and pagination. The checksum describes original bytes, not extracted text. Private resource availability is limited by TTL, eviction and server restarts.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- file_id: string; required. Opaque regular file ID returned by Drive tools, never a URL or path. Replacement returns a different ID.
- format: string; enum=["file", "text", "base64"]; default="file"; optional. file returns complete original bytes as native MCP resources; text extracts readable text; base64 returns original byte chunks. Only these exact values are accepted.
- offset: integer; default=0; minimum=0; maximum=30000000; optional. Zero-based character offset for text or decoded-byte offset for base64; file requires 0. Decode each base64 chunk separately before concatenation. Drive offset is at most 30000000 and nonzero offsets require expected_version.
- limit: integer; default=20000; minimum=1; maximum=1000000; optional. Chunk size: text characters 1..100000, base64 decoded bytes 1..1000000. Ignored in file mode, which returns the complete file up to 30000000 bytes.
- expected_version: string | null; default=null; optional. Exact version returned by Drive reads/listings. Required for replacement and subsequent nonzero-offset chunks; mismatches reject changed files. Discard previously collected chunks on version_changed.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveFileReply": {
      "additionalProperties": true,
      "properties": {
        "filename": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Filename"
        },
        "content_type": {
          "title": "Content Type",
          "type": "string"
        },
        "size": {
          "minimum": 0,
          "title": "Size",
          "type": "integer"
        },
        "format": {
          "enum": [
            "file",
            "text",
            "base64"
          ],
          "title": "Format",
          "type": "string"
        },
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "content_base64": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Content Base64"
        },
        "text": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text"
        },
        "text_status": {
          "anyOf": [
            {
              "enum": [
                "ok",
                "no_text",
                "unsupported",
                "encrypted",
                "too_large",
                "error"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text Status"
        },
        "text_message": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Text Message"
        },
        "returned_bytes": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Returned Bytes"
        },
        "returned_chars": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Returned Chars"
        },
        "resource_uri": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Opaque private snapshot URI, absent from public routes and resources/list.",
          "title": "Resource Uri"
        },
        "resource_expires_in_seconds": {
          "anyOf": [
            {
              "maximum": 900,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Resource Expires In Seconds"
        },
        "file_id": {
          "title": "File Id",
          "type": "string"
        },
        "version": {
          "title": "Version",
          "type": "string"
        },
        "sha256": {
          "title": "Sha256",
          "type": "string"
        }
      },
      "required": [
        "filename",
        "content_type",
        "size",
        "format",
        "offset",
        "has_more",
        "next_offset",
        "file_id",
        "version",
        "sha256"
      ],
      "title": "DriveFileReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveFileReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_drive_items`

Drive · List drive items (read-only).

List one iCloud Drive folder by an issued folder_id; omitted means root. limit 1..500, offset pagination. IDs are opaque account-scoped references. Shared folders, app libraries and document packages are skipped; check coverage_complete/skipped_count.

Workflow: Use an issued folder ID or the root, collect pages with next_offset, and retain file/folder IDs and versions for later reads or replacement.
Result interpretation: items, folder_id, total, pagination and coverage_complete/skipped_count. Unsupported shared/app-library/package items can be skipped. Folder coverage is bounded and does not prove absence elsewhere in Drive.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- folder_id: string | null; default=null; optional. Opaque owned regular folder ID from Drive tools; null selects the Drive root. Shared items, app libraries and packages are unsupported.
- limit: integer; default=100; minimum=1; maximum=500; optional. Maximum results for this page, 1..500.
- offset: integer; default=0; minimum=0; maximum=20000; optional. Zero-based pagination offset, 0..20000; check coverage_complete and returned pagination before inferring absence.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveItem": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "type": {
          "enum": [
            "file",
            "folder"
          ],
          "title": "Type",
          "type": "string"
        },
        "size": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "modified_at": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified At"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "id",
        "name",
        "type"
      ],
      "title": "DriveItem",
      "type": "object"
    },
    "DriveItemsReply": {
      "additionalProperties": true,
      "properties": {
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "coverage_complete": {
          "title": "Coverage Complete",
          "type": "boolean"
        },
        "skipped_count": {
          "minimum": 0,
          "title": "Skipped Count",
          "type": "integer"
        },
        "folder_id": {
          "title": "Folder Id",
          "type": "string"
        },
        "items": {
          "items": {
            "$ref": "#/$defs/DriveItem"
          },
          "title": "Items",
          "type": "array"
        },
        "total": {
          "minimum": 0,
          "title": "Total",
          "type": "integer"
        }
      },
      "required": [
        "offset",
        "has_more",
        "next_offset",
        "coverage_complete",
        "skipped_count",
        "folder_id",
        "items",
        "total"
      ],
      "title": "DriveItemsReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveItemsReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `replace_drive_file`

Drive · Replace file (write, destructive).

Replace the contents of an owned regular file, up to 30 MB. Requires explicit confirm=true and expected_version from list_drive_items/get_drive_file. Supply exactly one of content_base64, content_text or source_resource_uri. First stage and verify new bytes, then move the original to native Trash with its fresh etag and rename the staged file to the original name. This is non-atomic and returns a NEW file ID. Preserve all IDs, original_in_trash, confirmed_steps and uncertain_step on failure. Never retry or roll back automatically.

Workflow: Read the intended file/version, obtain explicit confirmation and supply exactly one replacement content source. Replacement verifies staged bytes, moves the original to native Trash, then renames the staged file.
Result interpretation: The replacement item with a new file ID, bytes_uploaded, sha256, version and write journal. This is non-atomic; preserve original/replacement IDs, original_in_trash and confirmed/uncertain steps. original_in_trash=null means unknown, not false. Never retry or roll back automatically.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- file_id: string; required. Opaque regular file ID returned by Drive tools, never a URL or path. Replacement returns a different ID.
- expected_version: string; required. Exact version returned by Drive reads/listings. Required for replacement and subsequent nonzero-offset chunks; mismatches reject changed files. Discard previously collected chunks on version_changed.
- confirm: boolean; default=false; optional. Explicit true authorizes this destructive operation; false does not perform it.
- content_base64: string | null; default=null; optional. Strict base64 of complete original file bytes, maximum 30000000 decoded bytes for Drive. Supply exactly one of content_base64, content_text or source_resource_uri.
- content_text: string | null; default=null; optional. Complete text encoded as UTF-8 (maximum 30000000 bytes). Supply exactly one of content_text, content_base64 or source_resource_uri.
- source_resource_uri: string | null; default=null; optional. Already-issued private Mail/Drive snapshot URI from this MCP server, valid up to 15 minutes subject to eviction/restart. No filesystem paths or external URLs. Supply exactly one content source.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveItem": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "type": {
          "enum": [
            "file",
            "folder"
          ],
          "title": "Type",
          "type": "string"
        },
        "size": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "modified_at": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified At"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "id",
        "name",
        "type"
      ],
      "title": "DriveItem",
      "type": "object"
    },
    "DriveWriteReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Phase"
        },
        "write_status": {
          "const": "succeeded",
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "title": "Uncertain Step",
          "type": "null"
        },
        "readback_verified": {
          "title": "Readback Verified",
          "type": "boolean"
        },
        "item": {
          "$ref": "#/$defs/DriveItem"
        },
        "folder_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Folder Id"
        },
        "file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "File Id"
        },
        "staged_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Staged File Id"
        },
        "reserved_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reserved File Id"
        },
        "original_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original File Id"
        },
        "original_in_trash": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original In Trash"
        },
        "atomic": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Atomic"
        },
        "preserves_file_id": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Preserves File Id"
        },
        "bytes_uploaded": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Bytes Uploaded"
        },
        "sha256": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sha256"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "operation",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "readback_verified",
        "item"
      ],
      "title": "DriveWriteReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveWriteReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `search_drive_files`

Drive · Search drive files (read-only).

Find files by case-insensitive filename substring under a folder. This is bounded folder traversal, not global or semantic content search. recursive=true, max_depth 0..10 (default 3), max_nodes 1..10000 (default 1000). limit 1..500; offset indexes matches. Check coverage_complete before concluding absence.

Workflow: Search filenames under the selected owned folder with explicit traversal budgets. For content/semantic search this tool is unsuitable; retrieve a matching original with get_drive_file.
Result interpretation: files, pagination and coverage_complete with traversal information. Depth/node limits and skipped items can make coverage incomplete; no match then does not prove the file is absent.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- query: string; required. Nonblank filename search text, at most 256 characters, within selected owned folders; inspect coverage_complete before inferring absence.
- folder_id: string | null; default=null; optional. Opaque owned regular folder ID from Drive tools; null selects the Drive root. Shared items, app libraries and packages are unsupported.
- recursive: boolean; default=true; optional. True searches descendant folders within traversal bounds; false searches only the selected folder.
- max_depth: integer; default=3; minimum=0; maximum=10; optional. Maximum descendant depth for Drive traversal, 0..10; 0 searches only the selected folder.
- max_nodes: integer; default=1000; minimum=1; maximum=10000; optional. Drive traversal budget, 1..10000 nodes. Check coverage_complete; an incomplete search cannot prove absence.
- limit: integer; default=100; minimum=1; maximum=500; optional. Maximum results for this page, 1..500.
- offset: integer; default=0; minimum=0; maximum=20000; optional. Zero-based pagination offset, 0..20000; check coverage_complete and returned pagination before inferring absence.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveItem": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "type": {
          "enum": [
            "file",
            "folder"
          ],
          "title": "Type",
          "type": "string"
        },
        "size": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "modified_at": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified At"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "id",
        "name",
        "type"
      ],
      "title": "DriveItem",
      "type": "object"
    },
    "DriveSearchReply": {
      "additionalProperties": true,
      "properties": {
        "offset": {
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "next_offset": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "coverage_complete": {
          "title": "Coverage Complete",
          "type": "boolean"
        },
        "skipped_count": {
          "minimum": 0,
          "title": "Skipped Count",
          "type": "integer"
        },
        "files": {
          "items": {
            "$ref": "#/$defs/DriveItem"
          },
          "title": "Files",
          "type": "array"
        },
        "examined_nodes": {
          "minimum": 0,
          "title": "Examined Nodes",
          "type": "integer"
        }
      },
      "required": [
        "offset",
        "has_more",
        "next_offset",
        "coverage_complete",
        "skipped_count",
        "files",
        "examined_nodes"
      ],
      "title": "DriveSearchReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveSearchReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `upload_drive_file`

Drive · Upload file (write).

Upload a new original file up to 30 MB into folder_id (omitted=root). Supply filename and exactly one of content_base64 (original bytes), content_text (UTF-8), or source_resource_uri (issued Mail/Drive snapshot). Reject existing names; never replace implicitly. Verify original bytes after activation. On failure preserve file_id/reserved_file_id and write_status; never retry automatically.

Workflow: Choose a parent, a name not already present and exactly one content source. Existing names require explicit version-checked replace_drive_file instead. Upload stages bytes, verifies them, then conditionally renames to the requested name.
Result interpretation: item, bytes_uploaded, sha256, version and write journal. Preserve staging/created IDs, confirmed_steps and uncertain_step on failure. Upload failure can leave a staged file; do not retry or remove artifacts automatically.
Failures and recovery: Errors expose application-owned error.code and may retain write journals. auth_required/access_required need explicit administrative action, not another runtime tool call. Incomplete coverage is not proof of absence. For uncertain writes preserve all IDs and confirmed/uncertain steps; never replay or roll back automatically. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- filename: string; required. Filename, one nonblank path component without slash, backslash or control characters.
- folder_id: string | null; default=null; optional. Opaque owned regular folder ID from Drive tools; null selects the Drive root. Shared items, app libraries and packages are unsupported.
- content_base64: string | null; default=null; optional. Strict base64 of complete original file bytes, maximum 30000000 decoded bytes for Drive. Supply exactly one of content_base64, content_text or source_resource_uri.
- content_text: string | null; default=null; optional. Complete text encoded as UTF-8 (maximum 30000000 bytes). Supply exactly one of content_text, content_base64 or source_resource_uri.
- source_resource_uri: string | null; default=null; optional. Already-issued private Mail/Drive snapshot URI from this MCP server, valid up to 15 minutes subject to eviction/restart. No filesystem paths or external URLs. Supply exactly one content source.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DriveItem": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "type": {
          "enum": [
            "file",
            "folder"
          ],
          "title": "Type",
          "type": "string"
        },
        "size": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "modified_at": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified At"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "id",
        "name",
        "type"
      ],
      "title": "DriveItem",
      "type": "object"
    },
    "DriveWriteReply": {
      "additionalProperties": true,
      "properties": {
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "phase": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Phase"
        },
        "write_status": {
          "const": "succeeded",
          "title": "Write Status",
          "type": "string"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "title": "Uncertain Step",
          "type": "null"
        },
        "readback_verified": {
          "title": "Readback Verified",
          "type": "boolean"
        },
        "item": {
          "$ref": "#/$defs/DriveItem"
        },
        "folder_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Folder Id"
        },
        "file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "File Id"
        },
        "staged_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Staged File Id"
        },
        "reserved_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reserved File Id"
        },
        "original_file_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original File Id"
        },
        "original_in_trash": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original In Trash"
        },
        "atomic": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Atomic"
        },
        "preserves_file_id": {
          "anyOf": [
            {
              "const": false,
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Preserves File Id"
        },
        "bytes_uploaded": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Bytes Uploaded"
        },
        "sha256": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sha256"
        },
        "version": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Version"
        }
      },
      "required": [
        "operation",
        "write_status",
        "confirmed_steps",
        "uncertain_step",
        "readback_verified",
        "item"
      ],
      "title": "DriveWriteReply",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DriveWriteReply"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `assign_reminder`

Reminders · Assign reminder (write, destructive).

Assign a reminder to an accepted participant of its shared list. Use an exact participant_id from list_reminder_participants. To remove the assignment, set clear=true and omit participant_id. This changes iCloud data; inspect an uncertain write before retrying.

Workflow: Read the reminder and accepted participants for its own list; use participant_id to assign or clear=true to remove assignment, never both. Membership and write permissions are refreshed before writing.
Result interpretation: id and status=assigned, unassigned or unchanged, with optional write_status. unchanged means the requested assignment already matched; it does not indicate a new invitation or membership change.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.
- participant_id: string | null; default=null; optional. Exact accepted participant ID from list_reminder_participants for this reminder's list. Supply participant_id or clear=true, never both; not an email, name or Contacts ID.
- clear: boolean; default=false; optional. True removes the assignee; mutually exclusive with participant_id. False requires participant_id.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "AssignmentResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/AssignmentResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "AssignmentResponse",
      "type": "object"
    },
    "AssignmentResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "enum": [
            "assigned",
            "unassigned",
            "unchanged"
          ],
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "AssignmentResult",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/AssignmentResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `batch_update_reminders`

Reminders · Batch update reminders (write, destructive).

Apply a complete target structure to one existing Reminders list in one call. reminders contains unsectioned top-level tasks; sections contains native sections with their top-level reminders. Each task has nested subtasks in desired manual order. Include every existing reminder exactly once, including completed tasks; use include_completed=true when reading. Existing tasks use exact id, new tasks omit id and require title. Optional title/due/notes/priority update existing fields. Include every existing section in current section order with id only; append new sections with title and no id. Section renaming/reordering, deletion, completion changes and assignments are unsupported. Maximum 500 total tasks, 100 sections and 20 task levels. dry_run=true (default) validates and previews without writing; set dry_run=false to apply the approved structure. Writes are sequential, not atomic. On failure the result preserves completed operations, created IDs and the uncertain operation. Stop and inspect current data before retrying; never automatically replay a batch. Requires a Go backend supporting native sections, moving and ordering.

Workflow: Read all pages with include_completed=true and existing native sections. Submit the complete target tree, preview with dry_run=true, review planned operations, then apply the authorized structure with dry_run=false.
Result interpretation: status=preview, applied or failed, atomic=false, operation counts, operations and path-to-ID mapping. On failure confirmed native results, created IDs and the failed/uncertain operation remain evidence of partial changes. A preview is not an applied change; never replay or roll back an uncertain batch automatically.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.
- reminders: array<ReminderNode>; maxItems=500; required. Complete target array of unsectioned top-level reminder nodes in desired order. Include all existing tasks, including completed ones, exactly once across this array and sections. Maximum 500 total tasks, 20 task levels.
- sections: array<ReminderSection>; maxItems=100 | null; default=null; optional. Complete target array of native sections in current section order; existing sections use id, new sections omit id and require title. Append new sections only; no section rename/reorder/deletion. Maximum 100 sections; null means no sections.
- dry_run: boolean; default=true; optional. True validates/previews without writing (default); false applies sequential non-atomic writes. Preserve confirmed IDs and uncertain steps and inspect before retrying.
Nested object ReminderNode:
- id: string | null; default=null; optional. Exact existing reminder ID; omit to create a new reminder with title.
- client_request_id: string | null; default=null; optional. Optional UUID idempotency key for a new reminder; preserve it when recovering that creation.
- title: string | null; default=null; optional. Required for a new reminder; changes an existing title when supplied.
- due: string | null; default=null; optional. YYYY-MM-DD; omit to preserve an existing due date. Clearing is unsupported.
- priority: string; enum=["none", "low", "medium", "high"] | null; default=null; optional. Exact string none, low, medium or high, mapped to native 0, 9, 5, 1. Null preserves existing priority or uses backend creation default. none explicitly clears priority; independent of manual order.
- notes: string | null; default=null; optional. Nonempty notes; omit to preserve existing notes.
- subtasks: array<ReminderNode>; maxItems=500; optional. Children in desired manual order; section is inherited. Maximum 500 tasks in the complete tree.
Nested object ReminderSection:
- id: string | null; default=null; optional. Exact existing section ID; omit to create a new section with title.
- title: string | null; default=null; optional. Heading for a new section. Renaming existing sections is unsupported.
- reminders: array<ReminderNode>; maxItems=500; optional. Top-level reminders in this section, in desired order. Maximum 500 tasks in the complete tree.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "Annotations": {
      "description": "Optional annotations the client can use to inform how objects are used or displayed.",
      "properties": {
        "audience": {
          "anyOf": [
            {
              "items": {
                "enum": [
                  "user",
                  "assistant"
                ],
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Audience"
        },
        "priority": {
          "anyOf": [
            {
              "maximum": 1.0,
              "minimum": 0.0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Priority"
        },
        "lastModified": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lastmodified"
        }
      },
      "title": "Annotations",
      "type": "object"
    },
    "AudioContent": {
      "description": "Audio provided to or from an LLM.",
      "properties": {
        "type": {
          "const": "audio",
          "default": "audio",
          "title": "Type",
          "type": "string"
        },
        "data": {
          "title": "Data",
          "type": "string"
        },
        "mimeType": {
          "title": "Mimetype",
          "type": "string"
        },
        "annotations": {
          "anyOf": [
            {
              "$ref": "#/$defs/Annotations"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        }
      },
      "required": [
        "data",
        "mimeType"
      ],
      "title": "AudioContent",
      "type": "object"
    },
    "BatchError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        },
        "code": {
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable",
        "code",
        "message"
      ],
      "title": "BatchError",
      "type": "object"
    },
    "BatchNativeResult": {
      "properties": {
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        },
        "content": {
          "items": {
            "anyOf": [
              {
                "$ref": "#/$defs/TextContent"
              },
              {
                "$ref": "#/$defs/ImageContent"
              },
              {
                "$ref": "#/$defs/AudioContent"
              },
              {
                "$ref": "#/$defs/ResourceLink"
              },
              {
                "$ref": "#/$defs/EmbeddedResource"
              }
            ]
          },
          "title": "Content",
          "type": "array"
        },
        "structuredContent": {
          "additionalProperties": {
            "$ref": "#/$defs/JsonValue"
          },
          "title": "Structuredcontent",
          "type": "object"
        },
        "isError": {
          "const": false,
          "default": false,
          "title": "Iserror",
          "type": "boolean"
        },
        "resultType": {
          "anyOf": [
            {
              "enum": [
                "complete",
                "input_required"
              ],
              "type": "string"
            },
            {
              "type": "string"
            }
          ],
          "default": "complete",
          "title": "Resulttype"
        }
      },
      "required": [
        "content",
        "structuredContent"
      ],
      "title": "BatchNativeResult",
      "type": "object"
    },
    "BatchResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/BatchResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "BatchResponse",
      "type": "object"
    },
    "BatchResult": {
      "additionalProperties": true,
      "properties": {
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "status": {
          "enum": [
            "preview",
            "applied",
            "failed"
          ],
          "title": "Status",
          "type": "string"
        },
        "dry_run": {
          "title": "Dry Run",
          "type": "boolean"
        },
        "atomic": {
          "const": false,
          "title": "Atomic",
          "type": "boolean"
        },
        "planned_operations": {
          "minimum": 0,
          "title": "Planned Operations",
          "type": "integer"
        },
        "completed_operations": {
          "minimum": 0,
          "title": "Completed Operations",
          "type": "integer"
        },
        "operations": {
          "items": {
            "$ref": "#/$defs/BatchStep"
          },
          "title": "Operations",
          "type": "array"
        },
        "ids": {
          "additionalProperties": {
            "type": "string"
          },
          "description": "Target paths mapped to existing or confirmed newly created IDs.",
          "title": "Ids",
          "type": "object"
        },
        "error": {
          "anyOf": [
            {
              "$ref": "#/$defs/BatchError"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "failed_operation": {
          "anyOf": [
            {
              "$ref": "#/$defs/BatchStep"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "write_result_unknown": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Result Unknown"
        },
        "inspect_before_retry": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Inspect Before Retry"
        }
      },
      "required": [
        "list_id",
        "status",
        "dry_run",
        "atomic",
        "planned_operations",
        "completed_operations",
        "operations",
        "ids"
      ],
      "title": "BatchResult",
      "type": "object"
    },
    "BatchStep": {
      "additionalProperties": true,
      "properties": {
        "tool": {
          "enum": [
            "create_reminder_section",
            "create_reminder",
            "update_reminder",
            "move_reminder",
            "reorder_reminders"
          ],
          "title": "Tool",
          "type": "string"
        },
        "target": {
          "description": "Target path in the submitted structure.",
          "title": "Target",
          "type": "string"
        },
        "result": {
          "anyOf": [
            {
              "$ref": "#/$defs/BatchNativeResult"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Confirmed native MCP result; omitted in previews and for the failed step."
        }
      },
      "required": [
        "tool",
        "target"
      ],
      "title": "BatchStep",
      "type": "object"
    },
    "BlobResourceContents": {
      "description": "Binary contents of a resource.",
      "properties": {
        "uri": {
          "title": "Uri",
          "type": "string"
        },
        "mimeType": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Mimetype"
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        },
        "blob": {
          "title": "Blob",
          "type": "string"
        }
      },
      "required": [
        "uri",
        "blob"
      ],
      "title": "BlobResourceContents",
      "type": "object"
    },
    "EmbeddedResource": {
      "description": "The contents of a resource, embedded into a prompt or tool call result.\n\nIt is up to the client how best to render embedded resources for the benefit\nof the LLM and/or the user.",
      "properties": {
        "type": {
          "const": "resource",
          "default": "resource",
          "title": "Type",
          "type": "string"
        },
        "resource": {
          "anyOf": [
            {
              "$ref": "#/$defs/TextResourceContents"
            },
            {
              "$ref": "#/$defs/BlobResourceContents"
            }
          ],
          "title": "Resource"
        },
        "annotations": {
          "anyOf": [
            {
              "$ref": "#/$defs/Annotations"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        }
      },
      "required": [
        "resource"
      ],
      "title": "EmbeddedResource",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "Icon": {
      "description": "An optionally-sized icon for display in a user interface (2025-11-25+).",
      "properties": {
        "src": {
          "title": "Src",
          "type": "string"
        },
        "mimeType": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Mimetype"
        },
        "sizes": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sizes"
        },
        "theme": {
          "anyOf": [
            {
              "enum": [
                "light",
                "dark"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Theme"
        }
      },
      "required": [
        "src"
      ],
      "title": "Icon",
      "type": "object"
    },
    "ImageContent": {
      "description": "An image provided to or from an LLM.",
      "properties": {
        "type": {
          "const": "image",
          "default": "image",
          "title": "Type",
          "type": "string"
        },
        "data": {
          "title": "Data",
          "type": "string"
        },
        "mimeType": {
          "title": "Mimetype",
          "type": "string"
        },
        "annotations": {
          "anyOf": [
            {
              "$ref": "#/$defs/Annotations"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        }
      },
      "required": [
        "data",
        "mimeType"
      ],
      "title": "ImageContent",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "JsonValue": {},
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "ResourceLink": {
      "description": "A resource that the server is capable of reading, included in a prompt or tool call result.\n\nNote: resource links returned by tools are not guaranteed to appear in the results of `resources/list` requests.",
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "title": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Title"
        },
        "uri": {
          "title": "Uri",
          "type": "string"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "mimeType": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Mimetype"
        },
        "size": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Size"
        },
        "icons": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/Icon"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Icons"
        },
        "annotations": {
          "anyOf": [
            {
              "$ref": "#/$defs/Annotations"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        },
        "type": {
          "const": "resource_link",
          "default": "resource_link",
          "title": "Type",
          "type": "string"
        }
      },
      "required": [
        "name",
        "uri"
      ],
      "title": "ResourceLink",
      "type": "object"
    },
    "TextContent": {
      "description": "Text provided to or from an LLM.",
      "properties": {
        "type": {
          "const": "text",
          "default": "text",
          "title": "Type",
          "type": "string"
        },
        "text": {
          "title": "Text",
          "type": "string"
        },
        "annotations": {
          "anyOf": [
            {
              "$ref": "#/$defs/Annotations"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        }
      },
      "required": [
        "text"
      ],
      "title": "TextContent",
      "type": "object"
    },
    "TextResourceContents": {
      "description": "Text contents of a resource.",
      "properties": {
        "uri": {
          "title": "Uri",
          "type": "string"
        },
        "mimeType": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Mimetype"
        },
        "_meta": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        },
        "text": {
          "title": "Text",
          "type": "string"
        }
      },
      "required": [
        "uri",
        "text"
      ],
      "title": "TextResourceContents",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/BatchResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `complete_reminder`

Reminders · Complete reminder (write).

Mark a reminder complete by exact ID; an already completed reminder is unchanged.

Workflow: Read the exact reminder identity and authorize marking it complete. The interface does not expose reopening a completed reminder.
Result interpretation: id and status=completed, with optional write_status. Already completed reminders remain completed; this does not delete the task or change its manual order.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "CompleteResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/CompleteResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "CompleteResponse",
      "type": "object"
    },
    "CompleteResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "const": "completed",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "CompleteResult",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/CompleteResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `create_reminder`

Reminders · Create reminder (write).

Create a reminder in an existing list using its exact list_id; optionally set a parent_id in the same list, a section_id from list_reminder_sections, a due date (YYYY-MM-DD), notes and priority. Subtasks inherit their parent's section. Optionally supply a UUID client_request_id for durable idempotency on an upgraded backend; recover an uncertain creation with the same ID and identical arguments. An older backend rejects keyed requests before writing. Never blindly retry an unkeyed uncertain write.

Workflow: Select a writable existing list and, if relevant, parent/section in that same list. For creation-key recovery preserve both the UUID and identical arguments; key support is checked before writes.
Result interpretation: id and status=created or already_created; newer backends may include write_status. already_created with a supported creation key recovers that existing creation and does not imply another task was inserted.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- title: string; required. Title text; nonblank when creating. On updates null/omission preserves the existing title.
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.
- due: string | null; default=null; optional. Due date YYYY-MM-DD. Null/omission leaves an existing due date unchanged or creates without a due date; clearing is unsupported.
- priority: string; enum=["none", "low", "medium", "high"] | null; default=null; optional. Exact string none, low, medium or high, mapped to native 0, 9, 5, 1. Null preserves existing priority or uses backend creation default. none explicitly clears priority; independent of manual order.
- notes: string | null; default=null; optional. Reminder notes. Null/omission preserves existing notes or creates without notes; clearing existing notes with an empty string is unsupported.
- parent_id: string | null; default=null; optional. Exact parent reminder ID in the same list. Creation null means top-level; move null preserves parent unless clear_parent=true; reorder null selects top-level siblings; reads null omit the parent filter.
- section_id: string | null; default=null; optional. Exact section ID from list_reminder_sections in the same list. Creation null means unsectioned or inherited from parent; move null preserves section unless clear_section=true; reorder null selects unsectioned siblings; reads null omit this filter.
- client_request_id: string | null; default=null; optional. Optional UUID creation key, supported only by capable Go backends. Preserve key and identical arguments for recovery; older backends reject before writing.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "CreateResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/CreateResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "CreateResponse",
      "type": "object"
    },
    "CreateResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "enum": [
            "created",
            "already_created"
          ],
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "CreateResult",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/CreateResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `create_reminder_section`

Reminders · Create reminder section (write).

Create a native section heading in an existing Reminders list. Use its exact list_id. Returns an exact section ID. Never automatically retry an uncertain creation.

Workflow: Select a writable list and supply the intended heading. Use the returned ID for moves or batches; this creates a native section, not a reminder.
Result interpretation: The new section id and status=created, with optional write_status. On an uncertain result inspect current sections before considering another creation.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.
- title: string; required. Title text; nonblank when creating. On updates null/omission preserves the existing title.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "CreateSectionResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/CreateSectionResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "CreateSectionResponse",
      "type": "object"
    },
    "CreateSectionResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "const": "created",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "CreateSectionResult",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/CreateSectionResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `delete_reminder`

Reminders · Delete reminder (write, destructive).

Permanently delete a reminder by exact ID. Requires explicit confirm=true and the user's approval.

Workflow: Read the exact task and obtain explicit confirmation for permanent deletion before calling confirm=true.
Result interpretation: id and status=deleted, with optional write_status. Deletion is destructive; an error with unknown write_status requires inspection, not automatic repeat.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.
- confirm: boolean; required. Explicit true authorizes this destructive operation; false does not perform it.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "DeleteResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/DeleteResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "DeleteResponse",
      "type": "object"
    },
    "DeleteResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "const": "deleted",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "DeleteResult",
      "type": "object"
    },
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/DeleteResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `get_reminder`

Reminders · Get reminder (read-only).

Read one reminder by its exact ID, including notes and list/parent references.

Workflow: Use an exact reminder ID from list_reminders to inspect current notes, completion, structure and assignment before mutation.
Result interpretation: A reminder object with identity, title, completion/priority and available due/notes/list/parent/section/assignee metadata. Missing optional fields on an older backend are not proof those features never exist.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "GetResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/ReminderResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "GetResponse",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "Reminder": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "title": {
          "title": "Title",
          "type": "string"
        },
        "completed": {
          "title": "Completed",
          "type": "boolean"
        },
        "priority": {
          "description": "0=none, 9=low, 5=medium, 1=high; independent of manual order.",
          "title": "Priority",
          "type": "integer"
        },
        "list_name": {
          "title": "List Name",
          "type": "string"
        },
        "list_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Ref"
        },
        "completion_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Completion Date"
        },
        "due": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Due"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "parent_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Parent Ref"
        },
        "modified_ts": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified Ts"
        },
        "assignee_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Assignee Id"
        },
        "section_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Section Ref"
        },
        "section_name": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Section Name"
        },
        "sort_index": {
          "anyOf": [
            {
              "minimum": -1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Native list position; -1 when unavailable, gaps after filtering are normal.",
          "title": "Sort Index"
        },
        "depth": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Depth"
        }
      },
      "required": [
        "id",
        "title",
        "completed",
        "priority",
        "list_name"
      ],
      "title": "Reminder",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "ReminderResult": {
      "additionalProperties": true,
      "properties": {
        "structure_warnings": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/StructureWarning"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Warnings"
        },
        "reminder": {
          "$ref": "#/$defs/Reminder"
        }
      },
      "required": [
        "reminder"
      ],
      "title": "ReminderResult",
      "type": "object"
    },
    "StructureWarning": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "const": "unsupported_structure",
          "title": "Error Code",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "record_type": {
          "title": "Record Type",
          "type": "string"
        },
        "structure_field": {
          "enum": [
            "ReminderIDs",
            "ReminderIDsAsset",
            "MembershipsOfRemindersInSectionsAsData",
            "SectionIDsOrderingAsData",
            "ResolutionTokenMap",
            "TitleDocument",
            "NotesDocument"
          ],
          "title": "Structure Field",
          "type": "string"
        },
        "structure_reason": {
          "enum": [
            "too_large",
            "invalid_json",
            "invalid_version",
            "unsupported_version",
            "missing_entries",
            "invalid_entries",
            "metadata_unavailable",
            "non_native_record_id"
          ],
          "title": "Structure Reason",
          "type": "string"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "list_id",
        "record_type",
        "structure_field",
        "structure_reason"
      ],
      "title": "StructureWarning",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/GetResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_reminder_lists`

Reminders · List reminder lists (read-only).

List iCloud Reminders lists and their exact IDs.

Workflow: Discover exact list IDs before reading or writing reminders, sections or collaborators; a list title alone is not a stable identifier.
Result interpretation: lists containing id/name and optional structure_warnings. Warning-bearing list structure must be inspected before structural writes; successfully readable tasks do not prove valid section/order metadata.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- No parameters; pass {}.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ListsResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/ListsResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "ListsResponse",
      "type": "object"
    },
    "ListsResult": {
      "additionalProperties": true,
      "properties": {
        "structure_warnings": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/StructureWarning"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Warnings"
        },
        "lists": {
          "items": {
            "$ref": "#/$defs/ReminderList"
          },
          "title": "Lists",
          "type": "array"
        }
      },
      "required": [
        "lists"
      ],
      "title": "ListsResult",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "ReminderList": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        }
      },
      "required": [
        "id",
        "name"
      ],
      "title": "ReminderList",
      "type": "object"
    },
    "StructureWarning": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "const": "unsupported_structure",
          "title": "Error Code",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "record_type": {
          "title": "Record Type",
          "type": "string"
        },
        "structure_field": {
          "enum": [
            "ReminderIDs",
            "ReminderIDsAsset",
            "MembershipsOfRemindersInSectionsAsData",
            "SectionIDsOrderingAsData",
            "ResolutionTokenMap",
            "TitleDocument",
            "NotesDocument"
          ],
          "title": "Structure Field",
          "type": "string"
        },
        "structure_reason": {
          "enum": [
            "too_large",
            "invalid_json",
            "invalid_version",
            "unsupported_version",
            "missing_entries",
            "invalid_entries",
            "metadata_unavailable",
            "non_native_record_id"
          ],
          "title": "Structure Reason",
          "type": "string"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "list_id",
        "record_type",
        "structure_field",
        "structure_reason"
      ],
      "title": "StructureWarning",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ListsResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_reminder_participants`

Reminders · List reminder participants (read-only).

List accepted participants of one shared Reminders list, including exact IDs, names and permissions. Obtain list_id from list_reminder_lists. Private lists return shared=false.

Workflow: Use the exact reminder list ID before assigning a shared-list task. Select the returned accepted participant ID for this list, never a Contacts ID, email or inferred name match.
Result interpretation: list_id, shared and participants with id, role, permission and current-user information. Discovery is read-only and does not assign anyone or invite new participants.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "Participant": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "role": {
          "title": "Role",
          "type": "string"
        },
        "permission": {
          "title": "Permission",
          "type": "string"
        },
        "is_current_user": {
          "title": "Is Current User",
          "type": "boolean"
        },
        "name": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Name"
        },
        "email": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Email"
        },
        "phone": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Phone"
        }
      },
      "required": [
        "id",
        "role",
        "permission",
        "is_current_user"
      ],
      "title": "Participant",
      "type": "object"
    },
    "ParticipantsResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/ParticipantsResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "ParticipantsResponse",
      "type": "object"
    },
    "ParticipantsResult": {
      "additionalProperties": true,
      "properties": {
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "shared": {
          "title": "Shared",
          "type": "boolean"
        },
        "participants": {
          "items": {
            "$ref": "#/$defs/Participant"
          },
          "title": "Participants",
          "type": "array"
        }
      },
      "required": [
        "list_id",
        "shared",
        "participants"
      ],
      "title": "ParticipantsResult",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ParticipantsResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_reminder_sections`

Reminders · List reminder sections (read-only).

List native Apple Reminders sections in one exact list_id, in their section order. Use the returned section IDs for creation, moving and filtering; section headings are not reminders.

Workflow: Discover native section IDs for one list before moving tasks into sections or constructing a complete batch. Section headings are separate native records, not reminder titles.
Result interpretation: list_id, sections with id/title/order metadata and optional structure_warnings. Preserve the existing section order; warnings can prohibit structural writes even while ordinary tasks are readable.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "Section": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "title": {
          "title": "Title",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "sort_index": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sort Index"
        }
      },
      "required": [
        "id",
        "title",
        "list_id"
      ],
      "title": "Section",
      "type": "object"
    },
    "SectionsResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/SectionsResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "SectionsResponse",
      "type": "object"
    },
    "SectionsResult": {
      "additionalProperties": true,
      "properties": {
        "structure_warnings": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/StructureWarning"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Warnings"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "sections": {
          "items": {
            "$ref": "#/$defs/Section"
          },
          "title": "Sections",
          "type": "array"
        }
      },
      "required": [
        "list_id",
        "sections"
      ],
      "title": "SectionsResult",
      "type": "object"
    },
    "StructureWarning": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "const": "unsupported_structure",
          "title": "Error Code",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "record_type": {
          "title": "Record Type",
          "type": "string"
        },
        "structure_field": {
          "enum": [
            "ReminderIDs",
            "ReminderIDsAsset",
            "MembershipsOfRemindersInSectionsAsData",
            "SectionIDsOrderingAsData",
            "ResolutionTokenMap",
            "TitleDocument",
            "NotesDocument"
          ],
          "title": "Structure Field",
          "type": "string"
        },
        "structure_reason": {
          "enum": [
            "too_large",
            "invalid_json",
            "invalid_version",
            "unsupported_version",
            "missing_entries",
            "invalid_entries",
            "metadata_unavailable",
            "non_native_record_id"
          ],
          "title": "Structure Reason",
          "type": "string"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "list_id",
        "record_type",
        "structure_field",
        "structure_reason"
      ],
      "title": "StructureWarning",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/SectionsResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `list_reminders`

Reminders · List reminders (read-only).

List current reminders, optionally filtering by exact list_id or parent_id, title query, section and completion. view=tree adds nested subtasks for the returned page; parent_ref is the authoritative parent even when filtered out. Manual list order is preserved; pagination uses limit (1..500) and offset. Priority: 0=none, 9=low (!), 5=medium (!!), 1=high (!!!). A drag handle (≡) changes manual order, not priority. •=pending, ✓=complete, ↳=subtask. Use move_reminder or reorder_reminders with exact IDs to arrange tasks; never add these symbols to titles. structure_warnings identifies lists whose metadata could not be parsed; base tasks remain readable, sort_index=-1 means unknown manual position, and structure writes to those lists must stop.

Workflow: Select exact list/parent/section IDs and page with next_offset. Include completed tasks when preparing reorder/batch operations; use tree only as a display aid for the returned page.
Result interpretation: reminders, total, next_offset and optional tree/legend/structure_warnings. The flat records and parent_ref remain authoritative when a parent is outside the page. Priority, completion and manual order are independent.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string | null; default=null; optional. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.
- parent_id: string | null; default=null; optional. Exact parent reminder ID in the same list. Creation null means top-level; move null preserves parent unless clear_parent=true; reorder null selects top-level siblings; reads null omit the parent filter.
- query: string | null; default=null; optional. Search text; null on optional filters means no text filter.
- include_completed: boolean; default=false; optional. True includes completed tasks. Required when preparing complete reorder/batch structures; false filters them out.
- limit: integer; default=100; minimum=1; maximum=500; optional. Maximum results for this page, 1..500.
- offset: integer; default=0; minimum=0; optional. Zero-based nonnegative pagination offset. See tool-specific bounds; advance only using returned coverage/pagination information.
- section_id: string | null; default=null; optional. Exact section ID from list_reminder_sections in the same list. Creation null means unsectioned or inherited from parent; move null preserves section unless clear_section=true; reorder null selects unsectioned siblings; reads null omit this filter.
- view: string; enum=["flat", "tree"]; default="flat"; optional. flat returns the flat page; tree additionally nests only subtasks present on that page. parent_ref remains authoritative if a parent is outside the page.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "PageResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/ReminderPage"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "PageResponse",
      "type": "object"
    },
    "Reminder": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "title": {
          "title": "Title",
          "type": "string"
        },
        "completed": {
          "title": "Completed",
          "type": "boolean"
        },
        "priority": {
          "description": "0=none, 9=low, 5=medium, 1=high; independent of manual order.",
          "title": "Priority",
          "type": "integer"
        },
        "list_name": {
          "title": "List Name",
          "type": "string"
        },
        "list_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Ref"
        },
        "completion_date": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Completion Date"
        },
        "due": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Due"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "parent_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Parent Ref"
        },
        "modified_ts": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Modified Ts"
        },
        "assignee_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Assignee Id"
        },
        "section_ref": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Section Ref"
        },
        "section_name": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Section Name"
        },
        "sort_index": {
          "anyOf": [
            {
              "minimum": -1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Native list position; -1 when unavailable, gaps after filtering are normal.",
          "title": "Sort Index"
        },
        "depth": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Depth"
        }
      },
      "required": [
        "id",
        "title",
        "completed",
        "priority",
        "list_name"
      ],
      "title": "Reminder",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "ReminderPage": {
      "additionalProperties": true,
      "properties": {
        "structure_warnings": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/StructureWarning"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Warnings"
        },
        "reminders": {
          "items": {
            "$ref": "#/$defs/Reminder"
          },
          "title": "Reminders",
          "type": "array"
        },
        "total": {
          "minimum": 0,
          "title": "Total",
          "type": "integer"
        },
        "next_offset": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Next Offset"
        },
        "tree": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/ReminderTree"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Tree"
        },
        "legend": {
          "anyOf": [
            {
              "additionalProperties": {
                "type": "string"
              },
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Legend"
        }
      },
      "required": [
        "reminders",
        "total"
      ],
      "title": "ReminderPage",
      "type": "object"
    },
    "ReminderTree": {
      "additionalProperties": true,
      "properties": {
        "reminder": {
          "$ref": "#/$defs/Reminder"
        },
        "subtasks": {
          "items": {
            "$ref": "#/$defs/ReminderTree"
          },
          "title": "Subtasks",
          "type": "array"
        }
      },
      "required": [
        "reminder",
        "subtasks"
      ],
      "title": "ReminderTree",
      "type": "object"
    },
    "StructureWarning": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "const": "unsupported_structure",
          "title": "Error Code",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "record_type": {
          "title": "Record Type",
          "type": "string"
        },
        "structure_field": {
          "enum": [
            "ReminderIDs",
            "ReminderIDsAsset",
            "MembershipsOfRemindersInSectionsAsData",
            "SectionIDsOrderingAsData",
            "ResolutionTokenMap",
            "TitleDocument",
            "NotesDocument"
          ],
          "title": "Structure Field",
          "type": "string"
        },
        "structure_reason": {
          "enum": [
            "too_large",
            "invalid_json",
            "invalid_version",
            "unsupported_version",
            "missing_entries",
            "invalid_entries",
            "metadata_unavailable",
            "non_native_record_id"
          ],
          "title": "Structure Reason",
          "type": "string"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "list_id",
        "record_type",
        "structure_field",
        "structure_reason"
      ],
      "title": "StructureWarning",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/PageResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `move_reminder`

Reminders · Move reminder (write, destructive).

Arrange an existing reminder within its current list. Set parent_id to indent under another reminder, or clear_parent=true to make it top-level. Set section_id to move into a native section, or clear_section=true to move out; subtasks inherit the parent's section. Omitted parent/section stays unchanged. Use exactly one before_id or after_id to place beside a sibling; without an anchor append to the target sibling group. The reminder's subtree stays together. IDs must come from the same list; cycles are rejected. order_verification=verified confirms a fresh iCloud read-back of the requested manual order. Inspect uncertain writes before retrying.

Workflow: Read list/parent/section structure first. Move within the same list; use explicit clear flags for detaching and at most one sibling anchor. The subtree moves together and cycles are rejected.
Result interpretation: id and status=moved; order_verification=verified when the backend freshly confirms manual order. Absence of that optional field on older backends is not verified order. Preserve any uncertain write diagnostics and inspect before retrying.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.
- parent_id: string | null; default=null; optional. Exact parent reminder ID in the same list. Creation null means top-level; move null preserves parent unless clear_parent=true; reorder null selects top-level siblings; reads null omit the parent filter.
- clear_parent: boolean; default=false; optional. True moves to top level; mutually exclusive with parent_id. False/omission preserves parent when parent_id is omitted.
- section_id: string | null; default=null; optional. Exact section ID from list_reminder_sections in the same list. Creation null means unsectioned or inherited from parent; move null preserves section unless clear_section=true; reorder null selects unsectioned siblings; reads null omit this filter.
- clear_section: boolean; default=false; optional. True removes section membership; mutually exclusive with section_id. False/omission preserves membership when section_id is omitted.
- before_id: string | null; default=null; optional. Exact sibling ID in the target group to insert before; mutually exclusive with after_id. Without either anchor append to the target group.
- after_id: string | null; default=null; optional. Exact sibling ID in the target group to insert after; mutually exclusive with before_id.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "MoveResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/MoveResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "MoveResponse",
      "type": "object"
    },
    "MoveResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "const": "moved",
          "title": "Status",
          "type": "string"
        },
        "order_verification": {
          "anyOf": [
            {
              "const": "verified",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Fresh iCloud metadata confirms the requested manual order; optional for older backends.",
          "title": "Order Verification"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "MoveResult",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/MoveResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `reorder_reminders`

Reminders · Reorder reminders (write, destructive).

Set the manual order of all siblings in one list, parent or section using reminder_ids in the desired order. Supply every sibling exactly once, including completed reminders (discover with include_completed=true). Omit parent_id for top-level reminders; omit section_id for the unsectioned group. Each subtree stays together. This changes manual order only; priority and completion stay unchanged. order_verification=verified confirms a fresh iCloud read-back of the requested manual order. Inspect uncertain writes before retrying.

Workflow: Read the entire target sibling group including completed tasks, then provide every sibling ID exactly once in desired order. This changes manual order, not priority/completion or section membership.
Result interpretation: id and status=reordered or unchanged, with optional order_verification. Only order_verification=verified confirms fresh order readback; an older response without it does not prove verification.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- list_id: string; required. Exact list ID from list_reminder_lists. Null on list_reminders means all available lists; writes require an existing writable list.
- reminder_ids: array<string>; required. Array of every sibling ID exactly once in desired manual order, including completed reminders. All IDs must belong to the selected list/parent/section group.
- parent_id: string | null; default=null; optional. Exact parent reminder ID in the same list. Creation null means top-level; move null preserves parent unless clear_parent=true; reorder null selects top-level siblings; reads null omit the parent filter.
- section_id: string | null; default=null; optional. Exact section ID from list_reminder_sections in the same list. Creation null means unsectioned or inherited from parent; move null preserves section unless clear_section=true; reorder null selects unsectioned siblings; reads null omit this filter.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "ReorderResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/ReorderResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "ReorderResponse",
      "type": "object"
    },
    "ReorderResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "enum": [
            "reordered",
            "unchanged"
          ],
          "title": "Status",
          "type": "string"
        },
        "order_verification": {
          "anyOf": [
            {
              "const": "verified",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Fresh iCloud metadata confirms the requested manual order; optional for older backends.",
          "title": "Order Verification"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "ReorderResult",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/ReorderResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `sync_reminders`

Reminders · Sync reminders (read-only).

Refresh the Go Reminders cache; full=true performs a full sync, which can take several minutes. This does not change iCloud data.

Workflow: Request synchronization when a cache refresh is needed; choose incremental by default, full only for a complete refresh. This is separate from account login and access approval.
Result interpretation: Safe list/reminder counts and optional structure_warnings. Counts describe the synchronization result, not successful mutation of task contents; a full sync can take longer than the call deadline.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- full: boolean; default=false; optional. True requests full Reminders synchronization; false requests incremental synchronization. Does not perform account login/device approval.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "StructureWarning": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "const": "unsupported_structure",
          "title": "Error Code",
          "type": "string"
        },
        "list_id": {
          "title": "List Id",
          "type": "string"
        },
        "record_type": {
          "title": "Record Type",
          "type": "string"
        },
        "structure_field": {
          "enum": [
            "ReminderIDs",
            "ReminderIDsAsset",
            "MembershipsOfRemindersInSectionsAsData",
            "SectionIDsOrderingAsData",
            "ResolutionTokenMap",
            "TitleDocument",
            "NotesDocument"
          ],
          "title": "Structure Field",
          "type": "string"
        },
        "structure_reason": {
          "enum": [
            "too_large",
            "invalid_json",
            "invalid_version",
            "unsupported_version",
            "missing_entries",
            "invalid_entries",
            "metadata_unavailable",
            "non_native_record_id"
          ],
          "title": "Structure Reason",
          "type": "string"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "list_id",
        "record_type",
        "structure_field",
        "structure_reason"
      ],
      "title": "StructureWarning",
      "type": "object"
    },
    "SyncResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/SyncResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "SyncResponse",
      "type": "object"
    },
    "SyncResult": {
      "additionalProperties": true,
      "properties": {
        "structure_warnings": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/StructureWarning"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Warnings"
        },
        "reminders": {
          "minimum": 0,
          "title": "Reminders",
          "type": "integer"
        },
        "lists": {
          "minimum": 0,
          "title": "Lists",
          "type": "integer"
        }
      },
      "required": [
        "reminders",
        "lists"
      ],
      "title": "SyncResult",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/SyncResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>

## `update_reminder`

Reminders · Update reminder (write, destructive).

Update specified nonempty reminder fields by exact ID. priority=none clears priority. Clearing notes or due dates is unsupported. Inspect an uncertain write before retrying.

Workflow: Read the reminder and submit only supported changed nonempty fields. Use move_reminder for parent/section/order and assign_reminder for assignment; this tool does not change completion.
Result interpretation: id and status=updated, with optional write_status. Updating due/notes cannot clear them; priority=none clears priority. A successful field update is not evidence of a structure or assignee change.
Failures and recovery: Errors expose error_code, retry_class and available write_status/structure diagnostics. Preserve confirmed native results and IDs; a write_status=unknown is not failure to write. Inspect before retrying. structure_warnings can block structural writes; an outage does not authorize creating replacement tasks or invoking account approval. Treat MCP isError=true as an error even when confirmed partial write information is present. Every error exposes error.code, service, request_operation, request_id, phase, overall_write_status, confirmed_steps, uncertain_step, retry_class, inspect_before_retry and automatic_retry_allowed=false. Native error fields remain preserved: error.write_status/operation can describe a failed sub-step, while overall_write_status describes the complete call. Preserve original IDs and native content. Successful replies are checked against outputSchema; a malformed reply becomes backend_protocol_error without erasing confirmed writes. Report only facts supported by the returned fields; omitted or unknown values are not confirmation.

Parameters (JSON; use exact names and enum values; no unknown fields):
- id: string; required. Exact reminder ID returned by Reminders tools; not a title, list ID or Contacts ID.
- title: string | null; default=null; optional. Title text; nonblank when creating. On updates null/omission preserves the existing title.
- due: string | null; default=null; optional. Due date YYYY-MM-DD. Null/omission leaves an existing due date unchanged or creates without a due date; clearing is unsupported.
- priority: string; enum=["none", "low", "medium", "high"] | null; default=null; optional. Exact string none, low, medium or high, mapped to native 0, 9, 5, 1. Null preserves existing priority or uses backend creation default. none explicitly clears priority; independent of manual order.
- notes: string | null; default=null; optional. Reminder notes. Null/omission preserves existing notes or creates without notes; clearing existing notes with an empty string is unsupported.

<details>
<summary>Response JSON Schema</summary>

```json
{
  "$defs": {
    "ErrorInfo": {
      "additionalProperties": true,
      "properties": {
        "code": {
          "enum": [
            "access_denied",
            "access_required",
            "addressbook_required",
            "auth_required",
            "authentication_failed",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "confirmation_required",
            "conflict",
            "coverage_incomplete",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "lookup_incomplete",
            "mailbox_unavailable",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "protocol_error",
            "read_only",
            "request_timeout",
            "response_too_large",
            "service_error",
            "snapshot_expired",
            "timeout",
            "too_large",
            "unknown_tool",
            "unsafe_target",
            "unsupported_backend",
            "unsupported_item",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "version_changed",
            "write_failed",
            "write_result_unknown",
            "write_uncertain",
            "write_verification_failed"
          ],
          "title": "Code",
          "type": "string"
        },
        "message": {
          "title": "Message",
          "type": "string"
        },
        "service": {
          "enum": [
            "calendar",
            "mail",
            "contacts",
            "drive",
            "reminders",
            "unknown"
          ],
          "title": "Service",
          "type": "string"
        },
        "operation": {
          "title": "Operation",
          "type": "string"
        },
        "request_operation": {
          "description": "Exact tool originally called; a preserved native operation may identify its failed sub-step.",
          "title": "Request Operation",
          "type": "string"
        },
        "request_id": {
          "title": "Request Id",
          "type": "string"
        },
        "phase": {
          "description": "Application-owned phase or write step; never raw exception text.",
          "title": "Phase",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Affected write step where the native backend supplies it, otherwise the overall operation. null for reads; unknown never means no change.",
          "title": "Write Status"
        },
        "overall_write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "partial",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "Overall request status; partial means earlier steps succeeded even if the affected step was not sent or rejected.",
          "title": "Overall Write Status"
        },
        "confirmed_steps": {
          "items": {
            "type": "string"
          },
          "title": "Confirmed Steps",
          "type": "array"
        },
        "uncertain_step": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Uncertain Step"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "description": "Whether a manual retry can be considered after the stated prerequisites; never automatic authorization.",
          "title": "Retryable",
          "type": "boolean"
        },
        "inspect_before_retry": {
          "title": "Inspect Before Retry",
          "type": "boolean"
        },
        "automatic_retry_allowed": {
          "const": false,
          "default": false,
          "title": "Automatic Retry Allowed",
          "type": "boolean"
        },
        "invalid_parameters": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/InvalidParameter"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Invalid Parameters"
        }
      },
      "required": [
        "code",
        "message",
        "service",
        "operation",
        "request_operation",
        "request_id",
        "phase",
        "write_status",
        "overall_write_status",
        "confirmed_steps",
        "uncertain_step",
        "retry_class",
        "retryable",
        "inspect_before_retry"
      ],
      "title": "ErrorInfo",
      "type": "object"
    },
    "ErrorPayload": {
      "additionalProperties": true,
      "properties": {
        "error": {
          "$ref": "#/$defs/ErrorInfo"
        }
      },
      "required": [
        "error"
      ],
      "title": "ErrorPayload",
      "type": "object"
    },
    "InvalidParameter": {
      "additionalProperties": false,
      "properties": {
        "parameter": {
          "title": "Parameter",
          "type": "string"
        },
        "expected": {
          "title": "Expected",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "parameter",
        "expected",
        "description"
      ],
      "title": "InvalidParameter",
      "type": "object"
    },
    "ReminderError": {
      "additionalProperties": true,
      "properties": {
        "error_code": {
          "description": "Application-owned error code; never raw upstream exception text.",
          "enum": [
            "auth_required",
            "backend_auth_failed",
            "backend_protocol_error",
            "backend_unavailable",
            "backend_upgrade_required",
            "icloud_access_denied",
            "icloud_request_failed",
            "icloud_write_failed",
            "idempotency_conflict",
            "invalid_argument",
            "local_state_failed",
            "not_configured",
            "not_found",
            "not_shared",
            "permission_denied",
            "request_timeout",
            "unsupported_backend",
            "unsupported_structure",
            "unsupported_text_document",
            "upstream_mismatch",
            "write_result_unknown",
            "write_verification_failed"
          ],
          "title": "Error Code",
          "type": "string"
        },
        "retry_class": {
          "enum": [
            "retryable_safe",
            "retryable_after_read",
            "not_retryable"
          ],
          "title": "Retry Class",
          "type": "string"
        },
        "retryable": {
          "title": "Retryable",
          "type": "boolean"
        },
        "operation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operation"
        },
        "request_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Request Id"
        },
        "write_status": {
          "anyOf": [
            {
              "enum": [
                "not_sent",
                "failed",
                "succeeded",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Write Status"
        },
        "http_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Http Status"
        },
        "upstream_status": {
          "anyOf": [
            {
              "maximum": 599,
              "minimum": 100,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Status"
        },
        "upstream_error_code": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Upstream Error Code"
        },
        "order_verification": {
          "anyOf": [
            {
              "enum": [
                "mismatch",
                "unavailable"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Order Verification"
        },
        "list_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "List Id"
        },
        "record_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Record Type"
        },
        "structure_field": {
          "anyOf": [
            {
              "enum": [
                "ReminderIDs",
                "ReminderIDsAsset",
                "MembershipsOfRemindersInSectionsAsData",
                "SectionIDsOrderingAsData",
                "ResolutionTokenMap",
                "TitleDocument",
                "NotesDocument"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Field"
        },
        "structure_reason": {
          "anyOf": [
            {
              "enum": [
                "too_large",
                "invalid_json",
                "invalid_version",
                "unsupported_version",
                "missing_entries",
                "invalid_entries",
                "metadata_unavailable",
                "non_native_record_id"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Reason"
        },
        "structure_version": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Structure Version"
        }
      },
      "required": [
        "error_code",
        "retry_class",
        "retryable"
      ],
      "title": "ReminderError",
      "type": "object"
    },
    "UpdateResponse": {
      "anyOf": [
        {
          "$ref": "#/$defs/UpdateResult"
        },
        {
          "$ref": "#/$defs/ReminderError"
        }
      ],
      "title": "UpdateResponse",
      "type": "object"
    },
    "UpdateResult": {
      "additionalProperties": true,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "write_status": {
          "anyOf": [
            {
              "const": "succeeded",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Present on the combined backend; absent on older backends.",
          "title": "Write Status"
        },
        "status": {
          "const": "updated",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "status"
      ],
      "title": "UpdateResult",
      "type": "object"
    }
  },
  "anyOf": [
    {
      "$ref": "#/$defs/UpdateResponse"
    },
    {
      "$ref": "#/$defs/ErrorPayload"
    }
  ],
  "type": "object"
}
```

</details>
