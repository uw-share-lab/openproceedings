"""The linear-time tests' one measure: how CPU time grows from an input to one `factor` times its size.

A wall-clock bound at one size flakes on a shared runner: nightly 37943547380 timed a 17 ms parse at 1.9 s and
38056534247 a 5 ms page at 2.5 s, while 4 xdist workers ran 50,000-example properties beside them. So a check
compares two sizes instead, in this thread's CPU time (time spent preempted doesn't count), as pairs measured
side by side in alternating order (a busy phase or a frequency change hits both sides of a pair), and takes the
median ratio over the pairs (one stall in one pair doesn't decide it). Linear growth is about `factor`, quadratic
about `factor`²; `assert_near_linear` allows 2 × `factor`, so 8 for 4x the input against ~16 for quadratic.
`floor` is the CPU time under which an input counts as free: both sides that fast pass, however noisy their
ratio (a refusal that stops at a bound is constant time). And the large side's median CPU time must stay under
`ceiling` (2 s): a backstop, far above any call site's cost, against a linear but far slower implementation,
which a ratio alone passes.

The cyclic garbage collector is paused while a call is timed (`cpu`). A full collection walks every tracked
object in the process, so its cost is the test worker's whole heap, not the input; and it fires once enough
objects have survived since the last one, so the side that keeps more objects alive pays it more often. In CI's
xdist workers the ICML 2007 paper page (107 KB against 407 KB, a tree of ~41,000 elements at the larger size)
failed at ratios 8.09 and 8.24 (runs 38176036366, 38197206724): the small side kept its local 70 ms except in the
one pair whose small call took 0.33-0.47 s, a full collection's cost there, and the large side took 0.5-0.76 s
against 0.26 s locally, about one such collection a call. A local `-n 4` run of the suite reproduced it (ratio
5.45 with eight full collections inside the measurement, 3.84 with the collector paused). Pausing it removes
that heap-sized cost and one other: freeing the call's own cyclic garbage (the HTML tree's parent links make
every parsed tree a cycle), which the next collection after the call does, linear in what the call allocated.
Allocating, copying and freeing what reference counting frees are still timed, so a quadratic in work or in
allocation still costs ~16x (`tests/unit/test_timing.py` shows both fail).
"""

from __future__ import annotations

import gc
import time
from collections.abc import Callable
from statistics import median


def cpu(f: Callable[[], object], calls: int = 1) -> float:
    """This thread's CPU seconds for one call of `f`, averaged over `calls`: allocation and non-cyclic freeing
    included, the cyclic garbage collector paused (module docstring) and restored as it was."""
    enabled = gc.isenabled()
    gc.disable()
    try:
        started = time.thread_time()
        for _ in range(calls):
            f()
        return (time.thread_time() - started) / calls
    finally:
        if enabled:
            gc.enable()


def growth(
    small: Callable[[], object],
    large: Callable[[], object],
    rounds: int = 9,
    floor: float = 0.002,
    calls: int = 1,
) -> tuple[float, list[tuple[float, float]]]:
    """The median of `large`'s CPU time over `small`'s, `rounds` pairs measured side by side in alternating
    order, each side at least `floor` (each the average of `calls` calls, for a call too fast to time alone);
    and the pairs, for the assertion message."""
    small()  # warm: a first call's caches and imports are not what is measured
    large()
    pairs = []
    for i in range(rounds):
        if i % 2:
            b = cpu(large, calls)
            a = cpu(small, calls)
        else:
            a = cpu(small, calls)
            b = cpu(large, calls)
        pairs.append((a, b))
    return median(max(b, floor) / max(a, floor) for a, b in pairs), pairs


def assert_near_linear(
    f: Callable[[str], object],
    build: Callable[[int], str],
    n: int,
    factor: int = 4,
    rounds: int = 9,
    floor: float = 0.002,
    ceiling: float = 2.0,
) -> None:
    """`f(build(n * factor))` costs at most 2 × `factor` times `f(build(n))` in CPU time, and under `ceiling`
    seconds (module docstring)."""
    small_arg, large_arg = build(n), build(n * factor)
    ratio, pairs = growth(lambda: f(small_arg), lambda: f(large_arg), rounds, floor)
    assert ratio < 2 * factor, (large_arg[:20], len(small_arg), len(large_arg), ratio, pairs)
    large = median(b for _, b in pairs)
    assert large < ceiling, (large_arg[:20], len(large_arg), large, ceiling)
