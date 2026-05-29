# AGENTS.md

## Current Repo Shape
- This directory is a Git repository; the initial MVP files may still be untracked until explicitly committed.
- Python FastAPI app managed with `uv`; dependencies live in `pyproject.toml` and `uv.lock`.
- Runtime entrypoint is `app.main:app`; config loading is in `app/config.py`.
- Local calendar sources belong in `config.yaml`, which is gitignored because shared iCloud calendar URLs are secrets.

## Commands
- Install/sync dependencies: `uv sync`.
- Run tests: `uv run pytest`.
- Run locally: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8080`.
- Validate Docker Compose config: `docker compose config`.
- Build Docker image after code/dependency/Dockerfile changes: `docker compose build`.
- Run with Docker: create `config.yaml` first, then `docker compose up`.
- After changing only `config.yaml`, restart the service with `docker compose restart icloud-cruncher`; no image rebuild is needed.

## Calendar Proxy Behavior
- `webcal://` source URLs are normalized to `https://`; plain `http://` sources are rejected.
- Public calendar URLs are `/<token>` only. Do not add routes or docs that expose calendar names, `ical`, `ics`, or source URL details in paths.
- Missing tokens are allowed but temporary: startup generates a UUID4 and logs a warning to persist it in `config.yaml`.
- Calendars may come from `config.yaml` or env vars shaped as `ICLOUDCRUNCHER.0.token` and `ICLOUDCRUNCHER.0.URL`; YAML and env calendars are combined.
- `ICLOUDCRUNCHER.BASE_URL` is only for startup logs that show answered external URLs.
- Calendar responses use an in-memory TTL cache; default is 300 seconds and can be changed with `ICLOUDCRUNCHER.CACHE_TTL_SECONDS`.
- Unknown tokens must stay neutral `404`; do not add calendar listing endpoints.

## Local Testing Notes
- Use `cp config.example.yaml config.yaml` before running the app manually or via Docker.
- `config.example.yaml` intentionally contains placeholder iCloud URLs only; never paste real shared calendar URLs into committed files.
- VS Code tasks are in `.vscode/tasks.json` for sync, local run, tests, and Docker compose.
