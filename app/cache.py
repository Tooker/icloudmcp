from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class CachedCalendarResponse:
    content: bytes
    content_type: str
    fetched_at: float
    expires_at: float


class CalendarResponseCache:
    def __init__(self, ttl_seconds: int, clock: Callable[[], float] = monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, CachedCalendarResponse] = {}

    def get_fresh(self, token: str) -> CachedCalendarResponse | None:
        entry = self._entries.get(token)
        if entry is None or entry.expires_at <= self._clock():
            return None
        return entry

    def get_stale(self, token: str) -> CachedCalendarResponse | None:
        return self._entries.get(token)

    def set(self, token: str, content: bytes, content_type: str) -> CachedCalendarResponse:
        fetched_at = self._clock()
        entry = CachedCalendarResponse(
            content=content,
            content_type=content_type,
            fetched_at=fetched_at,
            expires_at=fetched_at + self.ttl_seconds,
        )
        self._entries[token] = entry
        return entry
