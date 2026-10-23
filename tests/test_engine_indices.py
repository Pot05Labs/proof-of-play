from pop.engine import Engine, EngineConfig, replay
from pop.engine.fixtures import AWAY, HOME, EventBuilder, fictional_match_info


def kinds(engine: Engine) -> list[str]:
    return [f.kind for f in engine.facts.active()]


def attacking_spell(b: EventBuilder, team: str, prefix: str, n: int = 4) -> None:
    """A team repeatedly enters the final third and shoots."""
    for _ in range(n):
        b.pass_(team, f"{prefix}8", dt_ms=5_000, x=55, end_x=75)  # final-third entry
        b.shot(team, f"{prefix}9", dt_ms=3_000, x=86, y=45, outcome="saved")


def test_momentum_sign_follows_dominant_team():
    b = EventBuilder()
    b.kick_off(HOME)
    attacking_spell(b, HOME, "H")
    eng = Engine(fictional_match_info())
    for e in b.events:
        eng.ingest(e)
    assert eng.state().momentum > 0
    shifts = [f for f in eng.facts if f.kind == "momentum_shift"]
    assert shifts and shifts[-1].subject_id == HOME and float(shifts[-1].value) > 0

    # Away then dominates for longer than the window: momentum must flip sign.
    b.possession(AWAY)
    b.add("pass", 310_000, team_id=AWAY, player_id="A6", x=30, y=50, end_x=40, end_y=50, outcome="success")
    attacking_spell(b, AWAY, "A")
    for e in b.events[eng.state().seq:]:
        eng.ingest(e)
    assert eng.state().momentum < 0
    shifts = [f for f in eng.facts if f.kind == "momentum_shift"]
    assert shifts[-1].subject_id == AWAY and 0 < float(shifts[-1].value) <= 1  # unsigned swing towards the subject


def test_momentum_needs_minimum_sample():
    b = EventBuilder()
    b.kick_off(HOME)
    b.shot(HOME, "H9", x=95, y=50)
    eng, _ = replay(fictional_match_info(), b.events)
    assert eng.state().momentum > 0
    assert "momentum_shift" not in kinds(eng)


def test_pressure_spike_with_hysteresis():
    b = EventBuilder()
    b.kick_off(AWAY)
    for _ in range(6):
        b.pass_(AWAY, "A6")
        b.pressure(HOME, "H8")
    b.pressure(HOME, "H9")
    eng, _ = replay(fictional_match_info(), b.events)
    spikes = [f for f in eng.facts if f.kind == "pressure_spike"]
    assert len(spikes) == 1  # stays disarmed while intensity remains high
    assert spikes[0].subject_id == HOME and float(spikes[0].value) >= 0.6
    assert eng.state().teams[HOME].pressing_intensity >= 1.0
    assert any(m.kind == "pressure_spike" for m in eng.moments)


def test_pressure_spike_requires_min_opponent_passes():
    b = EventBuilder()
    b.kick_off(AWAY)
    for _ in range(3):
        b.pass_(AWAY, "A6")
        b.pressure(HOME, "H8")
    eng, _ = replay(fictional_match_info(), b.events)
    assert "pressure_spike" not in kinds(eng)


def test_control_to_chaos_and_back():
    cfg = EngineConfig(window_ms=60_000, min_window_ms=30_000)
    b = EventBuilder()
    b.kick_off(HOME)
    for _ in range(12):  # calm: same-length passes, no pressure, no turnovers
        b.pass_(HOME, "H6", dt_ms=5_000, x=40, end_x=50, pressure=0.0)
    chaos_start = len(b.events)
    for i in range(16):  # frantic: turnovers, mixed lengths, heavy pressure
        team = HOME if i % 2 else AWAY
        b.possession(team, dt_ms=2_000)
        end = 45 if i % 3 else 95
        b.pass_(team, "H7" if team == HOME else "A7", dt_ms=2_000, x=10, end_x=end, pressure=0.9, ok=False)
    for _ in range(14):
        b.pass_(HOME, "H6", dt_ms=5_000, x=40, end_x=50, pressure=0.0)
    eng, updates = replay(fictional_match_info(), b.events, cfg)
    ks = [f.kind for f in eng.facts]
    assert "control_to_chaos" in ks and "chaos_to_control" in ks
    assert ks.index("control_to_chaos") < ks.index("chaos_to_control")
    first = next(u for u in updates if any(f.kind == "control_to_chaos" for f in u.facts))
    assert first.seq > chaos_start
    for f in eng.facts:
        if f.kind in ("control_to_chaos", "chaos_to_control"):
            assert 0.0 <= float(f.value) <= 1.0
            assert f.window == "1min"


