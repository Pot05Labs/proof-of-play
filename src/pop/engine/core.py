"""The deterministic, incremental match engine.

The engine consumes ``MatchEvent`` objects one at a time and is the only source
of numbers in the product. It never looks ahead: every output at ``seq`` is a
function of the events with ``seq`` less than or equal to it.

Time base. Rolling windows and possession use a *play clock*: the sum of
``t_ms`` deltas while play is running (``kick_off`` to ``half_time`` or
``full_time``). The interval is excluded, so a 5-minute window at the start of
the second half covers the last minutes of the first. Negative ``t_ms`` deltas
are clamped to zero.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from pop.engine.config import EngineConfig
from pop.engine.models import pass_difficulty, pass_vector, shot_xg
from pop.engine.registry import Registry
from pop.engine.state import PlayerStats, State, TeamStats
from pop.schema import EventType, Fact, MatchEvent, MatchInfo, Moment, Retraction

DEFAULT_SHOT_X = 89.5  # penalty-spot distance (11 m) when a shot has no coordinates
DEFAULT_SHOT_Y = 50.0
ON_BALL_TYPES = {
    EventType.PASS,
    EventType.CARRY,
    EventType.SHOT,
    EventType.TACKLE,
    EventType.INTERCEPTION,
    EventType.CLEARANCE,
}


class EngineUpdate(BaseModel):
    seq: int
    event_id: str
    facts: list[Fact] = Field(default_factory=list)
    moments: list[Moment] = Field(default_factory=list)
    retraction: Retraction | None = None


@dataclass
class _ShotRec:
    event_id: str
    team_id: str
    player_id: str | None
    xg: float
    on_target: bool
    goal: bool


@dataclass
class _WinItem:
    play_ms: int
    kind: str  # shot | entry | pressure | pass | pc | press_val
    team_id: str | None
    value: float
    event_id: str


@dataclass
class _Segment:
    team_id: str
    start_ms: int
    end_ms: int
    event_id: str


class Engine:
    def __init__(self, match_info: MatchInfo, config: EngineConfig | None = None) -> None:
        self.info = match_info
        self.cfg = config or EngineConfig()
        self.home = match_info.home.team_id
        self.away = match_info.away.team_id
        self.facts: Registry[Fact] = Registry()
        self.moments: Registry[Moment] = Registry()

        self._last_seq = 0
        self._last_t: int | None = None
        self._t_ms = 0
        self._play_ms = 0
        self._running = False
        self._period = 1
        self._minute = 0
        self._ingested: dict[str, None] = {}

        self._teams = {t: TeamStats(team_id=t) for t in (self.home, self.away)}
        self._players: dict[str, PlayerStats] = {}
        for team in (match_info.home, match_info.away):
            for p in team.squad:
                self._players[p.player_id] = PlayerStats(player_id=p.player_id, team_id=team.team_id)
        self._difficulty_sum: dict[str, float] = {}
        self._carry_distance: dict[str, float] = {}
        self._has_tracking: set[str] = set()

        # possession
        self._owner: str | None = None
        self._seg_start = 0
        self._seg_event = ""
        self._segments: deque[_Segment] = deque()
        self._possession_ms = {self.home: 0, self.away: 0}

        # territory
        self._located_actions = {self.home: 0, self.away: 0}
        self._final_third_actions = {self.home: 0, self.away: 0}

        # shots and goals
        self._shots: dict[str, _ShotRec] = {}
        self._annulled: dict[str, None] = {}
        self._ball_speeds: dict[str, float] = {}
        self._red_events: dict[str, tuple[str, str | None]] = {}
        self._var_reviews: dict[str, str] = {}

        # rolling window
        self._window: deque[_WinItem] = deque()
        self._momentum = 0.0
        self._chaos = 0.0
        self._pressing = {self.home: 0.0, self.away: 0.0}

        # hysteresis
        self._momentum_side: str | None = None
        self._pressure_armed = {self.home: True, self.away: True}
        self._chaos_regime: str | None = None
        self._possession_leader: str | None = None
        self._streak_team: str | None = None
        self._streak: list[str] = []
        self._speed_alerted: set[str] = set()
        self._milestones: dict[str, set[float]] = {}

        # indices
        self._evidence_index: dict[str, list[str]] = {}
        self._fact_moments: dict[str, list[str]] = {}

        # per-ingest scratch
        self._ordinal = 0
        self._cur: MatchEvent | None = None
        self._new_facts: list[Fact] = []
        self._new_moments: list[Moment] = []

    # ------------------------------------------------------------------ public

    def fact(self, fact_id: str) -> Fact:
        return self.facts[fact_id]

    def ingest_many(self, events: Iterable[MatchEvent]) -> list[EngineUpdate]:
        return [self.ingest(e) for e in events]

    def ingest(self, event: MatchEvent) -> EngineUpdate:
        if event.match_id != self.info.match_id:
            raise ValueError(f"event {event.event_id} belongs to match {event.match_id}")
        if event.seq <= self._last_seq:
            raise ValueError(f"seq {event.seq} is not greater than {self._last_seq}")
        if event.event_id in self._ingested:
            raise ValueError(f"duplicate event_id {event.event_id}")
        self._cur = event
        self._ordinal = 0
        self._new_facts = []
        self._new_moments = []
        self._ingested[event.event_id] = None
        self._last_seq = event.seq

        self._advance_clock(event)
        retraction = self._dispatch(event)
        self._evaluate_windows()

        update = EngineUpdate(
            seq=event.seq,
            event_id=event.event_id,
            facts=list(self._new_facts),
            moments=list(self._new_moments),
            retraction=retraction,
        )
        self._cur = None
        return update

    def state(self) -> State:
        """Pure snapshot; never mutates engine state."""
        teams: dict[str, TeamStats] = {}
        pos_total = self._possession_ms[self.home] + self._possession_ms[self.away]
        home_pos = 100.0 * self._possession_ms[self.home] / pos_total if pos_total else 50.0
        ft_total = self._final_third_actions[self.home] + self._final_third_actions[self.away]
        home_terr = 100.0 * self._final_third_actions[self.home] / ft_total if ft_total else 50.0
        for tid in (self.home, self.away):
            t = self._teams[tid].model_copy(deep=True)
            t.possession_pct = home_pos if tid == self.home else 100.0 - home_pos
            t.territory_pct = home_terr if tid == self.home else 100.0 - home_terr
            located = self._located_actions[tid]
            t.territory_share = self._final_third_actions[tid] / located if located else 0.0
            t.pass_accuracy = t.passes_completed / t.passes if t.passes else 0.0
            t.pressing_intensity = self._pressing[tid]
            teams[tid] = t
        players: dict[str, PlayerStats] = {}
        for pid, p in self._players.items():
            q = p.model_copy(deep=True)
            if q.passes:
                q.pass_difficulty_avg = self._difficulty_sum.get(pid, 0.0) / q.passes
            if pid not in self._has_tracking:
                q.distance_m = self._carry_distance.get(pid, 0.0)
            players[pid] = q
        return State(
            match_id=self.info.match_id,
            seq=self._last_seq,
            t_ms=self._t_ms,
            play_ms=self._play_ms,
            period=self._period,
            minute=self._minute,
            home_team_id=self.home,
            away_team_id=self.away,
            score={tid: teams[tid].goals for tid in (self.home, self.away)},
            teams=teams,
            players=players,
            momentum=self._momentum,
            control_chaos=self._chaos,
            max_ball_speed_kmh=max(self._ball_speeds.values(), default=0.0),
            facts_total=len(self.facts),
            facts_retracted=len(self.facts.retracted_ids),
            moments_total=len(self.moments),
            moments_retracted=len(self.moments.retracted_ids),
        )

    # ------------------------------------------------------------- emission

    def _r(self, v: float) -> float:
        return round(v, self.cfg.fact_decimals)

    def _emit_fact(
        self,
        kind: str,
        subject_kind: str,
        subject_id: str,
        value: float | str,
        evidence: list[str],
        unit: str = "",
        window: str = "match",
    ) -> Fact:
        assert self._cur is not None
        ev = list(dict.fromkeys(evidence))
        if not ev:
            ev = [self._cur.event_id]
        self._ordinal += 1
        f = Fact(
            fact_id=f"{self.info.match_id}:F{self._cur.seq:05d}.{self._ordinal:02d}:{kind}",
            seq_at=self._cur.seq,
            kind=kind,
            subject_kind=subject_kind,  # type: ignore[arg-type]
            subject_id=subject_id,
            value=value,
            unit=unit,
            window=window,
            evidence=ev,
            computed_by=self.cfg.version,
        )
        self.facts.add(f)
        for eid in ev:
            self._evidence_index.setdefault(eid, []).append(f.fact_id)
        self._new_facts.append(f)
        return f

    def _emit_moment(self, kind: str, importance: float, facts: list[Fact]) -> Moment | None:
        assert self._cur is not None
        imp = min(1.0, max(0.0, importance))
        if not facts or imp < self.cfg.importance.min_importance:
            return None
        self._ordinal += 1
        m = Moment(
            moment_id=f"{self.info.match_id}:M{self._cur.seq:05d}.{self._ordinal:02d}:{kind}",
            seq_at=self._cur.seq,
            kind=kind,
            importance=self._r(imp),
            facts=[f.fact_id for f in facts],
        )
        self.moments.add(m)
        for f in facts:
            self._fact_moments.setdefault(f.fact_id, []).append(m.moment_id)
        self._new_moments.append(m)
        return m

    def _window_label(self) -> str:
        ms = self.cfg.window_ms
        return f"{ms // 60_000}min" if ms % 60_000 == 0 else f"{ms // 1000}s"

    def _base(self, kind: str) -> float:
        return self.cfg.importance.base.get(kind, 0.0)

    # ---------------------------------------------------------------- clock

    def _advance_clock(self, e: MatchEvent) -> None:
        if self._last_t is not None and self._running:
            delta = max(0, e.t_ms - self._last_t)
            self._play_ms += delta
            if self._owner is not None:
                self._possession_ms[self._owner] += delta
        self._last_t = e.t_ms
        self._t_ms = e.t_ms
        self._period = e.clock.period
        self._minute = e.clock.minute
        if not self._running and e.type in ON_BALL_TYPES | {EventType.POSSESSION_CHANGE}:
            self._running = True  # robustness: play events imply the clock is running

    # ------------------------------------------------------------- dispatch

    def _team_of(self, e: MatchEvent) -> str | None:
        if e.team_id is not None:
            return e.team_id
        if e.player_id is not None and e.player_id in self._players:
            return self._players[e.player_id].team_id
        return None

    def _player(self, pid: str | None, team: str | None) -> PlayerStats | None:
        if pid is None:
            return None
        if pid not in self._players:
            self._players[pid] = PlayerStats(player_id=pid, team_id=team or "")
        return self._players[pid]

    def _dispatch(self, e: MatchEvent) -> Retraction | None:
        team = self._team_of(e)
        t = e.type
        if t in ON_BALL_TYPES and team is not None:
            self._on_ball_common(e, team)
        if t == EventType.KICK_OFF:
            self._running = True
            if team is not None:
                self._set_owner(team, e.event_id)
        elif t in (EventType.HALF_TIME, EventType.FULL_TIME):
            self._running = False
            self._reset_streak()
        elif t == EventType.POSSESSION_CHANGE:
            to_team = e.meta.get("to_team_id") or team
            if to_team is not None:
                self._window.append(_WinItem(self._play_ms, "pc", to_team, 1.0, e.event_id))
                self._set_owner(to_team, e.event_id)
                if self._streak_team is not None and to_team != self._streak_team:
                    self._reset_streak()
        elif t == EventType.PASS and team is not None:
            self._on_pass(e, team)
        elif t == EventType.CARRY and team is not None:
            self._on_carry(e, team)
        elif t == EventType.SHOT and team is not None:
            self._on_shot(e, team)
        elif t == EventType.PRESSURE and team is not None:
            self._window.append(_WinItem(self._play_ms, "pressure", team, 1.0, e.event_id))
        elif t == EventType.FOUL and team is not None:
            self._on_foul(e, team)
        elif t == EventType.PLAYER_TRACKING:
            self._on_tracking(e, team)
        elif t == EventType.VAR_REVIEW:
            subject = e.meta.get("subject_event_id") or (e.related[0] if e.related else None)
            if subject:
                self._var_reviews[subject] = e.event_id
        elif t == EventType.VAR_DECISION:
            return self._on_var_decision(e)
        return None

    def _set_owner(self, team: str, event_id: str) -> None:
        if team == self._owner:
            return
        if self._owner is not None and self._play_ms > self._seg_start:
            self._segments.append(_Segment(self._owner, self._seg_start, self._play_ms, self._seg_event))
        self._owner = team
        self._seg_start = self._play_ms
        self._seg_event = event_id

    def _on_ball_common(self, e: MatchEvent, team: str) -> None:
        p = self._player(e.player_id, team)
        if p is not None:
            p.touches += 1
        if e.x is not None and team in self._located_actions:
            self._located_actions[team] += 1
            if e.x >= self.cfg.final_third_x:
                self._final_third_actions[team] += 1
        if e.pressure is not None:
            self._window.append(_WinItem(self._play_ms, "press_val", team, e.pressure, e.event_id))
        # Any on-ball action by the other side ends a passing streak.
        if self._streak_team is not None and team != self._streak_team:
            self._reset_streak()

    def _is_entry(self, e: MatchEvent) -> bool:
        f = self.cfg.final_third_x
        return e.x is not None and e.end_x is not None and e.x < f <= e.end_x

    def _record_entry(self, e: MatchEvent, team: str) -> None:
        self._teams[team].final_third_entries += 1
        self._window.append(_WinItem(self._play_ms, "entry", team, 1.0, e.event_id))

    def _ball_speed(self, e: MatchEvent, owner_subject: tuple[str, str]) -> Fact | None:
        speed = e.meta.get("ball_speed_kmh")
        if speed is None:
            return None
        speed = float(speed)
        prev = max(self._ball_speeds.values(), default=0.0)
        self._ball_speeds[e.event_id] = speed
        if speed > prev and speed >= self.cfg.ball_speed_record_min_kmh:
            return self._emit_fact(
                "ball_speed_record", owner_subject[0], owner_subject[1], self._r(speed),
                [e.event_id], unit="km/h",
            )
        return None

    def _subject(self, e: MatchEvent, team: str) -> tuple[str, str]:
        return ("player", e.player_id) if e.player_id else ("team", team)

    # ---------------------------------------------------------------- passes

    def _on_pass(self, e: MatchEvent, team: str) -> None:
        ts = self._teams[team]
        success = e.outcome == "success"
        ts.passes += 1
        ts.passes_completed += int(success)
        length, angle = pass_vector(
            e.x, e.y, e.end_x, e.end_y, e.meta.get("length_m"), e.meta.get("angle_deg"), self.cfg.pitch
        )
        diff = pass_difficulty(length, angle, e.pressure, self.cfg.pass_difficulty)
        p = self._player(e.player_id, team)
        if p is not None:
            p.passes += 1
            p.passes_completed += int(success)
            self._difficulty_sum[p.player_id] = self._difficulty_sum.get(p.player_id, 0.0) + diff
        self._window.append(_WinItem(self._play_ms, "pass", team, length, e.event_id))
        if success and self._is_entry(e):
            self._record_entry(e, team)
        self._ball_speed(e, self._subject(e, team))

        if not success:
            self._reset_streak()
            return
        if self._streak_team != team:
            self._streak_team = team
            self._streak = []
        self._streak.append(e.event_id)
        n = len(self._streak)
        lo, step = self.cfg.pass_streak_min, self.cfg.pass_streak_step
        if n >= lo and (n - lo) % step == 0:
            f = self._emit_fact("pass_streak", "team", team, n, list(self._streak), unit="passes",
                                window="current move")
            imp = self._base("pass_streak") + self.cfg.importance.streak_increment * (n - lo)
            self._emit_moment("pass_streak", imp, [f])

    def _reset_streak(self) -> None:
        self._streak_team = None
        self._streak = []

    def _on_carry(self, e: MatchEvent, team: str) -> None:
        p = self._player(e.player_id, team)
        dist = e.meta.get("distance_m")
        if p is not None and dist is not None:
            self._carry_distance[p.player_id] = self._carry_distance.get(p.player_id, 0.0) + float(dist)
        speed = e.meta.get("player_speed_kmh")
        if p is not None and speed is not None:
            self._player_speed(p, float(speed), e)
        if self._is_entry(e):
            self._record_entry(e, team)

    # ----------------------------------------------------------------- shots

    def _score_str(self) -> str:
        return f"{self._teams[self.home].goals}-{self._teams[self.away].goals}"

    def _counted_goals(self) -> list[str]:
        return [s.event_id for s in self._shots.values() if s.goal]

    def _xg_team_fact(self, team: str, extra: list[str]) -> Fact:
        ev = [s.event_id for s in self._shots.values() if s.team_id == team] + extra
        return self._emit_fact("xg_team", "team", team, self._r(self._teams[team].xg), ev, unit="xG")

    def _xg_player_fact(self, pid: str, extra: list[str]) -> Fact:
        ev = [s.event_id for s in self._shots.values() if s.player_id == pid] + extra
        return self._emit_fact("xg_player", "player", pid, self._r(self._players[pid].xg), ev, unit="xG")

    def _on_shot(self, e: MatchEvent, team: str) -> None:
        cfg = self.cfg
        x = e.x if e.x is not None else DEFAULT_SHOT_X
        y = e.y if e.y is not None else DEFAULT_SHOT_Y
        situation = e.meta.get("situation", "open_play")
        xg = shot_xg(x, y, e.meta.get("body_part"), situation, e.pressure, cfg.xg, cfg.pitch)
        goal = e.outcome == "goal"
        on_target = e.outcome in ("goal", "saved")
        ts = self._teams[team]
        other = self.away if team == self.home else self.home
        diff_before = ts.goals - self._teams[other].goals
        ts.shots += 1
        ts.shots_on_target += int(on_target)
        ts.xg += xg
        p = self._player(e.player_id, team)
        if p is not None:
            p.shots += 1
            p.xg += xg
        if goal:
            ts.goals += 1
            if p is not None:
                p.goals += 1
        self._shots[e.event_id] = _ShotRec(e.event_id, team, e.player_id, xg, on_target, goal)
        self._window.append(_WinItem(self._play_ms, "shot", team, xg, e.event_id))
        self._reset_streak()

        group: list[Fact] = []
        if goal:
            subj = self._subject(e, team)
            scorer_goals = p.goals if p is not None else ts.goals
            group.append(self._emit_fact("goal", subj[0], subj[1], scorer_goals, [e.event_id], unit="goals"))
            group.append(self._emit_fact("score", "match", self.info.match_id, self._score_str(),
                                         self._counted_goals(), unit="score"))
        elif xg >= cfg.big_chance_xg:
            subj = self._subject(e, team)
            group.append(self._emit_fact("big_chance_missed", subj[0], subj[1], self._r(xg),
                                         [e.event_id], unit="xG"))
        group.append(self._xg_team_fact(team, []))
        if p is not None:
            group.append(self._xg_player_fact(p.player_id, []))
        speed = e.meta.get("ball_speed_kmh")
        if speed is not None:
            subj = self._subject(e, team)
            group.append(self._emit_fact("shot_speed", subj[0], subj[1], self._r(float(speed)),
                                         [e.event_id], unit="km/h"))
        rec = self._ball_speed(e, self._subject(e, team))
        if rec is not None:
            group.append(rec)

        imp_cfg = cfg.importance
        if goal:
            imp = self._base("goal")
            if diff_before + 1 in (0, 1):
                imp += imp_cfg.goal_lead_change_bonus
            if e.clock.minute >= imp_cfg.late_minute:
                imp += imp_cfg.late_bonus
            self._emit_moment("goal", imp, group)
        elif xg >= cfg.big_chance_xg:
            self._emit_moment("big_chance", self._base("big_chance") + imp_cfg.big_chance_xg_weight * xg, group)
        elif speed is not None and float(speed) >= cfg.rocket_shot_kmh:
            self._emit_moment("rocket_shot", self._base("rocket_shot"), group)

    # ------------------------------------------------------------- discipline

    def _on_foul(self, e: MatchEvent, team: str) -> None:
        card = e.meta.get("card", "none")
        p = self._player(e.player_id, team)
        reason = None
        if card == "yellow":
            self._teams[team].yellow_cards += 1
            if p is not None:
                p.yellow_cards += 1
                if p.yellow_cards >= 2 and not p.red_card:
                    reason = "second_yellow"
        elif card == "red" and not (p is not None and p.red_card):
            reason = "straight_red"
        if reason is None:
            return
        self._teams[team].red_cards += 1
        if p is not None:
            p.red_card = True
        self._red_events[e.event_id] = (team, e.player_id)
        subj = self._subject(e, team)
        f = self._emit_fact("red_card", subj[0], subj[1], reason, [e.event_id])
        self._emit_moment("red_card", self._base("red_card"), [f])

    # --------------------------------------------------------------- tracking

    def _player_speed(self, p: PlayerStats, speed: float, e: MatchEvent) -> None:
        p.top_speed_kmh = max(p.top_speed_kmh, speed)
        if speed >= self.cfg.top_speed_alert_kmh and p.player_id not in self._speed_alerted:
            self._speed_alerted.add(p.player_id)
            f = self._emit_fact("player_top_speed_alert", "player", p.player_id, self._r(speed),
                                [e.event_id], unit="km/h")
            self._emit_moment("speed_alert", self._base("speed_alert"), [f])

    def _on_tracking(self, e: MatchEvent, team: str | None) -> None:
        p = self._player(e.player_id, team)
        if p is None:
            return
        m = e.meta
        if "distance_m_total" in m:
            self._has_tracking.add(p.player_id)
            p.distance_m = float(m["distance_m_total"])
            reached = self._milestones.setdefault(p.player_id, set())
            for ms in sorted(self.cfg.distance_milestones_m):
                if p.distance_m >= ms and ms not in reached:
                    reached.add(ms)
                    f = self._emit_fact("player_distance_milestone", "player", p.player_id, self._r(ms),
                                        [e.event_id], unit="m")
                    self._emit_moment("distance_milestone", self._base("distance_milestone"), [f])
        if "sprints" in m:
            p.sprints = int(m["sprints"])
        if "top_speed_kmh" in m:
            self._player_speed(p, float(m["top_speed_kmh"]), e)

    # -------------------------------------------------------------------- VAR

    def _on_var_decision(self, e: MatchEvent) -> Retraction | None:
        if e.meta.get("decision") != "overturned":
            return None
        subject = e.meta.get("subject_event_id") or (e.related[0] if e.related else None)
        if not subject or subject in self._annulled:
            return None
        self._annulled[subject] = None

        retracted_facts: list[str] = []
        for fid in self._evidence_index.get(subject, []):
            if not self.facts.is_retracted(fid):
                self.facts.retract(fid)
                retracted_facts.append(fid)
        retracted_moments: list[str] = []
        for fid in retracted_facts:
            for mid in self._fact_moments.get(fid, []):
                if not self.moments.is_retracted(mid) and mid not in retracted_moments:
                    self.moments.retract(mid)
                    retracted_moments.append(mid)

        evidence = [e.event_id]
        if subject in self._var_reviews:
            evidence.insert(0, self._var_reviews[subject])
        group: list[Fact] = []
        shot = self._shots.pop(subject, None)
        if shot is not None:
            ts = self._teams[shot.team_id]
            ts.shots -= 1
            ts.shots_on_target -= int(shot.on_target)
            ts.xg = max(0.0, ts.xg - shot.xg)
            p = self._players.get(shot.player_id) if shot.player_id else None
            if p is not None:
                p.shots -= 1
                p.xg = max(0.0, p.xg - shot.xg)
            if shot.goal:
                ts.goals -= 1
                if p is not None:
                    p.goals -= 1
            self._window = deque(w for w in self._window if w.event_id != subject)
            self._ball_speeds.pop(subject, None)
            group.append(self._emit_fact("var_overturn", "team", shot.team_id, self._score_str(),
                                         evidence, unit="score"))
            if shot.goal:
                group.append(self._emit_fact("score", "match", self.info.match_id, self._score_str(),
                                             self._counted_goals() + evidence, unit="score"))
            group.append(self._xg_team_fact(shot.team_id, evidence))
            if p is not None:
                group.append(self._xg_player_fact(p.player_id, evidence))
        elif subject in self._red_events:
            team, pid = self._red_events.pop(subject)
            self._teams[team].red_cards -= 1
            if pid is not None and pid in self._players:
                self._players[pid].red_card = False
            group.append(self._emit_fact("var_overturn", "team", team, "red_card", evidence))
        elif subject in self._ingested:
            group.append(self._emit_fact("var_overturn", "match", self.info.match_id, "decision", evidence))
        if group:
            self._emit_moment("var_overturn", self._base("var_overturn"), group)
        return Retraction(
            subject_event_id=subject,
            seq_at=e.seq,
            retracted_fact_ids=retracted_facts,
            retracted_moment_ids=retracted_moments,
        )

    # ------------------------------------------------------- rolling windows

    def _evaluate_windows(self) -> None:
        cfg = self.cfg
        now = self._play_ms
        start = now - cfg.window_ms
        while self._window and self._window[0].play_ms <= start:
            self._window.popleft()
        while self._segments and self._segments[0].end_ms <= start:
            self._segments.popleft()
        win = list(self._window)
        self._update_momentum(win)
        self._update_pressing(win)
        self._update_chaos(win, now)
        if self._running:
            self._update_possession_swing(now, start)

    def _update_momentum(self, win: list[_WinItem]) -> None:
        cfg = self.cfg
        load = {self.home: 0.0, self.away: 0.0}
        evidence: list[str] = []
        for w in win:
            if w.team_id not in load:
                continue
            if w.kind == "shot":
                load[w.team_id] += w.value
                evidence.append(w.event_id)
            elif w.kind == "entry":
                load[w.team_id] += cfg.momentum_entry_weight
                evidence.append(w.event_id)
        h, a = load[self.home], load[self.away]
        m = (h - a) / (h + a + cfg.momentum_smoothing)
        self._momentum = max(-1.0, min(1.0, m))
        if not self._running or len(evidence) < cfg.momentum_min_events:
            return
        side = None
        if m >= cfg.momentum_shift_threshold:
            side = self.home
        elif m <= -cfg.momentum_shift_threshold:
            side = self.away
        if side is not None and side != self._momentum_side:
            self._momentum_side = side
            # subject_id is the side gaining momentum, so the value is the unsigned size of the swing.
            # A signed home-positive value read as "-0.375 for the away side" by models and viewers alike.
            f = self._emit_fact("momentum_shift", "team", side, self._r(abs(self._momentum)), evidence,
                                unit="momentum swing towards this team (0 to 1)", window=self._window_label())
            self._emit_moment("momentum_shift",
                              self._base("momentum_shift") + cfg.importance.momentum_weight * abs(m), [f])

    def _update_pressing(self, win: list[_WinItem]) -> None:
        cfg = self.cfg
        for team in (self.home, self.away):
            pressures = [w.event_id for w in win if w.kind == "pressure" and w.team_id == team]
            opp_passes = [w.event_id for w in win if w.kind == "pass" and w.team_id not in (team, None)]
            intensity = len(pressures) / len(opp_passes) if opp_passes else 0.0
            self._pressing[team] = intensity
            if intensity < cfg.pressure_spike_rearm:
                self._pressure_armed[team] = True
            if (
                self._running
                and self._pressure_armed[team]
                and len(opp_passes) >= cfg.pressing_min_opponent_passes
                and intensity >= cfg.pressure_spike_threshold
            ):
                self._pressure_armed[team] = False
                f = self._emit_fact("pressure_spike", "team", team, self._r(intensity), pressures + opp_passes,
                                    unit="pressures per opponent pass", window=self._window_label())
                self._emit_moment("pressure_spike", self._base("pressure_spike"), [f])

    def _update_chaos(self, win: list[_WinItem], now: int) -> None:
        cfg = self.cfg
        pcs = [w for w in win if w.kind == "pc"]
        passes = [w for w in win if w.kind == "pass"]
        press = [w for w in win if w.kind == "press_val"]
        elapsed_min = max(cfg.min_window_ms, min(cfg.window_ms, now)) / 60_000.0
        c_pc = 1.0 - math.exp(-(len(pcs) / elapsed_min) / cfg.chaos_pc_rate_ref_per_min)
        spread = statistics.pstdev([w.value for w in passes]) if len(passes) >= 2 else 0.0
        c_len = 1.0 - math.exp(-spread / cfg.chaos_pass_len_std_ref_m)
        c_press = statistics.fmean([w.value for w in press]) if press else 0.0
        weights = (
            cfg.chaos_weight_possession_changes,
            cfg.chaos_weight_pass_length_spread,
            cfg.chaos_weight_pressure,
        )
        idx = (weights[0] * c_pc + weights[1] * c_len + weights[2] * c_press) / sum(weights)
        self._chaos = max(0.0, min(1.0, idx))
        n_events = len({w.event_id for w in pcs + passes + press})
        if not self._running or n_events < cfg.chaos_min_events or len(passes) < cfg.chaos_min_passes:
            return
        regime = None
        if self._chaos >= cfg.chaos_high:
            regime = "chaos"
        elif self._chaos <= cfg.control_low:
            regime = "control"
        if regime is None or regime == self._chaos_regime:
            return
        previous, self._chaos_regime = self._chaos_regime, regime
        if previous is None:
            return
        kind = "control_to_chaos" if regime == "chaos" else "chaos_to_control"
        evidence = [w.event_id for w in win if w.kind in ("pc", "pass", "press_val")]
        f = self._emit_fact(kind, "match", self.info.match_id, self._r(self._chaos), evidence,
                            unit="control-chaos index", window=self._window_label())
        lean = self._chaos if regime == "chaos" else 1.0 - self._chaos
        self._emit_moment(kind, self._base(kind) + self.cfg.importance.chaos_weight * lean, [f])

    def _update_possession_swing(self, now: int, start: int) -> None:
        cfg = self.cfg
        segs = list(self._segments)
        if self._owner is not None:
            segs.append(_Segment(self._owner, self._seg_start, now, self._seg_event))
        held = {self.home: 0, self.away: 0}
        evidence: list[str] = []
        for s in segs:
            overlap = min(s.end_ms, now) - max(s.start_ms, start)
            if overlap > 0 and s.team_id in held:
                held[s.team_id] += overlap
                evidence.append(s.event_id)
        total = held[self.home] + held[self.away]
        if total < cfg.possession_swing_min_observed_ms:
            return
        leader = None
        for team in (self.home, self.away):
            if held[team] / total >= cfg.possession_swing_share:
                leader = team
        if leader is None or leader == self._possession_leader:
            return
        self._possession_leader = leader
        f = self._emit_fact("possession_swing", "team", leader, self._r(100.0 * held[leader] / total),
                            evidence, unit="% possession", window=self._window_label())
        self._emit_moment("possession_swing", self._base("possession_swing"), [f])


def replay(
    match_info: MatchInfo, events: Iterable[MatchEvent], config: EngineConfig | None = None
) -> tuple[Engine, list[EngineUpdate]]:
    """Run a fresh engine over ``events`` and return it with every update."""
    engine = Engine(match_info, config)
    return engine, engine.ingest_many(events)
