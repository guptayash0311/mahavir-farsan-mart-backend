import time
from collections import defaultdict

_hits: dict[str, list[float]] = defaultdict(list)


def clear_rate_limits() -> None:
    _hits.clear()


def allow(key: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _hits[key] if now - stamp < window_seconds]
    if len(recent) >= limit:
        _hits[key] = recent
        return False
    recent.append(now)
    _hits[key] = recent
    return True
