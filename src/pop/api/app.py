"""HTTP API for the viewer app and the producer console.

Run locally:  POP_EXPERIMENT_SEED=dev uv run uvicorn pop.api.app:app --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pop.api.broadcast import GENERIC_SESSION, Broadcast, evidence, overlays
from pop.experiment.core import EngagementLog, new_session, readout
from pop.experiment.simulated import simulated_log
from pop.schema import EngagementEvent, EngagementKind

app = FastAPI(title="Proof of Play")
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def server_timing(request: Request, call_next):
    """Expose server-side processing time so load tests can separate server cost from network cost."""
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["server-timing"] = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}"
    return resp


app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("POP_CORS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

_STORE = None
if os.environ.get("COSMOS_ENDPOINT"):
    from pop.experiment.store import CosmosStore, rehydrate
    try:
        _STORE = CosmosStore()
    except Exception:  # the broadcast must start even if the database is unreachable
        logging.getLogger("pop.app").exception("cosmos unavailable; running in memory only")

B = Broadcast(id_key=os.environ.get("POP_EXPERIMENT_SEED", "dev"), seed=int(os.environ.get("POP_MATCH_SEED", "7")), speed=float(os.environ.get("POP_SPEED", "1")))
LOG = EngagementLog()
if _STORE is not None:
    try:
        _s, _e = _STORE.load()
        _n = rehydrate(LOG, _s, _e)
        logging.getLogger("pop.app").info("rehydrated %d sessions, %d events", len(_s), _n)
    except Exception:
        logging.getLogger("pop.app").exception("rehydrate failed; starting empty")
    LOG.sink = _STORE
for _sess in LOG.sessions.values():
    B.register(_sess)


class _Limiter:
    """Per-client sliding-window limit for the public endpoints."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute, self.hits = per_minute, {}

    def check(self, key: str) -> None:
        now = time.time()
        q = [t for t in self.hits.get(key, []) if now - t < 60]
        if len(q) >= self.per_minute:
            raise HTTPException(429, "too many requests, slow down")
        q.append(now)
        self.hits[key] = q


JOIN_LIMIT = _Limiter(int(os.environ.get("POP_JOIN_PER_MIN", "30")))
ENGAGE_LIMIT = _Limiter(int(os.environ.get("POP_ENGAGE_PER_MIN", "120")))


def _client_key(request: Request) -> str:
    """The address our ingress saw. Azure's ingress APPENDS the real client address to X-Forwarded-For,
    so the last entry is trustworthy; earlier entries are whatever the client sent and can be forged."""
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return fwd[-1] if fwd else (request.client.host if request.client else "unknown")
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


_CACHE: dict[tuple, tuple[float, object]] = {}


def _cached(key: tuple, ttl: float, compute):
    """Share one result between pollers. The console polls every 2 s per open tab, and in judging mode anyone
    can open it, so the single replica that runs the live match must not redo this work per request."""
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = compute()
    _CACHE[key] = (now, val)
    return val


def _public_console() -> bool:
    """For judging: anyone may READ the producer console and readout. Starting a match still needs the key."""
    return os.environ.get("POP_PUBLIC_CONSOLE") == "1"


def _reader(key: str | None) -> None:
    if not _public_console():
        _admin(key)


async def _autoloop() -> None:
    """Judging mode: play match after match so a visitor always finds one live. Seeds rotate, VAR always on."""
    speed = float(os.environ["POP_AUTOLOOP_SPEED"])
    seeds = [int(x) for x in os.environ.get("POP_AUTOLOOP_SEEDS", "7,11,23").split(",") if x.strip()]
    i = 0
    while True:
        try:
            B.seed, B.speed, B.var_overturn = seeds[i % len(seeds)], speed, True
            B.load()
            await B.run()
        except asyncio.CancelledError:
            raise
        except Exception:  # one bad match must not end the loop
            logging.getLogger("pop.app").exception("autoloop match failed")
        i += 1
        await asyncio.sleep(30)  # the full-time recap stays on screen before the next kick-off


@app.on_event("startup")
async def _start_autoloop() -> None:
    global _task
    if os.environ.get("POP_AUTOLOOP_SPEED"):
        _task = asyncio.create_task(_autoloop())


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
    return {"ok": True, "running": B.running, "finished": B.finished, "seq": B.seq, "model": B.llm.name,
            "public_console": _public_console()}


@app.post("/api/admin/start")
async def start(req: StartReq, x_pop_key: str | None = Header(default=None)):
    global _task
    _admin(x_pop_key)
    if os.environ.get("POP_AUTOLOOP_SPEED"):
        raise HTTPException(409, "judging mode: matches replay automatically, so a match cannot be started by hand")
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
def session(req: SessionReq, request: Request):
    JOIN_LIMIT.check(_client_key(request))
    if not req.consent:
        raise HTTPException(400, "consent is required to join")
    s = new_session(_seed(), consent=True, mode=req.mode, club_id=req.club_id,
                    player_id=req.player_id, language=req.language)
    LOG.add_session(s)
    B.register(s)
    return {"session_id": s.session_id}  # the arm is never sent to the client


@app.post("/api/engage")
def engage(req: EngageReq, request: Request):
    ENGAGE_LIMIT.check(req.session_id)
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


@app.get("/api/events")
def events(since: int = 0, limit: int = 200):
    """Match events already played (never ahead of the live clock)."""
    if B.info is None:
        B.load()
    played = B.events[since:B.seq]
    return {"seq": B.seq, "events": [e.model_dump() for e in played[-limit:]]}


@app.get("/api/feed/{session_id}")
def feed(session_id: str):
    s = LOG.sessions.get(session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    return {"seq": B.seq, "t_ms": B.t_ms, "insights": B.feed(s)}


@app.get("/api/overlays")
def broadcast_overlays(since_t_ms: int = 0):
    """The generic broadcast's timed overlays, as a graphics engine would consume them."""
    items = B.feed(GENERIC_SESSION) if B.engine else []
    return {"t_ms": B.t_ms, "overlays": [o for o in overlays(B, items) if o["hide_at_t_ms"] >= since_t_ms]}


@app.get("/api/overlays/{session_id}")
def session_overlays(session_id: str, since_t_ms: int = 0):
    s = LOG.sessions.get(session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    return {"t_ms": B.t_ms, "overlays": [o for o in overlays(B, B.feed(s)) if o["hide_at_t_ms"] >= since_t_ms]}


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
    _reader(x_pop_key)
    return _cached(("producer",), 1.0, lambda: {**B.producer_view(), "store": _STORE.stats() if _STORE else None})


@app.get("/api/readout")
def get_readout(simulated: bool = False, metric: str = "watched_minutes",
                x_pop_key: str | None = Header(default=None)):
    _reader(x_pop_key)

    def compute():
        log = simulated_log(400, true_lift_minutes=5.0, seed=11) if simulated else LOG
        r = readout(log, metric)
        clean = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.__dict__.items()}
        return {"simulated": simulated, **clean, "verdict": r.verdict}

    # The simulated readout never changes; the real one is a bootstrap, so recompute at most every 10 s.
    return _cached(("readout", metric, simulated), 1e9 if simulated else 10.0, compute)


# Serve the built web app (web/dist) from the same origin in production.
_DIST = Path(os.environ.get("POP_WEB_DIST", Path(__file__).resolve().parents[3] / "web" / "dist"))
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if path and f.is_file() else _DIST / "index.html")
