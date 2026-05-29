from __future__ import annotations

from time import perf_counter

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import CalendarConfig, load_calendars


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = (perf_counter() - start) * 1000
            status_code = response.status_code if response else 500
            logger.info(
                "request method={} path={} status={} duration_ms={:.1f} client={}",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
                request.client.host if request.client else "unknown",
            )


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestLoggingMiddleware)
    calendars = load_calendars()
    app.state.calendars = calendars

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{token}")
    async def forward_calendar(token: str) -> Response:
        calendar: CalendarConfig | None = app.state.calendars.get(token)
        if calendar is None:
            raise HTTPException(status_code=404, detail="Not found")

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                upstream_started = perf_counter()
                upstream_response = await client.get(
                    calendar.source_url,
                    headers={"Accept": "text/calendar,*/*;q=0.8"},
                )
                upstream_elapsed_ms = (perf_counter() - upstream_started) * 1000
                logger.info(
                    "upstream token={} status={} duration_ms={:.1f} content_type={} bytes={}",
                    token,
                    upstream_response.status_code,
                    upstream_elapsed_ms,
                    upstream_response.headers.get("content-type", "unknown"),
                    len(upstream_response.content),
                )
                upstream_response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("upstream_failed token={} error={}", token, exc.__class__.__name__)
            raise HTTPException(status_code=502, detail="Upstream unavailable") from exc

        return Response(
            content=upstream_response.content,
            media_type="text/calendar; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app()
