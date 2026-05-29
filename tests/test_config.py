from pathlib import Path
from uuid import UUID

import pytest

from app.config import load_calendars, normalize_source_url


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
