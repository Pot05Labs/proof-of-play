"""Watch-along load test: N simulated viewers against a live deployment.

Each viewer joins with consent, then every 2 s polls /api/state, /api/events and /api/feed (as the web app does)
and sends a heartbeat every 15 s. Reports request latency, error rate, and how far the live match clock
falls behind the wall clock.

Simulated viewers are NOT real data. Only run this against a deployment whose COSMOS_CONTAINER is `loadtest`
(check `store.container` in /api/producer first; the script refuses otherwise). Before the real watch-along,
redeploy with cosmosContainer=watchalong and a fresh POP_EXPERIMENT_SEED: that starts a new process, so no
simulated session survives in memory either.

  uv run python scripts/loadtest.py --url https://... --viewers 400 --minutes 3
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

import httpx

LAT: dict[str, list[float]] = {}
ERR: dict[str, int] = {}


async def call(client: httpx.AsyncClient, method: str, path: str, name: str, **kw) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await client.request(method, path, **kw)
        LAT.setdefault(name, []).append((time.perf_counter() - t) * 1000)
        if r.status_code >= 400:
            ERR[f"{name}:{r.status_code}"] = ERR.get(f"{name}:{r.status_code}", 0) + 1
        return r
    except httpx.HTTPError as e:
        ERR[f"{name}:{type(e).__name__}"] = ERR.get(f"{name}:{type(e).__name__}", 0) + 1
        return None


async def viewer(i: int, client: httpx.AsyncClient, stop: float, clubs: list[dict]) -> None:
    await asyncio.sleep(random.uniform(0, 20))  # people arrive over 20 s, not all at once
    club = random.choice(clubs)
    body = {"consent": True, "mode": random.choice(["fan", "analyst"]),
            "club_id": club["team_id"] if random.random() < 0.8 else None,
            "player_id": random.choice(club["squad"])["player_id"] if random.random() < 0.4 else None,
            "language": random.choices(["en", "zu", "sw", "es"], [6, 2, 1, 1])[0]}
    r = await call(client, "POST", "/api/session", "join", json=body)
    if not r or r.status_code != 200:
        return
    sid, since, last_beat = r.json()["session_id"], 0, 0.0
    while time.time() < stop:
        st = await call(client, "GET", "/api/state", "state")
        t_ms = st.json().get("t_ms", 0) if st is not None and st.status_code == 200 else 0
        ev = await call(client, "GET", "/api/events", "events", params={"since": since})
        if ev is not None and ev.status_code == 200:
            since = ev.json().get("seq", since)
        await call(client, "GET", f"/api/feed/{sid}", "feed")
        if time.time() - last_beat >= 15:
            await call(client, "POST", "/api/engage", "engage", json={"session_id": sid, "t_ms": t_ms, "kind": "heartbeat"})
            last_beat = time.time()
        await asyncio.sleep(2)


async def main(url: str, n: int, minutes: float, key: str | None, speed: float) -> None:
    limits = httpx.Limits(max_connections=n, max_keepalive_connections=n)
    async with httpx.AsyncClient(base_url=url, timeout=15, limits=limits) as client:
        if key:
            await client.post("/api/admin/start", headers={"x-pop-key": key},
                              json={"seed": 7, "speed": speed, "var_overturn": True})
        if key:
            store = (await client.get("/api/producer", headers={"x-pop-key": key})).json().get("store") or {}
            if store.get("container") != "loadtest":
                raise SystemExit(f"refusing: live app writes to container {store.get('container')!r}, not 'loadtest'")
        info = (await client.get("/api/match")).json()
        clubs = [info["home"], info["away"]]
        start = time.time()
        stop = start + minutes * 60
        s0 = (await client.get("/api/state")).json()
        await asyncio.gather(*(viewer(i, client, stop, clubs) for i in range(n)))
        s1 = (await client.get("/api/state")).json()
        wall = time.time() - start
        match_s = (s1["t_ms"] - s0["t_ms"]) / 1000
        prod = (await client.get("/api/producer", headers={"x-pop-key": key})).json() if key else {}
    print(f"viewers {n}, {minutes} min, broadcast speed {speed}x")
    for name, xs in sorted(LAT.items()):
        xs.sort()
        print(f"  {name:7s} n={len(xs):6d}  p50={statistics.median(xs):7.1f} ms  p95={xs[int(len(xs) * .95)]:7.1f} ms"
              f"  max={xs[-1]:7.1f} ms")
    print(f"  errors: {ERR or 'none'}")
    print(f"  match clock advanced {match_s:.0f} s in {wall:.0f} s wall = {match_s / wall:.2f}x (target {speed}x)")
    if prod:
        print(f"  producer: profiles={prod.get('profiles')} calls={prod.get('llm_calls')} queue={prod.get('queue_depth')}"
              f" write lag p50={prod.get('write_lag_ms_p50')} p95={prod.get('write_lag_ms_p95')} ms"
              f" usage={prod.get('usage')} store={prod.get('store')}")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--url", required=True)
    a.add_argument("--viewers", type=int, default=400)
    a.add_argument("--minutes", type=float, default=3)
    a.add_argument("--key")
    a.add_argument("--speed", type=float, default=10)
    x = a.parse_args()
    asyncio.run(main(x.url, x.viewers, x.minutes, x.key, x.speed))
