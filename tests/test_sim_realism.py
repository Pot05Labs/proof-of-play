"""Football realism of pop.sim over many seeds: totals, styles, game state, VAR, physical load."""

from __future__ import annotations

import itertools
import statistics
from collections import Counter
from functools import cache

from pop.sim import generate

N_SEEDS = 20


@cache
def match(seed: int, home: str = "high_press", away: str = "low_block", var: bool = False):
    return generate(seed, home, away, var_overturn=var)


def counts(events, team_id=None):
    c = Counter()
    for e in events:
        if team_id is None or e.team_id == team_id:
            c[e.type.value] += 1
            if e.type.value == "shot" and e.outcome == "goal":
                c["goal_shot"] += 1
    return c


def standing_goals(events):
    overturned = {
        e.meta["subject_event_id"]
        for e in events
        if e.type.value == "var_decision" and e.meta["decision"] == "overturned"
    }
    score = Counter()
    for e in events:
        if e.type.value == "shot" and e.outcome == "goal" and e.event_id not in overturned:
            score[e.team_id] += 1
    return score


def test_match_totals_are_realistic_over_20_seeds():
    shots, passes, fouls, goals_per_team = [], [], [], []
    for seed in range(N_SEEDS):
        info, events = match(seed)
        c = counts(events)
        shots.append(c["shot"])
        passes.append(c["pass"])
        fouls.append(c["foul"])
        score = standing_goals(events)
        goals_per_team += [score[info.home.team_id], score[info.away.team_id]]
        # Loose per-match bounds: real matches vary a lot.
        assert 8 <= c["shot"] <= 45, (seed, c["shot"])
        assert 700 <= c["pass"] <= 1250, (seed, c["pass"])
        assert 6 <= c["foul"] <= 45, (seed, c["foul"])
    # Tight bounds on the 20-seed mean.
    assert 20 <= statistics.mean(shots) <= 30, statistics.mean(shots)
    assert 800 <= statistics.mean(passes) <= 1100, statistics.mean(passes)
    assert 15 <= statistics.mean(fouls) <= 32, statistics.mean(fouls)
    assert 1.8 <= 2 * statistics.mean(goals_per_team) <= 4.0
    assert sum(g <= 4 for g in goals_per_team) / len(goals_per_team) >= 0.95
    assert max(goals_per_team) <= 7


def test_pass_completion_is_realistic():
    for seed in range(N_SEEDS):
        _, events = match(seed)
        passes = [e for e in events if e.type.value == "pass"]
        rate = sum(e.outcome == "success" for e in passes) / len(passes)
        assert 0.65 <= rate <= 0.92, (seed, rate)


def test_shots_come_mostly_from_the_final_third():
    xs = [e.x for seed in range(N_SEEDS) for e in match(seed)[1] if e.type.value == "shot"]
    assert sum(x >= 66.7 for x in xs) / len(xs) >= 0.9
    assert min(xs) >= 55


def test_structure_kickoffs_halves_and_added_time():
    for seed in range(N_SEEDS):
        _, events = match(seed)
        types = [e.type.value for e in events]
        assert types[0] == "match_start" and types[-1] == "full_time"
        assert types.count("kick_off") == 2 and types.count("half_time") == 1
        ht = next(e for e in events if e.type.value == "half_time")
        ft = events[-1]
        assert ht.clock.period == 1 and 1 <= ht.meta["added_minutes"] <= 5
        assert ft.clock.period == 2 and 2 <= ft.meta["added_minutes"] <= 10
        assert 45 + ht.meta["added_minutes"] <= ht.clock.minute <= 46 + ht.meta["added_minutes"]
        assert 90 + ft.meta["added_minutes"] <= ft.clock.minute <= 91 + ft.meta["added_minutes"]
        kos = [e for e in events if e.type.value == "kick_off"]
        assert kos[0].team_id != kos[1].team_id


def test_three_to_five_substitutions_per_team_in_the_second_half():
    for seed in range(N_SEEDS):
        info, events = match(seed)
        subs = [e for e in events if e.type.value == "substitution"]
        assert all(e.clock.period == 2 for e in subs)
        per_team = Counter(e.team_id for e in subs)
        for team in (info.home, info.away):
            assert 3 <= per_team[team.team_id] <= 5, (seed, team.team_id, per_team)
            bench = {p.player_id for p in team.squad if not p.starter}
            for e in subs:
                if e.team_id == team.team_id:
                    assert e.meta["player_in_id"] in bench
                    assert e.meta["player_out_id"] not in bench


def test_cards_are_occasional():
    yellows = reds = fouls = 0
    for seed in range(N_SEEDS):
        for e in match(seed)[1]:
            if e.type.value == "foul":
                fouls += 1
                yellows += e.meta["card"] == "yellow"
                reds += e.meta["card"] == "red"
    assert 0.08 <= yellows / fouls <= 0.25
    assert reds <= N_SEEDS  # well under one red per match on average