def test_pass_streak_emits_at_min_and_steps_and_resets():
    b = EventBuilder()
    b.kick_off(HOME)
    for _ in range(13):
        b.pass_(HOME, "H6")
    b.pass_(HOME, "H6", ok=False)
    for _ in range(7):
        b.pass_(HOME, "H6")
    eng, _ = replay(fictional_match_info(), b.events)
    streaks = [f for f in eng.facts if f.kind == "pass_streak"]
    assert [s.value for s in streaks] == [8, 13]
    assert len(streaks[1].evidence) == 13


def test_opponent_action_breaks_streak():
    b = EventBuilder()
    b.kick_off(HOME)
    for _ in range(5):
        b.pass_(HOME, "H6")
    b.add("interception", 1000, team_id=AWAY, player_id="A3", x=40, y=50)
    b.possession(HOME)
    for _ in range(5):
        b.pass_(HOME, "H6")
    eng, _ = replay(fictional_match_info(), b.events)
    assert "pass_streak" not in kinds(eng)


def test_tracking_alerts_fire_once():
    b = EventBuilder()
    b.kick_off(HOME)
    b.add("player_tracking", 60_000, team_id=HOME, player_id="H11",
          meta={"distance_m_total": 4_000.0, "top_speed_kmh": 30.0, "sprints": 2})
    b.add("player_tracking", 60_000, team_id=HOME, player_id="H11",
          meta={"distance_m_total": 5_200.0, "top_speed_kmh": 33.5, "sprints": 4})
    b.add("player_tracking", 60_000, team_id=HOME, player_id="H11",
          meta={"distance_m_total": 10_400.0, "top_speed_kmh": 35.0, "sprints": 6})
    b.add("player_tracking", 60_000, team_id=HOME, player_id="H11",
          meta={"distance_m_total": 10_900.0, "top_speed_kmh": 35.5, "sprints": 7})
    eng, _ = replay(fictional_match_info(), b.events)
    alerts = [f for f in eng.facts if f.kind == "player_top_speed_alert"]
    miles = [f for f in eng.facts if f.kind == "player_distance_milestone"]
    assert [a.value for a in alerts] == [33.5]
    assert [m.value for m in miles] == [5000.0, 10000.0]
    assert eng.state().players["H11"].top_speed_kmh == 35.5


def test_straight_red_and_carry_speed():
    b = EventBuilder()
    b.kick_off(HOME)
    b.add("carry", 2_000, team_id=HOME, player_id="H10", x=50, y=50, end_x=70, end_y=50,
          meta={"distance_m": 21.0, "player_speed_kmh": 34.0})
    b.add("foul", 2_000, team_id=AWAY, player_id="A5", x=60, y=50, meta={"card": "red"})
    eng, _ = replay(fictional_match_info(), b.events)
    s = eng.state()
    assert s.players["H10"].distance_m == 21.0
    assert s.teams[HOME].final_third_entries == 1
    assert s.teams[AWAY].red_cards == 1
    assert {"player_top_speed_alert", "red_card"} <= set(kinds(eng))


def test_possession_swing():
    b = EventBuilder()
    b.kick_off(AWAY)
    b.pass_(AWAY, "A6", dt_ms=30_000)
    b.possession(HOME, dt_ms=10_000)
    for _ in range(10):
        b.pass_(HOME, "H6", dt_ms=20_000)
    eng, _ = replay(fictional_match_info(), b.events)
    swings = [f for f in eng.facts if f.kind == "possession_swing"]
    assert len(swings) == 1 and swings[0].subject_id == HOME
    assert float(swings[0].value) >= 65.0


def test_penalty_shot_xg_and_rocket_shot():
    b = EventBuilder()
    b.kick_off(HOME)
    b.shot(HOME, "H9", x=89.5, situation="penalty", outcome="saved", speed=80.0)
    b.shot(HOME, "H10", x=72, y=50, outcome="off_target", speed=118.0)
    eng, _ = replay(fictional_match_info(), b.events)
    s = eng.state()
    assert s.players["H9"].xg == 0.76
    assert any(m.kind == "big_chance" for m in eng.moments)  # 0.76 >= 0.3, missed
    assert any(m.kind == "rocket_shot" for m in eng.moments)
    speeds = [f.value for f in eng.facts if f.kind == "shot_speed"]
    assert speeds == [80.0, 118.0]
