"""Suppress content-bearing library diagnostics only during private operations."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging

_active = ContextVar("private_http_active", default=False)


class _PrivateTransportFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _active.get()


_filter = _PrivateTransportFilter()


@contextmanager
def quiet_transport():
    # HTTPX logs resource URLs; vobject may log raw card lines. Install on
    # child loggers too, since ancestor filters do not apply to child records.
    for name in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "vobject"):
        logging.getLogger(name)
    for name, item in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(item, logging.Logger) and name.startswith(("httpx", "httpcore", "vobject")):
            if _filter not in item.filters:
                item.addFilter(_filter)
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)
