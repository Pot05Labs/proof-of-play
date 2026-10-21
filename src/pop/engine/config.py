"""Engine configuration: every threshold, window and minimum sample size."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pop.engine.models import PassDifficultyParams, PitchParams, XGParams

ENGINE_VERSION = "engine v0.1"


class ImportanceConfig(BaseModel):
    """Moment importance = base[kind] + kind-specific modifiers, clipped to [0, 1]."""

    base: dict[str, float] = Field(
        default_factory=lambda: {
            "goal": 0.85,
            "var_overturn": 0.95,
            "red_card": 0.8,
            "big_chance": 0.5,
            "momentum_shift": 0.4,
            "control_to_chaos": 0.4,
            "chaos_to_control": 0.3,
            "pressure_spike": 0.35,
            "possession_swing": 0.35,
            "pass_streak": 0.25,
            "rocket_shot": 0.3,
            "speed_alert": 0.25,
            "distance_milestone": 0.2,
        }
    )
    goal_lead_change_bonus: float = 0.1
    late_minute: int = 75
    late_bonus: float = 0.05
    big_chance_xg_weight: float = 0.4
    momentum_weight: float = 0.3
    chaos_weight: float = 0.2
    streak_increment: float = 0.02
    min_importance: float = Field(default=0.0, ge=0, le=1)


class EngineConfig(BaseModel):
    version: str = ENGINE_VERSION
    fact_decimals: int = 3

    pitch: PitchParams = Field(default_factory=PitchParams)
    xg: XGParams = Field(default_factory=XGParams)
    pass_difficulty: PassDifficultyParams = Field(default_factory=PassDifficultyParams)

    # Rolling windows, in play-clock milliseconds (time while the ball is in play
    # between kick_off and half_time/full_time; the interval break is excluded).
    window_ms: int = 300_000
    min_window_ms: int = 60_000
    final_third_x: float = 200.0 / 3.0

    # Shots
    big_chance_xg: float = 0.3
    rocket_shot_kmh: float = 110.0
    ball_speed_record_min_kmh: float = 90.0

    # Momentum: per team, xG + entry_weight * final-third entries in the window,
    # momentum = (home - away) / (home + away + smoothing).
    momentum_entry_weight: float = 0.1
    momentum_smoothing: float = 0.3
    momentum_shift_threshold: float = Field(default=0.35, gt=0, lt=1)
    momentum_min_events: int = 4

    # Pressing: pressures by a team per opponent pass in the window.
    pressing_min_opponent_passes: int = 5
    pressure_spike_threshold: float = 0.6
    pressure_spike_rearm: float = 0.4

    # Control vs chaos (0 = control, 1 = chaos).
    chaos_weight_possession_changes: float = 0.4
    chaos_weight_pass_length_spread: float = 0.3
    chaos_weight_pressure: float = 0.3
    chaos_pc_rate_ref_per_min: float = 1.5
    chaos_pass_len_std_ref_m: float = 15.0
    chaos_min_events: int = 10
    chaos_min_passes: int = 5
    chaos_high: float = 0.6
    control_low: float = 0.35

    # Possession swing: rolling time-weighted possession share.
    possession_swing_share: float = Field(default=0.65, gt=0.5, lt=1)
    possession_swing_min_observed_ms: int = 120_000

    # Pass streaks.
    pass_streak_min: int = 8
    pass_streak_step: int = 5

    # Player tracking tags.
    top_speed_alert_kmh: float = 33.0
    distance_milestones_m: list[float] = Field(default_factory=lambda: [5_000.0, 10_000.0])

    importance: ImportanceConfig = Field(default_factory=ImportanceConfig)
