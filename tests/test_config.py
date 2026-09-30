from pathlib import Path

import pytest

from app.config import (
    icloud_cache_path,
    icloud_cache_refresh_enabled,
    icloud_cache_refresh_interval_seconds,
    icloud_cache_ttl_seconds,
    icloud_calendars_cache_ttl_seconds,
    imap_email_cache_days,
    imap_email_cache_max_messages,
    imap_connection_pool_size,
    imap_email_cache_crawl_batch_size,
    imap_email_cache_crawl_enabled,
    imap_email_cache_crawl_interval_seconds,
    imap_email_cache_max_message_bytes,
    imap_email_cache_ttl_seconds,
    imap_email_content_ttl_seconds,
    imap_mailbox_cache_ttl_seconds,
    load_imap_config,
    load_icloud_config,
)


def write_config(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_calendar_cache_refresh_settings():
    assert icloud_cache_refresh_enabled({}) is True
    assert icloud_cache_refresh_enabled({"ICLOUD_CACHE_REFRESH_ENABLED": "off"}) is False
    assert icloud_cache_refresh_interval_seconds({}) == 30
    assert icloud_cache_refresh_interval_seconds({"ICLOUD_CACHE_REFRESH_INTERVAL_SECONDS": "10"}) == 10
    with pytest.raises(ValueError):
        icloud_cache_refresh_enabled({"ICLOUD_CACHE_REFRESH_ENABLED": "invalid"})
    for value in ("0", "-1", "3601", "invalid"):
        with pytest.raises(ValueError):
            icloud_cache_refresh_interval_seconds({"ICLOUD_CACHE_REFRESH_INTERVAL_SECONDS": value})


def test_icloud_cache_settings_have_separate_defaults_and_overrides(tmp_path: Path) -> None:
    assert icloud_cache_path(environ={}) == Path("data/icloud-calendar-cache.sqlite3")
    assert icloud_cache_ttl_seconds(environ={}) == 60
    assert icloud_calendars_cache_ttl_seconds(environ={}) == 300

    configured = {
        "ICLOUD_CACHE_PATH": str(tmp_path / "calendar-cache.sqlite3"),
        "ICLOUD_CACHE_TTL_SECONDS": "15",
        "ICLOUD_CALENDARS_CACHE_TTL_SECONDS": "900",
    }
    assert icloud_cache_path(environ=configured) == tmp_path / "calendar-cache.sqlite3"
    assert icloud_cache_ttl_seconds(environ=configured) == 15
    assert icloud_calendars_cache_ttl_seconds(environ=configured) == 900


def test_imap_email_cache_settings_default_to_recent_bounded_cache() -> None:
    assert imap_email_cache_ttl_seconds(environ={}) == 300
    assert imap_email_cache_days(environ={}) == 100
    assert imap_email_cache_max_messages(environ={}) == 1000
    assert imap_connection_pool_size(environ={}) == 4
    assert imap_email_content_ttl_seconds(environ={}) == 86400
    assert imap_mailbox_cache_ttl_seconds(environ={}) == 1800
    assert imap_email_cache_crawl_enabled(environ={}) is True
    assert imap_email_cache_crawl_batch_size(environ={}) == 25
    assert imap_email_cache_crawl_interval_seconds(environ={}) == 0.1
    assert imap_email_cache_max_message_bytes(environ={}) == 25_000_000
    configured = {
        "IMAP_EMAIL_CACHE_TTL_SECONDS": "600",
        "IMAP_EMAIL_CACHE_DAYS": "30",
        "IMAP_EMAIL_CACHE_MAX_MESSAGES": "250",
    }
    assert imap_email_cache_ttl_seconds(environ=configured) == 600
    assert imap_email_cache_days(environ=configured) == 30
    assert imap_email_cache_max_messages(environ=configured) == 250
    assert imap_connection_pool_size(environ={"IMAP_CONNECTION_POOL_SIZE": "2"}) == 2


def test_loads_icloud_caldav_config_from_yaml(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
icloud:
  username: user@example.com
  app_specific_password: xxxx-xxxx-xxxx-xxxx
  default_calendar: Work
  timezone: Europe/Berlin
""",
    )

    config = load_icloud_config(config_path)

    assert config is not None
    assert config.username == "user@example.com"
    assert config.app_specific_password == "xxxx-xxxx-xxxx-xxxx"
    assert config.caldav_url == "https://caldav.icloud.com/"
    assert config.default_calendar == "Work"
    assert config.timezone == "Europe/Berlin"


def test_icloud_environment_overrides_yaml(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
icloud:
  username: yaml@example.com
  app_specific_password: yaml-password
""",
    )

    config = load_icloud_config(
        config_path,
        environ={
            "ICLOUD_USERNAME": "env@example.com",
            "ICLOUD_APP_PASSWORD": "env-password",
            "ICLOUD_TIMEZONE": "America/New_York",
        },
    )

    assert config is not None
    assert config.username == "env@example.com"
    assert config.app_specific_password == "env-password"
    assert config.timezone == "America/New_York"


def test_missing_icloud_credentials_are_optional(tmp_path: Path) -> None:
    assert load_icloud_config(tmp_path / "missing.yaml", environ={}) is None


def test_partial_icloud_credentials_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="both username"):
        load_icloud_config(
            tmp_path / "missing.yaml",
            environ={"ICLOUD_USERNAME": "user@example.com"},
        )


def test_loads_imap_config_and_reuses_icloud_credentials(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
icloud:
  username: user@example.com
  app_specific_password: app-password
imap:
  default_mailbox: Archive
  drafts_mailbox: Entwürfe
""",
    )

    config = load_imap_config(config_path)

    assert config is not None
    assert config.username == "user@example.com"
    assert config.app_specific_password == "app-password"
    assert config.host == "imap.mail.me.com"
    assert config.port == 993
    assert config.default_mailbox == "Archive"
    assert config.drafts_mailbox == "Entwürfe"


def test_imap_environment_overrides_yaml(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
imap:
  username: yaml@example.com
  app_specific_password: yaml-password
  port: 1993
""",
    )

    config = load_imap_config(
        config_path,
        environ={
            "IMAP_USERNAME": "env@example.com",
            "IMAP_APP_PASSWORD": "env-password",
            "IMAP_PORT": "993",
        },
    )

    assert config is not None
    assert config.username == "env@example.com"
    assert config.app_specific_password == "env-password"
    assert config.port == 993


def test_partial_imap_credentials_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="both username"):
        load_imap_config(
            tmp_path / "missing.yaml",
            environ={"IMAP_USERNAME": "user@example.com"},
        )
