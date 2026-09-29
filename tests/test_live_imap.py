from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import load_imap_config
from app.imap import ICloudIMAPService, IMAPServiceError
from app.icloud_cache import SQLiteICloudCalendarCache

pytestmark = pytest.mark.live


def test_live_imap_login_mailboxes_and_header_search(tmp_path: Path) -> None:
    if os.environ.get("RUN_LIVE_IMAP_TESTS") != "1":
        pytest.skip("set RUN_LIVE_IMAP_TESTS=1 to access the configured iCloud mailbox")

    config = load_imap_config(environ=dict(os.environ))
    if config is None:
        pytest.fail("IMAP credentials are not configured")

    cache = SQLiteICloudCalendarCache(tmp_path / "live-imap-cache.sqlite3")
    service = ICloudIMAPService(config, cache=cache)
    try:
        mailboxes = service.list_mailboxes()
    except IMAPServiceError as exc:
        raise AssertionError(str(exc)) from None
    except Exception as exc:
        raise AssertionError(
            f"Live IMAP smoke test failed: {exc.__class__.__name__}"
        ) from None
    assert mailboxes, "iCloud returned no mailboxes"

    mailbox_names = {str(mailbox["name"]) for mailbox in mailboxes}
    mailbox = config.default_mailbox if config.default_mailbox in mailbox_names else next(iter(mailbox_names))
    try:
        results = service.search_emails(mailbox=mailbox, limit=5)
    except IMAPServiceError as exc:
        raise AssertionError(str(exc)) from None
    except Exception as exc:
        raise AssertionError(
            f"Live IMAP header search failed: {exc.__class__.__name__}"
        ) from None

    assert len(results) <= 5
    assert all("body" not in result and "raw" not in result for result in results)
    cached = service._cache.get_emails(mailbox)
    assert cached is not None and cached.fresh

    cached_results = service.search_emails(mailbox=mailbox, limit=5)
    assert cached_results == results
