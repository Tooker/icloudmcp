# IcloudCruncher

Read/write MCP server for iCloud Calendar, iCloud Mail and optional iCloud
Reminders. The MCP integration is exposed over Streamable HTTP at `/mcp`.

Calendar uses CalDAV; Mail uses IMAP over SSL. Reminders uses a separate Go MCP
backend on the private Docker network. Contacts, Notes, Files and SMTP mail
sending are out of scope.

## Local Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Create local account config:

   ```bash
   cp config.example.yaml config.yaml
   ```

3. Edit the `icloud` block in `config.yaml` with your Apple Account email and
   app-specific password. Mail reuses these credentials by default.

4. Run locally:

   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
   ```

5. Check the application health:

   ```bash
   curl -i http://127.0.0.1:8080/healthz
   ```

`config.yaml` is optional. You can instead export the `ICLOUD_*` and `IMAP_*`
environment variables described below. Docker Compose reads them from `.env`.

## Read/write iCloud MCP

Use an Apple Account email address and an app-specific password. Do not put the
primary Apple Account password into this service. Apple requires two-factor
authentication to create an app-specific password.

Add the credentials either to the `icloud` block in `config.yaml` or, preferably
for Docker, to `.env`:

```dotenv
ICLOUD_USERNAME=your-apple-id@example.com
ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
ICLOUD_DEFAULT_CALENDAR=Work
ICLOUD_TIMEZONE=Europe/Berlin