def test_possession_changes_follow_turnovers():
    _, events = match(5)
    causes = Counter(e.meta["cause"] for e in events if e.type.value == "possession_change")
    assert causes["interception"] > 0 and causes["tackle"] > 0
    for prev, e in itertools.pairwise(events):
        if prev.type.value == "tackle" and prev.outcome == "won":
            assert e.type.value == "possession_change" and e.team_id == prev.team_id


def _pressure_share(home, away):
    """Pressures by each side summed over seeds, as (home_total, away_total)."""
    h = a = 0
    for seed in range(N_SEEDS):
        info, events = match(seed, home, away)
        c_h = counts(events, info.home.team_id)
        c_a = counts(events, info.away.team_id)
        h += c_h["pressure"]
        a += c_a["pressure"]
    return h, a


def test_high_press_presses_more_than_low_block_both_venues():
    hp_home, lb_away = _pressure_share("high_press", "low_block")
    lb_home, hp_away = _pressure_share("low_block", "high_press")
    assert hp_home > 1.3 * lb_away
    assert hp_away > 1.3 * lb_home
    wins = 0
    for seed in range(N_SEEDS):
        info, events = match(seed)
        wins += counts(events, info.home.team_id)["pressure"] > counts(events, info.away.team_id)["pressure"]
    assert wins >= 16


def test_high_press_presses_higher_up_low_block_sits_deep():
    hp_x, lb_x = [], []
    for seed in range(N_SEEDS):
        info, events = match(seed)
        for e in events:
            if e.type.value == "pressure":
                (hp_x if e.team_id == info.home.team_id else lb_x).append(e.x)
    assert statistics.mean(hp_x) > statistics.mean(lb_x) + 15


def test_possession_plays_shorter_passes_than_direct():
    poss_len, direct_len = [], []
    for seed in range(N_SEEDS):
        info, events = match(seed, "possession", "direct")
        for e in events:
            if e.type.value == "pass" and "set_piece" not in e.meta:
                (poss_len if e.team_id == info.home.team_id else direct_len).append(e.meta["length_m"])
    assert statistics.mean(direct_len) > statistics.mean(poss_len) + 3
    assert len(poss_len) > len(direct_len)


def test_low_block_counters_produce_counter_shots():
    situations = Counter()
    for seed in range(N_SEEDS):
        info, events = match(seed)
        for e in events:
            if e.type.value == "shot" and e.team_id == info.away.team_id:
                situations[e.meta["situation"]] += 1
    assert situations["counter"] > 0
    assert situations["counter"] / sum(situations.values()) > 0.1


def test_trailing_team_presses_harder_and_goes_longer_after_60():
    """Compare the same team trailing after 60' against itself level or ahead after 60'."""
    trailing = {"press": 0, "opp_actions": 0, "long": 0, "passes": 0}
    other = {"press": 0, "opp_actions": 0, "long": 0, "passes": 0}
    for seed in range(40):
        info, events = match(seed, "direct", "direct")
        overturned = {
            e.meta["subject_event_id"]
            for e in events
            if e.type.value == "var_decision" and e.meta["decision"] == "overturned"
        }
        score = Counter()
        for e in events:
            if e.type.value == "shot" and e.outcome == "goal" and e.event_id not in overturned:
                score[e.team_id] += 1
            if e.clock.period != 2 or e.clock.minute < 62:
                continue
            for team_id in (info.home.team_id, info.away.team_id):
                opp = info.away.team_id if team_id == info.home.team_id else info.home.team_id
                bucket = trailing if score[team_id] < score[opp] else other
                if e.type.value == "pressure" and e.team_id == team_id:
                    bucket["press"] += 1
                if e.type.value in {"pass", "carry"} and e.team_id == opp:
                    bucket["opp_actions"] += 1
                if e.type.value == "pass" and e.team_id == team_id and "set_piece" not in e.meta:
                    bucket["passes"] += 1
                    bucket["long"] += e.meta["length_m"] >= 28
    assert trailing["opp_actions"] > 300 and other["opp_actions"] > 300
    assert trailing["press"] / trailing["opp_actions"] > 1.15 * other["press"] / other["opp_actions"]
    assert trailing["long"] / trailing["passes"] > other["long"] / other["passes"]


