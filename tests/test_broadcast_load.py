import asyncio
import time

from pop.agents.explainer import Viewer
from pop.api.broadcast import Broadcast


class SlowLLM:
    """Stands in for a slow model: 0.2 s per call, echoes the grounded draft."""

    name = "slow"

    def complete(self, system, user):
        import json
        time.sleep(0.2)
        return json.loads(user)["draft"]


def test_match_clock_never_waits_for_the_model():
    b = Broadcast(seed=7, speed=0, var_overturn=True, llm=SlowLLM(), workers=4)
    b.load()
    home, away = b.info.home, b.info.away
    for i in range(30):
        team = home if i % 2 else away
        b.profiles.add(Viewer(audience="analyst" if i % 3 else "fan", language=["en", "zu", "sw"][i % 3],
                              club_id=team.team_id, player_id=team.squad[i % 11].player_id))

    async def go():
        task = asyncio.create_task(b.run())
        await asyncio.sleep(1.0)
        streamed = b.seq
        pending = b.queue.qsize()
        await task
        return streamed, pending

    streamed, pending = asyncio.run(go())
    assert streamed == len(b.events), "the whole match streamed through while insights were still being written"
    assert pending > 0
    assert b.finished and b.queue.qsize() == 0


def test_profiles_collapse_to_what_changes_the_sentence():
    b = Broadcast(seed=7, speed=0, var_overturn=False, workers=2)
    b.load()
    for p in b.info.home.squad[:11]:
        b.profiles.add(Viewer(audience="fan", language="en", club_id=b.info.home.team_id, player_id=p.player_id))
    asyncio.run(b.run())
    moments_written = {k[0] for k in b.cache}
    # 11 player-specific fan profiles must not mean 11 model calls per moment
    assert len(b.cache) < 4 * len(moments_written)