# Optional: override the shared credentials or mailbox settings for IMAP.
IMAP_USERNAME=your-apple-id@example.com
IMAP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
IMAP_HOST=imap.mail.me.com
IMAP_PORT=993
IMAP_DEFAULT_MAILBOX=INBOX
IMAP_DRAFTS_MAILBOX=Drafts
IMAP_EMAIL_CACHE_TTL_SECONDS=300
IMAP_EMAIL_CACHE_DAYS=100
IMAP_EMAIL_CACHE_MAX_MESSAGES=1000
```

The MCP server provides:

- `list_calendars` — list calendar names and opaque CalDAV ids.
- `list_events` — read individual occurrences by calendar, date range, text query,
  and limit, with their actual start/end times and original recurrence IDs.
- `get_event` — read one event by UID.
- `create_event` — create a timed or all-day event.
- `update_event` — update only supplied event fields.
- `delete_event` — delete one occurrence or a whole event/series; explicit `scope`
  and `confirm=true` are required, in addition to the client's MCP approval flow.
- `list_mailboxes` — list IMAP mailboxes.
- `search_emails` — search by sender, recipient, subject, text, dates, or unread status.
- `semantic_search_emails` — search cached mail bodies and PDF/text attachments by meaning,
  returning excerpts plus safe references to their original mail and attachment.
- `email_search_index_status` — inspect indexing progress and omitted/truncated counts.
- `get_email` — read one message by its mailbox-local UID without marking it read. Bodies
  are bounded; attachments include metadata and an `attachment_id` for reading their contents.
- `get_email_attachment` — return the complete original attachment as a native binary
  MCP resource by default, including a resource link with filename, MIME type, and size.
  Also supports PDF/text extraction and bounded base64 chunks. Uses the UID, mailbox,
  and `attachment_id` from `get_email` and never marks the message read.
- `create_draft` — upload a plain-text or HTML draft, optionally with base64-encoded
  attachments. It never sends the message.
- `update_draft` — replace an existing draft with new content and optional attachments.
  It never sends the message.
- `mark_email_read` — set or clear the `\Seen` flag.
- `move_email` — copy a message to another mailbox and mark the source for deletion.
- `delete_email` — delete a message; it requires `confirm=true` and may leave a safe
  deletion marker when the server cannot isolate an IMAP expunge.

Calendar date windows include their start and exclude their end. For example,
`list_events(calendar="calendar-id", start="2026-09-30", end="2026-10-01")`
returns occurrences overlapping September 30 in the configured timezone. Each
recurring result includes the series `uid`/`series_uid`, a stable `occurrence_id`,
and `recurrence_id`. Its `start` and `end` describe the actual occurrence; its
`recurrence_id` identifies the original slot, even if it was moved to another day.
`get_event(calendar, uid)` continues to return the series master summary.

To delete only the selected occurrence, copy its `recurrence_id` unchanged:

```json
{
  "calendar": "calendar-id",
  "uid": "series-uid",
  "scope": "occurrence",
  "recurrence_id": "2026-09-30T18:00:00+02:00",
  "confirm": true
}
```

Timed IDs require a full ISO datetime: include an offset for zoned events, or
omit the offset for floating events. All-day IDs use `YYYY-MM-DD`. Equivalent
UTC timestamps are accepted for zoned events. Date-only IDs for timed events,
nonexistent series slots, missing IDs and missing/invalid scopes are rejected.
There is no fallback to deleting the series. To delete a whole event or series,
use `scope="series"` and omit `recurrence_id`. This also applies to nonrecurring
events; callers using the previous UID-only deletion interface must supply scope.

Occurrence deletion adds an `EXDATE` of the same type/timezone as the master
and removes matching single-occurrence overrides from the complete CalDAV resource.
`RANGE=THISANDFUTURE` anchors are retained so later modified occurrences remain
intact. The result explicitly confirms `scope`, `recurrence_id`, `occurrence_date`
(the original slot's date), and `affected_date` (the actual occurrence's date in
the series timezone). Repeating the deletion returns `already_deleted=true` and
does not add duplicate exceptions. Successful writes invalidate calendar caches;
expanded occurrences never replace UID-keyed master summaries in SQLite.

Expansion uses the same
[recurring-ical-events library](https://recurring-ical-events.readthedocs.io/en/v3.8.2/user-guide/examples.html)
as the installed CalDAV client. Exception identities follow
[RFC 5545, section 3.8.4.4](https://www.rfc-editor.org/rfc/rfc5545.html#section-3.8.4.4).

IMAP operations use mailbox-local UIDs, so callers should use the UID together with the
mailbox returned by `search_emails`. Drafts default to the `Drafts` mailbox and can be
redirected with `IMAP_DRAFTS_MAILBOX` or the tool's `mailbox` argument. Attachments are
passed as objects with `filename`, `content_type`, and `content_base64`. IMAP sending is
intentionally not implemented; send the uploaded draft manually from a mail client.

To retrieve a PDF attachment, call `get_email` first, then
`get_email_attachment(uid="42", mailbox="INBOX", attachment_id="1")`. The default
`format="file"` returns the complete file (up to 10 MB) in an `EmbeddedResource` with
`BlobResourceContents.blob` and the original MIME type, plus a `ResourceLink` carrying
the filename and size. File mode requires `offset=0`; `limit` does not truncate files.
The resource URI is private to MCP and contains an opaque random ID. Clients can also
fetch its contents using `resources/read`; no public download endpoint is added.
Resource reads return a snapshot of the issued file, not a subsequent message with a
reused UID. Snapshots are held in memory for up to 15 minutes, bounded by 64 files and
25 MB total; capacity eviction and service restarts may expire links sooner. Request
the file again if its link expires. Files are not exposed through `resources/list`.
Download and preview UI depend on the MCP client.

Use `format="text"` to return extracted PDF/text content in `text`. For long content,
follow `next_offset` while `has_more` is true. `offset` and `limit` count characters in
text mode, or decoded bytes in `format="base64"` mode; the default limit is 20,000 and
the maximum is 100,000. Base64 mode also supports files over the native file limit.
Decode each base64 chunk separately before joining the bytes.
Text extraction accepts files up to 10 MB and bounds PDF page content streams to 5 MB;
larger files remain available as base64. `text_status` and `text_message` explain PDFs
without embedded text, password protection, unsupported formats, or extraction errors.
Scanned PDFs without a text layer require OCR; this service does not run OCR.

The server uses the official Python MCP SDK's `MCPServer`, formerly named `FastMCP`.
Native file results use the SDK's MCP content types directly; the separate `fastmcp`
package is not required for this feature.

Mail searches reuse the header summaries already stored alongside full `.eml`
messages in SQLite, without a 1,000-message coverage limit. IMAP SEARCH still finds
current matches across the whole mailbox; only the selected UIDs are loaded.
Cached headers avoid downloading/parsing headers again. Flags and INTERNALDATE
are refreshed from IMAP, while missing headers are fetched only for those UIDs.
Mail bodies and attachment BLOBs are not read for a header search.

For mailboxes without full-message snapshots, the older header cache keeps up to
the 1,000 newest headers from the last 100 days. It refreshes every 300 seconds
by default and answers searches only when an explicit `since` date falls within
its complete coverage. Other searches run directly on IMAP, so the cache never
hides matching mail. Mailbox listings are cached for 30 minutes by default.
Full `.eml` messages, including message bodies and attachment bytes, are stored in a
separate SQLite BLOB table for 24 hours by default. On startup, a background crawler
walks configured mailboxes from newest to oldest in batches and skips already cached
messages. Large messages above `IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES` are skipped.
Successful flag, move, and delete operations invalidate the affected mailbox headers
and full-message entries. Set `IMAP_EMAIL_CACHE_CRAWL_ENABLED=false` to disable the
background crawler, or set `IMAP_EMAIL_CONTENT_TTL_SECONDS=0` to force full-message
refreshes.
Mailbox UIDVALIDITY is checked before cached searches and message reads. A
changed generation invalidates that mailbox's headers and message content;
messages are never reused when the server's UIDVALIDITY is unavailable.

### Semantic mail and PDF search

Optional semantic search uses **existing, account-scoped `.eml` BLOBs in SQLite**.
It does not perform additional IMAP fetches and does not index calendar entries.
The IMAP crawler fills SQLite independently. SQLite retains originals and cached
vectors; Qdrant is a derived index in its own persistent `qdrant-storage` volume.
Qdrant has no published ports and stores vectors/payloads on disk. No GPU is needed:
OpenAI computes the embeddings from mail headers, body text, and extracted attachment
text. Search queries are also sent to OpenAI. Original PDF/.eml files are not uploaded.

Set these values in the ignored `.env`:

```dotenv
MAIL_SEARCH_ENABLED=true
OPENAI_API_KEY=your-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
MAIL_SEARCH_EMBEDDING_MODE=batch
```

Start Qdrant and recreate the application so it receives the environment:

```bash
docker compose --profile search up -d --build qdrant icloud-cruncher
```

Background indexing uses the [OpenAI Batch API](https://developers.openai.com/api/docs/guides/batch)
by default: JSONL requests are uploaded, submitted with a `24h` completion window,
and polled every `MAIL_SEARCH_POLL_SECONDS` (default 30 seconds). One job is in flight
at a time, containing at most 1000 new, distinct text inputs. Each pass prepares up
to `MAIL_SEARCH_BATCH_SIZE` messages (default 100). Index progress, remote batch ID
and status are available through `email_search_index_status`. Batch processing costs
50% less than the standard endpoint; search queries use the standard endpoint for an
immediate response. Set `MAIL_SEARCH_EMBEDDING_MODE=standard` for immediate background
indexing, with up to 16 text chunks per API request.

Model defaults are 3072 dimensions for `text-embedding-3-large` and 1536 for
`text-embedding-3-small`; `OPENAI_EMBEDDING_DIMENSIONS` may reduce them. Changing the
account, model, dimensions, or extraction version selects a separate collection.
Unchanged inputs reuse persisted embeddings across restarts and rebuilds. Batch IDs
and input mappings survive restarts; reordered results are matched by input hash,
and partial results are retained. Completed input/output/error files are deleted
from OpenAI after ingestion. An ambiguous submission is recovered by its metadata;
if no corresponding remote job can be found, the worker reports `submitting`/retrying
and requires checking Platform before retrying rather than creating duplicate jobs.

`semantic_search_emails(query="bezahlte Heizkostenrechnung", source="attachment")`
returns `matches` with score, excerpt, mailbox, UID, UIDVALIDITY, attachment ID,
filename, and ready-to-use `email`/`attachment` MCP tool arguments. These include
`expected_uid_validity`; `get_email` and `get_email_attachment` reject a reference
after its mailbox's UID generation changes. The attachment reference retrieves the
original file through the existing native MCP resource output.

Search covers cached snapshots, including expired snapshots until invalidated, and
may lag behind iCloud. Successful mail mutations and known generation changes remove
the source from SQLite; old matches are suppressed immediately and Qdrant points are
removed by the worker. Use normal `search_emails` for live IMAP coverage.

Text inputs have a conservative 6500 UTF-8-byte bound with overlapping chunks. A
message contributes at most 64 chunks, 20 attachments, and 100000 characters per
body/attachment; omitted or truncated inputs are counted in index status. Scanned,
encrypted, unsupported or unreadable attachments are skipped; OCR is not included.
Only aggregate counts/statuses are logged, without text, queries, headers or keys.

IMAP uses a small reusable connection pool (4 connections by default) so sequential
requests do not repeat the TLS login/logout roundtrip. Set `IMAP_CONNECTION_POOL_SIZE`
to tune it; use `1` to serialize IMAP operations or `0` is not valid. Crawler batches
and pacing are controlled with `IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE` and
`IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS`.

An opt-in live smoke test is available for diagnosing real mailbox access. It logs no
credentials and checks only login, mailbox listing, and message headers:

```bash
set -a; source .env; set +a
RUN_LIVE_IMAP_TESTS=1 uv run pytest -m live tests/test_live_imap.py -q
```

Normal `uv run pytest` runs only the fake-client tests and skips this live test.

Apple's documented iCloud Mail settings are `imap.mail.me.com` on port `993` with SSL
and an app-specific password. The username may be the full iCloud Mail address or the
address name, depending on the client. See Apple's [iCloud Mail server settings](https://support.apple.com/en-us/102525).

The service listens on `http://127.0.0.1:8080/mcp` locally. The MCP endpoint
does not expose iCloud credentials, source URLs, or raw iCalendar payloads in
tool results.