def test_var_overturn_chain_references_the_goal_shot():
    for seed in range(N_SEEDS):
        _, events = match(seed, var=True)
        by_id = {e.event_id: e for e in events}
        decisions = [
            e for e in events if e.type.value == "var_decision" and e.meta["decision"] == "overturned"
        ]
        assert len(decisions) == 1, seed
        dec = decisions[0]
        shot = by_id[dec.meta["subject_event_id"]]
        assert shot.type.value == "shot" and shot.outcome == "goal"
        assert dec.related == [shot.event_id]
        reviews = [
            e for e in events if e.type.value == "var_review" and e.meta["subject_event_id"] == shot.event_id
        ]
        assert len(reviews) == 1
        review = reviews[0]
        assert review.related == [shot.event_id]
        assert shot.seq < review.seq < dec.seq
        assert shot.t_ms < review.t_ms < dec.t_ms
        between = [e.type.value for e in events[shot.seq : dec.seq - 1]]
        assert set(between) <= {"var_review", "player_tracking"}
        after = next(e for e in events[dec.seq :] if e.type.value != "player_tracking")
        assert after.type.value == "possession_change" and after.meta["cause"] == "var_overturn"
        assert after.team_id != shot.team_id


def test_no_overturn_without_the_flag():
    for seed in range(N_SEEDS):
        for e in match(seed)[1]:
            if e.type.value == "var_decision":
                assert e.meta["decision"] == "stands"


def test_var_flag_keeps_the_rest_of_the_match_valid():
    for seed in range(5):
        info, events = match(seed, var=True)
        assert info.match_id.endswith("-var")
        assert events[-1].type.value == "full_time"


def _full_match_players(info, events):
    changed = set()
    for e in events:
        if e.type.value == "substitution":
            changed |= {e.meta["player_in_id"], e.meta["player_out_id"]}
        if e.type.value == "player_tracking" and e.meta.get("snapshot") == "sent_off":
            changed.add(e.player_id)
    return [p for t in (info.home, info.away) for p in t.squad if p.starter and p.player_id not in changed]


def test_distances_and_speeds_in_range():
    for home, away in [("high_press", "low_block"), ("possession", "possession"), ("direct", "high_press")]:
        for seed in range(N_SEEDS):
            info, events = match(seed, home, away)
            tracking = [e for e in events if e.type.value == "player_tracking"]
            last, prev_total = {}, {}
            for e in tracking:
                total = e.meta["distance_m_total"]
                assert total >= prev_total.get(e.player_id, 0.0), e.event_id
                prev_total[e.player_id] = total
                assert 0 <= e.meta["top_speed_kmh"] <= 37
                last[e.player_id] = e
            for p in _full_match_players(info, events):
                d = last[p.player_id].meta["distance_m_total"]
                if p.position == "GK":
                    assert 5000 <= d <= 6500, (seed, p.player_id, d)
                else:
                    assert 9000 <= d <= 12500, (seed, p.player_id, d)
                    assert 8 <= last[p.player_id].meta["sprints"] <= 60


def test_tracking_every_60_seconds_for_every_player_on_the_pitch():
    info, events = match(9)
    on = {p.player_id for t in (info.home, info.away) for p in t.squad if p.starter}
    by_minute: dict[tuple[int, int], set[str]] = {}
    for e in events:
        if e.type.value == "substitution":
            on.discard(e.meta["player_out_id"])
            on.add(e.meta["player_in_id"])
        if e.type.value == "player_tracking":
            if e.meta.get("snapshot") == "sent_off":
                on.discard(e.player_id)
            if "snapshot" not in e.meta:
                assert e.clock.second == 0
                by_minute.setdefault((e.clock.period, e.clock.minute), set()).add(e.player_id)
                assert e.player_id in on
    assert len(by_minute) >= 90
    for players in by_minute.values():
        assert 14 <= len(players) <= 22


def test_carry_speed_never_exceeds_reported_top_speed():
    for seed in range(5):
        _, events = match(seed)
        best: dict[str, float] = {}
        for e in events:
            if e.type.value == "carry":
                best[e.player_id] = max(best.get(e.player_id, 0.0), e.meta["player_speed_kmh"])
                assert 5 <= e.meta["player_speed_kmh"] <= 37
            if e.type.value == "player_tracking" and e.player_id in best:
                assert e.meta["top_speed_kmh"] >= best[e.player_id] - 0.11


def test_shot_distance_and_penalty_rate_are_realistic():
    """Median shot distance 13-20 m, a real share from outside the box, penalties under 0.6 a match."""
    distances, penalties, outside = [], 0, 0
    for seed in range(N_SEEDS):
        for e in match(seed)[1]:
            if e.type.value != "shot":
                continue
            distances.append(((100 - e.x) * 1.05) ** 2 + ((50 - e.y) * 0.68) ** 2)
            penalties += e.meta["situation"] == "penalty"
            outside += not (e.x >= 84.3 and 20.4 <= e.y <= 79.6)
    distances = [d**0.5 for d in distances]
    assert 13.0 <= statistics.median(distances) <= 20.0, statistics.median(distances)
    assert 0.2 <= outside / len(distances) <= 0.55
    assert penalties / N_SEEDS < 0.6, penalties / N_SEEDS
