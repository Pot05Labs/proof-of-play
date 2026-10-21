"""Hand-built event sequences for engine tests and demos (fictional teams only)."""

from __future__ import annotations

from typing import Any

from pop.schema import Clock, EventType, MatchEvent, MatchInfo, Player, Team

HOME = "HOM"
AWAY = "AWY"


def fictional_match_info(match_id: str = "m1") -> MatchInfo:
    def squad(prefix: str) -> list[Player]:
        positions = ["GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW"]
        return [
            Player(player_id=f"{prefix}{i}", name=f"Player {prefix}{i}", number=i, position=pos)  # type: ignore[arg-type]
            for i, pos in enumerate(positions, start=1)
        ]

    return MatchInfo(
        match_id=match_id,
        seed=7,
        competition="Test Shield",
        venue="Example Park",
        home=Team(team_id=HOME, name="Riverside Test", short="RIV", style="possession", colour="#123456",
                  squad=squad("H")),
        away=Team(team_id=AWAY, name="Northgate Test", short="NOR", style="direct", colour="#654321",
                  squad=squad("A")),
    )


class EventBuilder:
    """Appends events with strictly increasing seq and non-decreasing t_ms."""

    def __init__(self, match_id: str = "m1") -> None:
        self.match_id = match_id
        self.seq = 0
        self.t_ms = 0
        self.period: int = 1
        self.events: list[MatchEvent] = []

    def add(self, type_: EventType | str, dt_ms: int = 0, **fields: Any) -> MatchEvent:
        self.seq += 1
        self.t_ms += dt_ms
        total_s = self.t_ms // 1000
        minute = min(130, total_s // 60)
        ev = MatchEvent(
            event_id=f"{self.match_id}:{self.seq:05d}",
            match_id=self.match_id,
            seq=self.seq,
            clock=Clock(period=self.period, minute=minute, second=total_s % 60),  # type: ignore[arg-type]
            t_ms=self.t_ms,
            type=EventType(type_),
            **fields,
        )
        self.events.append(ev)
        return ev

    # convenience wrappers -------------------------------------------------

    def kick_off(self, team: str = HOME, dt_ms: int = 0) -> MatchEvent:
        return self.add("kick_off", dt_ms, team_id=team)

    def pass_(self, team: str, player: str, dt_ms: int = 2000, x: float = 40.0, y: float = 50.0,
              end_x: float = 50.0, end_y: float = 50.0, ok: bool = True, pressure: float = 0.2,
              speed: float | None = None) -> MatchEvent:
        meta: dict[str, Any] = {"receiver_id": player, "body_part": "foot"}
        if speed is not None:
            meta["ball_speed_kmh"] = speed
        return self.add("pass", dt_ms, team_id=team, player_id=player, x=x, y=y, end_x=end_x, end_y=end_y,
                        outcome="success" if ok else "fail", pressure=pressure, meta=meta)

    def shot(self, team: str, player: str, dt_ms: int = 2000, x: float = 88.0, y: float = 50.0,
             outcome: str = "saved", situation: str = "open_play", body_part: str = "foot",
             pressure: float = 0.2, speed: float | None = 80.0) -> MatchEvent:
        meta: dict[str, Any] = {"body_part": body_part, "situation": situation}
        if speed is not None:
            meta["ball_speed_kmh"] = speed
        return self.add("shot", dt_ms, team_id=team, player_id=player, x=x, y=y, end_x=100.0, end_y=50.0,
                        outcome=outcome, pressure=pressure, meta=meta)

    def possession(self, to_team: str, dt_ms: int = 1000) -> MatchEvent:
        from_team = AWAY if to_team == HOME else HOME
        return self.add("possession_change", dt_ms, team_id=to_team,
                        meta={"from_team_id": from_team, "to_team_id": to_team, "cause": "tackle"})

    def pressure(self, team: str, player: str, dt_ms: int = 1000) -> MatchEvent:
        return self.add("pressure", dt_ms, team_id=team, player_id=player, x=60.0, y=50.0,
                        meta={"target_player_id": "x"})

    def var(self, subject: MatchEvent, decision: str = "overturned", dt_ms: int = 30_000) -> MatchEvent:
        self.add("var_review", dt_ms, related=[subject.event_id],
                 meta={"subject_event_id": subject.event_id, "check": "offside"})
        return self.add("var_decision", dt_ms, related=[subject.event_id],
                        meta={"subject_event_id": subject.event_id, "decision": decision, "reason": "offside"})
