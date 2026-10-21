import pytest

from pop.engine import Engine, EngineConfig, replay
from pop.engine.fixtures import AWAY, HOME, EventBuilder, fictional_match_info
from pop.schema import MatchEvent


def build_scenario() -> tuple[EventBuilder, dict[str, MatchEvent]]:
    """A short match: three goals, the first later overturned by VAR."""
    b = EventBuilder()
    b.add("match_start", meta={"home_team_id": HOME, "away_team_id": AWAY, "competition": "Test Shield",
                               "venue": "Example Park", "seed": 7})
    b.kick_off(HOME)
    for i in range(6):
        b.pass_(HOME, f"H{6 + i % 3}", x=40 + 6 * i, end_x=46 + 6 * i)
    g1 = b.shot(HOME, "H9", x=94, y=50, outcome="goal", speed=95.0)
    b.kick_off(AWAY, dt_ms=30_000)
    for i in range(4):
        b.pass_(AWAY, "A7", x=30 + 10 * i, end_x=40 + 10 * i)
    g2 = b.shot(AWAY, "A10", x=85, y=40, outcome="goal", speed=101.0)
    b.kick_off(HOME, dt_ms=30_000)
    b.pass_(HOME, "H7", ok=False)
    b.possession(AWAY)
    b.shot(AWAY, "A9", x=97, y=50, outcome="saved", speed=70.0)  # big chance
    b.possession(HOME)
    b.add("player_tracking", 20_000, team_id=HOME, player_id="H9",
          meta={"distance_m_total": 5_400.0, "top_speed_kmh": 34.2, "sprints": 9})
    g3 = b.shot(HOME, "H9", x=90, y=60, outcome="goal", speed=88.0)
    b.kick_off(AWAY, dt_ms=30_000)
    b.add("foul", 5_000, team_id=AWAY, player_id="A4", x=50, y=50, meta={"card": "yellow"})
    b.add("foul", 5_000, team_id=AWAY, player_id="A4", x=50, y=50, meta={"card": "yellow"})
    decision = b.var(g1)
    b.pass_(AWAY, "A7")
    b.add("half_time", 10_000)
    return b, {"g1": g1, "g2": g2, "g3": g3, "decision": decision}


def run_scenario():
    b, marks = build_scenario()
    engine, updates = replay(fictional_match_info(), b.events)
    return b, marks, engine, updates


def test_possession_time_weighted_and_sums_to_100():
    b = EventBuilder()
    b.kick_off(HOME)
    b.possession(AWAY, dt_ms=30_000)
    b.possession(HOME, dt_ms=10_000)
    b.pass_(HOME, "H6", dt_ms=20_000)
    eng = Engine(fictional_match_info())
    for e in b.events:
        eng.ingest(e)
        s = eng.state()
        assert abs(s.teams[HOME].possession_pct + s.teams[AWAY].possession_pct - 100.0) < 1e-9
    s = eng.state()
    assert s.teams[HOME].possession_pct == pytest.approx(100 * 50 / 60)


def test_possession_sums_to_100_throughout_scenario():
    b, _ = build_scenario()
    eng = Engine(fictional_match_info())
    for e in b.events:
        eng.ingest(e)
        s = eng.state()
        assert abs(s.teams[HOME].possession_pct + s.teams[AWAY].possession_pct - 100.0) <= 0.01


def test_possession_paused_over_half_time():
    b = EventBuilder()
    b.kick_off(HOME)
    b.add("half_time", 60_000)
    b.period = 2
    b.kick_off(AWAY, dt_ms=900_000)  # 15-minute interval must not count
    b.add("full_time", 60_000)
    eng, _ = replay(fictional_match_info(), b.events)
    s = eng.state()
    assert s.teams[HOME].possession_pct == pytest.approx(50.0)
    assert s.play_ms == 120_000


