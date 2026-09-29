# IcloudCruncher Plan

## Goal
- Keep the existing stateless proxy for shared iCloud calendar URLs.
- Add a read/write MCP server for iCloud Calendar events through authenticated CalDAV.
- Run the MCP server privately in Docker and connect it to OpenAI products with Secure MCP Tunnel.
- Keep the output paths opaque: no calendar names, `ical`, `ics`, or calendar-related words in the token path.

## Stack
- Python with FastAPI.
- `caldav` for iCloud Calendar CalDAV access.
- MCP Python SDK with Streamable HTTP at `/mcp`.
- Dependency and lockfile management with `uv`.
- YAML configuration for multiple source calendars.
- Docker deployment on internal port `8080`; TLS is handled by an external reverse proxy.

## Behavior
- Load calendars from `config.yaml`.
- Accept both `webcal://` and `https://` source URLs; normalize `webcal://` to `https://` before fetching.
- Serve each calendar at `GET /<token>` with `text/calendar` content.
- If a calendar has no configured token, generate a temporary `uuid4` at startup and log a warning that it changes after restart.
- Unknown tokens return a neutral `404`.
- Do not expose a calendar listing endpoint.
- Provide `GET /healthz` for local and container health checks.
- Provide MCP tools for listing calendars, listing/getting events, creating events, updating events, and deleting events.
- Require `confirm=true` for destructive event deletion.
- Keep Apple Account and OpenAI tunnel credentials out of tool results and logs.
- Keep the MCP service bound to the private Docker network; tunnel-client provides outbound-only OpenAI connectivity.

## Local Testing
- Use `uv sync` to install dependencies.
- Copy `config.example.yaml` to `config.yaml` and add real iCloud URLs locally.
- Run locally with `uv run uvicorn app.main:app --host 127.0.0.1 --port 8080`.
- Test via `curl -i http://127.0.0.1:8080/<token>`.

## Deliverables
- FastAPI application under `app/`.
- `pyproject.toml` and `uv.lock`.
- `Dockerfile` and `docker-compose.yml`.
- `.vscode/tasks.json` for local and Docker runs.
- `.gitignore`, `config.example.yaml`, `README.md`, and updated `AGENTS.md`.
- `.env.example` and a Compose `openai-tunnel` service.