Read results from iCloud Calendar use a persistent SQLite cache. Calendar lists
are cached for 300 seconds and event results for 60 seconds by default; a
successful create, update, or delete invalidates the event cache. iCloud stays
the source of truth, and the cache stores only normalized calendar/event data,
not credentials. The Docker Compose setup stores the database in the named
`icloud-cache` volume so it survives container restarts.

Persistent cache entries are isolated by protocol, server, and account using
opaque hashed namespaces. Changing an account or server does not reuse another
account's data. Legacy cache entries without an owner are ignored and refreshed.

Implicit event-search bounds use local midnight (30 days before today through
365 days after today), keeping range-cache keys stable between requests. Explicit
timestamps remain exact. A missing/expired result for one calendar does not discard
fresh results for other calendars. SQLite uses WAL so embedding writes can run
alongside cache reads. Unchanged UIDVALIDITY checks do not acquire a writer lock.

Calendar cache polling is enabled by default. The application warms the rolling
default event window at startup and refreshes it every 30 seconds in a background
thread. Successful event-list requests also register up to eight recent unfiltered
calendar/time windows; they remain active for one hour after their last use. Query
text and result limits do not restrict the cached data. Recent windows are kept in
memory; the default window is warmed again after a restart.

Set `ICLOUD_CACHE_REFRESH_ENABLED=false` to disable polling or
`ICLOUD_CACHE_REFRESH_INTERVAL_SECONDS` to adjust it. The effective interval is
capped at half the event-cache TTL; TTL 0 disables polling. Cached results remain
subject to the normal TTL. New windows, polling failures or slow refreshes can
therefore require a foreground iCloud request. Failures preserve previous snapshots
and retry with backoff. Successful writes immediately invalidate event entries;
an older refresh in flight cannot republish them after invalidation. The poller
stops with the application and logs only safe counts, durations and error classes.

