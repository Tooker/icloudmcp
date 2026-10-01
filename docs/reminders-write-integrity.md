# Reminders write integrity fixes

The SmokeTest fixes are merged into the adjacent Go checkout together with native
sections, parent changes and manual ordering. The Python batch-update worktree
is also merged, with safe per-step diagnostics and optional keyed creation.
`docker-compose.release.yml` builds the combined local pair. The historical
`patches/reminders-write-integrity.patch` reproduces the isolated fixes against
`f4d480349fa6a15d651e2c38444a40811c2d9233`; it is not the combined source.

## Findings

`ExtractTitle` previously searched printable runs across the entire decompressed
protobuf. The text field's UTF-8 byte length therefore became a visible prefix
when that length was printable ASCII. Every reported example matches: 36 bytes
produce `$`, 43 produce `+`, 37 produce `%`, 47 produce `/`, and 68 produce `D`.
The patch reads only `outer.document(2).note(3).text(2)`. It validates protobuf
framing, preserves whitespace and single-character text, and bounds decompression.
Notes use the same corrected decoder. A separate decoder cache version forces old
summaries to be rebuilt from iCloud; it does not rewrite existing remote titles.

The initial live test created and deleted its own reminder successfully, but
completion failed and read-back remained incomplete. The old completion writer
sent JSON `true` whereas creation and sync use a numeric `Completed` field. The
patch uses `1` and preserves the existing untyped field-value envelope. An explicit
`INT64` type was tested and rejected by this private iCloud endpoint (HTTP 400);
removing it succeeded and read-back confirmed completion. The fake CloudKit server now rejects a Boolean
instead of silently converting it, so the regression test detects this mismatch.

The Go SDK can wrap `icloud_write_failed` in a tool-error prefix. Previously Python
recognized only the first colon-separated word and collapsed such errors into
`backend_unavailable`. The bridge now accepts known error enums from structured
results and wrapped legacy errors, replacing all upstream text with local messages.
The Go registration uses an explicit success schema with a typed input and `any`
output, so the SDK cannot overwrite a structured error with a zero-value success
object. Real MCP transport tests verify that error metadata survives.

The original persistent failure of deletes on existing account objects has not
been reproduced or attributed to a session, token, rate limit or ID conversion.
Exact CloudKit record names are preserved, including their `Reminder/` prefix;
no destructive operation strips that prefix or uses a partial-ID match at the MCP
boundary. New keyed creations also exercise prefixed record names.

## Error contract

Confirmed mutation results include `write_status=succeeded`.
Error results remain native MCP `isError=true` results. Their `structuredContent`
contains only approved fields:

```json
{
  "error_code": "write_result_unknown",
  "operation": "create_reminder",
  "request_id": "local-correlation-id",
  "write_status": "unknown",
  "retry_class": "retryable_after_read",
  "retryable": true,
  "upstream_status": 504
}
```

- `not_sent`: the failure occurred before mutation dispatch, or validated local
  arguments were rejected. A transient pre-dispatch failure is `retryable_safe`.
- `failed`: a complete record-level response rejected the mutation. This does not
  automatically permit a retry with unchanged input.
- `succeeded`: a confirmed creation may still report failure persisting its local
  request ledger. Recover with its original key.
- `unknown`: transport errors after dispatch, incomplete confirmations, and
  partial record responses require reconciliation. A 5xx response alone never
  proves that a write failed.

`http_status` is the observed Python-to-Go transport status. `upstream_status`
refers to Go-to-iCloud. Only known CloudKit error enums are exposed as
`upstream_error_code`. Request IDs correlate with Python logs. Logs contain
operation, duration, safe counts and classified status only; no titles, notes,
URLs, raw errors, credentials or participant information are added.

Neither the bridge nor backend automatically retries mutations. Reads omit
`write_status`. Legacy backend errors remain conservatively `unknown` where
there is no trustworthy commit evidence.

## Keyed creation

`create_reminder` accepts an optional UUID `client_request_id`. Before sending a
creation, Go durably stores a payload hash and reserved account-scoped record ID
under its existing private data directory. The service serializes reservations
with the account gate. Titles and notes are not stored in this ledger.

