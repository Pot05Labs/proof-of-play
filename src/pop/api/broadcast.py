"""One live broadcast shared by every viewer: simulator -> engine -> agents.

Every viewer sees the same match on the same clock. The arm only changes the insight layer:
  generic       neutral sentences for moments above the broadcast floor, no mode, club or player;
  personalised  the viewer's mode, language, club and player, plus extra moments about their club
                and player above a lower floor.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

from pop.agents.explainer import Viewer
from pop.agents.llm import LLM, get_llm
from pop.agents.orchestrator import TraceStep, run_moment
from pop.engine import Engine
from pop.schema import Fact, Insight, MatchEvent, MatchInfo, Moment, Session
from pop.sim.match import generate
from pop.sim.stream import astream

BROADCAST_FLOOR = 0.25
PERSONAL_FLOOR = 0.10
NOISY_KINDS = {"player_distance_milestone", "pass_streak"}


@dataclass
class Published:
    insight: Insight
    seq: int
    t_ms: int
    minute: int
    latency_ms: float
    trace: list[TraceStep] = field(default_factory=list)


GENERIC_SESSION = Session(session_id="broadcast", started_at="", arm="generic", assignment_seed="", consent=True)

RECAP_KINDS = {"recap_half_time", "recap_full_time"}
# Overlay timing and placement by moment kind: (slot, template, on-screen milliseconds)
OVERLAY_STYLE = {
    "goal": ("full", "goal_card", 10_000),
    "recap_half_time": ("full", "recap_card", 20_000),
    "recap_full_time": ("full", "recap_card", 20_000),
    "var_overturn": ("lower_third", "var_card", 10_000),
    "big_chance": ("lower_third", "chance_card", 8_000),
    "rocket_shot": ("corner", "speed_card", 6_000),
}
DEFAULT_STYLE = ("lower_third", "insight_card", 8_000)


@dataclass
class Broadcast:
    seed: int = 7
    speed: float = 1.0
    var_overturn: bool = True
    llm: LLM = field(default_factory=get_llm)
    info: MatchInfo | None = None
    events: list[MatchEvent] = field(default_factory=list)
    engine: Engine | None = None
    seq: int = 0
    t_ms: int = 0
    running: bool = False
    finished: bool = False
    moments: list[Moment] = field(default_factory=list)
    cache: dict[tuple, Published] = field(default_factory=dict)
    retracted_insights: set[str] = field(default_factory=set)
    llm_calls: int = 0
    rejected_rewrites: int = 0
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    profiles: set[Viewer] = field(default_factory=lambda: {Viewer()})
    id_key: str = "dev"
    workers: int = int(os.environ.get("POP_WORKERS", "8"))
    queue: asyncio.Queue | None = None
    queued: set[tuple] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)
    lag_ms: list[float] = field(default_factory=list)
    ingest: object | None = None
    _held: dict = field(default_factory=dict)

    def register(self, session: Session) -> None:
        """Remember each viewer profile so its insights are written live, not on request.

        A viewer who joins mid-match gets the recent moments written for their profile too.
        """
        v = self.viewer_of(session)
        new = v not in self.profiles
        self.profiles.add(v)
        if new and self.queue is not None:
            arm = "personalised" if session.arm == "personalised" else "generic"
            for m in self.moments[-12:]:
                if self.visible(m, v, arm):
                    self._enqueue(m, v, arm)

    def effective(self, m: Moment, viewer: Viewer, arm: str) -> Viewer:
        """Collapse a profile to what actually changes this moment's sentence.

        Club and player framing only count when the moment is about that club or player, so many
        viewer profiles share one model call per moment.
        """
        if arm == "generic":
            return Viewer(language=viewer.language)
        subjects = {f.subject_id for f in self.facts_of(m)}
        player = viewer.player_id if viewer.player_id in subjects else None
        club = viewer.club_id if viewer.club_id and self._relevant(m, Viewer(club_id=viewer.club_id)) else None
        return Viewer(audience=viewer.audience, language=viewer.language, club_id=club, player_id=player)

    def _recap(self, ev: MatchEvent) -> Moment | None:
        """Half-time and full-time recap built only from facts the engine has already asserted and not retracted."""
        active = [f for f in self.engine.facts.active()]
        score = [f for f in active if f.kind == "score"]
        if not score:
            return None
        chosen = [score[-1].fact_id]
        for team in (self.info.home.team_id, self.info.away.team_id):
            xg = [f for f in active if f.kind == "xg_team" and f.subject_id == team]
            if xg:
                chosen.append(xg[-1].fact_id)
        top = sorted((m for m in self.moments if m.kind not in RECAP_KINDS
                      and not self.engine.moments.is_retracted(m.moment_id)),
                     key=lambda m: m.importance, reverse=True)[:2]
        for m in top:
            for fid in m.facts:
                f = self.engine.facts.get(fid)
                if f and f.kind not in ("score", "xg_team") and fid not in chosen and not self.engine.facts.is_retracted(fid):
                    chosen.append(fid)
        kind = "recap_half_time" if ev.type.value == "half_time" else "recap_full_time"
        return Moment(moment_id=f"{self.info.match_id}:R{ev.seq:05d}:{kind}", seq_at=ev.seq, kind=kind,
                      importance=1.0, facts=chosen[:7])

    def _enqueue(self, m: Moment, viewer: Viewer, arm: str) -> None:
        if self.queue is None:  # not broadcasting live: feeds write on demand
            return
        ev = self.effective(m, viewer, arm)
        key = (m.moment_id, ev)
        if key in self.cache or key in self.queued:
            return
        self.queued.add(key)
        self.queue.put_nowait((m, ev, time.perf_counter()))

    async def _worker(self) -> None:
        while True:
            m, v, t_in = await self.queue.get()
            try:
                await asyncio.to_thread(self.insight_for, m, v)
                self.lag_ms.append((time.perf_counter() - t_in) * 1000)
            except Exception:  # a failed write must never kill the worker
                logging.getLogger("pop.broadcast").exception("insight write failed")
            finally:
                self.queue.task_done()

    @staticmethod
    def viewer_of(session: Session) -> Viewer:
        if session.arm == "generic":
            return Viewer(language=session.language)
        return Viewer(audience=session.mode, language=session.language,
                      club_id=session.club_id, player_id=session.player_id)

    def public_id(self, insight_id: str) -> str:
        """Opaque id for the browser: reveals nothing about audience, language, club or player."""
        return hmac.new(self.id_key.encode(), insight_id.encode(), hashlib.sha256).hexdigest()[:16]

    def load(self) -> None:
        self.info, self.events = generate(self.seed, var_overturn=self.var_overturn)
        self.engine = Engine(self.info)
        self.seq, self.t_ms, self.moments, self.cache = 0, 0, [], {}
        self.retracted_insights, self.finished = set(), False

    async def run(self) -> None:
        if self.info is None:
            self.load()
        self.running = True
        self.queue, self.queued, self.lag_ms = asyncio.Queue(), set(), []
        pool = [asyncio.create_task(self._worker()) for _ in range(self.workers)]
        self._held = {}
        mode = os.environ.get("POP_INGEST", "direct")
        if mode == "eventhubs":
            from pop.api.ingest import EventHubsIngest
            self.ingest = EventHubsIngest()
            try:
                await self.ingest.run(self.events, self.speed, self.apply)
            except Exception:  # Event Hubs unavailable: finish the match in-process, never stall it
                logging.getLogger("pop.broadcast").exception("event hubs ingest failed; continuing direct")
                async for ev in astream([e for e in self.events if e.seq > self.seq], self.speed):
                    await self.apply(ev)
        else:
            async for ev in astream(self.events, self.speed):
                await self.apply(ev)
        await self.queue.join()
        for t in pool:
            t.cancel()
        self.running, self.finished = False, True
        self._fan_out({"type": "finished"})

    async def apply(self, ev: MatchEvent) -> int:
        """Ingest one event exactly once and strictly in order. Returns how many events this call applied.

        Safe to call from both the Event Hubs consumer and its fallback watchdog: duplicates are ignored and an
        event that arrives early waits until every earlier sequence number has been applied.
        """
        if ev.seq <= self.seq or ev.seq in self._held:
            return 0
        self._held[ev.seq] = ev
        applied = 0
        while self.seq + 1 in self._held:
            self._process(self._held.pop(self.seq + 1))
            applied += 1
        return applied

    def _process(self, ev: MatchEvent) -> None:
        upd = self.engine.ingest(ev)
        self.seq, self.t_ms = ev.seq, ev.t_ms
        if upd.retraction:
            for _key, pub in list(self.cache.items()):
                if set(pub.insight.fact_ids) & set(upd.retraction.retracted_fact_ids):
                    self.retracted_insights.add(pub.insight.insight_id)
            self._fan_out({"type": "retraction", "seq": ev.seq})
        new_moments = list(upd.moments)
        if ev.type.value in ("half_time", "full_time"):
            recap = self._recap(ev)
            if recap is not None:
                new_moments.append(recap)
        for m in new_moments:
            self.moments.append(m)
            # Insights are queued, never awaited here: the match clock does not wait for a model.
            # Generic and personalised jobs are shuffled together so neither arm is reliably fresher.
            jobs = []
            for viewer in list(self.profiles):
                arm = "generic" if viewer.generic and viewer.audience == "fan" else "personalised"
                if self.visible(m, viewer, arm):
                    jobs.append((viewer, arm))
            jobs.sort(key=lambda j: hashlib.sha256(repr((m.moment_id, j[0])).encode()).digest())
            for viewer, arm in jobs:
                self._enqueue(m, viewer, arm)
            self._fan_out({"type": "moment", "moment_id": m.moment_id, "importance": m.importance})
        self._fan_out({"type": "tick", "seq": ev.seq})

    def _fan_out(self, msg: dict) -> None:
        for q in list(self.subscribers):
            q.put_nowait(msg)

    # ---- per-viewer selection and explanation ----
    def is_pulled(self, pub: Published) -> bool:
        return pub.insight.insight_id in self.retracted_insights or any(
            self.engine.facts.is_retracted(fid) for fid in pub.insight.fact_ids)

    def facts_of(self, m: Moment) -> list[Fact]:
        return [self.engine.facts.get(fid) for fid in m.facts if self.engine.facts.get(fid) is not None]

    def _relevant(self, m: Moment, viewer: Viewer) -> bool:
        subjects = {f.subject_id for f in self.facts_of(m)}
        if viewer.player_id and viewer.player_id in subjects:
            return True
        if viewer.club_id:
            squad = {p.player_id for t in (self.info.home, self.info.away) if t.team_id == viewer.club_id
                     for p in t.squad}
            return viewer.club_id in subjects or bool(subjects & squad)
        return False

    def visible(self, m: Moment, viewer: Viewer, arm: str) -> bool:
        if m.kind in RECAP_KINDS:
            return True
        if self.engine.moments.is_retracted(m.moment_id):
            return False
        kinds = {f.kind for f in self.facts_of(m)}
        if arm == "personalised" and self._relevant(m, viewer):
            return m.importance >= PERSONAL_FLOOR
        if kinds and kinds <= NOISY_KINDS:
            return False
        return m.importance >= BROADCAST_FLOOR

    def insight_for(self, m: Moment, viewer: Viewer) -> Published:
        """Write (or return) the insight for one moment and one collapsed profile. Runs in a worker thread."""
        key = (m.moment_id, viewer)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        facts = self.facts_of(m)
        ev = self.events[m.seq_at - 1]
        t0 = time.perf_counter()
        ins, trace = run_moment(m, facts, self.info, viewer, llm=self.llm, minute=ev.clock.minute)
        pub = Published(ins, m.seq_at, ev.t_ms, ev.clock.minute, (time.perf_counter() - t0) * 1000, trace)
        with self.lock:
            if key not in self.cache:
                self.cache[key] = pub
                self.llm_calls += 1
                self.rejected_rewrites += "rejected" in ins.verifier_notes
            return self.cache[key]

    def feed(self, session: Session) -> list[dict]:
        """Only insights already written. A feed request never waits on a model."""
        viewer = self.viewer_of(session)
        out = []
        for m in self.moments:
            if not self.visible(m, viewer, session.arm):
                continue
            with self.lock:
                pub = self.cache.get((m.moment_id, self.effective(m, viewer, session.arm)))
            if pub is None:
                if self.queue is not None:
                    continue
                pub = self.insight_for(m, self.effective(m, viewer, session.arm))  # offline/tests only
            if self.is_pulled(pub) or pub.insight.status == "rejected":
                continue
            out.append({"insight_id": self.public_id(pub.insight.insight_id), "minute": pub.minute, "t_ms": pub.t_ms,
                        "text": pub.insight.text, "fact_ids": pub.insight.fact_ids,
                        "importance": m.importance, "kind": m.kind})
        return out

    def producer_view(self) -> dict:
        rows = []
        with self.lock:
            items = list(self.cache.items())
        for (mid, viewer), pub in items:
            rows.append({"insight_id": pub.insight.insight_id, "minute": pub.minute, "text": pub.insight.text,
                         "verified": pub.insight.verified, "notes": pub.insight.verifier_notes,
                         "retracted": self.is_pulled(pub),
                         "audience": viewer.audience, "language": viewer.language,
                         "club": viewer.club_id, "player": viewer.player_id,
                         "latency_ms": round(pub.latency_ms, 1),
                         "kind": next((m.kind for m in self.moments if m.moment_id == mid), None),
                         "trace": [t.model_dump() for t in pub.trace]})
        rows.sort(key=lambda r: r["minute"])
        lag = sorted(self.lag_ms)
        usage = getattr(self.llm, "usage", None)
        return {"model": self.llm.name, "llm_calls": self.llm_calls, "rejected_rewrites": self.rejected_rewrites,
                "retracted": sum(r["retracted"] for r in rows), "total": len(rows),
                "queue_depth": self.queue.qsize() if self.queue else 0,
                "profiles": len(self.profiles),
                "ingest": self.ingest.stats() if self.ingest else {"mode": "direct"},
                "write_lag_ms_p50": round(lag[len(lag) // 2], 1) if lag else None,
                "write_lag_ms_p95": round(lag[int(len(lag) * 0.95)], 1) if lag else None,
                "usage": usage.as_dict() if usage else None,
                "insights": rows[-500:]}


def overlays(b: Broadcast, items: list[dict]) -> list[dict]:
    """Timed, machine-readable overlays for a graphics renderer, one per published insight.

    show/hide are in match milliseconds (t_ms), so a renderer can sync them to the feed it is playing.
    """
    out = []
    for it in items:
        slot, template, dur = OVERLAY_STYLE.get(it["kind"], DEFAULT_STYLE)
        facts = [b.engine.facts.get(f) for f in it["fact_ids"]]
        metric = next(({"kind": f.kind, "value": f.value, "unit": f.unit} for f in facts
                       if f is not None and isinstance(f.value, (int, float)) and f.kind != "score"), None)
        teams = {f.subject_id for f in facts if f is not None}
        colour = (b.info.home.colour if b.info.home.team_id in teams else
                  b.info.away.colour if b.info.away.team_id in teams else None)
        out.append({"overlay_id": it["insight_id"], "insight_id": it["insight_id"], "show_at_t_ms": it["t_ms"],
                    "hide_at_t_ms": it["t_ms"] + dur, "slot": slot, "template": template,
                    "payload": {"minute": it["minute"], "text": it["text"], "kind": it["kind"], "metric": metric,
                                "team_colour": colour, "evidence_facts": len(it["fact_ids"])}})
    return out


def evidence(engine: Engine, fact_ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for fid in fact_ids:
        f = engine.facts.get(fid)
        if f:
            out[fid] = f.evidence
    return dict(out)
