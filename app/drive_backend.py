"""Private, bearer-authenticated Drive MCP backend. No startup Apple calls."""

from contextlib import asynccontextmanager
import hmac
import os

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from app.drive import ICloudDriveService
from app.drive_config import drive_token, load_drive_backend_config
from app.drive_tools import register_drive_tools
from app.tool_contracts import DescribedMCPServer


class _Bearer:
    def __init__(self, app, token):
        self.app = app
        self.expected = ("Bearer " + token).encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in ("/mcp", "/mcp/"):
            auth = dict(scope.get("headers", [])).get(b"authorization", b"")
            if not hmac.compare_digest(auth, self.expected):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class _Endpoint:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "path": "/", "raw_path": b"/"}
        await self.app(scope, receive, send)


def create_drive_app(environ=None, *, service=None):
    env = os.environ if environ is None else environ
    token = drive_token(env)
    backend = service or ICloudDriveService(load_drive_backend_config(env))
    server = DescribedMCPServer("icloud-drive", instructions="Drive read/write access. Preserve write state; never retry uncertain mutations. Authentication and approval use the shared administrative Go CLI.")
    server.private_backend = True
    register_drive_tools(server, backend, native_files=False)
    http = server.streamable_http_app(
        streamable_http_path="/", json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["drive:*", "localhost:*", "127.0.0.1:*", "testserver"],
            allowed_origins=["http://drive:*", "http://localhost:*", "http://127.0.0.1:*"],
        ),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():
            yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(_Bearer, token=token)
    app.state.drive_service = backend
    app.state.mcp_server = server

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    for path in ("/mcp", "/mcp/"):
        app.add_route(path, _Endpoint(http), methods=["GET", "POST", "DELETE"])
    return app
