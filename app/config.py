from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DEFAULT_CONFIG_PATH = Path(os.environ.get("ICLOUD_CRUNCHER_CONFIG", "config.yaml"))
DEFAULT_ICLOUD_CACHE_PATH = Path("data/icloud-calendar-cache.sqlite3")
DEFAULT_ICLOUD_CACHE_TTL_SECONDS = 60
DEFAULT_ICLOUD_CALENDARS_CACHE_TTL_SECONDS = 300
DEFAULT_ICLOUD_CALDAV_URL = "https://caldav.icloud.com/"
DEFAULT_ICLOUD_TIMEZONE = "UTC"
DEFAULT_IMAP_HOST = "imap.mail.me.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_MAILBOX = "INBOX"
DEFAULT_IMAP_DRAFTS_MAILBOX = "Drafts"
DEFAULT_IMAP_EMAIL_CACHE_TTL_SECONDS = 300
DEFAULT_IMAP_EMAIL_CONTENT_TTL_SECONDS = 86400
DEFAULT_IMAP_MAILBOX_CACHE_TTL_SECONDS = 1800
DEFAULT_IMAP_EMAIL_CACHE_DAYS = 100
DEFAULT_IMAP_EMAIL_CACHE_MAX_MESSAGES = 1000
DEFAULT_IMAP_CONNECTION_POOL_SIZE = 4
DEFAULT_IMAP_EMAIL_CACHE_CRAWL_ENABLED = True
DEFAULT_IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE = 25
DEFAULT_IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS = 0.1
DEFAULT_IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES = 25_000_000


@dataclass(frozen=True)
class ICloudConfig:
    username: str
    app_specific_password: str
    caldav_url: str = DEFAULT_ICLOUD_CALDAV_URL
    default_calendar: str | None = None
    timezone: str = DEFAULT_ICLOUD_TIMEZONE


@dataclass(frozen=True)
class IMAPConfig:
    username: str
    app_specific_password: str
    host: str = DEFAULT_IMAP_HOST
    port: int = DEFAULT_IMAP_PORT
    default_mailbox: str = DEFAULT_IMAP_MAILBOX
    drafts_mailbox: str = DEFAULT_IMAP_DRAFTS_MAILBOX


@dataclass(frozen=True)
class RemindersConfig:
    mcp_url: str
    token: str = field(default="", repr=False)
    timeout_seconds: int = 210


def load_reminders_config(environ: dict[str, str] | None = None) -> RemindersConfig | None:
    """Connect to the separately authenticated Go backend; no Apple credentials."""
    env = os.environ if environ is None else environ
    endpoint = env.get("REMINDERS_MCP_URL", "").strip()
    if not endpoint:
        return None
    try:
        parsed = urlsplit(endpoint)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        raise ValueError("REMINDERS_MCP_URL must be an HTTP(S) MCP endpoint") from None
    if (
        parsed.scheme not in ("http", "https") or not parsed.hostname or not valid_port
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in ("/mcp", "/mcp/") or parsed.query or parsed.fragment
        or any(character.isspace() for character in endpoint)
    ):
        raise ValueError("REMINDERS_MCP_URL must end in /mcp or /mcp/ without credentials, query or fragment")
    token = env.get("REMINDERS_MCP_TOKEN", "")
    if token != token.strip() or any(ord(character) < 32 or ord(character) > 126 for character in token):
        raise ValueError("REMINDERS_MCP_TOKEN must be printable ASCII without surrounding whitespace")
    try:
        timeout = int(env.get("REMINDERS_MCP_TIMEOUT_SECONDS", "210"))
    except ValueError:
        raise ValueError("REMINDERS_MCP_TIMEOUT_SECONDS must be an integer from 1 to 900") from None
    if not 1 <= timeout <= 900:
        raise ValueError("REMINDERS_MCP_TIMEOUT_SECONDS must be an integer from 1 to 900")
    return RemindersConfig(endpoint, token, timeout)


