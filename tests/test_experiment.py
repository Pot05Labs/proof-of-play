import numpy as np
import pytest

from pop.experiment.core import EngagementLog, assign_arm, new_session, readout
from pop.experiment.simulated import is_simulated, simulated_log
from pop.schema import EngagementEvent


def test_assignment_is_stable_and_seed_dependent():
    assert assign_arm("abc", "s1") == assign_arm("abc", "s1")
    arms = {assign_arm("abc", f"seed{i}") for i in range(50)}
    assert arms == {"personalised", "generic"}


def test_assignment_is_balanced():
    arms = [assign_arm(f"session-{i}", "balance-seed") for i in range(10_000)]
    share = arms.count("personalised") / len(arms)
    assert abs(share - 0.5) < 0.02


def test_no_session_without_consent_and_no_empty_seed():
    with pytest.raises(PermissionError):
        new_session("seed", consent=False)
    with pytest.raises(ValueError):
        assign_arm("x", "")


def test_session_never_stores_the_seed():
    s = new_session("super-secret-seed", consent=True)
    assert "super-secret-seed" not in s.model_dump_json()


def test_arm_cannot_be_reassigned():
    log = EngagementLog()
    s = new_session("seed", consent=True)
    log.add_session(s)
    with pytest.raises(ValueError):
        log.add_session(s)


def test_watched_minutes_counts_distinct_heartbeat_slots():
    log = EngagementLog()
    s = new_session("seed", consent=True)
    log.add_session(s)
    for t in [0, 15_000, 15_000, 30_000, 45_000]:  # duplicate beat must not double count
        log.record(EngagementEvent(session_id=s.session_id, t_ms=t, kind="heartbeat"))
    assert log.watched_minutes(s.session_id) == pytest.approx(1.0)


def test_readout_detects_a_planted_lift():
    r = readout(simulated_log(1500, true_lift_minutes=6.0, seed=3))
    assert r.ci_low > 0 and r.ci_low < 6.0 < r.ci_high
    assert "more" in r.verdict


def test_readout_finds_nothing_when_there_is_nothing():
    r = readout(simulated_log(1500, true_lift_minutes=0.0, seed=4))
    assert r.ci_low < 0 < r.ci_high
    assert "No detectable difference" in r.verdict


def test_interval_coverage_is_honest():
    """Across repeated simulated audiences the 95% interval should contain the truth ~95% of the time."""
    truth, hits, runs = 4.0, 0, 60
    for k in range(runs):
        r = readout(simulated_log(300, true_lift_minutes=truth, seed=100 + k), n_boot=1500, rng_seed=k)
        hits += r.ci_low <= truth <= r.ci_high
    assert hits / runs >= 0.85


def test_small_samples_refuse_a_verdict():
    r = readout(simulated_log(2, true_lift_minutes=10, seed=9))
    assert r.verdict == "Not enough sessions yet." or np.isnan(r.ci_low)


def test_simulated_sessions_are_labelled():
    log = simulated_log(10, true_lift_minutes=0, seed=1)
    assert all(is_simulated(s) for s in log.sessions)
