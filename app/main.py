from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from loguru import logger
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.cache import CachedCalendarResponse, CalendarResponseCache
from app.config import (
    DEFAULT_CONFIG_PATH,
    CalendarConfig,
    ICloudConfig,
    IMAPConfig,
    cache_ttl_seconds,
    icloud_cache_path,
    icloud_cache_ttl_seconds,
    icloud_calendars_cache_ttl_seconds,
    load_calendars,
    load_imap_config,
    load_icloud_config,
    public_url_for_token,
)
from app.icloud import ICloudCalendarService
from app.icloud_cache import SQLiteICloudCalendarCache
from app.imap import ICloudIMAPService
from app.mcp_server import create_mcp_server


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


class ExactMcpEndpoint:
    """Adapt an exact /mcp route to the MCP SDK's mounted / route."""

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["path"] = "/"
            scope["raw_path"] = b"/"
        await self._app(scope, receive, send)


def create_app(
    config_path: Path = DEFAULT_CONFIG_PATH,
    environ: dict[str, str] | None = None,
    icloud_service: ICloudCalendarService | None = None,
    imap_service: ICloudIMAPService | None = None,
) -> FastAPI:
    calendars = load_calendars(config_path, environ)
    icloud_config: ICloudConfig | None = load_icloud_config(config_path, environ)
    imap_config: IMAPConfig | None = load_imap_config(config_path, environ)
    if icloud_service is not None:
        service = icloud_service
        icloud_cache = getattr(icloud_service, "_cache", None)
    elif icloud_config is not None:
        icloud_cache = SQLiteICloudCalendarCache(
            icloud_cache_path(environ),
            events_ttl_seconds=icloud_cache_ttl_seconds(environ),
            calendars_ttl_seconds=icloud_calendars_cache_ttl_seconds(environ),
        )
        service = ICloudCalendarService(icloud_config, cache=icloud_cache)
    else:
        icloud_cache = None
        service = None
    mail_service = imap_service or (
        ICloudIMAPService(imap_config) if imap_config is not None else None
    )
    mcp_server = create_mcp_server(service, mail_service)
    mcp_http_app = mcp_server.streamable_http_app(
        streamable_http_path="/",
        host="0.0.0.0",
        transport_security=_mcp_transport_security(environ),
    )

    async def mcp_endpoint(scope, receive, send) -> None:
        # Starlette's Mount passes an exact /mcp request to the child with an
        # empty path, while the MCP SDK route is /. Normalize both /mcp and
        # /mcp/ so tunnel clients do not depend on a redirect.
        if scope["type"] == "http" and scope.get("path") in ("", "/"):
            scope = dict(scope)
            scope["path"] = "/"
            scope["raw_path"] = b"/"
        await mcp_http_app(scope, receive, send)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Mounted Starlette applications do not run their own lifespan under
        # FastAPI, so the MCP session manager is owned by the host app.
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    cache = CalendarResponseCache(ttl_seconds=cache_ttl_seconds(environ))
    app.state.calendars = calendars
    app.state.calendar_cache = cache
    app.state.icloud_service = service
    app.state.icloud_cache = icloud_cache
    app.state.imap_service = mail_service
    app.state.mcp_server = mcp_server
    logger.info("calendar_cache ttl_seconds={}", cache.ttl_seconds)
    if icloud_cache is not None:
        logger.info(
            "icloud_cache_backend type=sqlite path={} events_ttl_seconds={} calendars_ttl_seconds={}",
            icloud_cache.path,
            icloud_cache.events_ttl_seconds,
            icloud_cache.calendars_ttl_seconds,
        )
    if service is None:
        logger.warning(
            "iCloud CalDAV is not configured; MCP tools require ICLOUD_USERNAME and ICLOUD_APP_PASSWORD"
        )
    if mail_service is None:
        logger.warning(
            "iCloud IMAP is not configured; mail MCP tools require IMAP_USERNAME and IMAP_APP_PASSWORD"
        )
    for token in calendars:
        logger.info("answering_calendar url={}", public_url_for_token(token, environ))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Mount before the legacy catch-all token route so GET /mcp is not
    # interpreted as a public-calendar token.
    app.add_route(
        "/mcp",
        ExactMcpEndpoint(mcp_http_app),
        methods=["GET", "POST", "DELETE"],
        name="mcp_exact",
    )
    app.mount("/mcp", mcp_endpoint, name="mcp")

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


def _mcp_transport_security(environ: dict[str, str] | None) -> TransportSecuritySettings:
    env = os.environ if environ is None else environ
    allowed_hosts = _split_csv(
        env.get("MCP_ALLOWED_HOSTS"),
        default=("icloud-cruncher:*", "localhost:*", "127.0.0.1:*", "testserver"),
    )
    allowed_origins = _split_csv(
        env.get("MCP_ALLOWED_ORIGINS"),
        default=("http://localhost:8080", "http://127.0.0.1:8080"),
    )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def _split_csv(value: str | None, default: tuple[str, ...]) -> list[str]:
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


app = create_app()
