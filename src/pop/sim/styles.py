"""Tactical style parameters. Numbers are simulator tuning knobs, not measurements."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyleParams:
    name: str
    # Chance of a pressing action on an opponent's on-ball action, by the PRESSER's own x zone:
    # (own third, middle third, attacking third). High press is high up, low block is deep.
    press_zones: tuple[float, float, float]
    counterpress: float  # pressing multiplier for a few seconds after losing the ball
    short_len_m: float  # typical short-pass length
    long_prob: float  # share of long balls
    forward_prob: float  # share of passes played forward
    carry_prob: float
    tempo: float  # time-on-ball multiplier; lower is quicker
    accuracy: float  # additive pass-completion modifier
    counter_prob: float  # chance a regain in the own half turns into a counter-attack
    tackle_rate: float  # how often the team challenges a ball carrier
    work_rate: float  # running-distance multiplier


STYLES: dict[str, StyleParams] = {
    "high_press": StyleParams(
        name="high_press",
        press_zones=(0.10, 0.24, 0.42),
        counterpress=1.6,
        short_len_m=14.0,
        long_prob=0.10,
        forward_prob=0.55,
        carry_prob=0.20,
        tempo=0.85,
        accuracy=0.0,
        counter_prob=0.35,
        tackle_rate=1.25,
        work_rate=1.03,
    ),
    "possession": StyleParams(
        name="possession",
        press_zones=(0.10, 0.17, 0.24),
        counterpress=1.8,
        short_len_m=12.0,
        long_prob=0.05,
        forward_prob=0.45,
        carry_prob=0.18,
        tempo=1.0,
        accuracy=0.04,
        counter_prob=0.15,
        tackle_rate=1.0,
        work_rate=1.0,
    ),
    "low_block": StyleParams(
        name="low_block",
        press_zones=(0.26, 0.10, 0.04),
        counterpress=1.0,
        short_len_m=15.0,
        long_prob=0.16,
        forward_prob=0.60,
        carry_prob=0.22,
        tempo=0.95,
        accuracy=-0.02,
        counter_prob=0.75,
        tackle_rate=1.05,
        work_rate=0.98,
    ),
    "direct": StyleParams(
        name="direct",
        press_zones=(0.15, 0.17, 0.20),
        counterpress=1.1,
        short_len_m=17.0,
        long_prob=0.24,
        forward_prob=0.65,
        carry_prob=0.18,
        tempo=0.90,
        accuracy=-0.03,
        counter_prob=0.45,
        tackle_rate=1.10,
        work_rate=1.01,
    ),
}

STYLE_CODES = {"high_press": "HP", "possession": "PO", "low_block": "LB", "direct": "DI"}
