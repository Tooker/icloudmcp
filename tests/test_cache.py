from app.cache import CalendarResponseCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_cache_returns_fresh_entry_before_ttl_expires() -> None:
    clock = FakeClock()
    cache = CalendarResponseCache(ttl_seconds=300, clock=clock)

    cache.set("token", b"calendar", "text/calendar")
    clock.now += 299

    assert cache.get_fresh("token") is not None


def test_cache_returns_no_fresh_entry_after_ttl_expires() -> None:
    clock = FakeClock()
    cache = CalendarResponseCache(ttl_seconds=300, clock=clock)

    cache.set("token", b"calendar", "text/calendar")
    clock.now += 300

    assert cache.get_fresh("token") is None
    assert cache.get_stale("token") is not None


def test_zero_ttl_disables_fresh_cache_hits_but_keeps_stale_fallback() -> None:
    clock = FakeClock()
    cache = CalendarResponseCache(ttl_seconds=0, clock=clock)

    cache.set("token", b"calendar", "text/calendar")

    assert cache.get_fresh("token") is None
    assert cache.get_stale("token") is not None
