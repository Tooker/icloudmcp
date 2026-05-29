from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from loguru import logger

DEFAULT_CONFIG_PATH = Path(os.environ.get("ICLOUD_CRUNCHER_CONFIG", "config.yaml"))
ENV_PREFIX = "ICLOUDCRUNCHER."
DEFAULT_CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class CalendarConfig:
    token: str
    source_url: str


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
        calendars = raw_config.get("calendars")

        if not isinstance(calendars, list) or not calendars:
            raise ValueError("config.yaml must define a non-empty 'calendars' list")

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
