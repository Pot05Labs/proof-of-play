"""Durable engagement log: write-through to Azure Cosmos DB, rehydrate on start.

Writes go through a background thread so a viewer's request never waits on the database.
If Cosmos is slow or briefly unavailable, writes retry with backoff; the in-memory log keeps serving.
Documents expire after 30 days (container TTL), so the watch-along data deletes itself after judging.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Iterable

from pop.schema import EngagementEvent, Session

log = logging.getLogger("pop.store")


class CosmosStore:
    def __init__(self, endpoint: str | None = None, database: str = "pop", container: str = "engagement") -> None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        self.client = CosmosClient(endpoint or os.environ["COSMOS_ENDPOINT"], credential=DefaultAzureCredential())
        self.container = self.client.get_database_client(database).get_container_client(container)
        self.q: queue.Queue[dict] = queue.Queue()
        self.written = 0
        self.failed = 0
        threading.Thread(target=self._drain, name="cosmos-writer", daemon=True).start()

    # ---- sink interface used by EngagementLog ----
    def session(self, s: Session) -> None:
        self.q.put({"id": f"s:{s.session_id}", "kind": "session", **s.model_dump()})

    def event(self, e: EngagementEvent, received_s: float, n: int) -> None:
        self.q.put({"id": f"e:{e.session_id}:{n:06d}", "kind": "event", "received_s": received_s, **e.model_dump()})

    def _drain(self) -> None:
        while True:
            doc = self.q.get()
            for attempt in range(6):
                try:
                    self.container.upsert_item(doc)
                    self.written += 1
                    break
                except Exception as exc:  # noqa: BLE001 - retry any transient 429/503/network error
                    if attempt == 5:
                        self.failed += 1
                        log.error("cosmos write dropped after retries: %s", type(exc).__name__)
                    time.sleep(0.2 * 2**attempt)
            self.q.task_done()

    def flush(self, timeout: float = 10.0) -> bool:
        end = time.time() + timeout
        while self.q.unfinished_tasks and time.time() < end:
            time.sleep(0.05)
        return not self.q.unfinished_tasks

    def load(self) -> tuple[list[Session], list[tuple[EngagementEvent, float]]]:
        sessions, events = [], []
        for doc in self.container.query_items("SELECT * FROM c", enable_cross_partition_query=True):
            if doc.get("kind") == "session":
                sessions.append(Session.model_validate(_strip(doc)))
            elif doc.get("kind") == "event":
                events.append((EngagementEvent.model_validate(_strip(doc)), float(doc["received_s"]),
                               doc["id"]))
        events.sort(key=lambda t: t[2])  # per-session order is encoded in the id counter
        return sessions, [(e, r) for e, r, _ in events]

    def stats(self) -> dict:
        return {"written": self.written, "failed": self.failed, "pending": self.q.qsize()}


_SYSTEM = {"id", "kind", "received_s", "_rid", "_self", "_etag", "_attachments", "_ts", "ttl"}


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in _SYSTEM}


def rehydrate(log_, sessions: Iterable[Session], events: Iterable[tuple[EngagementEvent, float]]) -> int:
    """Rebuild an EngagementLog from stored documents without writing them back."""
    sink, log_.sink = log_.sink, None
    try:
        for s in sessions:
            if s.session_id not in log_.sessions:
                log_.add_session(s)
        n = 0
        for e, r in events:
            if e.session_id in log_.sessions:
                log_.record(e, received_s=r)
                n += 1
        return n
    finally:
        log_.sink = sink