def load_icloud_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    environ: dict[str, str] | None = None,
) -> ICloudConfig | None:
    """Load iCloud CalDAV credentials without ever logging the password.

    Calendar credentials are optional so Mail and Reminders can run independently.
    Environment variables take precedence over the optional YAML configuration.
    """

    env = os.environ if environ is None else environ
    raw_config: dict[str, Any] = {}
    if config_path.exists():
        raw_config = _load_yaml(config_path)

    raw_icloud = raw_config.get("icloud", {})
    if raw_icloud is None:
        raw_icloud = {}
    if not isinstance(raw_icloud, dict):
        raise ValueError("config.yaml 'icloud' must be an object")

    username = _first_non_empty(
        env.get("ICLOUD_USERNAME"),
        env.get("ICLOUDCRUNCHER.ICLOUD_USERNAME"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_USERNAME"),
        raw_icloud.get("username"),
        raw_icloud.get("apple_id"),
    )
    app_specific_password = _first_non_empty(
        env.get("ICLOUD_APP_PASSWORD"),
        env.get("ICLOUDCRUNCHER.ICLOUD_APP_PASSWORD"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_APP_PASSWORD"),
        raw_icloud.get("app_specific_password"),
        raw_icloud.get("password"),
    )

    if username is None and app_specific_password is None:
        return None
    if username is None or app_specific_password is None:
        raise ValueError(
            "iCloud configuration must define both username and app_specific_password"
        )

    caldav_url = _first_non_empty(
        env.get("ICLOUD_CALDAV_URL"),
        env.get("ICLOUDCRUNCHER.ICLOUD_CALDAV_URL"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_CALDAV_URL"),
        raw_icloud.get("caldav_url"),
    ) or DEFAULT_ICLOUD_CALDAV_URL
    if not caldav_url.startswith("https://"):
        raise ValueError("icloud.caldav_url must start with https://")
    caldav_url = caldav_url.rstrip("/") + "/"

    default_calendar = _first_non_empty(
        env.get("ICLOUD_DEFAULT_CALENDAR"),
        env.get("ICLOUDCRUNCHER.ICLOUD_DEFAULT_CALENDAR"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_DEFAULT_CALENDAR"),
        raw_icloud.get("default_calendar"),
    )
    timezone = _first_non_empty(
        env.get("ICLOUD_TIMEZONE"),
        env.get("ICLOUDCRUNCHER.ICLOUD_TIMEZONE"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_TIMEZONE"),
        raw_icloud.get("timezone"),
    ) or DEFAULT_ICLOUD_TIMEZONE
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"icloud.timezone is not a known IANA timezone: {timezone}") from exc

    return ICloudConfig(
        username=username,
        app_specific_password=app_specific_password,
        caldav_url=caldav_url,
        default_calendar=default_calendar,
        timezone=timezone,
    )


def load_imap_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    environ: dict[str, str] | None = None,
) -> IMAPConfig | None:
    """Load iCloud Mail IMAP credentials and connection settings.

    IMAP normally uses the same Apple Account email and app-specific password
    as CalDAV.  Dedicated ``IMAP_*`` values take precedence, while the
    ``icloud`` credentials remain a convenient shared fallback.
    """

    env = os.environ if environ is None else environ
    raw_config: dict[str, Any] = {}
    if config_path.exists():
        raw_config = _load_yaml(config_path)

    raw_imap = raw_config.get("imap", {})
    if raw_imap is None:
        raw_imap = {}
    if not isinstance(raw_imap, dict):
        raise ValueError("config.yaml 'imap' must be an object")

    raw_icloud = raw_config.get("icloud", {})
    if raw_icloud is None:
        raw_icloud = {}
    if not isinstance(raw_icloud, dict):
        raise ValueError("config.yaml 'icloud' must be an object")

    username = _first_non_empty(
        env.get("IMAP_USERNAME"),
        env.get("ICLOUDCRUNCHER.IMAP_USERNAME"),
        env.get("ICLOUD_CRUNCHER_IMAP_USERNAME"),
        raw_imap.get("username"),
        raw_imap.get("apple_id"),
        env.get("ICLOUD_USERNAME"),
        env.get("ICLOUDCRUNCHER.ICLOUD_USERNAME"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_USERNAME"),
        raw_icloud.get("username"),
        raw_icloud.get("apple_id"),
    )
    app_specific_password = _first_non_empty(
        env.get("IMAP_APP_PASSWORD"),
        env.get("ICLOUDCRUNCHER.IMAP_APP_PASSWORD"),
        env.get("ICLOUD_CRUNCHER_IMAP_APP_PASSWORD"),
        raw_imap.get("app_specific_password"),
        raw_imap.get("password"),
        env.get("ICLOUD_APP_PASSWORD"),
        env.get("ICLOUDCRUNCHER.ICLOUD_APP_PASSWORD"),
        env.get("ICLOUD_CRUNCHER_ICLOUD_APP_PASSWORD"),
        raw_icloud.get("app_specific_password"),
        raw_icloud.get("password"),
    )

    if username is None and app_specific_password is None:
        return None
    if username is None or app_specific_password is None:
        raise ValueError(
            "IMAP configuration must define both username and app_specific_password"
        )

    host = _first_non_empty(
        env.get("IMAP_HOST"),
        env.get("ICLOUDCRUNCHER.IMAP_HOST"),
        env.get("ICLOUD_CRUNCHER_IMAP_HOST"),
        raw_imap.get("host"),
    ) or DEFAULT_IMAP_HOST
    if any(character.isspace() for character in host) or "/" in host:
        raise ValueError("imap.host must be a hostname")

    raw_port: Any = (
        env.get("IMAP_PORT")
        or env.get("ICLOUDCRUNCHER.IMAP_PORT")
        or env.get("ICLOUD_CRUNCHER_IMAP_PORT")
        or raw_imap.get("port")
        or DEFAULT_IMAP_PORT
    )
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("imap.port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("imap.port must be between 1 and 65535")

    default_mailbox = _first_non_empty(
        env.get("IMAP_DEFAULT_MAILBOX"),
        env.get("ICLOUDCRUNCHER.IMAP_DEFAULT_MAILBOX"),
        env.get("ICLOUD_CRUNCHER_IMAP_DEFAULT_MAILBOX"),
        raw_imap.get("default_mailbox"),
    ) or DEFAULT_IMAP_MAILBOX

    drafts_mailbox = _first_non_empty(
        env.get("IMAP_DRAFTS_MAILBOX"),
        env.get("ICLOUDCRUNCHER.IMAP_DRAFTS_MAILBOX"),
        env.get("ICLOUD_CRUNCHER_IMAP_DRAFTS_MAILBOX"),
        raw_imap.get("drafts_mailbox"),
    ) or DEFAULT_IMAP_DRAFTS_MAILBOX

    return IMAPConfig(
        username=username,
        app_specific_password=app_specific_password,
        host=host,
        port=port,
        default_mailbox=default_mailbox,
        drafts_mailbox=drafts_mailbox,
    )


def icloud_cache_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    raw_path = (
        env.get("ICLOUD_CACHE_PATH")
        or env.get("ICLOUDCRUNCHER.ICLOUD_CACHE_PATH")
        or env.get("ICLOUD_CRUNCHER_ICLOUD_CACHE_PATH")
    )
    return Path(raw_path) if raw_path else DEFAULT_ICLOUD_CACHE_PATH


def icloud_cache_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "ICLOUD_CACHE_TTL_SECONDS",
            "ICLOUDCRUNCHER.ICLOUD_CACHE_TTL_SECONDS",
            "ICLOUD_CRUNCHER_ICLOUD_CACHE_TTL_SECONDS",
        ),
        DEFAULT_ICLOUD_CACHE_TTL_SECONDS,
        "ICLOUD_CACHE_TTL_SECONDS",
    )


def icloud_calendars_cache_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "ICLOUD_CALENDARS_CACHE_TTL_SECONDS",
            "ICLOUDCRUNCHER.ICLOUD_CALENDARS_CACHE_TTL_SECONDS",
            "ICLOUD_CRUNCHER_ICLOUD_CALENDARS_CACHE_TTL_SECONDS",
        ),
        DEFAULT_ICLOUD_CALENDARS_CACHE_TTL_SECONDS,
        "ICLOUD_CALENDARS_CACHE_TTL_SECONDS",
    )


def icloud_cache_refresh_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    value = env.get("ICLOUD_CACHE_REFRESH_ENABLED", "true").strip().casefold()
    if value not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise ValueError("ICLOUD_CACHE_REFRESH_ENABLED must be a boolean")
    return value in {"1", "true", "yes", "on"}


def icloud_cache_refresh_interval_seconds(environ: dict[str, str] | None = None) -> int:
    return _bounded_int(
        environ, ("ICLOUD_CACHE_REFRESH_INTERVAL_SECONDS",), 30,
        "ICLOUD_CACHE_REFRESH_INTERVAL_SECONDS", minimum=1, maximum=3600,
    )


def imap_email_cache_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_EMAIL_CACHE_TTL_SECONDS",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_TTL_SECONDS",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_TTL_SECONDS",
        ),
        DEFAULT_IMAP_EMAIL_CACHE_TTL_SECONDS,
        "IMAP_EMAIL_CACHE_TTL_SECONDS",
    )


