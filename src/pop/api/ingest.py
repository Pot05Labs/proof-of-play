"""Event Hubs ingest: the simulator publishes, the engine consumes, in order.

Every match event is sent to Azure Event Hubs with the match id as partition key (one partition, strict order).
A consumer started before the first send reads them back and hands them to the broadcast. A watchdog keeps the
match moving if Event Hubs stalls: any event still not consumed after `max_lag_s` is applied straight from the
local buffer. Applying is idempotent by sequence number, so an event can never be ingested twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable

from pop.schema import MatchEvent
from pop.sim.stream import astream

log = logging.getLogger("pop.ingest")


class EventHubsIngest:
    def __init__(self, namespace: str | None = None, hub: str = "match-events", max_lag_s: float = 3.0) -> None:
        self.namespace = namespace or os.environ["EVENTHUB_NAMESPACE"]
        self.hub = hub
        self.max_lag_s = max_lag_s
        self.sent = 0
        self.via_hub = 0
        self.via_fallback = 0

    async def run(self, events: list[MatchEvent], speed: float,
                  apply: Callable[[MatchEvent], Awaitable[int]]) -> None:
        """Publish `events` paced by `speed`, consume them back, and call apply(ev) once per event in order."""
        from azure.eventhub import EventData
        from azure.eventhub.aio import EventHubConsumerClient, EventHubProducerClient
        from azure.identity.aio import DefaultAzureCredential

        cred = DefaultAzureCredential()
        producer = EventHubProducerClient(self.namespace, self.hub, credential=cred)
        consumer = EventHubConsumerClient(self.namespace, self.hub, consumer_group="$Default", credential=cred)
        buffer: dict[int, tuple[MatchEvent, float]] = {}
        match_id = events[0].match_id if events else ""
        done = asyncio.Event()

        async def on_event(partition_context, event) -> None:
            if event is None:
                return
            try:
                ev = MatchEvent.model_validate(json.loads(event.body_as_str()))
            except Exception:  # noqa: BLE001 - foreign or malformed message on the hub
                return
            if ev.match_id != match_id:
                return
            buffer.pop(ev.seq, None)
            self.via_hub += await apply(ev)

        recv = asyncio.create_task(consumer.receive(on_event=on_event, starting_position="@latest",
                                                    max_wait_time=1))
        await asyncio.sleep(2.0)  # let the consumer attach before the first send

        async def watchdog() -> None:
            while not done.is_set() or buffer:
                now = time.monotonic()
                for seq in sorted(buffer):
                    ev, sent_at = buffer[seq]
                    if now - sent_at < self.max_lag_s:
                        break
                    buffer.pop(seq, None)
                    self.via_fallback += await apply(ev)
                await asyncio.sleep(0.25)

        dog = asyncio.create_task(watchdog())
        try:
            async with producer:
                async for ev in astream(events, speed):
                    buffer[ev.seq] = (ev, time.monotonic())
                    batch = await producer.create_batch(partition_key=match_id)
                    batch.add(EventData(ev.model_dump_json()))
                    try:
                        await producer.send_batch(batch)
                        self.sent += 1
                    except Exception:  # noqa: BLE001 - the watchdog applies it from the buffer
                        log.warning("event hubs send failed at seq %s", ev.seq)
            done.set()
            await asyncio.wait_for(dog, timeout=self.max_lag_s + 30)
        finally:
            done.set()
            dog.cancel()
            await consumer.close()
            recv.cancel()
            await cred.close()

    def stats(self) -> dict:
        return {"mode": "eventhubs", "sent": self.sent, "consumed_via_hub": self.via_hub,
                "applied_via_fallback": self.via_fallback}
