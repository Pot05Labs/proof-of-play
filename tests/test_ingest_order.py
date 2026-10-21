import asyncio
import random

from pop.api.broadcast import Broadcast


def test_apply_is_exactly_once_and_in_order_whatever_the_arrival_order():
    """Simulates Event Hubs and its fallback racing: duplicates and out-of-order arrivals."""
    ref = Broadcast(seed=11, speed=0, var_overturn=True)
    ref.load()

    async def straight():
        for ev in ref.events:
            await ref.apply(ev)
    asyncio.run(straight())

    b = Broadcast(seed=11, speed=0, var_overturn=True)
    b.load()
    rng = random.Random(3)
    arrivals = list(b.events) + rng.sample(b.events, 400)  # 400 duplicates
    window = []  # shuffle within a sliding window, like a late hub plus an eager watchdog

    async def chaotic():
        for ev in arrivals:
            window.append(ev)
            if len(window) >= 5:
                rng.shuffle(window)
                await b.apply(window.pop())
        for ev in window:
            await b.apply(ev)
        for ev in b.events:  # the watchdog's final sweep
            await b.apply(ev)
    asyncio.run(chaotic())

    assert b.seq == len(b.events)
    assert b.engine.state().model_dump() == ref.engine.state().model_dump()
    assert [m.moment_id for m in b.moments] == [m.moment_id for m in ref.moments]
