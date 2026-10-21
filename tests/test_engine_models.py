import math

from hypothesis import given
from hypothesis import strategies as st

from pop.engine.models import (
    XGParams,
    normalise_body_part,
    pass_difficulty,
    pass_vector,
    shot_geometry,
    shot_xg,
    xg_from_geometry,
)

coord = st.floats(min_value=0, max_value=100, allow_nan=False)
dist = st.floats(min_value=0, max_value=120, allow_nan=False)
angle = st.floats(min_value=0, max_value=math.pi, allow_nan=False)
press = st.floats(min_value=0, max_value=1, allow_nan=False)
body = st.sampled_from(["foot", "left_foot", "right_foot", "head", "header", "chest", None])
situation = st.sampled_from(["open_play", "set_piece", "counter", None])


@given(coord, coord, body, situation, press)
def test_xg_strictly_inside_unit_interval(x, y, b, s, p):
    v = shot_xg(x, y, b, s, p)
    assert 0.0 < v < 1.0
    assert not math.isnan(v)


@given(dist, dist, angle, body, situation, press)
def test_xg_monotone_non_increasing_in_distance_at_fixed_angle(d1, d2, a, b, s, p):
    near, far = sorted((d1, d2))
    assert xg_from_geometry(near, a, b, s, p) >= xg_from_geometry(far, a, b, s, p)


def test_xg_strictly_decreasing_in_distance_at_fixed_angle_unsaturated():
    vals = [xg_from_geometry(d, 0.5) for d in (5, 10, 20, 30)]
    assert vals == sorted(vals, reverse=True) and len(set(vals)) == 4


@given(st.floats(min_value=70, max_value=99.5))
def test_xg_falls_moving_away_along_centre_line(x):
    assert shot_xg(x, 50.0) >= shot_xg(x - 0.5, 50.0)


@given(coord, coord, body, press)
def test_penalty_is_fixed(x, y, b, p):
    assert shot_xg(x, y, b, "penalty", p) == 0.76
    assert XGParams().penalty_xg == 0.76


@given(dist, angle, press, press)
def test_xg_non_increasing_in_pressure(d, a, p1, p2):
    lo, hi = sorted((p1, p2))
    assert xg_from_geometry(d, a, pressure=lo) >= xg_from_geometry(d, a, pressure=hi)


def test_header_lower_than_foot_and_sensible_values():
    d, a = shot_geometry(89.5, 50.0)  # penalty spot
    assert 10.5 < d < 11.5
    foot = xg_from_geometry(d, a, "foot")
    assert 0.2 < foot < 0.5
    assert xg_from_geometry(d, a, "head") < foot
    assert shot_xg(75.0, 50.0) < 0.1  # ~26 m out
    assert normalise_body_part("Right Foot") == "foot"


def test_goal_mouth_degenerate_point_is_finite():
    d, a = shot_geometry(100.0, 50.0)
    assert d == 0.0 and a == math.pi
    assert 0 < shot_xg(100.0, 50.0) < 1
    _, a_out = shot_geometry(100.0, 0.0)
    assert a_out == 0.0


@given(st.floats(min_value=0, max_value=120), st.floats(min_value=-180, max_value=180), press)
def test_pass_difficulty_bounded(length, ang, p):
    v = pass_difficulty(length, ang, p)
    assert 0.0 < v < 1.0


@given(st.floats(min_value=0, max_value=120), st.floats(min_value=0, max_value=120),
       st.floats(min_value=-180, max_value=180), press)
def test_pass_difficulty_non_decreasing_in_length(l1, l2, ang, p):
    short, long_ = sorted((l1, l2))
    assert pass_difficulty(short, ang, p) <= pass_difficulty(long_, ang, p)


@given(st.floats(min_value=0, max_value=120), st.floats(min_value=-180, max_value=180), press, press)
def test_pass_difficulty_non_decreasing_in_pressure(length, ang, p1, p2):
    lo, hi = sorted((p1, p2))
    assert pass_difficulty(length, ang, lo) <= pass_difficulty(length, ang, hi)


def test_pass_difficulty_strict_in_unsaturated_range_and_forward_harder():
    assert pass_difficulty(10, 0, 0.2) < pass_difficulty(30, 0, 0.2) < pass_difficulty(30, 0, 0.8)
    assert pass_difficulty(20, 180, 0.2) < pass_difficulty(20, 0, 0.2)


def test_pass_vector_prefers_coordinates():
    length, ang = pass_vector(40, 50, 60, 50, None, 90.0)
    assert abs(length - 21.0) < 1e-9 and ang == 0.0
    length, ang = pass_vector(None, None, None, None, 12.0, 45.0)
    assert (length, ang) == (12.0, 45.0)
