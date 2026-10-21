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

from pop.agents.explainer import Viewer, explain
from pop.agents.llm import LLM, get_llm
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

    def _enqueue(self, m: Moment, viewer: Viewer, arm: str) -> None:
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
        async for ev in astream(self.events, self.speed):
            upd = self.engine.ingest(ev)
            self.seq, self.t_ms = ev.seq, ev.t_ms
            if upd.retraction:
                for key, pub in list(self.cache.items()):
                    if set(pub.insight.fact_ids) & set(upd.retraction.retracted_fact_ids):
                        self.retracted_insights.add(pub.insight.insight_id)
                self._fan_out({"type": "retraction", "seq": ev.seq})
            for m in upd.moments:
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
        await self.queue.join()
        for t in pool:
            t.cancel()
        self.running, self.finished = False, True
        self._fan_out({"type": "finished"})

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
        ins = explain(m, facts, self.info, viewer, llm=self.llm, minute=ev.clock.minute)
        pub = Published(ins, m.seq_at, ev.t_ms, ev.clock.minute, (time.perf_counter() - t0) * 1000)
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
                         "latency_ms": round(pub.latency_ms, 1)})
        rows.sort(key=lambda r: r["minute"])
        lag = sorted(self.lag_ms)
        usage = getattr(self.llm, "usage", None)
        return {"model": self.llm.name, "llm_calls": self.llm_calls, "rejected_rewrites": self.rejected_rewrites,
                "retracted": sum(r["retracted"] for r in rows), "total": len(rows),
                "queue_depth": self.queue.qsize() if self.queue else 0,
                "profiles": len(self.profiles),
                "write_lag_ms_p50": round(lag[len(lag) // 2], 1) if lag else None,
                "write_lag_ms_p95": round(lag[int(len(lag) * 0.95)], 1) if lag else None,
                "usage": usage.as_dict() if usage else None,
                "insights": rows[-500:]}


def evidence(engine: Engine, fact_ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for fid in fact_ids:
        f = engine.facts.get(fid)
        if f:
            out[fid] = f.evidence
    return dict(out)
