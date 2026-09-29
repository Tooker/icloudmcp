# IcloudCruncher

Python proxy for shared iCloud calendars plus a read/write MCP server for iCloud Calendar.
The MCP integration uses CalDAV and is exposed over Streamable HTTP at `/mcp`.

The current write-capable scope is iCloud Calendar events (VEVENT). iCloud Mail,
Contacts, Notes, Files, and Reminders are not exposed by this version.

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
```

The MCP server provides:

- `list_calendars` — list calendar names and opaque CalDAV ids.
- `list_events` — read events by calendar, date range, text query, and limit.
- `get_event` — read one event by UID.
- `create_event` — create a timed or all-day event.
- `update_event` — update only supplied event fields.
- `delete_event` — delete an event; it requires `confirm=true` and should also
  be protected by the client's MCP approval flow.

The service listens on `http://127.0.0.1:8080/mcp` locally. The MCP endpoint
does not expose iCloud credentials, source URLs, or raw iCalendar payloads in
tool results.

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
- `GET /healthz` returns `{"status":"ok"}`.
- `POST/GET/DELETE /mcp` and `/mcp/` serve the Streamable HTTP MCP transport.

There is no calendar listing endpoint. Unknown tokens return a neutral `404`.

## Logging

The app uses `loguru` and logs incoming requests plus upstream iCloud fetch results. Upstream logs include token, status, duration, content type, and response size, but not the configured iCloud source URL.

At startup, the app logs every URL path it answers. With `ICLOUDCRUNCHER.BASE_URL=https://calendar.example.com`, it logs full external URLs.
Cache logs include `cache_hit` for fresh cached responses and `cache_stale_fallback` when iCloud is unavailable but a previous response can still be served.

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
