"""The public bridge has a bearer token; only the private backend has a session."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DriveConfig:
    mcp_url: str
    token: str = field(repr=False)
    timeout_seconds: int = 90


@dataclass(frozen=True)
class DriveBackendConfig:
    session_path: Path = Path("secrets/icloud-drive/session.json")
    timeout_seconds: int = 60
    max_file_bytes: int = 30_000_000
    max_folder_items: int = 2000


def _number(env, name, default, maximum):
    try:
        value = int(env.get(name, str(default)))
        if not 1 <= value <= maximum:
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer from 1 to {maximum}") from None


def drive_token(env) -> str:
    token = env.get("DRIVE_MCP_TOKEN", "")
    if (len(token) < 32 or len(token) > 512 or any(ord(char) <= 32 or ord(char) > 126 for char in token)
            or token == env.get("ICLOUD_APP_PASSWORD") or token == env.get("REMINDERS_MCP_TOKEN")):
        raise ValueError("DRIVE_MCP_TOKEN must be a dedicated printable token of 32..512 characters")
    return token


def load_drive_config(environ=None) -> DriveConfig | None:
    env = os.environ if environ is None else environ
    endpoint = env.get("DRIVE_MCP_URL", "").strip()
    if not endpoint:
        return None
    try:
        parsed = urlsplit(endpoint)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.port == 0
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ("/mcp", "/mcp/") or any(ord(char) <= 32 for char in endpoint)):
            raise ValueError
    except ValueError:
        raise ValueError("DRIVE_MCP_URL must be an HTTP(S) /mcp endpoint without credentials, query or fragment") from None
    return DriveConfig(endpoint, drive_token(env), _number(env, "DRIVE_MCP_TIMEOUT_SECONDS", 90, 300))


def load_drive_backend_config(environ=None) -> DriveBackendConfig:
    env = os.environ if environ is None else environ
    return DriveBackendConfig(
        Path(env.get("DRIVE_SESSION_PATH", "secrets/icloud-drive/session.json")),
        _number(env, "DRIVE_REQUEST_TIMEOUT_SECONDS", 60, 300),
        _number(env, "DRIVE_MAX_FILE_BYTES", 30_000_000, 30_000_000),
        _number(env, "DRIVE_MAX_FOLDER_ITEMS", 2000, 20000),
    )
