"""The linear-time tests' measure (tests/timing.py) fails quadratic growth and passes linear growth, at the cutoff
the tests use (testing-standards §CPU growth checks: a sampling method is shown to fail the former quadratic). It
pauses the cyclic garbage collector while it times a call, so a quadratic must fail whether its cost is work or
allocation, and no collection may run inside a timed call."""

from __future__ import annotations

import gc

import pytest

from tests.timing import assert_near_linear, cpu, growth


def linear(s: str) -> int:
    return sum(1 for _ in range(1_000 * len(s)))


def quadratic(s: str) -> int:
    return sum(1 for _ in s for _ in s)


def quadratic_allocation(s: str) -> int:
    """Each step copies everything kept so far into a new tuple (a tracked object) and frees the old one."""
    kept: tuple[str, ...] = ()
    for c in s:
        kept = (*kept, c)
    return len(kept)


def test_a_linear_cost_passes() -> None:
    assert_near_linear(linear, lambda k: "x" * k, 300)


def test_a_quadratic_cost_fails() -> None:
    with pytest.raises(AssertionError):
        assert_near_linear(quadratic, lambda k: "x" * k, 500)


def test_a_quadratic_allocation_fails_with_the_collector_paused() -> None:
    """Pausing the collector leaves allocating, copying and reference-counted freeing in the measure: ~16x for 4x
    the input."""
    with pytest.raises(AssertionError):
        assert_near_linear(quadratic_allocation, lambda k: "x" * k, 3_000)


def test_no_collection_runs_inside_a_timed_call_and_the_collector_is_restored() -> None:
    """A full collection walks the worker's whole heap, a cost of the process and not of the input; the timed call
    allocates far past the youngest generation's threshold, and still no collection starts until it returns."""
    starts: list[int] = []
    timing = False  # only a collection that starts inside the timed call counts: one after it is outside

    def started(phase: str, info: dict[str, int]) -> None:
        if phase == "start" and timing:
            starts.append(info["generation"])

    def allocate() -> None:
        nonlocal timing
        timing = True
        try:
            kept = [[i] for i in range(20 * gc.get_threshold()[0])]
            assert not gc.isenabled() and len(kept)
        finally:
            timing = False

    gc.callbacks.append(started)
    try:
        cpu(allocate, calls=3)
        assert starts == [] and gc.isenabled()
        gc.disable()  # paused already: left paused
        try:
            cpu(allocate)
            assert not gc.isenabled()
        finally:
            gc.enable()
        with pytest.raises(ZeroDivisionError):  # a call that raises restores it too
            cpu(lambda: 1 / 0)
        assert gc.isenabled()
    finally:
        gc.callbacks.remove(started)


def test_both_sides_under_the_floor_count_as_free() -> None:
    """A refusal that stops at a bound costs the same at both sizes; noise in two tiny times is not growth."""
    ratio, pairs = growth(lambda: None, lambda: sum(range(10)), rounds=3)
    assert ratio == 1.0 and len(pairs) == 3


def test_a_linear_but_far_too_slow_cost_fails_the_ceiling() -> None:
    """A growth ratio alone passes a parse 100x slower that is still linear: the large side also has a CPU
    ceiling (2 s by default), far above anything a call site costs."""
    with pytest.raises(AssertionError):
        assert_near_linear(linear, lambda k: "x" * k, 300, ceiling=0.001)