def imap_email_content_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_EMAIL_CONTENT_TTL_SECONDS",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CONTENT_TTL_SECONDS",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CONTENT_TTL_SECONDS",
        ),
        DEFAULT_IMAP_EMAIL_CONTENT_TTL_SECONDS,
        "IMAP_EMAIL_CONTENT_TTL_SECONDS",
    )


def imap_mailbox_cache_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_MAILBOX_CACHE_TTL_SECONDS",
            "ICLOUDCRUNCHER.IMAP_MAILBOX_CACHE_TTL_SECONDS",
            "ICLOUD_CRUNCHER_IMAP_MAILBOX_CACHE_TTL_SECONDS",
        ),
        DEFAULT_IMAP_MAILBOX_CACHE_TTL_SECONDS,
        "IMAP_MAILBOX_CACHE_TTL_SECONDS",
    )


def imap_email_cache_days(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_EMAIL_CACHE_DAYS",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_DAYS",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_DAYS",
        ),
        DEFAULT_IMAP_EMAIL_CACHE_DAYS,
        "IMAP_EMAIL_CACHE_DAYS",
    )


def imap_email_cache_max_messages(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_EMAIL_CACHE_MAX_MESSAGES",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_MAX_MESSAGES",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_MAX_MESSAGES",
        ),
        DEFAULT_IMAP_EMAIL_CACHE_MAX_MESSAGES,
        "IMAP_EMAIL_CACHE_MAX_MESSAGES",
    )