## Configuration

Credentials can be supplied through environment variables or an optional
`config.yaml`. Environment variables take precedence. Both `.env` and
`config.yaml` are ignored by git because iCloud credentials are secrets.

```yaml
icloud:
  username: "your-apple-id@example.com"
  app_specific_password: "xxxx-xxxx-xxxx-xxxx"
  default_calendar: null
  timezone: "Europe/Berlin"
imap:
  host: "imap.mail.me.com"
  port: 993
  default_mailbox: "INBOX"
```

See `config.example.yaml` for all account options. Set `ICLOUD_CRUNCHER_CONFIG`
to use a different file path. Docker Compose uses `.env` without a config-file
mount. To use YAML in Docker, add this to `docker-compose.override.yml`:

```yaml
services:
  icloud-cruncher:
    volumes:
      - ./config.yaml:/app/config.yaml:ro
```

The MCP cache can be tuned with `ICLOUD_CACHE_TTL_SECONDS` for
events, `ICLOUD_CALENDARS_CACHE_TTL_SECONDS` for calendar lists, and
`ICLOUD_CACHE_PATH` for the SQLite file path. Set either TTL to `0` to disable
fresh hits for that data type.

## Go Reminders integration

Python remains the single MCP endpoint at `/mcp` and `/mcp/`. Its ten typed
Reminders tools call the separate Go backend over MCP Streamable HTTP at
`http://reminders:8080/mcp`. Calendar, Mail and attachment resources continue to
use the existing Python services. The tunnel still connects only to Python.

