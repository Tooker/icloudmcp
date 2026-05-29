# IcloudCruncher

Stateless Python proxy for forwarding shared iCloud calendars to opaque, hard-to-guess URLs.

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

## Configuration

`config.yaml` is intentionally ignored by git because shared calendar URLs are secrets.

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
cp config.example.yaml config.yaml
docker compose build
docker compose up
```

The container listens on port `8080`. Put TLS and public routing in front of it with your reverse proxy.

Use `docker compose build` only after code, dependency, or Dockerfile changes. For changes in `config.yaml` or Compose environment values, use `docker compose up` to recreate the container without rebuilding the image. If only `config.yaml` changed and the service is already running, `docker compose restart icloud-cruncher` is enough because the app reads config at startup.

## Endpoints

- `GET /<token>` forwards the matching calendar as `text/calendar`.
- `GET /healthz` returns `{"status":"ok"}`.

There is no calendar listing endpoint. Unknown tokens return a neutral `404`.

## Logging

The app uses `loguru` and logs incoming requests plus upstream iCloud fetch results. Upstream logs include token, status, duration, content type, and response size, but not the configured iCloud source URL.

At startup, the app logs every URL path it answers. With `ICLOUDCRUNCHER.BASE_URL=https://calendar.example.com`, it logs full external URLs.

## VS Code

Use `Terminal: Run Task` and choose:

- `app: run local`
- `app: test`
- `docker: compose up`
- `docker: compose build`
- `docker: compose down`
