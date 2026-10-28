"""When normalizing in worker processes pays: the measurement behind `engine.index.PARALLEL_FROM` (TASK-284;
`docs/results/2026-10-24-parallel-normalize-crossover.md`). Run from `backend/`, on a quiet machine (load under 5;
the pool's wall time suffers most from other load):

    uv run python -m tests.bench.normalize_crossover [--words 120,250] [--sizes 1000,2000,5000,10000,20000]
        [--repeats 3] [--workers N]

For each size it writes a snapshot of `synthetic_5k.records(size, words)` to a temporary directory, then iterates
`normalized()` to the end, serially (`workers=1`) and through a pool of `--workers` (default `os.cpu_count()`;
`PARALLEL_FROM` set to 1). The two alternate within each repeat. It prints one markdown row per size: the minimum
wall time on each path, and the median CPU time (user + sys, `resource.getrusage`) of the serial run and of the
pool run's own process and its reaped workers, plus the load average at the start and the end. A report, not a
gate.
"""

from __future__ import annotations

import argparse
import os
import resource
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from openproceedings.engine import index as idx
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.snapshot import render

from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper

BUILT = datetime(2026, 9, 26, tzinfo=UTC)


def _cpu() -> tuple[float, float]:
    own, workers = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime, workers.ru_utime + workers.ru_stime


def _snapshot(size: int, words: tuple[int, int], root: Path) -> Path:
    snap = root / f"snap-{size}"
    snap.mkdir()
    papers = tuple(sorted((as_paper(r) for r in records(size, words)), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    return snap


def _run(snap: Path, workers: int) -> tuple[float, float, float]:
    """One pass of `normalized()`: wall seconds, own CPU, workers' CPU (the pool is shut down when it ends)."""
    (own, kids), started = _cpu(), time.perf_counter()
    for _ in idx.normalized(snap, workers):
        pass
    wall = time.perf_counter() - started
    own2, kids2 = _cpu()
    return wall, own2 - own, kids2 - kids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--words", default="120,250", help="abstract length range, in words")
    parser.add_argument("--sizes", default="1000,2000,5000,10000,20000")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()
    lo, hi = (int(w) for w in args.words.split(","))
    idx.PARALLEL_FROM = 1  # the pool whenever workers > 1
    print(
        f"abstracts of {lo}-{hi} words, {args.workers} workers, {args.repeats} repeats; load {os.getloadavg()[0]:.1f}"
    )
    print("| records | serial wall | pool wall | serial CPU | pool CPU (self + children) |")
    print("|---:|---:|---:|---:|---:|")
    with tempfile.TemporaryDirectory(prefix="op-crossover-") as tmp:
        for size in (int(n) for n in args.sizes.split(",")):
            snap = _snapshot(size, (lo, hi), Path(tmp))
            runs: dict[int, list[tuple[float, float, float]]] = {1: [], args.workers: []}
            for repeat in range(args.repeats):
                for w in (1, args.workers) if repeat % 2 == 0 else (args.workers, 1):
                    runs[w].append(_run(snap, w))
            serial, pool = runs[1], runs[args.workers]
            print(
                f"| {size:,} | {min(r[0] for r in serial):.2f} s | {min(r[0] for r in pool):.2f} s "
                f"| {statistics.median(r[1] for r in serial):.2f} s "
                f"| {statistics.median(r[1] for r in pool):.2f} + {statistics.median(r[2] for r in pool):.2f} s |"
            )
    print(f"load at the end {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
