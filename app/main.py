from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from loguru import logger
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import (
    DEFAULT_CONFIG_PATH,
    ICloudConfig,
    IMAPConfig,
    icloud_cache_path,
    icloud_cache_refresh_enabled,
    icloud_cache_refresh_interval_seconds,
    icloud_cache_ttl_seconds,
    icloud_calendars_cache_ttl_seconds,
    imap_connection_pool_size,
    imap_email_cache_crawl_batch_size,
    imap_email_cache_crawl_enabled,
    imap_email_cache_crawl_interval_seconds,
    imap_email_cache_max_message_bytes,
    imap_email_cache_days,
    imap_email_cache_max_messages,
    imap_email_cache_ttl_seconds,
    imap_email_content_ttl_seconds,
    imap_mailbox_cache_ttl_seconds,
    load_imap_config,
    load_icloud_config,
    load_reminders_config,
)
from app.icloud import ICloudCalendarService
from app.icloud_cache import SQLiteICloudCalendarCache
from app.imap import ICloudIMAPService
from app.mcp_server import create_mcp_server
from app.reminders import GoRemindersService
from app.search_config import load_mail_search_config
from app.semantic_search import SemanticMailSearch


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/healthz":
            return await call_next(request)
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


class _HealthCheckAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/healthz" not in record.getMessage()


