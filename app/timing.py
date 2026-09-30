"""Correlated, content-free timings for synchronous MCP worker operations."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
from typing import Iterator
from uuid import uuid4

from loguru import logger


_trace: ContextVar[tuple[str, str] | None] = ContextVar("mcp_trace", default=None)
_span: ContextVar[str | None] = ContextVar("mcp_span", default=None)


def call_id() -> str:
    trace = _trace.get()
    return trace[1] if trace else "none"


@contextmanager
def tool_trace(tool: str) -> Iterator[None]:
    token = _trace.set((tool, uuid4().hex[:16]))
    parent = _span.set(None)
    try:
        yield
    finally:
        _span.reset(parent)
        _trace.reset(token)


def _log_phase(phase: str, started: float, span: str, parent: str | None, outcome: str) -> None:
    trace = _trace.get()
    if trace:
        logger.info(
            "mcp_phase tool={} call_id={} span_id={} parent_span={} phase={} outcome={} duration_ms={:.1f}",
            trace[0], trace[1], span, parent or "none", phase, outcome,
            (perf_counter() - started) * 1000,
        )


def log_elapsed(phase: str, started: float) -> None:
    _log_phase(phase, started, uuid4().hex[:16], _span.get(), "ok")


@contextmanager
def measure_phase(phase: str) -> Iterator[None]:
    # Background crawlers/indexers keep their aggregate logs; only MCP
    # requests generate detailed spans, with no arguments or result data.
    if _trace.get() is None:
        yield
        return
    started = perf_counter()
    parent = _span.get()
    span = uuid4().hex[:16]
    token = _span.set(span)
    outcome = "ok"
    try:
        yield
    except BaseException:
        outcome = "error"
        raise
    finally:
        _span.reset(token)
        _log_phase(phase, started, span, parent, outcome)


def timed_phase(phase: str):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            with measure_phase(phase):
                return function(*args, **kwargs)
        return measured
    return decorate


@contextmanager
def measured_lock(lock) -> Iterator[None]:
    with measure_phase("cache_lock_wait"):
        lock.acquire()
    try:
        yield
    finally:
        lock.release()
