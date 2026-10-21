"""Randomised holdout: does personalisation change how people watch?

Plain textbook design, written for this project:
  * each consenting session is assigned once, at random, to `personalised` or `generic`;
  * both arms see the same match, clock and engine facts; only the insight layer differs;
  * the primary metric is watched minutes per session, from heartbeats;
  * the readout is the difference in means with a percentile bootstrap interval over sessions.

Nothing here identifies a person. A session is a random ID and a list of timestamps.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from pop.schema import Arm, EngagementEvent, Session

HEARTBEAT_SECONDS = 15


def assign_arm(session_id: str, seed: str, p_personalised: float = 0.5) -> Arm:
    """Deterministic given (seed, session_id), unpredictable without the seed.

    HMAC-SHA256 of the session id keyed by the server-side seed, mapped to [0,1).
    The same session always lands in the same arm; a client cannot choose its arm.
    """
    if not seed:
        raise ValueError("assignment seed must be set")
    digest = hmac.new(seed.encode(), session_id.encode(), hashlib.sha256).digest()
    u = int.from_bytes(digest[:8], "big") / 2**64
    return "personalised" if u < p_personalised else "generic"


def new_session(seed: str, *, consent: bool, mode: str = "fan", club_id: str | None = None,
                player_id: str | None = None, language: str = "en") -> Session:
    if not consent:
        raise PermissionError("no session without consent")
    sid = secrets.token_hex(12)
    return Session(
        session_id=sid,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        arm=assign_arm(sid, seed),
        assignment_seed=hashlib.sha256(seed.encode()).hexdigest()[:12],  # fingerprint, never the seed
        consent=True, mode=mode, club_id=club_id, player_id=player_id, language=language,
    )


@dataclass
class EngagementLog:
    sessions: dict[str, Session] = field(default_factory=dict)
    events: dict[str, list[EngagementEvent]] = field(default_factory=lambda: defaultdict(list))

    def add_session(self, s: Session) -> None:
        if s.session_id in self.sessions:
            raise ValueError("session already registered; arms are never re-assigned")
        self.sessions[s.session_id] = s

    def record(self, e: EngagementEvent) -> None:
        if e.session_id not in self.sessions:
            raise KeyError("unknown session")
        self.events[e.session_id].append(e)

    def watched_minutes(self, session_id: str) -> float:
        hb = {e.t_ms // 1000 // HEARTBEAT_SECONDS for e in self.events[session_id] if e.kind == "heartbeat"}
        return len(hb) * HEARTBEAT_SECONDS / 60.0

    def taps_per_minute(self, session_id: str) -> float:
        mins = self.watched_minutes(session_id)
        taps = sum(1 for e in self.events[session_id] if e.kind in ("why_tap", "show_me_tap"))
        return taps / mins if mins > 0 else 0.0


@dataclass(frozen=True)
class Readout:
    metric: str
    n_personalised: int
    n_generic: int
    mean_personalised: float
    mean_generic: float
    diff: float
    ci_low: float
    ci_high: float
    level: float

    @property
    def verdict(self) -> str:
        if self.n_personalised < 2 or self.n_generic < 2:
            return "Not enough sessions yet."
        if self.ci_low > 0:
            return "Personalised viewers engaged more; the interval excludes zero."
        if self.ci_high < 0:
            return "Personalised viewers engaged less; the interval excludes zero."
        return "No detectable difference yet; the interval includes zero."


def readout(log: EngagementLog, metric: str = "watched_minutes", *, n_boot: int = 5000,
            level: float = 0.95, rng_seed: int = 0) -> Readout:
    fn = {"watched_minutes": log.watched_minutes, "taps_per_minute": log.taps_per_minute}[metric]
    a = np.array([fn(s) for s, ses in log.sessions.items() if ses.arm == "personalised"], dtype=float)
    b = np.array([fn(s) for s, ses in log.sessions.items() if ses.arm == "generic"], dtype=float)
    if len(a) < 2 or len(b) < 2:
        ma = float(a.mean()) if len(a) else float("nan")
        mb = float(b.mean()) if len(b) else float("nan")
        return Readout(metric, len(a), len(b), ma, mb, ma - mb, float("nan"), float("nan"), level)
    rng = np.random.default_rng(rng_seed)
    ia = rng.integers(0, len(a), size=(n_boot, len(a)))
    ib = rng.integers(0, len(b), size=(n_boot, len(b)))
    diffs = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    lo, hi = np.quantile(diffs, [(1 - level) / 2, 1 - (1 - level) / 2])
    return Readout(metric, len(a), len(b), float(a.mean()), float(b.mean()),
                   float(a.mean() - b.mean()), float(lo), float(hi), level)