def _configure_healthcheck_access_logging() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, _HealthCheckAccessFilter) for item in access_logger.filters):
        access_logger.addFilter(_HealthCheckAccessFilter())


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
    mail_search: SemanticMailSearch | None = None,
    reminders_service: GoRemindersService | None = None,
) -> FastAPI:
    _configure_healthcheck_access_logging()
    icloud_config: ICloudConfig | None = load_icloud_config(config_path, environ)
    imap_config: IMAPConfig | None = load_imap_config(config_path, environ)
    if icloud_service is not None:
        service = icloud_service
        shared_cache = getattr(icloud_service, "_cache", None)
    elif icloud_config is not None:
        shared_cache = _build_icloud_cache(environ)
        service = ICloudCalendarService(icloud_config, cache=shared_cache)
    else:
        shared_cache = None
        service = None
    if imap_service is not None:
        mail_service = imap_service
        mail_service_created = False
    elif imap_config is not None:
        if shared_cache is None:
            shared_cache = _build_icloud_cache(environ)
        mail_service = ICloudIMAPService(
            imap_config,
            cache=shared_cache,
            email_cache_days=imap_email_cache_days(environ),
            email_cache_max_messages=imap_email_cache_max_messages(environ),
            connection_pool_size=imap_connection_pool_size(environ),
            crawl_batch_size=imap_email_cache_crawl_batch_size(environ),
            crawl_interval_seconds=imap_email_cache_crawl_interval_seconds(environ),
            max_cached_message_bytes=imap_email_cache_max_message_bytes(environ),
        )
        mail_service_created = True
    else:
        mail_service = None
        mail_service_created = False
    search_config = load_mail_search_config(environ)
    if mail_search is not None:
        search_service = mail_search
    elif search_config.enabled and search_config.api_key and getattr(mail_service, "_cache", None) is not None:
        search_service = SemanticMailSearch(mail_service._cache, search_config)
    else:
        search_service = None
        if search_config.enabled:
            logger.warning("mail_search action=start status=not_configured api_key_present={} mail_cache_present={}",
                           bool(search_config.api_key), getattr(mail_service, "_cache", None) is not None)
    reminders_config = load_reminders_config(environ)
    reminders_backend = reminders_service or (GoRemindersService(reminders_config) if reminders_config else None)
    mcp_server = create_mcp_server(service, mail_service, search_service, reminders_backend)
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
        crawl_task: asyncio.Task | None = None
        search_task: asyncio.Task | None = None
        calendar_refresh_task: asyncio.Task | None = None
        try:
            if (
                isinstance(service, ICloudCalendarService)
                and service.cache_refresh_supported
                and icloud_cache_refresh_enabled(environ)
            ):
                calendar_refresh_task = asyncio.create_task(
                    asyncio.to_thread(service.run_cache_refresh, icloud_cache_refresh_interval_seconds(environ)),
                    name="icloud-calendar-cache-refresh",
                )
            if search_service is not None:
                logger.info("mail_search action=start status=scheduled model={} dimensions={}", search_service.config.model, search_service.config.dimensions)
                search_task = asyncio.create_task(asyncio.to_thread(search_service.run), name="mail-search-index")
            if mail_service_created and imap_email_cache_crawl_enabled(environ):
                logger.info(
                    "imap_cache tool=crawl_email_cache action=launch status=scheduled batch_size={} interval_seconds={} max_message_bytes={}",
                    imap_email_cache_crawl_batch_size(environ),
                    imap_email_cache_crawl_interval_seconds(environ),
                    imap_email_cache_max_message_bytes(environ),
                )
                crawl_task = asyncio.create_task(
                    asyncio.to_thread(mail_service.crawl_email_cache),
                    name="imap-email-cache-crawl",
                )
            async with mcp_server.session_manager.run():
                yield
        finally:
            if calendar_refresh_task is not None:
                service.stop_cache_refresh()
            if search_service is not None:
                search_service.stop()
            if search_task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(search_task), timeout=35)
                except (asyncio.CancelledError, TimeoutError):
                    search_task.cancel()
            if search_service is not None:
                await asyncio.to_thread(search_service.close)
            if calendar_refresh_task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(calendar_refresh_task), timeout=35)
                except (asyncio.CancelledError, TimeoutError):
                    calendar_refresh_task.cancel()
            if crawl_task is not None and not crawl_task.done():
                stop = getattr(mail_service, "stop_crawl", None)
                if callable(stop):
                    stop()
                try:
                    await asyncio.wait_for(crawl_task, timeout=5)
                except (asyncio.CancelledError, TimeoutError):
                    crawl_task.cancel()
            close = getattr(mail_service, "close", None)
            if callable(close):
                await asyncio.to_thread(close)

    app = FastAPI(
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.state.icloud_service = service
    app.state.icloud_cache = shared_cache
    app.state.imap_service = mail_service
    app.state.mail_search = search_service
    app.state.reminders_service = reminders_backend
    app.state.mcp_server = mcp_server
    if shared_cache is not None:
        logger.info(
            "icloud_cache_backend type=sqlite path={} events_ttl_seconds={} calendars_ttl_seconds={} mailboxes_ttl_seconds={} email_ttl_seconds={} email_content_ttl_seconds={} email_max_messages={} imap_connection_pool_size={}",
            shared_cache.path,
            shared_cache.events_ttl_seconds,
            shared_cache.calendars_ttl_seconds,
            shared_cache.mailboxes_ttl_seconds,
            shared_cache.email_ttl_seconds,
            shared_cache.email_content_ttl_seconds,
            shared_cache.email_max_messages,
            imap_connection_pool_size(environ),
        )
    if service is None:
        logger.warning(
            "iCloud CalDAV is not configured; MCP tools require ICLOUD_USERNAME and ICLOUD_APP_PASSWORD"
        )
    if mail_service is None:
        logger.warning(
            "iCloud IMAP is not configured; mail MCP tools require IMAP_USERNAME and IMAP_APP_PASSWORD"
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.add_route(
        "/mcp",
        ExactMcpEndpoint(mcp_http_app),
        methods=["GET", "POST", "DELETE"],
        name="mcp_exact",
    )
    app.mount("/mcp", mcp_endpoint, name="mcp")

    return app


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


def _build_icloud_cache(environ: dict[str, str] | None) -> SQLiteICloudCalendarCache:
    return SQLiteICloudCalendarCache(
        icloud_cache_path(environ),
        events_ttl_seconds=icloud_cache_ttl_seconds(environ),
        calendars_ttl_seconds=icloud_calendars_cache_ttl_seconds(environ),
        email_ttl_seconds=imap_email_cache_ttl_seconds(environ),
        mailboxes_ttl_seconds=imap_mailbox_cache_ttl_seconds(environ),
        email_content_ttl_seconds=imap_email_content_ttl_seconds(environ),
        email_max_messages=imap_email_cache_max_messages(environ),
    )


app = create_app()
