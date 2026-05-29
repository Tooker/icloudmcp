# MVP Plan

## Goal
- Build a stateless Python web application that forwards multiple shared iCloud calendar URLs as hard-to-guess public calendar URLs.
- Keep the output paths opaque: no calendar names, `ical`, `ics`, or calendar-related words in the token path.

## Stack
- Python with FastAPI.
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
