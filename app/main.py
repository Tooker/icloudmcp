from __future__ import annotations

from time import perf_counter

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.cache import CachedCalendarResponse, CalendarResponseCache
from app.config import CalendarConfig, cache_ttl_seconds, load_calendars, public_url_for_token


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
    cache = CalendarResponseCache(ttl_seconds=cache_ttl_seconds())
    app.state.calendars = calendars
    app.state.calendar_cache = cache
    logger.info("calendar_cache ttl_seconds={}", cache.ttl_seconds)
    for token in calendars:
        logger.info("answering_calendar url={}", public_url_for_token(token))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{token}")
    async def forward_calendar(token: str) -> Response:
        calendar: CalendarConfig | None = app.state.calendars.get(token)
        if calendar is None:
            raise HTTPException(status_code=404, detail="Not found")

        cached_response = app.state.calendar_cache.get_fresh(token)
        if cached_response is not None:
            logger.info("cache_hit token={} bytes={}", token, len(cached_response.content))
            return calendar_response(cached_response, cache_status="HIT")

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
            stale_response = app.state.calendar_cache.get_stale(token)
            if stale_response is not None:
                logger.warning("cache_stale_fallback token={} bytes={}", token, len(stale_response.content))
                return calendar_response(stale_response, cache_status="STALE")
            raise HTTPException(status_code=502, detail="Upstream unavailable") from exc

        cached_response = app.state.calendar_cache.set(
            token=token,
            content=upstream_response.content,
            content_type=upstream_response.headers.get("content-type", "text/calendar; charset=utf-8"),
        )
        return calendar_response(cached_response, cache_status="MISS")

    return app


def calendar_response(cached_response: CachedCalendarResponse, cache_status: str) -> Response:
    return Response(
        content=cached_response.content,
        media_type=cached_response.content_type,
        headers={"Cache-Control": "no-store", "X-Calendar-Cache": cache_status},
    )


app = create_app()
