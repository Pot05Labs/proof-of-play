"""One live broadcast shared by every viewer: simulator -> engine -> agents.

Every viewer sees the same match on the same clock. The arm only changes the insight layer:
  generic       neutral sentences for moments above the broadcast floor, no mode, club or player;
  personalised  the viewer's mode, language, club and player, plus extra moments about their club
                and player above a lower floor.
"""

from __future__ import annotations

import asyncio
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

    def load(self) -> None:
        self.info, self.events = generate(self.seed, var_overturn=self.var_overturn)
        self.engine = Engine(self.info)
        self.seq, self.t_ms, self.moments, self.cache = 0, 0, [], {}
        self.retracted_insights, self.finished = set(), False

    async def run(self) -> None:
        if self.info is None:
            self.load()
        self.running = True
        async for ev in astream(self.events, self.speed):
            upd = self.engine.ingest(ev)
            self.seq, self.t_ms = ev.seq, ev.t_ms
            if upd.retraction:
                for key, pub in list(self.cache.items()):
                    if set(pub.insight.fact_ids) & set(upd.retraction.retracted_fact_ids):
                        self.retracted_insights.add(pub.insight.insight_id)
                self._fan_out({"type": "retraction", "retraction": upd.retraction.model_dump(),
                               "insight_ids": sorted(self.retracted_insights)})
            for m in upd.moments:
                self.moments.append(m)
                if self.visible(m, Viewer(), "generic"):
                    self.insight_for(m, Viewer())  # the broadcast version is written live
                self._fan_out({"type": "moment", "moment_id": m.moment_id, "importance": m.importance})
            self._fan_out({"type": "tick", "seq": ev.seq})
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
        key = (m.moment_id, viewer)
        if key not in self.cache:
            facts = self.facts_of(m)
            ev = self.events[m.seq_at - 1]
            t0 = time.perf_counter()
            ins = explain(m, facts, self.info, viewer, llm=self.llm, minute=ev.clock.minute)
            self.llm_calls += 1
            self.rejected_rewrites += "rejected" in ins.verifier_notes
            self.cache[key] = Published(ins, m.seq_at, ev.t_ms, ev.clock.minute,
                                        (time.perf_counter() - t0) * 1000)
        return self.cache[key]

    def feed(self, session: Session) -> list[dict]:
        viewer = Viewer(language=session.language) if session.arm == "generic" else Viewer(
            audience=session.mode, language=session.language, club_id=session.club_id, player_id=session.player_id)
        out = []
        for m in self.moments:
            if not self.visible(m, viewer, session.arm):
                continue
            pub = self.insight_for(m, viewer)
            if self.is_pulled(pub) or pub.insight.status == "rejected":
                continue
            out.append({"insight_id": pub.insight.insight_id, "minute": pub.minute, "t_ms": pub.t_ms,
                        "text": pub.insight.text, "fact_ids": pub.insight.fact_ids,
                        "importance": m.importance, "kind": m.kind})
        return out

    def producer_view(self) -> dict:
        rows = []
        for (mid, viewer), pub in self.cache.items():
            rows.append({"insight_id": pub.insight.insight_id, "minute": pub.minute, "text": pub.insight.text,
                         "verified": pub.insight.verified, "notes": pub.insight.verifier_notes,
                         "retracted": self.is_pulled(pub),
                         "audience": viewer.audience, "language": viewer.language,
                         "club": viewer.club_id, "player": viewer.player_id,
                         "latency_ms": round(pub.latency_ms, 1)})
        rows.sort(key=lambda r: r["minute"])
        return {"model": self.llm.name, "llm_calls": self.llm_calls, "rejected_rewrites": self.rejected_rewrites,
                "retracted": sum(r["retracted"] for r in rows), "insights": rows[-200:]}


def evidence(engine: Engine, fact_ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for fid in fact_ids:
        f = engine.facts.get(fid)
        if f:
            out[fid] = f.evidence
    return dict(out)
