from pop.experiment.core import EngagementLog, new_session
from pop.experiment.store import rehydrate
from pop.schema import EngagementEvent


class FakeStore:
    """Records what the log writes, the way CosmosStore would."""

    def __init__(self):
        self.sessions, self.events = [], []

    def session(self, s):
        self.sessions.append(s)

    def event(self, e, received_s, n):
        self.events.append((e, received_s, n))


def test_every_session_and_event_is_written_through():
    store = FakeStore()
    log = EngagementLog(sink=store)
    s = new_session("seed", consent=True)
    log.add_session(s)
    for k in range(4):
        log.record(EngagementEvent(session_id=s.session_id, t_ms=0, kind="heartbeat"), received_s=1000 + 15 * k)
    assert [x.session_id for x in store.sessions] == [s.session_id]
    assert [n for _, _, n in store.events] == [1, 2, 3, 4]


def test_restart_rebuilds_the_same_readout_without_rewriting():
    store = FakeStore()
    log = EngagementLog(sink=store)
    for _ in range(6):
        s = new_session("seed", consent=True)
        log.add_session(s)
        for k in range(8):
            log.record(EngagementEvent(session_id=s.session_id, t_ms=0, kind="heartbeat"), received_s=5000 + 15 * k)
    written = len(store.events)

    fresh = EngagementLog(sink=store)
    n = rehydrate(fresh, store.sessions, [(e, r) for e, r, _ in store.events])
    assert n == written and len(store.events) == written  # rehydrate never writes back
    assert {k: fresh.watched_minutes(k) for k in fresh.sessions} == {k: log.watched_minutes(k) for k in log.sessions}
    assert {k: v.arm for k, v in fresh.sessions.items()} == {k: v.arm for k, v in log.sessions.items()}


def test_store_names_argument_then_env_then_default(monkeypatch):
    from pop.experiment.store import resolve_names
    monkeypatch.delenv("COSMOS_CONTAINER", raising=False)
    monkeypatch.delenv("COSMOS_DATABASE", raising=False)
    assert resolve_names() == ("pop", "engagement")
    monkeypatch.setenv("COSMOS_CONTAINER", "")  # blank means unset, never an empty container name
    assert resolve_names() == ("pop", "engagement")
    monkeypatch.setenv("COSMOS_CONTAINER", "watchalong")
    monkeypatch.setenv("COSMOS_DATABASE", "popx")
    assert resolve_names() == ("popx", "watchalong")
    assert resolve_names("d", "loadtest") == ("d", "loadtest")
