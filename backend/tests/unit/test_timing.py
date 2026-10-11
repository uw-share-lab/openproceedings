"""The linear-time tests' measure (tests/timing.py) fails quadratic growth and passes linear growth, at the cutoff
the tests use (testing-standards §CPU growth checks: a sampling method is shown to fail the former quadratic)."""

from __future__ import annotations

import pytest

from tests.timing import assert_near_linear, growth


def linear(s: str) -> int:
    return sum(1 for _ in range(1_000 * len(s)))


def quadratic(s: str) -> int:
    return sum(1 for _ in s for _ in s)


def test_a_linear_cost_passes() -> None:
    assert_near_linear(linear, lambda k: "x" * k, 300)


def test_a_quadratic_cost_fails() -> None:
    with pytest.raises(AssertionError):
        assert_near_linear(quadratic, lambda k: "x" * k, 500)


def test_both_sides_under_the_floor_count_as_free() -> None:
    """A refusal that stops at a bound costs the same at both sizes; noise in two tiny times is not growth."""
    ratio, pairs = growth(lambda: None, lambda: sum(range(10)), rounds=3)
    assert ratio == 1.0 and len(pairs) == 3


def test_a_linear_but_far_too_slow_cost_fails_the_ceiling() -> None:
    """A growth ratio alone passes a parse 100x slower that is still linear: the large side also has a CPU
    ceiling (2 s by default), far above anything a call site costs."""
    with pytest.raises(AssertionError):
        assert_near_linear(linear, lambda k: "x" * k, 300, ceiling=0.001)
