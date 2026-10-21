"""Simulated audience. For demos and for testing the readout. Never mixed with real sessions.

Every simulated session id starts with "SIM-" so it can be filtered out of any real readout,
and the log built here is a separate EngagementLog object.
"""

from __future__ import annotations

import numpy as np

from pop.experiment.core import HEARTBEAT_SECONDS, EngagementLog, assign_arm
from pop.schema import EngagementEvent, Session

SIM_PREFIX = "SIM-"


def simulated_log(n_sessions: int, *, true_lift_minutes: float, seed: int = 1,
                  match_minutes: int = 95, base_mean_minutes: float = 38.0,
                  sd_minutes: float = 22.0, assign_seed: str = "simulated-audience") -> EngagementLog:
    """Sessions whose watch time is drawn with a known, planted personalisation effect."""
    rng = np.random.default_rng(seed)
    log = EngagementLog()
    for i in range(n_sessions):
        sid = f"{SIM_PREFIX}{seed}-{i:05d}"
        arm = assign_arm(sid, assign_seed)
        log.add_session(Session(session_id=sid, started_at="simulated", arm=arm,
                                assignment_seed="simulated", consent=True))
        mean = base_mean_minutes + (true_lift_minutes if arm == "personalised" else 0.0)
        minutes = float(np.clip(rng.normal(mean, sd_minutes), 0, match_minutes))
        start = int(rng.uniform(0, max(1, match_minutes - minutes)) * 60)
        beats = int(minutes * 60 // HEARTBEAT_SECONDS)
        for k in range(beats):
            ts = start + k * HEARTBEAT_SECONDS
            log.record(EngagementEvent(session_id=sid, t_ms=ts * 1000, kind="heartbeat"), received_s=ts)
        taps = rng.poisson(0.15 * minutes * (1.3 if arm == "personalised" else 1.0))
        for _ in range(taps):
            ts = start + rng.uniform(0, minutes * 60)
            log.record(EngagementEvent(session_id=sid, t_ms=int(ts * 1000), kind="why_tap"), received_s=ts)
    return log


def is_simulated(session_id: str) -> bool:
    return session_id.startswith(SIM_PREFIX)
