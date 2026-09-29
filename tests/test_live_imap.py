from __future__ import annotations

import os

import pytest

from app.config import load_imap_config
from app.imap import ICloudIMAPService, IMAPServiceError

pytestmark = pytest.mark.live


def test_live_imap_login_mailboxes_and_header_search() -> None:
    if os.environ.get("RUN_LIVE_IMAP_TESTS") != "1":
        pytest.skip("set RUN_LIVE_IMAP_TESTS=1 to access the configured iCloud mailbox")

    config = load_imap_config(environ=dict(os.environ))
    if config is None:
        pytest.fail("IMAP credentials are not configured")

    service = ICloudIMAPService(config)
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