def test_score_excludes_overturned_goal():
    _, marks, eng, _ = run_scenario()
    s = eng.state()
    assert s.score == {HOME: 1, AWAY: 1}
    assert s.players["H9"].goals == 1
    # The annulled shot no longer counts: only the third goal remains for the home side.
    assert s.teams[HOME].shots == 1
    active_scores = [f for f in eng.facts.active() if f.kind == "score"]
    assert active_scores[-1].value == "1-1"
    assert marks["g1"].event_id not in active_scores[-1].evidence


def test_score_before_overturn_counts_goal():
    b, marks = build_scenario()
    prefix = [e for e in b.events if e.seq < marks["decision"].seq]
    eng, _ = replay(fictional_match_info(), prefix)
    assert eng.state().score == {HOME: 2, AWAY: 1}


def test_retraction_lists_exactly_the_facts_built_on_the_goal():
    _, marks, eng, updates = run_scenario()
    g1 = marks["g1"].event_id
    retraction = next(u.retraction for u in updates if u.retraction is not None)
    assert retraction.subject_event_id == g1
    assert retraction.seq_at == marks["decision"].seq
    expected = [f.fact_id for f in eng.facts if g1 in f.evidence]
    assert retraction.retracted_fact_ids == expected
    kinds = {eng.fact(fid).kind for fid in expected}
    assert {"goal", "score", "xg_team", "xg_player", "shot_speed", "ball_speed_record"} <= kinds
    # The score fact after the third goal ("2-1") cited the first goal, so it is retracted too.
    assert any(eng.fact(fid).kind == "score" and eng.fact(fid).value == "2-1" for fid in expected)
    for fid in expected:
        assert eng.facts.is_retracted(fid)
    # Moments: every moment containing a retracted fact, and only those.
    exp_moments = [m.moment_id for m in eng.moments if set(m.facts) & set(expected)]
    assert retraction.retracted_moment_ids == exp_moments
    assert any(eng.moments[m].kind == "goal" for m in exp_moments)
    for mid in exp_moments:
        assert eng.moments.is_retracted(mid)
    # No surviving fact or moment rests on the overturned goal.
    assert all(g1 not in f.evidence for f in eng.facts.active())
    active_fact_ids = {f.fact_id for f in eng.facts.active()}
    for m in eng.moments.active():
        assert set(m.facts) <= active_fact_ids


def test_overturn_emits_corrected_facts_and_moment():
    _, _, eng, updates = run_scenario()
    upd = next(u for u in updates if u.retraction is not None)
    kinds = [f.kind for f in upd.facts]
    assert kinds[0] == "var_overturn"
    assert "score" in kinds and "xg_team" in kinds
    assert upd.moments and upd.moments[0].kind == "var_overturn"
    xg = next(f for f in upd.facts if f.kind == "xg_team")
    assert xg.value == round(eng.state().teams[HOME].xg, 3)


def test_repeat_and_unknown_and_stands_are_harmless():
    b, marks = build_scenario()
    b.add("var_decision", 1000, meta={"subject_event_id": marks["g1"].event_id, "decision": "overturned"})
    b.add("var_decision", 1000, meta={"subject_event_id": "m1:99999", "decision": "overturned"})
    b.add("var_decision", 1000, meta={"subject_event_id": marks["g3"].event_id, "decision": "stands"})
    eng, updates = replay(fictional_match_info(), b.events)
    assert updates[-3].retraction is None
    unknown = updates[-2].retraction
    assert unknown is not None and unknown.retracted_fact_ids == [] and unknown.retracted_moment_ids == []
    assert updates[-1].retraction is None
    assert eng.state().score == {HOME: 1, AWAY: 1}


def test_every_fact_evidence_was_ingested_before_the_fact():
    b, _, eng, _ = run_scenario()
    seq_of = {e.event_id: e.seq for e in b.events}
    assert len(eng.facts) > 0
    for f in eng.facts:
        assert f.evidence, f.fact_id
        assert f.computed_by == "engine v0.1"
        for eid in f.evidence:
            assert eid in seq_of
            assert seq_of[eid] <= f.seq_at
    for m in eng.moments:
        assert m.facts and all(fid in eng.facts for fid in m.facts)