A replay with identical arguments returns the original ID and `already_created`.
A pending replay reads that exact record from the original list database/owner
zone. If absent, a caller-initiated repeat uses the same reserved record ID, so it
cannot create a second object. Changed arguments yield `idempotency_conflict`.
A completed ledger entry remains consumed even if the reminder is later deleted.
The journal must be retained with the backend data volume.

The Python bridge validates UUIDs and checks the Go tool schema before forwarding
a keyed creation. An older backend returns `unsupported_backend` / `not_sent`;
it never silently accepts an ineffective key. Unkeyed creations retain their
existing behavior and must be inspected after an uncertain error.

## Integration with concurrent backend work

The combined backend retains every structure field in `CreateInput`, including
`section_id` in the keyed request hash. Organized creates use the reserved record
identity in the atomic reminder/list metadata request. Recovery tests verify the
section, exact title and a single manual-order entry after a lost response.
Incomplete, mixed, duplicate or foreign record confirmations remain unknown.

The Python batch uses the same session and diagnostics implementation as single
calls, with one total deadline. It validates any creation keys and discovers all
required capabilities before writing. Confirmed native results and created IDs
survive a later failure; the failing step's commit evidence stays explicit.

For reproducing these fixes against the pinned baseline, an explicit Compose
overlay builds the upstream source with the local patch and runs its Go tests:

```sh
docker compose -f docker-compose.yml -f docker-compose.reminders-write-fixes.yml config --quiet
docker compose -p icloudmcp-write-verify -f docker-compose.yml -f docker-compose.reminders-write-fixes.yml build reminders icloud-cruncher
```

This overlay pins the historical baseline and excludes the native structure
tools. Use `docker-compose.release.yml` for the combined source. The normal
Compose pin remains the published native-structure 1.1.0 commit; publishing and
pinning the newer combined backend is a separate release step.

## Verification

The backend patch includes exact-title coverage across all byte lengths from
1 through 4096, the reported UTF-8 strings, emoji, punctuation, whitespace,
malformed protobufs and bounded decompression. Its CloudKit integration tests run
100 create/read/update/read/complete/read/delete/read cycles and recover a committed
creation after a lost response across service restart without a second write.

The normal `RUN_LIVE_REMINDERS_TESTS=1` smoke remains read-only. Mutation tests use
a separate explicit opt-in and exact authorized list ID:

```sh
RUN_LIVE_REMINDERS_WRITE_TESTS=1 \
LIVE_REMINDERS_WRITE_LIST_ID=List/EXACT-AUTHORIZED-TEST-LIST-ID \
LIVE_REMINDERS_WRITE_MCP_URL=http://127.0.0.1:18080/mcp \
uv run pytest tests/test_live_reminders_writes.py -q -s
```

The live test uses a unique marker in its own parent title and reminder notes,
mutates only its own objects, and verifies cleanup. It deliberately replays
confirmed keyed creates to check idempotency; uncertain mutations are not
blindly retried. Existing reminders and the old duplicate set are untouched.

Verified on 2026-10-01: 267 Python tests passed, three opt-in live tests skipped
in the default suite; all backend Go tests passed. The separately enabled live
write regression passed all eight complete lifecycles in SmokeTest, including
exact strings, parent/date/priority preservation, keyed replay, completion,
delete read-back and final cleanup. Both patched-backend and Python Compose
images built successfully under the isolated verification project name.
The temporary test containers, network and copied account session/cache were
removed. The normal running Compose services were not restarted by this work.

The default backend deployment still needs the combined reviewed upstream
changes. The local paired build does not publish or activate a new release.

Combined-source verification on 2026-10-01: 307 Python tests passed and three
opt-in live tests skipped; all Go tests passed, including native-section keyed
recovery and 100 write lifecycles. After the final validation-diagnostics change,
55 affected Python tests passed. Both local paired Docker images built. A private
container contract check matched all fourteen Go input schemas and read/write
annotations to Python, discovered the local batch tool, and verified that keyed
create and batch authentication failures remain `not_sent`. No account session
was mounted for that contract check and no live mutations were performed by it.
The contract containers/network were removed; running services were not restarted.
