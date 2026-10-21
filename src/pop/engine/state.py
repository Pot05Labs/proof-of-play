"""Immutable snapshot of engine state at a given seq."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TeamStats(BaseModel):
    team_id: str
    goals: int = 0
    possession_pct: float = 50.0
    territory_share: float = Field(default=0.0, ge=0, le=1)
    """Share of this team's located on-ball actions that happen in its attacking final third."""
    territory_pct: float = 50.0
    """This team's share (0..100) of all final-third actions by both teams."""
    passes: int = 0
    passes_completed: int = 0
    pass_accuracy: float = Field(default=0.0, ge=0, le=1)
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    pressing_intensity: float = Field(default=0.0, ge=0)
    """Pressures by this team per opponent pass over the rolling window."""
    final_third_entries: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


class PlayerStats(BaseModel):
    player_id: str
    team_id: str
    touches: int = 0
    passes: int = 0
    passes_completed: int = 0
    pass_difficulty_avg: float = Field(default=0.0, ge=0, le=1)
    shots: int = 0
    goals: int = 0
    xg: float = 0.0
    distance_m: float = 0.0
    """From player_tracking when available, else the sum of carry distances."""
    top_speed_kmh: float = 0.0
    sprints: int = 0
    yellow_cards: int = 0
    red_card: bool = False


class State(BaseModel):
    match_id: str
    seq: int = 0
    t_ms: int = 0
    play_ms: int = 0
    period: int = 1
    minute: int = 0
    home_team_id: str
    away_team_id: str
    score: dict[str, int]
    teams: dict[str, TeamStats]
    players: dict[str, PlayerStats]
    momentum: float = Field(default=0.0, ge=-1, le=1)
    """Positive favours the home team, negative the away team."""
    control_chaos: float = Field(default=0.0, ge=0, le=1)
    """0 = controlled, 1 = chaotic."""
    max_ball_speed_kmh: float = 0.0
    facts_total: int = 0
    facts_retracted: int = 0
    moments_total: int = 0
    moments_retracted: int = 0
