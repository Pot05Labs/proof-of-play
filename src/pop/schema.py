"""Shared data contracts. Every stage imports from here; see docs/SPEC.md."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    MATCH_START = "match_start"
    KICK_OFF = "kick_off"
    HALF_TIME = "half_time"
    FULL_TIME = "full_time"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    CLEARANCE = "clearance"
    FOUL = "foul"
    PRESSURE = "pressure"
    POSSESSION_CHANGE = "possession_change"
    SUBSTITUTION = "substitution"
    VAR_REVIEW = "var_review"
    VAR_DECISION = "var_decision"


Outcome = Literal["success", "fail", "goal", "saved", "off_target", "blocked", "won", "lost"]


class Clock(BaseModel):
    period: Literal[1, 2]
    minute: int = Field(ge=0, le=130)
    second: int = Field(ge=0, le=59)
    added: int = Field(default=0, ge=0)


class MatchEvent(BaseModel):
    event_id: str
    match_id: str
    seq: int = Field(ge=1)
    clock: Clock
    t_ms: int = Field(ge=0)
    type: EventType
    team_id: str | None = None
    player_id: str | None = None
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    end_x: float | None = Field(default=None, ge=0, le=100)
    end_y: float | None = Field(default=None, ge=0, le=100)
    outcome: Outcome | None = None
    pressure: float | None = Field(default=None, ge=0, le=1)
    related: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class Player(BaseModel):
    player_id: str
    name: str
    number: int
    position: Literal["GK", "DF", "MF", "FW"]
    starter: bool = True


class Team(BaseModel):
    team_id: str
    name: str
    short: str
    style: Literal["high_press", "possession", "low_block", "direct"]
    colour: str
    squad: list[Player]


class MatchInfo(BaseModel):
    match_id: str
    seed: int
    competition: str
    venue: str
    home: Team
    away: Team


SubjectKind = Literal["team", "player", "match"]


class Fact(BaseModel):
    fact_id: str
    seq_at: int
    kind: str
    subject_kind: SubjectKind
    subject_id: str
    value: float | int | str
    unit: str = ""
    window: str = "match"
    evidence: list[str]
    computed_by: str


class Moment(BaseModel):
    moment_id: str
    seq_at: int
    kind: str
    importance: float = Field(ge=0, le=1)
    facts: list[str]


class Retraction(BaseModel):
    subject_event_id: str
    seq_at: int
    retracted_fact_ids: list[str]
    retracted_moment_ids: list[str]


Audience = Literal["analyst", "fan"]
InsightStatus = Literal["draft", "approved", "published", "retracted", "rejected"]


class Insight(BaseModel):
    insight_id: str
    moment_id: str
    audience: Audience
    language: str = "en"
    text: str
    fact_ids: list[str]
    verified: bool = False
    verifier_notes: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)
    status: InsightStatus = "draft"
    personalised_for: dict[str, str] = Field(default_factory=dict)


class Overlay(BaseModel):
    overlay_id: str
    insight_id: str
    show_at_t_ms: int
    hide_at_t_ms: int
    slot: Literal["lower_third", "corner", "full"]
    template: str
    payload: dict[str, Any]


Arm = Literal["personalised", "generic"]


class Session(BaseModel):
    session_id: str
    started_at: str
    arm: Arm
    assignment_seed: str
    consent: bool
    mode: Audience = "fan"
    club_id: str | None = None
    player_id: str | None = None
    language: str = "en"


EngagementKind = Literal[
    "heartbeat", "why_tap", "show_me_tap", "replay_open", "mode_change",
    "visibility_hidden", "visibility_visible", "leave",
]


class EngagementEvent(BaseModel):
    session_id: str
    t_ms: int = Field(ge=0)
    kind: EngagementKind
    meta: dict[str, Any] = Field(default_factory=dict)