def imap_connection_pool_size(environ: dict[str, str] | None = None) -> int:
    return _positive_or_zero_int(
        environ,
        (
            "IMAP_CONNECTION_POOL_SIZE",
            "ICLOUDCRUNCHER.IMAP_CONNECTION_POOL_SIZE",
            "ICLOUD_CRUNCHER_IMAP_CONNECTION_POOL_SIZE",
        ),
        DEFAULT_IMAP_CONNECTION_POOL_SIZE,
        "IMAP_CONNECTION_POOL_SIZE",
    )


def imap_email_cache_crawl_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    raw_value = next(
        (
            env.get(name)
            for name in (
                "IMAP_EMAIL_CACHE_CRAWL_ENABLED",
                "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_CRAWL_ENABLED",
                "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_CRAWL_ENABLED",
            )
            if env.get(name) is not None
        ),
        None,
    )
    if raw_value is None:
        return DEFAULT_IMAP_EMAIL_CACHE_CRAWL_ENABLED
    normalized = raw_value.strip().casefold()
    if normalized not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise ValueError("IMAP_EMAIL_CACHE_CRAWL_ENABLED must be a boolean")
    return normalized in {"1", "true", "yes", "on"}


def imap_email_cache_crawl_batch_size(environ: dict[str, str] | None = None) -> int:
    return _bounded_int(
        environ,
        (
            "IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE",
        ),
        DEFAULT_IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE,
        "IMAP_EMAIL_CACHE_CRAWL_BATCH_SIZE",
        minimum=1,
        maximum=100,
    )


def imap_email_cache_crawl_interval_seconds(environ: dict[str, str] | None = None) -> float:
    env = os.environ if environ is None else environ
    raw_value = next(
        (
            env.get(name)
            for name in (
                "IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS",
                "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS",
                "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS",
            )
            if env.get(name) is not None
        ),
        None,
    )
    if raw_value is None:
        return DEFAULT_IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError("IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS must be a number") from exc
    if value < 0:
        raise ValueError("IMAP_EMAIL_CACHE_CRAWL_INTERVAL_SECONDS must not be negative")
    return value


def imap_email_cache_max_message_bytes(environ: dict[str, str] | None = None) -> int:
    return _bounded_int(
        environ,
        (
            "IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES",
            "ICLOUDCRUNCHER.IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES",
            "ICLOUD_CRUNCHER_IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES",
        ),
        DEFAULT_IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES,
        "IMAP_EMAIL_CACHE_MAX_MESSAGE_BYTES",
        minimum=1,
        maximum=100_000_000,
    )


def _positive_or_zero_int(
    environ: dict[str, str] | None,
    names: tuple[str, ...],
    default: int,
    setting_name: str,
) -> int:
    env = os.environ if environ is None else environ
    raw_value = next((env.get(name) for name in names if env.get(name) is not None), None)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{setting_name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{setting_name} must not be negative")
    return value


def _bounded_int(
    environ: dict[str, str] | None,
    names: tuple[str, ...],
    default: int,
    setting_name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _positive_or_zero_int(environ, names, default, setting_name)
    if value < minimum or value > maximum:
        raise ValueError(f"{setting_name} must be between {minimum} and {maximum}")
    return value


def _load_yaml(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file) or {}

    if not isinstance(raw_config, dict):
        raise ValueError("config.yaml must contain a YAML object")

    return raw_config


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
