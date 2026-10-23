import asyncio

from fastapi.testclient import TestClient

import pop.api.app as appmod
from pop.api.broadcast import Broadcast
from pop.experiment.core import EngagementLog


def _client(monkeypatch):
    monkeypatch.setenv("POP_EXPERIMENT_SEED", "test-seed")
    monkeypatch.setenv("POP_ADMIN_KEY", "k")
    appmod.B = Broadcast(seed=7, speed=0, var_overturn=True)
    appmod.LOG = EngagementLog()
    appmod.JOIN_LIMIT = appmod._Limiter(10_000)
    appmod.ENGAGE_LIMIT = appmod._Limiter(10_000)
    return TestClient(appmod.app)


def _run_match():
    asyncio.run(appmod.B.run())


def test_full_match_end_to_end(monkeypatch):
    c = _client(monkeypatch)
    info = c.get("/api/match").json()
    home = info["home"]["team_id"]
    star = info["home"]["squad"][9]["player_id"]

    sessions = [c.post("/api/session", json={"consent": True, "mode": "analyst", "club_id": home,
                                              "player_id": star}).json()["session_id"] for _ in range(40)]
    assert all("arm" not in c.post("/api/session", json={"consent": True}).json() for _ in range(3))

    _run_match()
    assert appmod.B.finished

    arms = {appmod.LOG.sessions[s].arm for s in sessions}
    assert arms == {"personalised", "generic"}

    feeds = {s: c.get(f"/api/feed/{s}").json()["insights"] for s in sessions}
    p = next(feeds[s] for s in sessions if appmod.LOG.sessions[s].arm == "personalised")
    g = next(feeds[s] for s in sessions if appmod.LOG.sessions[s].arm == "generic")
    assert len(g) > 0
    assert len(p) >= len(g)  # personalised viewers get their club and player moments on top

    prod = c.get("/api/producer", headers={"x-pop-key": "k"}).json()
    assert prod["insights"] and all(r["verified"] for r in prod["insights"] if not r["retracted"])
    assert prod["retracted"] >= 1  # the VAR overturn pulled at least one published insight

    retracted = {r["insight_id"] for r in prod["insights"] if r["retracted"]}
    for f in feeds.values():
        assert not retracted & {i["insight_id"] for i in f}

    fid = g[0]["fact_ids"][0]
    ev = c.get("/api/evidence", params={"fact_ids": fid}).json()
    assert ev["evidence"][fid]


def test_engagement_and_readout(monkeypatch):
    c = _client(monkeypatch)
    sid = c.post("/api/session", json={"consent": True}).json()["session_id"]
    for t in range(0, 120_000, 15_000):
        assert c.post("/api/engage", json={"session_id": sid, "t_ms": t, "kind": "heartbeat"}).status_code == 200
    assert c.post("/api/engage", json={"session_id": "nope", "t_ms": 0, "kind": "heartbeat"}).status_code == 404
    assert c.get("/api/readout").status_code == 403
    r = c.get("/api/readout", params={"simulated": True}, headers={"x-pop-key": "k"}).json()
    assert r["simulated"] is True and r["n_personalised"] + r["n_generic"] == 400