The optional `reminders` Compose service builds directly from
[Tooker/icloud-reminders-cli](https://github.com/Tooker/icloud-reminders-cli),
pinned to commit `f4d480349fa6a15d651e2c38444a40811c2d9233`. No Go source is
copied into this repository and no second checkout or submodule is required.
To upgrade, review a new Go commit and update the pinned build context. For
local development, `REMINDERS_BUILD_CONTEXT=../icloud-reminders-cli` builds
your adjacent checkout instead. Docker supports this through its
[Git build contexts](https://docs.docker.com/build/concepts/context/#git-repositories).

Enable it in your untracked `.env`:

```dotenv
COMPOSE_PROFILES=reminders
REMINDERS_MCP_URL=http://reminders:8080/mcp
REMINDERS_MCP_TOKEN=replace-with-a-private-random-token
REMINDERS_MCP_TIMEOUT_SECONDS=210
```

If semantic search is already enabled, use `COMPOSE_PROFILES=search,reminders`.
The same optional bearer token is passed to Python and Go; it is independent
of Apple credentials. The Go service publishes no host port. Neither calendar
app-specific passwords nor the Go session files are passed through MCP tools.

For a new Reminders account:

```bash
docker compose build reminders icloud-cruncher
docker compose run --rm reminders auth
# With Advanced Data Protection, approve on a trusted device:
docker compose run --rm reminders auth --approve-web-access --approval-timeout 3m
docker compose up -d reminders icloud-cruncher
docker compose ps
```

Go owns its login and cache in the `reminders-data` volume. If you already have
a standalone Go login, stop that server first. You can copy only `session.json`
into the new volume, without exposing its contents or copying the old cache:

```bash
docker compose -f ../icloud-reminders-cli/compose.yaml stop reminders
docker compose run --rm --entrypoint sh \
  -v icloud-reminders-cli_reminders-data:/existing:ro reminders \
  -c 'test ! -e /data/session.json && cp -p /existing/session.json /data/session.json'
docker compose up -d reminders icloud-cruncher
```

Replace the source volume name if the standalone project uses a different
Compose project name. The copy refuses to overwrite an existing account.
Do not run administrative CLI commands while the Go server holds its data
directory lock. Renew login or temporary ADP approval with:

```bash
docker compose stop reminders
docker compose run --rm reminders auth --approve-web-access --approval-timeout 3m
# Use ordinary `auth` instead if the login has expired.
docker compose up -d reminders
```

Python never requests 2FA or device approval. Missing login returns
`auth_required`; blocked private-database access returns `icloud_access_denied`.
Go outages do not stop Python startup, tool discovery, Calendar, Mail or native
attachment resources. A later Reminders call opens a fresh MCP session, so
restarting Go does not require restarting Python. Reads and writes are not
automatically retried; after an uncertain write, inspect current data before
trying again. The default 210-second total bridge deadline allows for Go's
three-minute operation timeout and the connection handshake.

Available tools are `list_reminder_lists`, `list_reminders`, `get_reminder`,
`create_reminder`, `update_reminder`, `complete_reminder`, `delete_reminder`,
`sync_reminders`, `list_reminder_participants` and `assign_reminder`.
They preserve Go's structured results, exact IDs, filters and
pagination. Creation requires an existing list; dates use `YYYY-MM-DD` and
priorities are `none`, `low`, `medium` or `high`. Deletion requires explicit
`confirm=true`. Clearing notes/due dates and creating/deleting lists are not
supported. For details, see the
[Go backend documentation](https://github.com/Tooker/icloud-reminders-cli/blob/f4d480349fa6a15d651e2c38444a40811c2d9233/docs/mcp.md).

For assignments, first call `list_reminder_participants(list_id=...)` for the
reminder's list. It returns accepted collaborators with their exact participant
IDs, available names/contact details, permissions and `is_current_user`.
Call `assign_reminder(id=..., participant_id=...)` to assign or reassign to one
of that list's accepted collaborators with write access, including yourself.
Call `assign_reminder(id=..., clear=true)` to remove the assignment. The two
options are mutually exclusive; names and email addresses are not participant
IDs. Reminder reads include `assignee_id` when assigned.

Private lists return `shared=false` with no participants and reject assignment.
The Go backend refreshes membership and checks the current user's write access
before each assignment. It syncs both owned lists and incoming shared lists,
keeping every read/write in its original CloudKit database and owner zone.
The first sync after upgrading rebuilds the cache to include sharing and
assignment records. Assignment records and the reminder link are written in
one atomic batch; an uncertain write is never automatically retried.

For a local Python process talking to the standalone Go container:

```bash
REMINDERS_MCP_URL=http://127.0.0.1:8081/mcp \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Set `REMINDERS_MCP_TOKEN` to the existing Go token if bearer access is enabled.
To verify the complete Python-to-Go-to-iCloud read path after setup:

```bash
RUN_LIVE_REMINDERS_TESTS=1 uv run pytest tests/test_live_reminders.py -q -s
```

This opt-in smoke test connects to Python's existing endpoint, discovers all
three groups of tools, lists active reminders, reads one item when present,
and checks participant discovery for each list.
It never calls write tools or initiates login/device approval, and reports only
counts. Override the target with `LIVE_REMINDERS_MCP_URL` (default
`http://127.0.0.1:8080/mcp`). Normal tests use a simulated Go MCP endpoint and
skip real account access.

## Docker

```bash
cp .env.example .env
${EDITOR:-vi} .env
docker compose up --build
```

The Compose file starts two containers by default:

- `icloud-cruncher` serves the MCP endpoint. Its port is bound to loopback only.
- `openai-tunnel` runs OpenAI's outbound-only Secure MCP Tunnel client and
  forwards tunnel traffic to `http://icloud-cruncher:8080/mcp`.

The optional `reminders` profile adds the private Go backend described above.

Before starting the tunnel, create a tunnel in [OpenAI Platform tunnel
settings](https://platform.openai.com/settings/organization/tunnels), put its
`tunnel_id` and runtime API key in `.env`, and associate the tunnel with the
target ChatGPT workspace or Platform organization. The tunnel client needs
outbound HTTPS access to `api.openai.com:443`; no inbound port is required.

In ChatGPT developer mode, select **Tunnel** when creating the app and choose
the associated tunnel. With the Responses API, configure the MCP tool with
`tunnel_id`; do not pass the OpenAI-hosted tunnel as `server_url`.

Do not publish port `8080` to the public internet: the MCP endpoint is
write-capable and this example intentionally keeps it on the Docker host's
loopback interface. Use an authenticated, stable HTTPS proxy and an explicit
authorization design if a public endpoint is needed.

Use `docker compose build` after code, dependency, or Dockerfile changes. For
changes in `.env` or Compose environment values, use `docker compose up -d` to
recreate the container without rebuilding the image. If only an optionally
mounted `config.yaml` changed, `docker compose restart icloud-cruncher` is enough
because the app reads it at startup.

## Endpoints

- `GET /healthz` returns `{"status":"ok"}`. The Docker health check probes this
  endpoint, so `docker compose ps` shows whether the MCP container is healthy.
  It intentionally checks only the local application and does not contact iCloud
  or IMAP on every probe; external connectivity is verified when the tools are
  used.
- `POST/GET/DELETE /mcp` and `/mcp/` serve the Streamable HTTP MCP transport.

Other paths return `404`.

## Logging

The app uses `loguru` and logs incoming requests with method, path, status and
duration. Every MCP call logs `mcp_tool_start` and `mcp_tool_complete` with the
tool name, outcome, duration, and (where applicable) result count. Cache logs
identify read hits/misses/bypasses, refresh writes, and invalidations with counts;
they never log event contents, email headers, message bodies, or credentials.

MCP start/completion logs include an opaque `call_id`. Detailed `mcp_phase` logs
share that ID and add `span_id`, `parent_span`, `phase`, `outcome` and `duration_ms`.
This correlates parallel calls and nested steps: worker-queue and cache/pool waits,
TLS/login, UIDVALIDITY checks, IMAP search/fetch, SQLite reads/writes/commit,
MIME/PDF parsing, CalDAV discovery/event searches, and query embedding/Qdrant search.
Durations include child spans; do not add parent and child durations together.
Phase logs never include arguments, queries, result contents or exception messages.
Background workers retain their aggregate progress logs instead of detailed spans.

Calendar MCP cache logs use `icloud_cache tool=<name> action=<read|write|invalidate>`,
and IMAP cache logs use `imap_cache tool=<name> action=<read|write|invalidate>`.

## Useful references

- [Apple app-specific passwords](https://support.apple.com/en-us/102654)
- [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [OpenAI MCP servers guide](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [python-caldav](https://github.com/python-caldav/caldav)

## VS Code

Use `Terminal: Run Task` and choose:

- `app: run local`
- `app: test`
- `docker: compose up`
- `docker: compose build`
- `docker: compose down`
