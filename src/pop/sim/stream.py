"""Replay simulated events paced by match time, for live demos."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterable, Iterator

from pop.schema import MatchEvent


def _delays(events: Iterable[MatchEvent], speed: float) -> Iterator[tuple[float, MatchEvent]]:
    if speed < 0:
        raise ValueError("speed must be >= 0 (0 means no pacing)")
    prev: int | None = None
    for ev in events:
        delay = 0.0
        if speed > 0 and prev is not None:
            delay = max(0, ev.t_ms - prev) / 1000.0 / speed
        prev = ev.t_ms
        yield delay, ev


def stream(
    events: Iterable[MatchEvent], speed: float = 1.0, sleep: Callable[[float], None] = time.sleep
) -> Iterator[MatchEvent]:
    """Yield events in order, sleeping the t_ms gap divided by `speed`. speed=0 never sleeps."""
    for delay, ev in _delays(events, speed):
        if delay > 0:
            sleep(delay)
        yield ev


async def astream(events: Iterable[MatchEvent], speed: float = 1.0) -> AsyncIterator[MatchEvent]:
    """Async twin of `stream` for event-loop servers."""
    for delay, ev in _delays(events, speed):
        if delay > 0:
            await asyncio.sleep(delay)
        yield ev
