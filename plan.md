# IcloudCruncher Plan

## Goal
- Provide a read/write MCP server for iCloud Calendar events through authenticated CalDAV.
- Provide iCloud Mail read/write tools through authenticated IMAP over SSL.
- Integrate optional iCloud Reminders through a separate private Go MCP backend.
- Run the MCP server privately in Docker and connect it to OpenAI products with Secure MCP Tunnel.
- Shared-calendar forwarding remains in its standalone project and is out of scope here.

## Stack
- Python with FastAPI.
- `caldav` for iCloud Calendar CalDAV access.
- Python's standard-library `imaplib` for iCloud Mail IMAP access.
- MCP Python SDK with Streamable HTTP at `/mcp`.
- Dependency and lockfile management with `uv`.
- Environment configuration with optional YAML for CalDAV and IMAP account settings.
- Docker deployment on internal port `8080`; TLS is handled by an external reverse proxy.

## Behavior
- Load account credentials from environment variables or optional `config.yaml`.
- Provide `GET /healthz` for local and container health checks.
- Provide MCP tools for listing calendars, listing/getting events, creating events, updating events, and deleting events.
- Require explicit `scope=occurrence|series` and `confirm=true` for event deletion.
- Provide mailbox/search/read/flag/move/delete tools for iCloud Mail; IMAP does not send mail, so SMTP is out of scope.
- Provide optional Reminders tools through Python's existing MCP endpoint; deletion requires `confirm=true`.
- Keep Apple Account and OpenAI tunnel credentials out of tool results and logs.
- Keep the MCP service bound to the private Docker network; tunnel-client provides outbound-only OpenAI connectivity.

## Local Testing
- Use `uv sync` to install dependencies.
- Copy `config.example.yaml` to `config.yaml` and add account credentials locally, or export the equivalent environment variables.
- Run locally with `uv run uvicorn app.main:app --host 127.0.0.1 --port 8080`.
- Check health via `curl -i http://127.0.0.1:8080/healthz` and run `uv run pytest`.

## Deliverables
- FastAPI application under `app/`.
- `pyproject.toml` and `uv.lock`.
- `Dockerfile` and `docker-compose.yml`.
- `.vscode/tasks.json` for local and Docker runs.
- `.gitignore`, `config.example.yaml`, `README.md`, and updated `AGENTS.md`.
- `.env.example` and a Compose `openai-tunnel` service.