def test_indices_bounded_at_every_step():
    b, _ = build_scenario()
    eng = Engine(fictional_match_info())
    for e in b.events:
        upd = eng.ingest(e)
        s = eng.state()
        assert -1.0 <= s.momentum <= 1.0
        assert 0.0 <= s.control_chaos <= 1.0
        for t in s.teams.values():
            assert 0.0 <= t.pass_accuracy <= 1.0
            assert 0.0 <= t.territory_share <= 1.0
            assert t.pressing_intensity >= 0.0
        for p in s.players.values():
            assert 0.0 <= p.pass_difficulty_avg <= 1.0
        for m in upd.moments:
            assert 0.0 <= m.importance <= 1.0
        for f in upd.facts:
            if f.unit == "xG":
                assert 0.0 <= float(f.value) <= max(1.0, s.teams[HOME].xg + s.teams[AWAY].xg)


def test_basic_counts_and_player_stats():
    _, _, eng, _ = run_scenario()
    s = eng.state()
    home, away = s.teams[HOME], s.teams[AWAY]
    assert home.passes == 7 and home.passes_completed == 6
    assert home.pass_accuracy == pytest.approx(6 / 7)
    assert away.passes == 5 and away.shots == 2 and away.shots_on_target == 2
    assert away.red_cards == 1 and away.yellow_cards == 2
    h9 = s.players["H9"]
    assert h9.distance_m == 5_400.0 and h9.top_speed_kmh == 34.2 and h9.sprints == 9
    assert h9.touches == 2 and h9.shots == 1
    assert 0 < h9.xg < 1
    assert s.max_ball_speed_kmh == 101.0  # 95 km/h belonged to the annulled shot
    kinds = [f.kind for f in eng.facts.active()]
    for k in ("big_chance_missed", "red_card", "player_top_speed_alert", "player_distance_milestone"):
        assert k in kinds
    red = next(f for f in eng.facts.active() if f.kind == "red_card")
    assert red.value == "second_yellow" and red.subject_id == "A4"


def test_replay_is_byte_identical():
    b, _ = build_scenario()
    e1, u1 = replay(fictional_match_info(), b.events)
    e2, u2 = replay(fictional_match_info(), [MatchEvent.model_validate_json(e.model_dump_json())
                                             for e in b.events])
    assert [u.model_dump_json() for u in u1] == [u.model_dump_json() for u in u2]
    assert e1.state().model_dump_json() == e2.state().model_dump_json()


def test_streaming_equals_batch_on_every_prefix():
    b, _ = build_scenario()
    streaming = Engine(fictional_match_info())
    stream_updates = []
    for k, e in enumerate(b.events, start=1):
        stream_updates.append(streaming.ingest(e))
        streaming.state()  # snapshots must not perturb the engine
        batch, batch_updates = replay(fictional_match_info(), b.events[:k])
        assert streaming.state().model_dump_json() == batch.state().model_dump_json()
        assert [u.model_dump_json() for u in stream_updates] == [u.model_dump_json() for u in batch_updates]


def test_fact_ids_unique_and_deterministic_format():
    _, _, eng, _ = run_scenario()
    ids = [f.fact_id for f in eng.facts]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("m1:F") for i in ids)


def test_rejects_out_of_order_and_foreign_events():
    b, _ = build_scenario()
    eng = Engine(fictional_match_info())
    eng.ingest(b.events[0])
    eng.ingest(b.events[1])
    with pytest.raises(ValueError):
        eng.ingest(b.events[1])
    other = b.events[2].model_copy(update={"match_id": "other"})
    with pytest.raises(ValueError):
        eng.ingest(other)


def test_config_is_respected():
    cfg = EngineConfig(big_chance_xg=0.99)
    b, _ = build_scenario()
    eng, _ = replay(fictional_match_info(), b.events, cfg)
    assert not any(f.kind == "big_chance_missed" for f in eng.facts)
