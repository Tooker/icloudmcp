from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from loguru import logger

DEFAULT_CONFIG_PATH = Path(os.environ.get("ICLOUD_CRUNCHER_CONFIG", "config.yaml"))
ENV_PREFIX = "ICLOUDCRUNCHER."
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_ICLOUD_CALDAV_URL = "https://caldav.icloud.com/"
DEFAULT_ICLOUD_TIMEZONE = "UTC"
DEFAULT_IMAP_HOST = "imap.mail.me.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_MAILBOX = "INBOX"


@dataclass(frozen=True)
class CalendarConfig:
    token: str
    source_url: str


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


def normalize_source_url(source_url: str) -> str:
    if source_url.startswith("webcal://"):
        return "https://" + source_url.removeprefix("webcal://")
    if not source_url.startswith("https://"):
        raise ValueError("source_url must start with webcal:// or https://")
    return source_url


def load_calendars(
    config_path: Path = DEFAULT_CONFIG_PATH,
    environ: dict[str, str] | None = None,
) -> dict[str, CalendarConfig]:
    env_calendars = _load_env_calendars(os.environ if environ is None else environ)
    yaml_calendars: list[Any] = []

    if config_path.exists():
        raw_config = _load_yaml(config_path)
        calendars = raw_config.get("calendars", [])

        if calendars is None:
            calendars = []

        if not isinstance(calendars, list):
            raise ValueError("config.yaml 'calendars' must be a list")

        yaml_calendars = calendars
    elif not env_calendars:
        logger.error(
            "Configuration file not found: {}. Copy config.example.yaml to config.yaml and add your calendars.",
            config_path,
        )
        return {}

    result: dict[str, CalendarConfig] = {}
    for index, raw_calendar in enumerate([*yaml_calendars, *env_calendars], start=1):
        if not isinstance(raw_calendar, dict):
            raise ValueError(f"calendar #{index} must be an object")

        source_url = raw_calendar.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ValueError(f"calendar #{index} must define source_url")

        token = raw_calendar.get("token")
        if token is None or token == "":
            token = str(uuid4())
            logger.warning(
                "Generated temporary token for calendar #{}: {}. "
                "Persist this token in config.yaml if the URL should survive restarts.",
                index,
                token,
            )
        elif not isinstance(token, str):
            raise ValueError(f"calendar #{index} token must be a string")

        token = token.strip("/").strip()
        if not token:
            raise ValueError(f"calendar #{index} token must not be empty")
        if "/" in token:
            raise ValueError(f"calendar #{index} token must be a single path segment")
        if token in result:
            raise ValueError(f"duplicate token configured for calendar #{index}")

        result[token] = CalendarConfig(
            token=token,
            source_url=normalize_source_url(source_url.strip()),
        )

    return result


def load_icloud_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    environ: dict[str, str] | None = None,
) -> ICloudConfig | None:
    """Load iCloud CalDAV credentials without ever logging the password.

    The YAML block is optional so the original public-calendar proxy remains
    usable on its own. Environment variables take precedence over YAML and
    are convenient for Docker deployments.
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

    return IMAPConfig(
        username=username,
        app_specific_password=app_specific_password,
        host=host,
        port=port,
        default_mailbox=default_mailbox,
    )


def public_url_for_token(token: str, environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    base_url = env.get("ICLOUDCRUNCHER.BASE_URL") or env.get("ICLOUD_CRUNCHER_BASE_URL")
    if not base_url:
        return f"/{token}"
    return f"{base_url.rstrip('/')}/{token}"


def cache_ttl_seconds(environ: dict[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    raw_ttl = env.get("ICLOUDCRUNCHER.CACHE_TTL_SECONDS") or env.get("ICLOUD_CRUNCHER_CACHE_TTL_SECONDS")
    if raw_ttl is None:
        return DEFAULT_CACHE_TTL_SECONDS

    try:
        ttl = int(raw_ttl)
    except ValueError as exc:
        raise ValueError("ICLOUDCRUNCHER.CACHE_TTL_SECONDS must be an integer") from exc

    if ttl < 0:
        raise ValueError("ICLOUDCRUNCHER.CACHE_TTL_SECONDS must not be negative")
    return ttl


def _load_yaml(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file) or {}

    if not isinstance(raw_config, dict):
        raise ValueError("config.yaml must contain a YAML object")

    return raw_config


def _load_env_calendars(environ: dict[str, str]) -> list[dict[str, str]]:
    grouped: dict[int, dict[str, str]] = {}
    for key, value in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue

        parts = key.split(".", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue

        field = parts[2].lower()
        if field == "url":
            field = "source_url"
        if field not in {"token", "source_url"}:
            continue

        grouped.setdefault(int(parts[1]), {})[field] = value

    return [grouped[index] for index in sorted(grouped)]


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
