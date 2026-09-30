from pathlib import Path
from uuid import UUID

import pytest

from app.config import (
    cache_ttl_seconds,
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
    load_calendars,
    load_imap_config,
    load_icloud_config,
    normalize_source_url,
    public_url_for_token,
)


def write_config(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_normalizes_webcal_to_https() -> None:
    assert normalize_source_url("webcal://example.com/calendar") == "https://example.com/calendar"


def test_rejects_non_https_source_urls() -> None:
    with pytest.raises(ValueError, match="webcal:// or https://"):
        normalize_source_url("http://example.com/calendar")


def test_loads_configured_token(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
calendars:
  - token: abc123
    source_url: webcal://example.com/calendar
""",
    )

    calendars = load_calendars(config_path)

    assert calendars["abc123"].source_url == "https://example.com/calendar"


def test_generates_uuid_token_when_missing(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
calendars:
  - source_url: https://example.com/calendar
""",
    )

    calendars = load_calendars(config_path)
    token = next(iter(calendars))

    assert UUID(token).version == 4


def test_missing_config_returns_empty_calendar_map(tmp_path: Path) -> None:
    assert load_calendars(tmp_path / "missing.yaml") == {}


def test_loads_calendar_from_environment_without_config(tmp_path: Path) -> None:
    calendars = load_calendars(
        tmp_path / "missing.yaml",
        environ={
            "ICLOUDCRUNCHER.0.token": "env-token",
            "ICLOUDCRUNCHER.0.URL": "webcal://example.com/env-calendar",
        },
    )

    assert calendars["env-token"].source_url == "https://example.com/env-calendar"


def test_loads_multiple_numbered_environment_calendars(tmp_path: Path) -> None:
    calendars = load_calendars(
        tmp_path / "missing.yaml",
        environ={
            "ICLOUDCRUNCHER.0.token": "first-token",
            "ICLOUDCRUNCHER.0.URL": "webcal://example.com/first",
            "ICLOUDCRUNCHER.1.token": "second-token",
            "ICLOUDCRUNCHER.1.URL": "webcal://example.com/second",
        },
    )

    assert calendars["first-token"].source_url == "https://example.com/first"
    assert calendars["second-token"].source_url == "https://example.com/second"


def test_loads_env_calendars_after_yaml_calendars(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
calendars:
  - token: yaml-token
    source_url: https://example.com/yaml
""",
    )

    calendars = load_calendars(
        config_path,
        environ={
            "ICLOUDCRUNCHER.0.token": "env-token",
            "ICLOUDCRUNCHER.0.URL": "https://example.com/env",
        },
    )

    assert set(calendars) == {"yaml-token", "env-token"}


def test_public_url_for_token_uses_optional_base_url() -> None:
    assert public_url_for_token("abc", environ={}) == "/abc"
    assert public_url_for_token("abc", environ={"ICLOUDCRUNCHER.BASE_URL": "https://example.com/root/"}) == "https://example.com/root/abc"


def test_cache_ttl_seconds_defaults_and_reads_environment() -> None:
    assert cache_ttl_seconds(environ={}) == 300
    assert cache_ttl_seconds(environ={"ICLOUDCRUNCHER.CACHE_TTL_SECONDS": "60"}) == 60


def test_cache_ttl_seconds_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        cache_ttl_seconds(environ={"ICLOUDCRUNCHER.CACHE_TTL_SECONDS": "-1"})


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


def test_rejects_duplicate_tokens(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
calendars:
  - token: same
    source_url: https://example.com/one
  - token: same
    source_url: https://example.com/two
""",
    )

    with pytest.raises(ValueError, match="duplicate token"):
        load_calendars(config_path)


def test_rejects_token_with_slash(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
calendars:
  - token: nested/path
    source_url: https://example.com/calendar
""",
    )

    with pytest.raises(ValueError, match="single path segment"):
        load_calendars(config_path)


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
