# IcloudCruncher

Python proxy for shared iCloud calendars plus a read/write MCP server for iCloud
Calendar and iCloud Mail. The MCP integration is exposed over Streamable HTTP at
`/mcp`.

Calendar uses CalDAV; Mail uses IMAP over SSL. Contacts, Notes, Reminders, Files,
and SMTP mail sending are out of scope.

## Local Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Create local config:

   ```bash
   cp config.example.yaml config.yaml
   ```

3. Edit `config.yaml` and add your shared iCloud `webcal://` URLs.

4. Run locally:

   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
   ```

5. Test a configured token:

   ```bash
   curl -i http://127.0.0.1:8080/11111111-1111-4111-8111-111111111111
   ```

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
- `list_events` — read events by calendar, date range, text query, and limit.
- `get_event` — read one event by UID.
- `create_event` — create a timed or all-day event.
- `update_event` — update only supplied event fields.
- `delete_event` — delete an event; it requires `confirm=true` and should also
  be protected by the client's MCP approval flow.
- `list_mailboxes` — list IMAP mailboxes.
- `search_emails` — search by sender, recipient, subject, text, dates, or unread status.
- `get_email` — read one message by its mailbox-local UID without marking it read. Bodies
  are bounded; attachments are returned as metadata only.
- `create_draft` — upload a plain-text or HTML draft, optionally with base64-encoded
  attachments. It never sends the message.
- `update_draft` — replace an existing draft with new content and optional attachments.
  It never sends the message.
- `mark_email_read` — set or clear the `\Seen` flag.
- `move_email` — copy a message to another mailbox and mark the source for deletion.
- `delete_email` — delete a message; it requires `confirm=true` and may leave a safe
  deletion marker when the server cannot isolate an IMAP expunge.

IMAP operations use mailbox-local UIDs, so callers should use the UID together with the
mailbox returned by `search_emails`. Drafts default to the `Drafts` mailbox and can be
redirected with `IMAP_DRAFTS_MAILBOX` or the tool's `mailbox` argument. Attachments are
passed as objects with `filename`, `content_type`, and `content_base64`. IMAP sending is
intentionally not implemented; send the uploaded draft manually from a mail client.

The IMAP read cache keeps up to the 1,000 newest message headers per mailbox from the
last 100 days in the same persistent SQLite volume as the calendar cache. It refreshes
every 300 seconds by default. Search filters for sender, recipient, subject, dates, and
unread status can use the cache; free-text searches and `get_email` still query iCloud
because they may require message bodies. Bodies and attachments are not stored in the
cache. Successful flag, move, and delete operations invalidate the affected mailbox
cache. Set `IMAP_EMAIL_CACHE_TTL_SECONDS=0` to disable it.

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

## Configuration

`config.yaml` is intentionally ignored by git because shared calendar URLs and
iCloud credentials are secrets.

```yaml
calendars:
  - token: "11111111-1111-4111-8111-111111111111"
    source_url: "webcal://p106-caldav.icloud.com/published/2/..."
```

If `token` is omitted, the app generates a temporary UUID4 at startup and logs it. Add that token to `config.yaml` if the public URL must survive restarts.

You can also configure calendars via environment variables. The numeric part groups one calendar:

```bash
ICLOUDCRUNCHER.0.token="your-secret-token"
ICLOUDCRUNCHER.0.URL="webcal://p106-caldav.icloud.com/published/2/..."
ICLOUDCRUNCHER.1.token="another-secret-token"
ICLOUDCRUNCHER.1.URL="webcal://p106-caldav.icloud.com/published/2/..."
```

YAML and environment calendars are combined. Set `ICLOUDCRUNCHER.BASE_URL` if startup logs should show full external URLs instead of only `/<token>`.

Calendar responses are cached in memory for 300 seconds by default. Override with `ICLOUDCRUNCHER.CACHE_TTL_SECONDS`. Set it to `0` to disable fresh cache hits while still keeping the last successful response as an upstream-error fallback.

The MCP cache can be tuned independently with `ICLOUD_CACHE_TTL_SECONDS` for
events, `ICLOUD_CALENDARS_CACHE_TTL_SECONDS` for calendar lists, and
`ICLOUD_CACHE_PATH` for the SQLite file path. Set either TTL to `0` to disable
fresh hits for that data type.

Because dots are not valid in normal shell variable assignment, use one of these forms for env-only local testing:

```bash
env \
  'ICLOUDCRUNCHER.0.token=first-token' \
  'ICLOUDCRUNCHER.0.URL=webcal://p106-caldav.icloud.com/published/2/...' \
  'ICLOUDCRUNCHER.1.token=second-token' \
  'ICLOUDCRUNCHER.1.URL=webcal://p106-caldav.icloud.com/published/2/...' \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

For Docker Compose, put the numbered keys under `environment` as quoted YAML keys.

## Docker

```bash
cp .env.example .env
cp config.example.yaml config.yaml
${EDITOR:-vi} .env
docker compose up --build
```

The Compose file starts two containers:

- `icloud-cruncher` serves the MCP endpoint and the legacy shared-calendar
  proxy. Its port is bound to loopback only.
- `openai-tunnel` runs OpenAI's outbound-only Secure MCP Tunnel client and
  forwards tunnel traffic to `http://icloud-cruncher:8080/mcp`.

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

Use `docker compose build` only after code, dependency, or Dockerfile changes. For changes in `config.yaml` or Compose environment values, use `docker compose up` to recreate the container without rebuilding the image. If only `config.yaml` changed and the service is already running, `docker compose restart icloud-cruncher` is enough because the app reads config at startup.

## Endpoints

- `GET /<token>` forwards the matching calendar as `text/calendar`.
- `GET /healthz` returns `{"status":"ok"}`. The Docker health check probes this
  endpoint, so `docker compose ps` shows whether the MCP container is healthy.
  It intentionally checks only the local application and does not contact iCloud
  or IMAP on every probe; external connectivity is verified when the tools are
  used.
- `POST/GET/DELETE /mcp` and `/mcp/` serve the Streamable HTTP MCP transport.

There is no calendar listing endpoint. Unknown tokens return a neutral `404`.

## Logging

The app uses `loguru` and logs incoming requests plus upstream iCloud fetch results. Upstream logs include token, status, duration, content type, and response size, but not the configured iCloud source URL. Every MCP call logs `mcp_tool_start` and `mcp_tool_complete` with the tool name, outcome, duration, and (where applicable) result count. Cache logs identify read hits/misses/bypasses, refresh writes, and invalidations with counts; they never log event contents, email headers, message bodies, or credentials.

At startup, the app logs every URL path it answers. With `ICLOUDCRUNCHER.BASE_URL=https://calendar.example.com`, it logs full external URLs.
Cache logs include `cache_hit` for fresh public-calendar responses, `public_calendar_cache action=write` for refreshed public feeds, and `cache_stale_fallback` when iCloud is unavailable but a previous response can still be served. Calendar MCP cache logs use `icloud_cache tool=<name> action=<read|write|invalidate>`, and IMAP cache logs use `imap_cache tool=<name> action=<read|write|invalidate>`.

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
