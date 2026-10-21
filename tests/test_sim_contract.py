"""Contract tests for pop.sim: schema, ids, clock, meta keys, possession, determinism, streaming."""

from __future__ import annotations

import asyncio
import itertools
import json
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from pop.schema import MatchEvent, MatchInfo
from pop.sim import astream, generate, stream, write_match

SEEDS = range(6)
STYLE_PAIRS = [("high_press", "low_block"), ("possession", "direct"), ("direct", "high_press")]

REQUIRED_META = {
    "match_start": {"home_team_id", "away_team_id", "competition", "venue", "seed"},
    "pass": {"receiver_id", "length_m", "angle_deg", "body_part", "ball_speed_kmh"},
    "carry": {"distance_m", "player_speed_kmh"},
    "shot": {"body_part", "situation", "ball_speed_kmh"},
    "foul": {"card"},
    "pressure": {"target_player_id"},
    "possession_change": {"from_team_id", "to_team_id", "cause"},
    "substitution": {"player_out_id", "player_in_id"},
    "var_review": {"subject_event_id", "check"},
    "var_decision": {"subject_event_id", "decision", "reason"},
    "player_tracking": {"distance_m_total", "top_speed_kmh", "sprints"},
}
ALLOWED_OUTCOMES = {
    "pass": {"success", "fail"},
    "shot": {"goal", "saved", "off_target", "blocked"},
    "tackle": {"won", "lost"},
}


@cache
def match(seed: int, home: str = "high_press", away: str = "low_block", var: bool = False):
    return generate(seed, home, away, var_overturn=var)


def all_matches():
    for seed in SEEDS:
        for home, away in STYLE_PAIRS:
            yield match(seed, home, away)
    yield match(3, var=True)


def test_every_event_round_trips_through_the_schema():
    for info, events in all_matches():
        assert isinstance(info, MatchInfo)
        MatchInfo.model_validate_json(info.model_dump_json())
        for ev in events:
            again = MatchEvent.model_validate_json(ev.model_dump_json())
            assert again == ev


def test_seq_and_event_ids():
    for info, events in all_matches():
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        ids = [e.event_id for e in events]
        assert len(set(ids)) == len(ids)
        for e in events:
            assert e.match_id == info.match_id
            assert e.event_id == f"{info.match_id}:{e.seq:05d}"
            assert re.fullmatch(r".+:\d{5}", e.event_id)


def test_clock_monotonic_within_period_and_t_ms_non_decreasing():
    for _, events in all_matches():
        last: dict[int, tuple[int, int]] = {}
        prev_t = -1
        prev_period = 1
        for e in events:
            key = (e.clock.minute, e.clock.second)
            assert key >= last.get(e.clock.period, (-1, -1)), e.event_id
            last[e.clock.period] = key
            assert e.t_ms >= prev_t, e.event_id
            assert e.clock.period >= prev_period
            prev_t, prev_period = e.t_ms, e.clock.period
            reg = 45 if e.clock.period == 1 else 90
            assert e.clock.added == (e.clock.minute - reg + 1 if e.clock.minute >= reg else 0)
            assert e.clock.minute >= (0 if e.clock.period == 1 else 45)


def test_required_meta_and_outcomes_per_type():
    for _, events in all_matches():
        for e in events:
            t = e.type.value
            missing = REQUIRED_META.get(t, set()) - set(e.meta)
            assert not missing, (e.event_id, t, missing)
            if t in ALLOWED_OUTCOMES:
                assert e.outcome in ALLOWED_OUTCOMES[t], e.event_id
            if t == "shot":
                assert e.meta["situation"] in {"open_play", "set_piece", "penalty", "counter"}
                assert 40 <= e.meta["ball_speed_kmh"] <= 130
            if t == "pass":
                assert 15 <= e.meta["ball_speed_kmh"] <= 90
                assert e.meta["receiver_id"] != e.player_id
            if t == "foul":
                assert e.meta["card"] in {"none", "yellow", "red"}
            if t == "var_decision":
                assert e.meta["decision"] in {"stands", "overturned"}
            if t in {"pass", "carry", "shot"}:
                assert None not in (e.x, e.y, e.end_x, e.end_y, e.pressure, e.player_id, e.team_id)


def test_simulator_never_emits_xg_or_difficulty():
    for _, events in all_matches():
        for e in events:
            for key in e.meta:
                assert "xg" not in key.lower() and "difficulty" not in key.lower(), (e.event_id, key)