def test_consent_is_required(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/session", json={"consent": False}).status_code >= 400


def test_events_never_run_ahead_of_the_clock(monkeypatch):
    c = _client(monkeypatch)
    c.get("/api/match")
    assert c.get("/api/events").json()["events"] == []
    appmod.B.seq = 10
    ev = c.get("/api/events", params={"since": 0}).json()["events"]
    assert len(ev) == 10 and ev[-1]["seq"] == 10


def test_feed_ids_are_opaque_and_retraction_events_leak_nothing(monkeypatch):
    c = _client(monkeypatch)
    sid = c.post("/api/session", json={"consent": True, "mode": "analyst"}).json()["session_id"]
    q = asyncio.Queue()
    appmod.B.subscribers.add(q)
    _run_match()
    for item in c.get(f"/api/feed/{sid}").json()["insights"]:
        assert ":" not in item["insight_id"] and len(item["insight_id"]) == 16
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    retractions = [m for m in msgs if m["type"] == "retraction"]
    assert retractions and all(set(m) == {"type", "seq"} for m in retractions)


def test_readout_with_one_session_returns_nulls_not_500(monkeypatch):
    c = _client(monkeypatch)
    c.post("/api/session", json={"consent": True})
    r = c.get("/api/readout", headers={"x-pop-key": "k"})
    assert r.status_code == 200 and r.json()["ci_low"] is None


def test_join_is_rate_limited_per_client(monkeypatch):
    c = _client(monkeypatch)
    appmod.JOIN_LIMIT = appmod._Limiter(3)
    codes = [c.post("/api/session", json={"consent": True}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_forged_forwarded_for_cannot_dodge_the_join_limit(monkeypatch):
    c = _client(monkeypatch)
    appmod.JOIN_LIMIT = appmod._Limiter(2)
    codes = [c.post("/api/session", json={"consent": True},
                    headers={"x-forwarded-for": f"1.2.3.{i}, 9.9.9.9"}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]


def test_recaps_overlays_and_agent_trace(monkeypatch):
    c = _client(monkeypatch)
    c.get("/api/match")
    _run_match()
    b = appmod.B
    recaps = [m for m in b.moments if m.kind in ("recap_half_time", "recap_full_time")]
    assert [m.kind for m in recaps] == ["recap_half_time", "recap_full_time"]
    for m in recaps:  # recaps cite only facts the engine still stands behind
        assert m.facts and not any(b.engine.facts.is_retracted(f) for f in m.facts)
    ft_score = b.engine.facts.get(recaps[-1].facts[0])
    assert ft_score.kind == "score" and ft_score.value == f"{b.engine.state().score[b.info.home.team_id]}-" \
        f"{b.engine.state().score[b.info.away.team_id]}"  # the corrected score after the VAR overturn

    ov = c.get("/api/overlays").json()["overlays"]
    assert ov and all(o["hide_at_t_ms"] > o["show_at_t_ms"] for o in ov)
    assert {o["slot"] for o in ov} <= {"lower_third", "corner", "full"}
    assert any(o["template"] == "recap_card" for o in ov)
    assert all(":" not in o["insight_id"] for o in ov)  # opaque ids here too

    prod = c.get("/api/producer", headers={"x-pop-key": "k"}).json()
    traced = [r for r in prod["insights"] if r["trace"]]
    assert traced and {"Interpreter", "Verifier"} <= {s["agent"] for s in traced[0]["trace"]}


def test_public_console_is_read_only(monkeypatch):
    c = _client(monkeypatch)
    assert c.get("/api/producer").status_code == 403  # private by default
    assert c.get("/api/health").json()["public_console"] is False
    monkeypatch.setenv("POP_PUBLIC_CONSOLE", "1")
    assert c.get("/api/health").json()["public_console"] is True
    assert c.get("/api/producer").status_code == 200
    assert c.get("/api/readout").status_code == 200
    assert c.post("/api/admin/start", json={"seed": 7, "speed": 0}).status_code == 403  # starting still needs the key


def test_autoloop_plays_matches_back_to_back(monkeypatch):
    _client(monkeypatch)
    monkeypatch.setenv("POP_AUTOLOOP_SPEED", "0")
    monkeypatch.setenv("POP_AUTOLOOP_SEEDS", "7,11")
    played = []
    real_run = appmod.B.run

    async def run_and_record():
        played.append(appmod.B.seed)
        await real_run()
        if len(played) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(appmod.B, "run", run_and_record)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(appmod.asyncio, "sleep", lambda s: real_sleep(0))
    try:
        asyncio.run(appmod._autoloop())
    except asyncio.CancelledError:
        pass
    assert played == [7, 11]
    assert appmod.B.finished and appmod.B.var_overturn
