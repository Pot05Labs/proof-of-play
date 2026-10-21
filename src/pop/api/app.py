"""HTTP API for the viewer app and the producer console.

Run locally:  POP_EXPERIMENT_SEED=dev uv run uvicorn pop.api.app:app --reload
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pop.api.broadcast import Broadcast, evidence
from pop.experiment.core import EngagementLog, new_session, readout
from pop.experiment.simulated import simulated_log
from pop.schema import EngagementEvent, EngagementKind

app = FastAPI(title="Proof of Play")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("POP_CORS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

B = Broadcast(seed=int(os.environ.get("POP_MATCH_SEED", "7")), speed=float(os.environ.get("POP_SPEED", "1")))
LOG = EngagementLog()
_task: asyncio.Task | None = None


def _seed() -> str:
    s = os.environ.get("POP_EXPERIMENT_SEED", "")
    if not s:
        raise HTTPException(503, "experiment seed not configured")
    return s


def _admin(key: str | None) -> None:
    want = os.environ.get("POP_ADMIN_KEY")
    if not want or key != want:
        raise HTTPException(403, "producer key required")


class StartReq(BaseModel):
    seed: int = 7
    speed: float = 1.0
    var_overturn: bool = True


class SessionReq(BaseModel):
    consent: bool
    mode: str = "fan"
    club_id: str | None = None
    player_id: str | None = None
    language: str = "en"


class EngageReq(BaseModel):
    session_id: str
    t_ms: int
    kind: EngagementKind


@app.get("/api/health")
def health():
    return {"ok": True, "running": B.running, "finished": B.finished, "seq": B.seq, "model": B.llm.name}


@app.post("/api/admin/start")
async def start(req: StartReq, x_pop_key: str | None = Header(default=None)):
    global _task
    _admin(x_pop_key)
    if _task and not _task.done():
        raise HTTPException(409, "a broadcast is already running")
    B.seed, B.speed, B.var_overturn = req.seed, req.speed, req.var_overturn
    B.load()
    _task = asyncio.create_task(B.run())
    return {"started": True, "match_id": B.info.match_id}


@app.get("/api/match")
def match():
    if B.info is None:
        B.load()
    return B.info.model_dump()


@app.post("/api/session")
def session(req: SessionReq):
    if not req.consent:
        raise HTTPException(400, "consent is required to join")
    s = new_session(_seed(), consent=True, mode=req.mode, club_id=req.club_id,
                    player_id=req.player_id, language=req.language)
    LOG.add_session(s)
    return {"session_id": s.session_id}  # the arm is never sent to the client


@app.post("/api/engage")
def engage(req: EngageReq):
    try:
        LOG.record(EngagementEvent(session_id=req.session_id, t_ms=req.t_ms, kind=req.kind))
    except KeyError as e:
        raise HTTPException(404, "unknown session") from e
    return {"ok": True}


@app.get("/api/state")
def state():
    if B.engine is None:
        B.load()
    return B.engine.state().model_dump()


@app.get("/api/feed/{session_id}")
def feed(session_id: str):
    s = LOG.sessions.get(session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    return {"seq": B.seq, "t_ms": B.t_ms, "insights": B.feed(s)}


@app.get("/api/evidence")
def get_evidence(fact_ids: str):
    ids = [f for f in fact_ids.split(",") if f]
    facts = {fid: B.engine.facts.get(fid).model_dump() for fid in ids if B.engine.facts.get(fid)}
    return {"facts": facts, "evidence": evidence(B.engine, ids)}


@app.get("/api/stream")
async def stream():
    q: asyncio.Queue = asyncio.Queue()
    B.subscribers.add(q)

    async def gen():
        try:
            while True:
                msg = await q.get()
                yield {"event": msg["type"], "data": json.dumps(msg)}
        finally:
            B.subscribers.discard(q)
    return EventSourceResponse(gen())


@app.get("/api/producer")
def producer(x_pop_key: str | None = Header(default=None)):
    _admin(x_pop_key)
    return B.producer_view()


@app.get("/api/readout")
def get_readout(simulated: bool = False, metric: str = "watched_minutes",
                x_pop_key: str | None = Header(default=None)):
    _admin(x_pop_key)
    log = simulated_log(400, true_lift_minutes=5.0, seed=11) if simulated else LOG
    r = readout(log, metric)
    return {"simulated": simulated, **r.__dict__, "verdict": r.verdict}
