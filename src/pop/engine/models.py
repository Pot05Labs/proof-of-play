"""Geometric shot (xG) and pass-difficulty models.

Both models are written from first principles for this project. They are
deliberately simple, transparent logistic models over a handful of geometric
and contextual features, so every number they produce can be explained in one
sentence. All coefficients live in pydantic parameter models with defaults so
they can be tuned through ``EngineConfig`` without touching code.

Coordinate convention (docs/SPEC.md section 2): ``x`` and ``y`` run 0..100,
with the acting team attacking left to right, so the opponent goal centre is at
``(100, 50)``. Coordinates are converted to metres using a nominal pitch of
``pitch_length_m`` by ``pitch_width_m``.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

GOAL_X = 100.0
GOAL_Y = 50.0


def _sigmoid(z: float) -> float:
    """Numerically stable logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _clip_open(p: float, eps: float) -> float:
    """Clip a probability into the open interval (0, 1) as [eps, 1 - eps]."""
    return min(1.0 - eps, max(eps, p))


class PitchParams(BaseModel):
    pitch_length_m: float = 105.0
    pitch_width_m: float = 68.0
    goal_width_m: float = 7.32


class XGParams(BaseModel):
    """Coefficients of the logistic xG model.

    ``logit = intercept + angle_coef * angle_rad - distance_coef * distance_m
    + body_part_coef[body] + situation_coef[situation] - pressure_coef * pressure``
    """

    intercept: float = -1.0
    angle_coef: float = 2.0
    distance_coef: float = Field(default=0.09, gt=0)
    pressure_coef: float = Field(default=1.0, ge=0)
    body_part_coef: dict[str, float] = Field(
        default_factory=lambda: {"foot": 0.0, "head": -0.9, "other": -0.6}
    )
    situation_coef: dict[str, float] = Field(
        default_factory=lambda: {"open_play": 0.0, "counter": 0.3, "set_piece": -0.2}
    )
    penalty_xg: float = Field(default=0.76, gt=0, lt=1)
    eps: float = 1e-4


class PassDifficultyParams(BaseModel):
    """Coefficients of the logistic pass-difficulty model.

    ``logit = intercept + length_coef * length_m + forward_coef * forwardness
    + pressure_coef * pressure + lateral_coef * lateralness``
    """

    intercept: float = -2.0
    length_coef: float = Field(default=0.06, gt=0)
    forward_coef: float = 0.8
    pressure_coef: float = Field(default=1.5, gt=0)
    lateral_coef: float = 0.3
    eps: float = 1e-4


def normalise_body_part(body_part: str | None) -> str:
    """Map free-text body parts onto the model's three classes: foot, head, other."""
    if body_part is None:
        return "foot"
    b = body_part.lower()
    if "head" in b:
        return "head"
    if "foot" in b or b in {"left", "right"}:
        return "foot"
    return "other"


def shot_geometry(x: float, y: float, pitch: PitchParams | None = None) -> tuple[float, float]:
    """Distance (m) to the goal centre and the angle (rad) the goal mouth subtends.

    The angle between the two posts as seen from the shooter is
    ``atan2(w * dx, dx^2 + dy^2 - (w/2)^2)`` where ``w`` is the goal width,
    ``dx`` the distance to the goal line and ``dy`` the lateral offset from the
    goal centre. It lies in [0, pi]: pi on the goal line between the posts,
    0 on the goal line outside them.
    """
    p = pitch or PitchParams()
    dx = max(0.0, (GOAL_X - x) / 100.0 * p.pitch_length_m)
    dy = (y - GOAL_Y) / 100.0 * p.pitch_width_m
    distance = math.hypot(dx, dy)
    half = p.goal_width_m / 2.0
    angle = math.atan2(p.goal_width_m * dx, dx * dx + dy * dy - half * half)
    if angle < 0:  # only possible through float noise at dx = 0
        angle = 0.0
    if dx == 0.0 and abs(dy) < half:
        angle = math.pi
    return distance, angle


def xg_from_geometry(
    distance_m: float,
    angle_rad: float,
    body_part: str | None = "foot",
    situation: str | None = "open_play",
    pressure: float | None = 0.0,
    params: XGParams | None = None,
) -> float:
    """Expected goals for a shot, in the open interval (0, 1).

    Formula: ``xG = sigmoid(b0 + b_a*angle - b_d*distance + body + situation - b_p*pressure)``,
    clipped to [eps, 1-eps]. Penalties bypass geometry and return ``penalty_xg``
    (0.76 by default). Distance enters only with a negative coefficient, so with
    the angle held fixed xG is monotone non-increasing in distance.
    """
    q = params or XGParams()
    if situation == "penalty":
        return q.penalty_xg
    z = (
        q.intercept
        + q.angle_coef * angle_rad
        - q.distance_coef * max(0.0, distance_m)
        + q.body_part_coef.get(normalise_body_part(body_part), 0.0)
        + q.situation_coef.get(situation or "open_play", 0.0)
        - q.pressure_coef * min(1.0, max(0.0, pressure or 0.0))
    )
    return _clip_open(_sigmoid(z), q.eps)


def shot_xg(
    x: float,
    y: float,
    body_part: str | None = "foot",
    situation: str | None = "open_play",
    pressure: float | None = 0.0,
    params: XGParams | None = None,
    pitch: PitchParams | None = None,
) -> float:
    """xG from pitch coordinates: ``shot_geometry`` then ``xg_from_geometry``."""
    d, a = shot_geometry(x, y, pitch)
    return xg_from_geometry(d, a, body_part, situation, pressure, params)


def pass_vector(
    x: float | None,
    y: float | None,
    end_x: float | None,
    end_y: float | None,
    length_m: float | None,
    angle_deg: float | None,
    pitch: PitchParams | None = None,
) -> tuple[float, float]:
    """Return (length_m, angle_deg) for a pass.

    Angle convention: 0 deg is straight towards the opponent goal, +-180 deg is
    straight back. Coordinates win when all four are present; otherwise the
    ``meta`` values are used, defaulting to a 0 m, 0 deg pass.
    """
    p = pitch or PitchParams()
    if None not in (x, y, end_x, end_y):
        dx = (end_x - x) / 100.0 * p.pitch_length_m  # type: ignore[operator]
        dy = (end_y - y) / 100.0 * p.pitch_width_m  # type: ignore[operator]
        coord_len = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx)) if coord_len > 0 else 0.0
        return (length_m if length_m is not None else coord_len), ang
    return (length_m or 0.0), (angle_deg or 0.0)


def pass_difficulty(
    length_m: float,
    angle_deg: float = 0.0,
    pressure: float | None = 0.0,
    params: PassDifficultyParams | None = None,
) -> float:
    """Pass difficulty in the open interval (0, 1).

    Formula: ``sigmoid(c0 + c_len*length + c_fwd*cos(angle) + c_p*pressure + c_lat*|sin(angle)|)``,
    clipped to [eps, 1-eps]. ``cos(angle)`` is forwardness (+1 straight at goal,
    -1 straight back) and ``|sin(angle)|`` is lateralness (a cross-field switch).
    Length and pressure have positive coefficients, so difficulty is monotone
    non-decreasing in both.
    """
    q = params or PassDifficultyParams()
    rad = math.radians(angle_deg)
    z = (
        q.intercept
        + q.length_coef * max(0.0, length_m)
        + q.forward_coef * math.cos(rad)
        + q.pressure_coef * min(1.0, max(0.0, pressure or 0.0))
        + q.lateral_coef * abs(math.sin(rad))
    )
    return _clip_open(_sigmoid(z), q.eps)
