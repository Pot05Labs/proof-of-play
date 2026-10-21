"""Seeded synthetic football match simulator.

The model is a possession-chain walk, not uniform noise. One team holds the ball at a
location (x, y) in its own attacking frame (0..100, attacking left to right). Each step the
opponent may press, then the carrier passes, carries or shoots. Passes and carries move the
ball up the pitch; failed passes, tackles and interceptions hand the ball over with a
`possession_change`. Shot probability rises sharply near goal, so shots come mostly from the
final third. Team style sets pressing height and rate, pass length and directness, and
counter-attacking. Game state changes those settings as the match goes on: a team trailing
after 60' presses harder and goes longer, a team leading late slows down, and a red card
weakens the short-handed side.

Determinism: one numpy Generator(PCG64(seed)) drives every random draw, and nothing reads
the wall clock, so the same seed and parameters give byte-identical output.

The simulator never emits xG or pass difficulty; the engine computes those.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pop.schema import Clock, EventType, MatchEvent, MatchInfo

from .names import build_teams
from .styles import STYLE_CODES, STYLES, StyleParams

PITCH_L = 105.0
PITCH_W = 68.0
HALF_S = 45 * 60.0

# Which positions tend to be on the ball, by x zone in the acting team's frame.
ZONE_WEIGHTS: list[tuple[float, dict[str, float]]] = [
    (20.0, {"GK": 0.30, "DF": 0.55, "MF": 0.14, "FW": 0.01}),
    (40.0, {"GK": 0.0, "DF": 0.50, "MF": 0.42, "FW": 0.08}),
    (65.0, {"GK": 0.0, "DF": 0.22, "MF": 0.53, "FW": 0.25}),
    (80.0, {"GK": 0.0, "DF": 0.10, "MF": 0.45, "FW": 0.45}),
    (101.0, {"GK": 0.0, "DF": 0.06, "MF": 0.34, "FW": 0.60}),
]
# Running load: metres per minute of match time, and sprint rate per minute.
METRES_PER_MIN = {"GK": 59.0, "DF": 106.0, "MF": 112.0, "FW": 105.0}
SPRINTS_PER_MIN = {"GK": 0.02, "DF": 0.22, "MF": 0.25, "FW": 0.32}
VMAX_MEAN = {"GK": 25.5, "DF": 32.0, "MF": 31.5, "FW": 33.0}
SPRINT_KMH = 25.2

VAR_CHECKS = ["offside", "handball", "foul_in_buildup"]
VAR_OVERTURN_REASONS = {
    "offside": "attacker offside in the build-up",
    "handball": "handball by the scorer",
    "foul_in_buildup": "foul on a defender in the build-up",
}


def _r(v: float, nd: int = 1) -> float:
    return float(round(float(v), nd))


def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return lo if v < lo else hi if v > hi else float(v)


def _metres(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float]:
    """Length (m) and angle (deg, 0 = straight at the opponent goal) between two pitch points."""
    dx = (x1 - x0) * PITCH_L / 100.0
    dy = (y1 - y0) * PITCH_W / 100.0
    return math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))


def _in_box(x: float, y: float) -> bool:
    return x >= 84.0 and 20.0 <= y <= 80.0


@dataclass
class _PlayerState:
    player_id: str
    position: str
    team_idx: int
    pace: float
    vmax: float
    last_tick: float = 0.0
    distance: float = 0.0
    top_speed: float = 0.0
    sprints: int = 0
    yellows: int = 0


@dataclass
class _TeamState:
    team_id: str
    style: StyleParams
    on_pitch: list[str]
    bench: list[str]
    goals: int = 0
    reds: int = 0
    subs_left: list[tuple[float, int]] = field(default_factory=list)  # (match second, count)
    counterpress_until: float = -1.0
    came_on: list[str] = field(default_factory=list)


@dataclass
class _Mods:
    press: float = 1.0
    long: float = 0.0
    fwd: float = 0.0
    tempo: float = 1.0
    acc: float = 0.0


class _Simulator:
    def __init__(self, seed: int, home_style: str, away_style: str, var_overturn: bool) -> None:
        for s in (home_style, away_style):
            if s not in STYLES:
                raise ValueError(f"unknown style {s!r}; expected one of {sorted(STYLES)}")
        self.rng = np.random.Generator(np.random.PCG64(seed))
        rng = self.rng
        self.seed = int(seed)
        self.match_id = f"pop-{seed}-{STYLE_CODES[home_style]}v{STYLE_CODES[away_style]}" + (
            "-var" if var_overturn else ""
        )
        home, away, competition, venue = build_teams(rng, home_style, away_style)
        self.info = MatchInfo(
            match_id=self.match_id, seed=self.seed, competition=competition, venue=venue, home=home, away=away
        )
        self.events: list[MatchEvent] = []
        self.players: dict[str, _PlayerState] = {}
        self.teams: list[_TeamState] = []
        for ti, team in enumerate((home, away)):
            for p in team.squad:
                pace = float(np.clip(rng.normal(1.0, 0.025), 0.96, 1.04))
                vmax = float(np.clip(rng.normal(VMAX_MEAN[p.position], 1.2), 23.0, 36.0))
                self.players[p.player_id] = _PlayerState(p.player_id, p.position, ti, pace, vmax)
            self.teams.append(
                _TeamState(
                    team_id=team.team_id,
                    style=STYLES[team.style],
                    on_pitch=[p.player_id for p in team.squad if p.starter],
                    bench=[p.player_id for p in team.squad if not p.starter],
                )
            )
        for ts in self.teams:
            ts.subs_left = self._plan_subs()

        # Clock and ball state.
        self.period = 1
        self.ps = 0.0  # seconds since the start of the current period
        self.period_base_ms = 0
        self.next_track = 60.0
        self.added: int | None = None
        self.end_ps: float | None = None
        self.stoppages = {"goals": 0, "subs": 0, "cards": 0, "var": 0}
        self.poss = 0
        self.bx = 50.0
        self.by = 50.0
        self.carrier: str | None = None
        self.restart: str | None = None
        self.counter_until = -1.0
        self.set_piece_until = -1.0
        self.aerial = False

        # Drama hook: a goal that VAR overturns, guaranteed before full time.
        self.var_pending = bool(var_overturn)
        self.var_trigger = float(rng.uniform(25.0, 70.0)) * 60.0

    # ------------------------------------------------------------------ clock and emit
    @property
    def total_s(self) -> float:
        return self.ps + (0.0 if self.period == 1 else HALF_S)

    def _clock(self, ps: float) -> Clock:
        total = int(ps + (0.0 if self.period == 1 else HALF_S))
        minute, second = divmod(total, 60)
        reg = 45 if self.period == 1 else 90
        added = minute - reg + 1 if minute >= reg else 0
        return Clock(period=self.period, minute=minute, second=second, added=added)

    def _append(self, etype: EventType, at_ps: float, **kw: Any) -> str:
        seq = len(self.events) + 1
        event_id = f"{self.match_id}:{seq:05d}"
        for key in ("x", "y", "end_x", "end_y"):
            if kw.get(key) is not None:
                kw[key] = _r(_clip(kw[key]))
        if kw.get("pressure") is not None:
            kw["pressure"] = _r(_clip(kw["pressure"], 0.0, 1.0), 2)
        self.events.append(
            MatchEvent(
                event_id=event_id,
                match_id=self.match_id,
                seq=seq,
                clock=self._clock(at_ps),
                t_ms=self.period_base_ms + int(at_ps * 1000),
                type=etype,
                **kw,
            )
        )
        return event_id

    def emit(self, etype: EventType, **kw: Any) -> str:
        self._flush_tracking(self.ps)
        return self._append(etype, self.ps, **kw)

    def advance(self, seconds: float) -> None:
        self.ps += max(0.0, float(seconds))

    # ------------------------------------------------------------------ physical tracking
    def _flush_tracking(self, upto: float) -> None:
        while self.next_track <= upto:
            boundary = self.next_track
            for ts in self.teams:
                for pid in list(ts.on_pitch):
                    self._tick(pid, boundary)
            self.next_track += 60.0

    def _tick(self, pid: str, at_ps: float, snapshot: str | None = None) -> None:
        ps_ = self.players[pid]
        frac = max(0.0, (at_ps - ps_.last_tick) / 60.0)
        ts = self.teams[ps_.team_idx]
        m = self._mods(ps_.team_idx)
        fatigue = 1.0 - 0.08 * min(1.0, self.total_s / 5700.0)
        short_handed = 1.03 if ts.reds > self.teams[1 - ps_.team_idx].reds else 1.0
        if ps_.position == "GK":  # keepers do not chase the press
            load = METRES_PER_MIN["GK"] * ps_.pace * fatigue
        else:
            load = (
                METRES_PER_MIN[ps_.position]
                * ps_.pace
                * ts.style.work_rate
                * (1.0 + 0.04 * (m.press - 1.0))
                * fatigue
                * short_handed
            )
        ps_.distance += load * frac * float(np.clip(self.rng.normal(1.0, 0.12), 0.5, 1.5))
        n_sprints = int(self.rng.poisson(SPRINTS_PER_MIN[ps_.position] * frac * max(0.6, m.press)))
        ps_.sprints += n_sprints
        if n_sprints > 0:
            ps_.top_speed = max(ps_.top_speed, ps_.vmax * float(self.rng.uniform(0.84, 1.0)))
        elif frac > 0:
            ps_.top_speed = max(ps_.top_speed, float(self.rng.uniform(15.0, 23.0)))
        ps_.last_tick = at_ps
        meta: dict[str, Any] = {
            "distance_m_total": _r(ps_.distance),
            "top_speed_kmh": _r(ps_.top_speed),
            "sprints": int(ps_.sprints),
        }
        if snapshot:
            meta["snapshot"] = snapshot
        self._append(EventType.PLAYER_TRACKING, at_ps, team_id=ts.team_id, player_id=pid, meta=meta)

    # ------------------------------------------------------------------ helpers
    def _plan_subs(self) -> list[tuple[float, int]]:
        rng = self.rng
        n = int(rng.integers(3, 6))
        windows = int(rng.integers(2, min(n, 3) + 1))
        times = np.sort(rng.uniform(55.0, 88.0, size=windows))
        counts = [1] * windows
        for _ in range(n - windows):
            counts[int(rng.integers(0, windows))] += 1
        return [(float(t) * 60.0, c) for t, c in zip(times, counts, strict=True)]

    def _mods(self, ti: int) -> _Mods:
        m = _Mods()
        me, them = self.teams[ti], self.teams[1 - ti]
        minute = self.total_s / 60.0
        diff = me.goals - them.goals
        if diff < 0 and minute >= 60.0:
            m.press, m.long, m.fwd, m.tempo = 1.4, 0.12, 0.15, 0.85
        elif diff > 0 and minute >= 70.0:
            m.press, m.long, m.fwd, m.tempo = 0.8, -0.04, -0.10, 1.15
        if me.reds > them.reds:
            m.press *= 0.7
            m.acc -= 0.04
            m.long += 0.08
        elif me.reds < them.reds:
            m.press *= 1.1
            m.acc += 0.03
            m.fwd += 0.05
        m.press *= 1.0 - 0.12 * min(1.0, minute / 95.0)
        return m

    def _pick(self, ti: int, x: float, exclude: str | None = None, positions: str | None = None) -> str:
        weights = next(w for bound, w in ZONE_WEIGHTS if x < bound)
        ids = [p for p in self.teams[ti].on_pitch if p != exclude]
        if positions:
            narrowed = [p for p in ids if self.players[p].position in positions]
            ids = narrowed or ids
        w = np.array([weights[self.players[p].position] + 0.01 for p in ids])
        return ids[int(self.rng.choice(len(ids), p=w / w.sum()))]

    def _team_id(self, ti: int) -> str:
        return self.teams[ti].team_id

    def turnover(
        self, cause: str, x: float, y: float, restart: str | None = None, player: str | None = None
    ) -> None:
        old, new = self.poss, 1 - self.poss
        self.poss = new
        self.bx, self.by = _clip(x, 0.5, 99.5), _clip(y, 0.5, 99.5)
        self.carrier = player
        self.restart = restart
        self.aerial = False
        self.set_piece_until = -1.0
        self.emit(
            EventType.POSSESSION_CHANGE,
            team_id=self._team_id(new),
            x=self.bx,
            y=self.by,
            meta={"from_team_id": self._team_id(old), "to_team_id": self._team_id(new), "cause": cause},
        )
        self.teams[old].counterpress_until = self.total_s + 6.0
        self.counter_until = -1.0
        if restart is None and self.bx < 50.0 and self.rng.random() < self.teams[new].style.counter_prob:
            self.counter_until = self.total_s + 16.0

    def _in_counter(self) -> bool:
        return self.total_s < self.counter_until

    # ------------------------------------------------------------------ actions
    def _pressure_value(self) -> float:
        """Opponent pressing, may emit a `pressure` event. Returns pressure on the carrier."""
        opp = 1 - self.poss
        st = self.teams[opp].style
        px = 100.0 - self.bx
        zone = 0 if px < 33.3 else 1 if px < 66.7 else 2
        p = st.press_zones[zone] * self._mods(opp).press
        if self.total_s < self.teams[opp].counterpress_until:
            p *= st.counterpress
        if self.rng.random() < min(0.85, p):
            presser = self._pick(opp, px, positions=None)
            self.emit(
                EventType.PRESSURE,
                team_id=self._team_id(opp),
                player_id=presser,
                x=px + self.rng.normal(0, 2),
                y=100.0 - self.by + self.rng.normal(0, 3),
                meta={"target_player_id": self.carrier},
            )
            if self.rng.random() < 0.05:
                self._foul(opp, presser, px, 100.0 - self.by)
                return -1.0
            return float(self.rng.uniform(0.45, 1.0))
        return float(self.rng.uniform(0.0, 0.3) + (0.1 if self.bx > 66 else 0.0))

    def step(self) -> None:
        if self.restart:
            self._restart()
            return
        ti = self.poss
        if self.carrier is None or self.carrier not in self.teams[ti].on_pitch:
            self.carrier = self._pick(ti, self.bx)
        pressure = self._pressure_value()
        if pressure < 0:  # the press ended in a foul; a restart is pending
            return
        if self.aerial:
            self.aerial = False
            if self.rng.random() < 0.28:
                self._shot(pressure, body="head" if self.rng.random() < 0.7 else "foot")
                return
        if self.rng.random() < self._shot_prob():
            self._shot(pressure)
            return
        st = self.teams[ti].style
        carry_p = st.carry_prob * (1.8 if self._in_counter() else 1.0)
        if self.players[self.carrier].position == "GK":
            carry_p = 0.03
        if self.rng.random() < carry_p:
            self._carry(pressure)
        else:
            self._pass(pressure)

    def _shot_prob(self) -> float:
        if self.bx < 60.0:
            return 0.0
        d, _ = _metres(self.bx, self.by, 100.0, 50.0)
        lateral = abs(self.by - 50.0) * PITCH_W / 100.0
        base = 0.12 if d >= 14.0 else 0.065  # players shoot on sight from the edge of the box
        p = base * math.exp(-max(0.0, d - 26.0) / 5.0) * math.exp(-max(0.0, lateral - 9.0) / 7.0)
        if self.var_pending and self.total_s >= self.var_trigger:
            p *= 2.0
        return min(0.4, p)

    def _pass(
        self,
        pressure: float,
        target: tuple[float, float] | None = None,
        set_piece: str | None = None,
        body: str = "foot",
        p_succ: float | None = None,
    ) -> None:
        rng = self.rng
        ti, opp = self.poss, 1 - self.poss
        st, m = self.teams[ti].style, self._mods(ti)
        passer = self.carrier or self._pick(ti, self.bx)
        cross = False
        if target is not None:
            ex, ey = target
        else:
            counter = self._in_counter()
            long_p = st.long_prob + m.long + (0.25 if counter else 0.0)
            fwd_p = min(0.95, st.forward_prob + m.fwd + (0.25 if counter else 0.0))
            if self.players[passer].position == "GK":
                long_p += 0.25
            if self.bx > 72 and (self.by < 25 or self.by > 75) and rng.random() < 0.22:
                cross = True
                ex, ey = rng.uniform(86, 96), rng.uniform(36, 64)
            else:
                if rng.random() < long_p:
                    length = rng.uniform(28, 58)
                    ang = rng.normal(0, 25)
                else:
                    length = float(np.clip(rng.lognormal(math.log(st.short_len_m), 0.45), 4, 35))
                    if rng.random() < fwd_p:
                        ang = rng.normal(0, 35)
                    else:
                        ang = rng.uniform(65, 180) * (1 if rng.random() < 0.5 else -1)
                rad = math.radians(ang)
                ex = self.bx + length * math.cos(rad) * 100.0 / PITCH_L
                ey = self.by + length * math.sin(rad) * 100.0 / PITCH_W
        ex, ey = _clip(ex, 0.5, 99.5 if target is not None else 92.0), _clip(ey, 0.5, 99.5)
        length, angle = _metres(self.bx, self.by, ex, ey)
        lofted = length > 30 or cross or set_piece in ("corner", "free_kick", "goal_kick")
        speed = 22.0 + 1.05 * length + rng.normal(0, 4) + (6.0 if lofted else 0.0)
        if body == "hands":
            speed = 18.0 + 0.6 * length + rng.normal(0, 2)
        speed = float(np.clip(speed, 15.0, 90.0))
        if p_succ is None:
            p_succ = (
                0.95
                + st.accuracy
                + m.acc
                - 0.0065 * max(0.0, length - 12.0)
                - 0.22 * pressure
                - (0.08 if _in_box(ex, ey) else 0.0)
                - (0.04 if self.bx > 66 else 0.0)
                + (0.04 if abs(angle) > 90 else 0.0)
            )
            if ex > 70 and self.teams[opp].style.name == "low_block":
                p_succ -= 0.05
            if cross:
                p_succ = 0.30 - 0.1 * pressure
        ok = rng.random() < float(np.clip(p_succ, 0.15, 0.98))
        receiver = self._pick(ti, ex, exclude=passer)
        meta: dict[str, Any] = {
            "receiver_id": receiver,
            "length_m": _r(length),
            "angle_deg": _r(angle),
            "body_part": body,
            "ball_speed_kmh": _r(speed),
        }
        if set_piece:
            meta["set_piece"] = set_piece
        if cross:
            meta["cross"] = True
        self.emit(
            EventType.PASS,
            team_id=self._team_id(ti),
            player_id=passer,
            x=self.bx,
            y=self.by,
            end_x=ex,
            end_y=ey,
            outcome="success" if ok else "fail",
            pressure=pressure,
            meta=meta,
        )
        hold = rng.uniform(1.0, 2.9) * st.tempo * m.tempo * (0.6 if self._in_counter() else 1.0)
        self.advance(length / (speed / 3.6) * 1.3 + hold)
        if ok:
            self.bx, self.by, self.carrier = ex, ey, receiver
            if cross or (set_piece in ("corner", "free_kick") and _in_box(ex, ey)):
                self.aerial = True
                self.set_piece_until = self.total_s + 8.0 if set_piece else self.set_piece_until
            return
        self._lost_pass(ex, ey)

    def _lost_pass(self, ex: float, ey: float) -> None:
        rng = self.rng
        opp = 1 - self.poss
        ox, oy = 100.0 - ex, 100.0 - ey
        if _in_box(ex, ey) and rng.random() < 0.55:
            defender = self._pick(opp, ox, positions="DF")
            cx, cy = rng.uniform(30, 60), rng.uniform(10, 90)
            self.emit(
                EventType.CLEARANCE,
                team_id=self._team_id(opp),
                player_id=defender,
                x=ox,
                y=oy,
                end_x=cx,
                end_y=cy,
            )
            self.advance(rng.uniform(1.5, 3.0))
            r = rng.random()
            if r < 0.15:
                self.advance(rng.uniform(20, 32))
                self.bx, self.by = 99.5, 0.5 if ey < 50 else 99.5
                self.carrier, self.restart = None, "corner"
            elif r < 0.6:
                self.turnover("clearance", cx, cy)
            else:  # attackers win the second ball
                self.bx, self.by, self.carrier = 100.0 - cx, 100.0 - cy, None
            return
        if ex >= 99.0 or ey <= 1.5 or ey >= 98.5:
            self.advance(rng.uniform(6, 14))
            if ex >= 99.0:
                self.turnover("out_of_play", 5.5, rng.uniform(35, 65), restart="goal_kick")
            else:
                self.turnover("out_of_play", ox, 0.5 if oy < 50 else 99.5, restart="throw_in")
            return
        if rng.random() < 0.72:
            interceptor = self._pick(opp, ox)
            self.emit(
                EventType.INTERCEPTION,
                team_id=self._team_id(opp),
                player_id=interceptor,
                x=ox,
                y=oy,
                outcome="success",
            )
            self.turnover("interception", ox, oy, player=interceptor)
        else:
            self.advance(rng.uniform(0.5, 1.5))
            self.turnover("loose_ball", ox + rng.normal(0, 3), oy + rng.normal(0, 3))

    def _carry(self, pressure: float) -> None:
        rng = self.rng
        ti, opp = self.poss, 1 - self.poss
        carrier = self.carrier or self._pick(ti, self.bx)
        counter = self._in_counter()
        dist = rng.uniform(10, 28) if counter else rng.uniform(3, 13)
        rad = math.radians(rng.normal(0, 30 if counter else 40))
        ex = _clip(self.bx + dist * math.cos(rad) * 100.0 / PITCH_L, 0.5, 92.0)
        ey = _clip(self.by + dist * math.sin(rad) * 100.0 / PITCH_W, 0.5, 99.5)
        dist, _ = _metres(self.bx, self.by, ex, ey)
        ps_ = self.players[carrier]
        speed = 9.0 + 0.55 * dist + (6.0 if counter else 0.0) + rng.normal(0, 2)
        speed = float(np.clip(speed, 6.0, ps_.vmax))
        ps_.top_speed = max(ps_.top_speed, speed)
        challenge_p = (0.10 + 0.30 * pressure) * self.teams[opp].style.tackle_rate
        challenged = rng.random() < min(0.7, challenge_p)
        outcome = "success"
        tackle_won = foul = attacker_foul = False
        if challenged:
            r = rng.random()
            foul = r < 0.16
            attacker_foul = 0.16 <= r < 0.20
            tackle_won = (not foul) and (attacker_foul or rng.random() < 0.5)
            outcome = "fail" if tackle_won else "success"
        self.emit(
            EventType.CARRY,
            team_id=self._team_id(ti),
            player_id=carrier,
            x=self.bx,
            y=self.by,
            end_x=ex,
            end_y=ey,
            outcome=outcome,
            pressure=pressure,
            meta={"distance_m": _r(dist), "player_speed_kmh": _r(speed)},
        )
        self.advance(dist / (speed / 3.6) + rng.uniform(0.3, 1.0))
        self.bx, self.by = ex, ey
        if not challenged:
            return
        ox, oy = 100.0 - ex, 100.0 - ey
        tackler = self._pick(opp, ox)
        if foul:
            self._foul(opp, tackler, ox, oy)
            return
        if attacker_foul:
            self._foul(ti, carrier, ex, ey)
            return
        self.emit(
            EventType.TACKLE,
            team_id=self._team_id(opp),
            player_id=tackler,
            x=ox,
            y=oy,
            outcome="won" if tackle_won else "lost",
        )
        if tackle_won:
            self.turnover("tackle", ox, oy, player=tackler)

    def _foul(self, fouling_ti: int, player: str, x: float, y: float) -> None:
        """A foul by `fouling_ti` at (x, y) in that team's frame. The other team gets the restart."""
        rng = self.rng
        if _in_box(100.0 - x, 100.0 - y) and rng.random() < 0.93:
            x = float(rng.uniform(17.0, 20.0))
        ps_ = self.players[player]
        trailing_late = (
            self.teams[fouling_ti].goals < self.teams[1 - fouling_ti].goals and self.total_s > 4200
        )
        yellow_p = 0.13 + (0.05 if trailing_late else 0.0) + (0.08 if self._in_counter() else 0.0)
        r = rng.random()
        card = "none"
        if r < 0.006:
            card = "red"
        elif r < 0.006 + yellow_p:
            ps_.yellows += 1
            card = "red" if ps_.yellows >= 2 else "yellow"
        meta: dict[str, Any] = {"card": card}
        if card == "red" and ps_.yellows >= 2:
            meta["reason"] = "second_yellow"
        self.emit(EventType.FOUL, team_id=self._team_id(fouling_ti), player_id=player, x=x, y=y, meta=meta)
        if card != "none":
            self.stoppages["cards"] += 1
            self.advance(rng.uniform(20, 45))
        if card == "red":
            self._send_off(fouling_ti, player)
        victim = 1 - fouling_ti
        vx, vy = 100.0 - x, 100.0 - y
        penalty = _in_box(vx, vy)
        restart = "penalty" if penalty else "free_kick"
        if self.poss == victim:
            self.bx, self.by = _clip(vx, 0.5, 99.5), _clip(vy, 0.5, 99.5)
            self.carrier, self.restart = None, restart
            self.aerial = False
        else:
            self.turnover("foul", vx, vy, restart=restart)

    def _send_off(self, ti: int, pid: str) -> None:
        ts = self.teams[ti]
        if pid in ts.on_pitch:
            self._flush_tracking(self.ps)
            self._tick(pid, self.ps, snapshot="sent_off")
            ts.on_pitch.remove(pid)
            ts.reds += 1
        if self.carrier == pid:
            self.carrier = None

    def _shot(self, pressure: float, body: str | None = None, situation: str | None = None) -> None:
        rng = self.rng
        ti, opp = self.poss, 1 - self.poss
        shooter = self.carrier or self._pick(ti, self.bx)
        if situation is None:
            if self.total_s < self.set_piece_until:
                situation = "set_piece"
            elif self._in_counter():
                situation = "counter"
            else:
                situation = "open_play"
        if body is None:
            body = "head" if rng.random() < 0.08 else "foot"
        d, _ = _metres(self.bx, self.by, 100.0, 50.0)
        lateral = abs(self.by - 50.0) * PITCH_W / 100.0
        if situation == "penalty":
            p_goal = 0.77
        else:
            p_goal = 0.6 * math.exp(-d / 11.0) * math.exp(-max(0.0, lateral - 6.0) / 10.0)
            p_goal *= (0.6 if body == "head" else 1.0) * (1.0 - 0.4 * pressure)
            p_goal = float(np.clip(p_goal, 0.01, 0.6))
        forced = self.var_pending and self.total_s >= self.var_trigger and (d < 22.0 or self.total_s > 5100)
        r = rng.random()
        if forced or r < p_goal:
            outcome = "goal"
        else:
            q = rng.random()
            on_target = 0.42 if situation == "penalty" else 0.33
            blocked = 0.0 if situation == "penalty" else 0.27
            outcome = "saved" if q < on_target else "blocked" if q < on_target + blocked else "off_target"
        if body == "head":
            speed = rng.normal(55, 9)
        elif situation == "penalty":
            speed = rng.normal(98, 9)
        else:
            speed = rng.normal(94, 14) - (10 if d < 8 else 0)
        speed = float(np.clip(speed, 40.0, 130.0))
        if outcome in ("goal", "saved"):
            gx, gy = 100.0, rng.uniform(45.5, 54.5)
        elif outcome == "off_target":
            gx, gy = 100.0, rng.choice([rng.uniform(36, 44.5), rng.uniform(55.5, 64)])
        else:
            gx, gy = min(99.5, self.bx + rng.uniform(1, 4)), self.by + rng.normal(0, 2)
        shot_id = self.emit(
            EventType.SHOT,
            team_id=self._team_id(ti),
            player_id=shooter,
            x=self.bx,
            y=self.by,
            end_x=gx,
            end_y=gy,
            outcome=outcome,
            pressure=pressure,
            meta={"body_part": body, "situation": situation, "ball_speed_kmh": _r(speed)},
        )
        self.advance(rng.uniform(1.0, 2.5))
        if outcome == "goal":
            self._goal(shot_id, forced)
        elif outcome == "saved":
            r = rng.random()
            if r < 0.55:
                gk = self._pick(opp, 5.0, positions="GK")
                self.turnover("save", 6.0, 50.0 + rng.normal(0, 6), player=gk)
            elif r < 0.85:
                self.advance(rng.uniform(20, 32))
                self.bx, self.by = 99.5, (0.5 if rng.random() < 0.5 else 99.5)
                self.carrier, self.restart = None, "corner"
            else:
                self.bx, self.by, self.carrier = min(97.0, self.bx + 4), self.by + rng.normal(0, 8), None
        elif outcome == "blocked":
            r = rng.random()
            if r < 0.33:
                self.advance(rng.uniform(20, 32))
                self.bx, self.by = 99.5, (0.5 if self.by < 50 else 99.5)
                self.carrier, self.restart = None, "corner"
            elif r < 0.75:
                self.turnover("block", 100.0 - self.bx, 100.0 - self.by)
            else:
                self.bx, self.by, self.carrier = max(60.0, self.bx - 6), self.by, None
        else:
            self.advance(rng.uniform(10, 20))
            self.turnover("out_of_play", 5.5, rng.uniform(35, 65), restart="goal_kick")

    def _goal(self, shot_id: str, forced: bool) -> None:
        rng = self.rng
        ti = self.poss
        self.stoppages["goals"] += 1
        if forced:
            self.var_pending = False
            check = VAR_CHECKS[int(rng.integers(0, len(VAR_CHECKS)))]
            self.advance(rng.uniform(25, 45))
            self.emit(
                EventType.VAR_REVIEW, related=[shot_id], meta={"subject_event_id": shot_id, "check": check}
            )
            self.advance(rng.uniform(60, 130))
            self.emit(
                EventType.VAR_DECISION,
                related=[shot_id],
                meta={
                    "subject_event_id": shot_id,
                    "decision": "overturned",
                    "reason": VAR_OVERTURN_REASONS[check],
                },
            )
            self.stoppages["var"] += 1
            self.advance(rng.uniform(15, 30))
            self.turnover("var_overturn", rng.uniform(12, 22), rng.uniform(20, 80), restart="free_kick")
            return
        self.teams[ti].goals += 1
        if rng.random() < 0.25:
            check = VAR_CHECKS[int(rng.integers(0, len(VAR_CHECKS)))]
            self.advance(rng.uniform(20, 35))
            self.emit(
                EventType.VAR_REVIEW, related=[shot_id], meta={"subject_event_id": shot_id, "check": check}
            )
            self.advance(rng.uniform(30, 70))
            self.emit(
                EventType.VAR_DECISION,
                related=[shot_id],
                meta={
                    "subject_event_id": shot_id,
                    "decision": "stands",
                    "reason": f"no {check.replace('_', ' ')}",
                },
            )
            self.stoppages["var"] += 1
            self.advance(rng.uniform(10, 20))
        else:
            self.advance(rng.uniform(45, 75))
        self.turnover("goal", 50.0, 50.0, restart="kick_off")

    def _restart(self) -> None:
        rng = self.rng
        kind, self.restart = self.restart, None
        ti = self.poss
        if kind == "kick_off":
            self.bx, self.by = 50.0, 50.0
            self.carrier = self._pick(ti, 50.0, positions="FW")
            self._pass(
                0.0, target=(rng.uniform(38, 46), rng.uniform(40, 60)), set_piece="kick_off", p_succ=0.98
            )
        elif kind == "throw_in":
            self.carrier = self._pick(ti, self.bx, positions="DF" if self.bx < 60 else "MF")
            inward = 1.0 if self.by < 50 else -1.0
            target = (self.bx + rng.uniform(-6, 10), self.by + inward * rng.uniform(8, 22))
            self._pass(
                float(rng.uniform(0, 0.4)), target=target, set_piece="throw_in", body="hands", p_succ=0.82
            )
        elif kind == "goal_kick":
            self.advance(rng.uniform(8, 18))
            self.carrier = self._pick(ti, 5.0, positions="GK")
            st = self.teams[ti].style
            if rng.random() < st.long_prob * 2.5:
                target = (rng.uniform(45, 70), rng.uniform(20, 80))
                self._pass(0.3, target=target, set_piece="goal_kick", p_succ=0.5)
            else:
                target = (rng.uniform(10, 22), rng.choice([rng.uniform(10, 30), rng.uniform(70, 90)]))
                self._pass(0.1, target=target, set_piece="goal_kick", p_succ=0.95)
        elif kind == "corner":
            self.carrier = self._pick(ti, 80.0, positions="MF")
            self.set_piece_until = self.total_s + 8.0
            target = (rng.uniform(86, 96), rng.uniform(36, 64))
            self._pass(0.3, target=target, set_piece="corner", p_succ=0.38)
        elif kind == "free_kick":
            self.advance(rng.uniform(12, 30))
            self.carrier = self._pick(ti, self.bx, positions="MF")
            self.set_piece_until = self.total_s + 8.0
            d, _ = _metres(self.bx, self.by, 100.0, 50.0)
            if d < 30 and abs(self.by - 50) < 25 and rng.random() < 0.3:
                self._shot(0.2, body="foot", situation="set_piece")
            elif self.bx > 65 and rng.random() < 0.6:
                self._pass(
                    0.3, target=(rng.uniform(86, 95), rng.uniform(36, 64)), set_piece="free_kick", p_succ=0.4
                )
            else:
                ang = math.radians(rng.normal(0, 60))
                length = rng.uniform(8, 25)
                tgt = (
                    self.bx + length * math.cos(ang) * 100 / PITCH_L,
                    self.by + length * math.sin(ang) * 100 / PITCH_W,
                )
                self._pass(0.05, target=tgt, set_piece="free_kick", p_succ=0.93)
        elif kind == "penalty":
            self.advance(rng.uniform(50, 90))
            self.bx, self.by = 88.6, 50.0
            self.carrier = self._pick(ti, 90.0, positions="FW")
            self._shot(0.0, body="foot", situation="penalty")

    # ------------------------------------------------------------------ substitutions
    def _maybe_subs(self) -> None:
        if self.period != 2:
            return
        for ti, ts in enumerate(self.teams):
            while ts.subs_left and self.total_s >= ts.subs_left[0][0]:
                _, count = ts.subs_left.pop(0)
                self.advance(self.rng.uniform(15, 35))
                self.stoppages["subs"] += 1
                for _ in range(count):
                    self._substitute(ti)

    def _substitute(self, ti: int) -> None:
        rng = self.rng
        ts = self.teams[ti]
        outfield = [p for p in ts.on_pitch if self.players[p].position != "GK" and p not in ts.came_on]
        bench = [p for p in ts.bench if self.players[p].position != "GK"]
        if not outfield or not bench:
            return
        trailing = ts.goals < self.teams[1 - ti].goals
        wpos = {"DF": 0.6, "MF": 1.2, "FW": 1.4}
        w = np.array([wpos[self.players[p].position] + 0.8 * self.players[p].yellows for p in outfield])
        out_id = outfield[int(rng.choice(len(outfield), p=w / w.sum()))]
        out_pos = self.players[out_id].position
        same = [p for p in bench if self.players[p].position == out_pos]
        if trailing:
            forwards = [p for p in bench if self.players[p].position == "FW"]
            same = forwards or same
        pool = same or bench
        in_id = pool[int(rng.integers(0, len(pool)))]
        self._flush_tracking(self.ps)
        self._tick(out_id, self.ps, snapshot="substituted")
        ts.on_pitch[ts.on_pitch.index(out_id)] = in_id
        ts.bench.remove(in_id)
        ts.came_on.append(in_id)
        self.players[in_id].last_tick = self.ps
        if self.carrier == out_id:
            self.carrier = None
        self.emit(
            EventType.SUBSTITUTION,
            team_id=ts.team_id,
            player_id=in_id,
            meta={"player_out_id": out_id, "player_in_id": in_id},
        )

    # ------------------------------------------------------------------ periods
    def _period_over(self) -> bool:
        if self.end_ps is None and self.ps >= HALF_S:
            s = self.stoppages
            base = 1 if self.period == 1 else 3
            extra = round(0.5 * s["goals"] + 0.4 * s["subs"] + 0.3 * s["cards"] + 1.0 * s["var"])
            hi = 5 if self.period == 1 else 9
            self.added = int(np.clip(base + extra + int(self.rng.integers(0, 3)), 1, hi))
            self.end_ps = HALF_S + self.added * 60.0 + float(self.rng.uniform(0, 40))
        return self.end_ps is not None and self.ps >= self.end_ps

    def _play_period(self, period: int, kickoff_team: int) -> None:
        self.period = period
        self.ps = 0.0
        self.next_track = 60.0
        self.added, self.end_ps = None, None
        self.stoppages = {"goals": 0, "subs": 0, "cards": 0, "var": 0}
        for ts in self.teams:
            for pid in ts.on_pitch:
                self.players[pid].last_tick = 0.0
        self.poss = kickoff_team
        self.counter_until = self.set_piece_until = -1.0
        self.aerial = False
        self.carrier = None
        self.emit(
            EventType.KICK_OFF, team_id=self._team_id(kickoff_team), x=50.0, y=50.0, meta={"period": period}
        )
        self.restart = "kick_off"
        while not self._period_over():
            self._maybe_subs()
            # Safety net for the drama hook: from 85' a pending overturned goal is forced through.
            if period == 2 and self.var_pending and self.total_s > 5100 and not self.restart:
                self.bx, self.by = max(self.bx, 88.0), 50.0 + float(self.rng.normal(0, 6))
                self._shot(0.3)
                continue
            self.step()
        self._flush_tracking(self.ps)
        snapshot = "half_time" if period == 1 else "full_time"
        for ts in self.teams:
            for pid in list(ts.on_pitch):
                self._tick(pid, self.ps, snapshot=snapshot)
        self.emit(
            EventType.HALF_TIME if period == 1 else EventType.FULL_TIME,
            meta={"added_minutes": int(self.added or 0)},
        )

    def run(self) -> tuple[MatchInfo, list[MatchEvent]]:
        self.emit(
            EventType.MATCH_START,
            meta={
                "home_team_id": self.info.home.team_id,
                "away_team_id": self.info.away.team_id,
                "competition": self.info.competition,
                "venue": self.info.venue,
                "seed": self.seed,
            },
        )
        first = int(self.rng.integers(0, 2))
        self._play_period(1, first)
        self.period_base_ms = self.events[-1].t_ms
        self._play_period(2, 1 - first)
        return self.info, self.events


def generate(
    seed: int, home_style: str = "high_press", away_style: str = "low_block", var_overturn: bool = False
) -> tuple[MatchInfo, list[MatchEvent]]:
    """Simulate one fictional match. Same arguments, byte-identical output."""
    return _Simulator(seed, home_style, away_style, var_overturn).run()
