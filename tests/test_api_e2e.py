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
