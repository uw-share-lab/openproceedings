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

`peak_bytes` is the other measure: a tracemalloc peak, for a bound a runner's cache can't move (a greedy regex
repeat holds `re` state per repetition, TASK-272).

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

Work done on another thread is invisible to this thread's CPU clock, so `growth` takes the side's measure as an
argument (`measure`, `cpu` by default). The one such check, `contract/test_verification_scale.py`'s
`width_is_free`, times requests TestClient serves on its server thread: its measure reads the CPU time the
server's verifying thread spent in its verification slot from the request's access line (`verify_cpu_ms`),
around a call made with the collector paused (`collector_paused`, which `cpu` uses: the collector is the
process's, so the pause reaches the server thread too). Pairing, alternation, the median and `floor` are
`growth`'s as for every other check; no CPU-time growth check in the test suite has a timer of its own.
"""

from __future__ import annotations

import gc
import time
import tracemalloc
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from statistics import median

# one side's CPU seconds for a call, averaged over `calls` calls (`cpu`, or another thread's figure: `growth`)
type Measure = Callable[[Callable[[], object], int], float]


@contextmanager
def collector_paused() -> Iterator[None]:
    """The cyclic garbage collector paused for the block (in every thread: it is the process's) and restored as
    it was, even if the block raises."""
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


def cpu(f: Callable[[], object], calls: int = 1) -> float:
    """This thread's CPU seconds for one call of `f`, averaged over `calls`: allocation and non-cyclic freeing
    included, the cyclic garbage collector paused (module docstring) and restored as it was."""
    with collector_paused():
        started = time.thread_time()
        for _ in range(calls):
            f()
        return (time.thread_time() - started) / calls


def growth(
    small: Callable[[], object],
    large: Callable[[], object],
    rounds: int = 9,
    floor: float = 0.002,
    calls: int = 1,
    measure: Measure = cpu,
) -> tuple[float, list[tuple[float, float]]]:
    """The median of `large`'s CPU time over `small`'s, `rounds` pairs measured side by side in alternating
    order, each side at least `floor` (each the average of `calls` calls, for a call too fast to time alone);
    and the pairs, for the assertion message. `measure(f, calls)` gives one side's CPU seconds: `cpu` (this
    thread's), or for work another thread does, a measure of that thread's CPU time that also pauses the
    collector (`collector_paused`), as the width check reads the server's own figure from its access line."""
    small()  # warm: a first call's caches and imports are not what is measured
    large()
    pairs = []
    for i in range(rounds):
        if i % 2:
            b = measure(large, calls)
            a = measure(small, calls)
        else:
            a = measure(small, calls)
            b = measure(large, calls)
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


def peak_bytes(f: Callable[[], object]) -> int:
    """The peak memory `f()` allocates (tracemalloc), for a bound in bytes where CPU time depends on the runner:
    a greedy repeated group that backtracks holds `re` state per repetition (63 MB on a 1 MB value, TASK-272),
    and its time then follows the runner's cache. Refuses to run under an outer trace, whose peak it can't reset
    without disturbing."""
    assert not tracemalloc.is_tracing(), "peak_bytes needs tracemalloc off (PYTHONTRACEMALLOC is set?)"
    tracemalloc.start()
    try:
        f()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
