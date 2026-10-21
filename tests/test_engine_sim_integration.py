"""Engine invariants over full simulated matches (SPEC section 6)."""

import pytest

from pop.engine import replay
from pop.sim import generate


@pytest.mark.parametrize("seed", [3, 11])
def test_engine_invariants_on_simulated_match(seed):
    info, events = generate(seed, "high_press", "low_block", var_overturn=True)
    engine, updates = replay(info, events)
    state = engine.state()

    overturned = {
        e.meta["subject_event_id"] for e in events
        if e.type.value == "var_decision" and e.meta.get("decision") == "overturned"
    }
    assert overturned, "scenario must exercise a VAR overturn"
    for team in (info.home.team_id, info.away.team_id):
        goals = [e for e in events if e.type.value == "shot" and e.outcome == "goal" and e.team_id == team]
        assert state.score[team] == len([g for g in goals if g.event_id not in overturned])

    pos = sum(t.possession_pct for t in state.teams.values())
    assert abs(pos - 100.0) <= 0.01
    assert -1 <= state.momentum <= 1 and 0 <= state.control_chaos <= 1

    seen = {e.event_id for e in events}
    for f in engine.facts:
        assert f.evidence and set(f.evidence) <= seen
    for f in engine.facts.active():
        assert not (set(f.evidence) & overturned)
    for m in engine.moments:
        assert 0 <= m.importance <= 1

    retractions = [u.retraction for u in updates if u.retraction is not None]
    assert {r.subject_event_id for r in retractions} == overturned

    again, _ = replay(info, events)
    assert again.state().model_dump_json() == state.model_dump_json()