def test_pass_ball_speed_rises_with_length():
    _, events = match(1)
    passes = [e for e in events if e.type.value == "pass" and e.meta["body_part"] == "foot"]
    short = [e.meta["ball_speed_kmh"] for e in passes if e.meta["length_m"] < 10]
    long_ = [e.meta["ball_speed_kmh"] for e in passes if e.meta["length_m"] > 35]
    assert short and long_
    assert sum(long_) / len(long_) > sum(short) / len(short) + 20


def test_pass_meta_length_matches_coordinates():
    _, events = match(2)
    for e in events:
        if e.type.value == "pass":
            dx = (e.end_x - e.x) * 1.05
            dy = (e.end_y - e.y) * 0.68
            assert abs((dx * dx + dy * dy) ** 0.5 - e.meta["length_m"]) < 0.3, e.event_id


def test_on_ball_actions_belong_to_the_team_in_possession():
    for info, events in all_matches():
        teams = {info.home.team_id, info.away.team_id}
        holder = None
        for e in events:
            t = e.type.value
            if t == "kick_off":
                holder = e.team_id
            elif t == "possession_change":
                assert e.meta["from_team_id"] == holder, e.event_id
                assert e.meta["to_team_id"] == e.team_id != holder
                assert e.team_id in teams
                holder = e.team_id
            elif t in {"pass", "carry", "shot"}:
                assert e.team_id == holder, e.event_id


def test_interception_coordinates_are_flipped_from_the_failed_pass():
    for _, events in all_matches():
        for prev, e in itertools.pairwise(events):
            if e.type.value == "interception" and prev.type.value == "pass":
                assert prev.outcome == "fail"
                assert prev.team_id != e.team_id
                assert abs(e.x - (100 - prev.end_x)) < 0.25
                assert abs(e.y - (100 - prev.end_y)) < 0.25


def test_same_seed_is_byte_identical_in_process():
    a_info, a = generate(11, "possession", "high_press", var_overturn=True)
    b_info, b = generate(11, "possession", "high_press", var_overturn=True)
    assert a_info.model_dump_json() == b_info.model_dump_json()
    assert "\n".join(e.model_dump_json() for e in a) == "\n".join(e.model_dump_json() for e in b)
    _, c = generate(12, "possession", "high_press", var_overturn=True)
    assert [e.model_dump_json() for e in a] != [e.model_dump_json() for e in c]


def test_cli_output_is_byte_identical_across_processes(tmp_path: Path):
    outs = []
    for run in ("a", "b"):
        out = tmp_path / run
        subprocess.run(
            [sys.executable, "-m", "pop.sim", "--seed", "7", "--out", str(out), "--var-overturn"],
            check=True,
            capture_output=True,
        )
        outs.append(out)
    for name in ("match.json", "events.jsonl"):
        assert (outs[0] / name).read_bytes() == (outs[1] / name).read_bytes()
    lines = (outs[0] / "events.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert first["type"] == "match_start" and first["meta"]["seed"] == 7
    info = MatchInfo.model_validate_json((outs[0] / "match.json").read_text())
    assert info.seed == 7 and info.home.style == "high_press" and info.away.style == "low_block"


def test_write_match_matches_generate(tmp_path: Path):
    info, events = match(4)
    _, events_path = write_match(info, events, tmp_path)
    lines = events_path.read_text().splitlines()
    assert len(lines) == len(events)
    assert MatchEvent.model_validate_json(lines[-1]) == events[-1]


def test_stream_speed_zero_never_sleeps():
    _, events = match(0)
    slept: list[float] = []
    out = list(stream(events, speed=0, sleep=slept.append))
    assert out == events and slept == []


def test_stream_paces_by_t_ms_over_speed():
    _, events = match(0)
    head = events[:400]
    slept: list[float] = []
    out = list(stream(head, speed=10.0, sleep=slept.append))
    assert out == head
    expected = (head[-1].t_ms - head[0].t_ms) / 1000.0 / 10.0
    assert sum(slept) == pytest.approx(expected, rel=1e-9)
    assert all(s > 0 for s in slept)


def test_stream_rejects_negative_speed():
    with pytest.raises(ValueError):
        list(stream(match(0)[1][:3], speed=-1))


def test_astream_yields_in_order():
    _, events = match(0)

    async def collect():
        return [e async for e in astream(events[:200], speed=0)]

    assert asyncio.run(collect()) == events[:200]


def test_unknown_style_is_rejected():
    with pytest.raises(ValueError):
        generate(1, "tiki_taka", "low_block")
