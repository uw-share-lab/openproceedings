#!/usr/bin/env python3
"""Mutation-test the gates and tooling: every mutant must make at least one case table fail.

    python3 .claude/scripts/mutate.py              # all mutants (after changing a gate)
    python3 .claude/scripts/mutate.py --changed    # only mutants in files changed vs origin/dev (reviews)
    python3 .claude/scripts/mutate.py --jobs 8     # parallelism (default: CPU count, max 8)
    python3 .claude/scripts/mutate.py --match glob # only mutants whose label contains "glob"
    python3 .claude/scripts/mutate.py --shard 2/8  # every 8th selected mutant from the 2nd (nightly CI runs 1/12..12/12)
    python3 .claude/scripts/mutate.py --list       # print the selected mutants' labels; run nothing
    python3 .claude/scripts/mutate.py --check      # vet the selected mutants (below); run no table (make tooling)
    python3 .claude/scripts/mutate.py --table-timeout 900  # a table past 900 s is a hang (default: 10x its baseline,
                                                           # >= 60 s; refused under 10x any table's baseline)

Mutants live in .claude/scripts/mutants/*.json as {label, file, old, new[, also][, equivalent]}: `old` is
replaced by `new` once in `file`, and once in each file `also` lists (text kept identical in several files, such
as the shared AI-attribution pattern, whose identity row would otherwise kill any one-file mutant: TASK-243).
`--changed` selects by `file`. A mutant marked "equivalent" is expected to survive (documented reason in the
label). A mutant whose `old` text is missing from any of its files is STALE and fails the run — update it, so the
list never rots. One whose `old` text occurs more than once in a file is AMBIGUOUS (only the first would change,
an accident of order that hid what the mutant meant: TASK-254), and one whose edit stops a file compiling that
compiled is UNCOMPILABLE (any table that runs the file would "kill" it); both fail the run without running a
table. `breaks_compile` reads a .py file, a .json file, and a shell script (`bash -n`) with each `<<'PY'`
heredoc in it compiled as Python; other files always compile. `--check` vets every selected mutant this way and runs no
table, in seconds (`make tooling`).

A mutant is killed when any case table fails; the first failure decides it. So each mutant runs, first, the
tables that name its file (its name, or its stem as a word, in the table or a helper beside it that the table
names), then the rest only if those all pass, and a phase stops as soon as one table fails. The verdict is the
same as running every table (a survivor runs them all); only the time differs: about a third of it on the
nightly logs, where every mutant ran all 13 tables and four 12-way shards ran past 140 min (TASK-171 rerun).
A table whose header comment (its leading `#` lines) has `# mutate-scope: <file> ...` lines (repo-relative paths,
exactly as a mutant's `file`) exercises only those files: it runs only for a mutant that changes one of them, so a
table that fails for another reason (one slowed by load) can never be credited with killing another file's mutant
(TASK-238: test-mutate-run.sh, which runs only mutate.py, was credited with 15 of 17 docker_digest.py mutants on a
loaded machine). A declared path that doesn't exist is refused (exit 2): a misspelt one would stop the table running
for any mutant (TASK-254).
A table that runs past its timeout under a mutant has hung (an infinite loop): it is stopped, so one hang never
stalls a shard, and run again alone; if it hangs again the mutant is TIMEOUT, which counts as killed, as in other
mutation tools, and if not, that run's verdict stands (a table slowed by the other jobs is not a hang). The
timeout is 10x the table's own baseline time, at least 60 s, so only a far slower table is a hang; a
--table-timeout under 10x any table's baseline is refused (exit 2), since it would make a slow survivor a kill.
This is THE way to mutation-test here; don't hand-roll a serial loop (review round 3: ~33 min serial vs ~5
min parallel). Standard: .claude/skills/testing-standards/SKILL.md and .claude/agents/qa-auditor.md.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = sorted(
    str(p.relative_to(ROOT))
    for p in [*ROOT.glob(".claude/hooks/tests/*.sh"), *ROOT.glob(".claude/scripts/tests/*.sh")]
)
IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", "__pycache__", "data", ".ruff_cache", ".mypy_cache"
)


def _ignore(directory: str, names: list[str]) -> set[str]:
    """IGNORE, plus .claude/worktrees/ (gitignored agent checkouts) — only there, not any `worktrees`."""
    skip = set(IGNORE(directory, names))
    if Path(directory).resolve() == (ROOT / ".claude").resolve() and "worktrees" in names:
        skip.add("worktrees")
    return skip


ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # never touch the real repo


def copy_tree(dest: Path) -> None:
    shutil.copytree(ROOT, dest, ignore=_ignore)
    if (ROOT / ".venv").exists():
        os.symlink(ROOT / ".venv", dest / ".venv")


TIMEOUT_FACTOR, TIMEOUT_FLOOR = 10, 60.0  # a table's timeout under a mutant: 10x its baseline, at least 60 s
LIVE: set[subprocess.Popen[bytes]] = set()  # every running table, stopped on the way out (Ctrl-C, timeout)
LIVE_LOCK = threading.Lock()
STOPPING = threading.Event()  # interrupted: every worker stops its tables and starts no more


def stop(p: subprocess.Popen[bytes]) -> None:
    """Stop a table and everything it started (its own process group): TERM, so its EXIT trap removes its
    temporary files, then, 2 s later, KILL whatever is left in the group."""
    with contextlib.suppress(OSError):
        os.killpg(p.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        p.wait(2)
    with contextlib.suppress(OSError):  # the group can outlive its leader
        os.killpg(p.pid, signal.SIGKILL)
    p.wait()


def run_tables(
    tree: Path, tables: list[str], timeouts: dict[str, float] | None = None
) -> tuple[list[str], list[str], dict[str, float]]:
    """Run `tables` in parallel against `tree`: the ones that failed and the ones past their timeout (stopped),
    as table names, and each finished table's wall time. With `timeouts`, the first failure or timeout stops
    the rest (one is enough to kill a mutant); without, every table runs to the end (the baseline)."""
    started = time.monotonic()
    procs: dict[str, subprocess.Popen[bytes]] = {}
    failed: list[str] = []
    hung: list[str] = []
    took: dict[str, float] = {}
    try:
        for t in tables:
            p = subprocess.Popen(
                ["bash", str(tree / t)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=ENV,
                start_new_session=True,  # its own process group, so stop() reaches what it started
            )
            procs[t] = p
            with LIVE_LOCK:
                LIVE.add(p)
        running = dict(procs)
        while running and not STOPPING.is_set() and not (timeouts is not None and (failed or hung)):
            time.sleep(0.05)
            now = time.monotonic()
            for t, p in list(running.items()):
                if (rc := p.poll()) is not None:
                    del running[t]
                    took[t] = now - started
                    if rc != 0:
                        failed.append(Path(t).name)
                elif timeouts is not None and now - started > timeouts[t]:
                    del running[t]
                    stop(p)
                    hung.append(Path(t).name)
    finally:
        for p in procs.values():
            if p.poll() is None:
                stop(p)
            with LIVE_LOCK:
                LIVE.discard(p)
    return failed, hung, took


_TABLE_TEXT: dict[str, str] = {}


def table_text(t: str) -> str:
    """A table's text, with the text of every helper beside it that it names (dependabot_cases.py)."""
    if t not in _TABLE_TEXT:
        path = ROOT / t
        text = path.read_text(errors="replace")
        for helper in sorted(path.parent.iterdir()):
            if helper.is_file() and helper.suffix != ".sh" and helper.name in text:
                text += helper.read_text(errors="replace")
        _TABLE_TEXT[t] = text
    return _TABLE_TEXT[t]


SCOPE = re.compile(r"#\s*mutate-scope:\s*(.*)")


@functools.cache
def table_scope(t: str) -> frozenset[str] | None:
    """The files table `t` declares it exercises (`# mutate-scope:` lines in its header comment, the `#` lines
    before its first other line; a fixture a table writes later is not its header), or None: it may exercise any."""
    files: set[str] = set()
    for line in (ROOT / t).read_text(errors="replace").splitlines():
        if not line.startswith("#"):
            break
        if m := SCOPE.match(line):
            files.update(m.group(1).split())
    return frozenset(files) or None


def check_scopes() -> None:
    """Exit 2 when a table declares a `# mutate-scope:` path that doesn't exist: it matches no mutant's `file`, so
    the table would never run for the file it meant (TASK-254)."""
    missing = [
        f"{Path(t).name}: {f}"
        for t in TABLES
        for f in sorted(table_scope(t) or ())
        if not (ROOT / f).is_file()
    ]
    if missing:
        print(f"# mutate-scope: names a file that doesn't exist ({'; '.join(missing)})", file=sys.stderr)
        sys.exit(2)


PY_HEREDOC = re.compile(r"<<'PY'[^\n]*\n(.*?)\nPY\n", re.DOTALL)  # a hook's embedded Python program
SHELL_LINE = re.compile(r"#![^\n]*\b(ba)?sh\b")


def _python_compiles(text: str, name: str) -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # an invalid escape's SyntaxWarning is not a failure
        try:
            compile(text, name, "exec")
        except (SyntaxError, ValueError):
            return False
    return True


def _parts(file: str, text: str) -> list[tuple[str, str]] | None:
    """What `breaks_compile` checks in `file`, as (kind, text) pairs, or None: nothing (a file it can't check)."""
    if file.endswith(".py"):
        return [("python", text)]
    if file.endswith(".json"):
        return [("json", text)]
    if file.endswith(".sh") or SHELL_LINE.match(text):
        return [("shell", PY_HEREDOC.sub("<<'PY'\nPY\n", text))] + [
            ("python", b) for b in PY_HEREDOC.findall(text)
        ]
    return None


def _part_compiles(kind: str, text: str, name: str) -> bool:
    if kind == "python":
        return _python_compiles(text, name)
    if kind == "json":
        try:
            json.loads(text)
        except ValueError:
            return False
        return True
    return subprocess.run(["bash", "-n"], input=text, capture_output=True, text=True).returncode == 0


# the files as they are: a few dozen texts, each compiled once
_compiled_before = functools.lru_cache(maxsize=256)(_part_compiles)


def breaks_compile(file: str, before: str, after: str) -> bool:
    """Whether `after` (a mutant of `file`) fails to compile where `before` compiles. Only the parts the edit
    changed are checked (each heredoc's program, and the shell around them), when it kept the parts' shape."""
    old, new = _parts(file, before), _parts(file, after)
    if old is None or new is None:
        return False
    if len(old) != len(new):  # the edit moved a heredoc's bounds: the whole file, both ways
        return all(_compiled_before(*o, file) for o in old) and not all(_part_compiles(*n, file) for n in new)
    return any(
        _compiled_before(*o, file) and not _part_compiles(*n, file)
        for o, n in zip(old, new, strict=False)
        if o != n
    )


def vet(m: dict) -> str | None:
    """Why mutant `m` can't be run as written (module docstring): STALE, AMBIGUOUS or UNCOMPILABLE; None if it can."""
    for f in [m["file"], *m.get("also", [])]:
        text = (ROOT / f).read_text()
        n = text.count(m["old"])
        if n != 1:
            return "STALE" if n == 0 else "AMBIGUOUS"
        if breaks_compile(f, text, text.replace(m["old"], m["new"], 1)):
            return "UNCOMPILABLE"
    return None


def can_kill(t: str, files: list[str]) -> bool:
    """Whether table `t` exercises any of the mutated `files` (`table_scope`)."""
    scope = table_scope(t)
    return scope is None or not scope.isdisjoint(files)


def first_tables(file: str) -> list[str]:
    """The tables that name `file`: its name, or its stem as a word (`cmdparse`, imported by name). Only an
    order: a mutant these all pass still runs every other table."""
    path = Path(file)
    stem = re.compile(r"(?<![\w.-])" + re.escape(path.stem) + r"(?![\w-])")
    return [t for t in TABLES if path.name in table_text(t) or stem.search(table_text(t))]


def run_phase(tree: Path, tables: list[str], timeouts: dict[str, float]) -> tuple[list[str], list[str]]:
    """`run_tables` with every hang confirmed: a table that hung is run again alone, and only a second hang
    stands; if it passes, the tables the hang stopped run again too (module docstring)."""
    failed, hung, took = run_tables(tree, tables, timeouts)
    if failed or not hung:
        return failed, hung
    again = [t for t in tables if Path(t).name in hung]
    failed, hung, _ = run_tables(tree, again, timeouts)
    if failed or hung:
        return failed, hung
    left = [t for t in tables if t not in took and t not in again]
    return run_phase(tree, left, timeouts) if left else ([], [])


def killing_tables(tree: Path, files: list[str], timeouts: dict[str, float]) -> tuple[list[str], list[str]]:
    """The tables that fail and the tables that hang with `tree`'s mutant in `files` (its `file` first, then
    `also`): of the tables that can kill it (`can_kill`), those that name its file first, then the rest only if
    none of those failed (module docstring). Both empty: it survived."""
    tables = [t for t in TABLES if can_kill(t, files)]
    first = [t for t in first_tables(files[0]) if t in tables]
    rest = [t for t in tables if t not in first]
    failed: list[str] = []
    hung: list[str] = []
    for phase in (first, rest):
        if phase and not (failed or hung):
            failed, hung = run_phase(tree, phase, timeouts)
    return failed, hung


def table_timeouts(took: dict[str, float], explicit: float | None) -> dict[str, float]:
    """Each table's timeout: `explicit`, or 10x its baseline and at least 60 s. An explicit one under 10x any
    table's baseline exits 2: a survivor that table is merely slow for would count as killed."""
    if explicit is not None:
        for t in TABLES:
            if explicit < TIMEOUT_FACTOR * took[t]:
                print(
                    f"--table-timeout {explicit:g} s is under {TIMEOUT_FACTOR}x the baseline of {Path(t).name} "
                    f"({took[t]:.1f} s): a slow survivor would count as killed",
                    file=sys.stderr,
                )
                sys.exit(2)
        return dict.fromkeys(TABLES, explicit)
    return {t: max(TIMEOUT_FLOOR, TIMEOUT_FACTOR * took[t]) for t in TABLES}


def changed_files() -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "origin/dev...HEAD"], capture_output=True, text=True
    )
    if r.returncode != 0:
        sys.exit("--changed needs origin/dev: run `git fetch origin dev` first")
    s = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only"], capture_output=True, text=True)
    return set((r.stdout + s.stdout).split())


def parse_shard(spec: str) -> tuple[int, int]:
    """`i/n` with 1 <= i <= n, else exit with a clear error (TASK-171)."""
    parts = spec.split("/")
    if len(parts) != 2 or not all(p.isascii() and p.isdigit() for p in parts):
        sys.exit(f"--shard {spec!r}: expected i/n, e.g. 2/8")
    i, n = int(parts[0]), int(parts[1])
    if not 1 <= i <= n:
        sys.exit(f"--shard {spec!r}: need 1 <= i <= n")
    return i, n


def shard(mutants: list[dict], i: int, n: int) -> list[dict]:
    """Shard i of n: every n-th mutant from the i-th. Deterministic, and the n shards partition the list."""
    return mutants[i - 1 :: n]


def interrupted(_signum: int, _frame: object) -> None:
    """SIGINT (Ctrl-C, CI's `timeout --signal=INT`) and SIGTERM (a nested run stopped by an outer one's
    timeout) unwind the run, so its tables stop too; set for SIGINT as well, since a shell starts a background
    job with SIGINT ignored."""
    raise KeyboardInterrupt


def main() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument("--match", help="only mutants whose label contains this text (case-insensitive)")
    ap.add_argument("--shard", help="i/n: run only shard i of n of the selected mutants (1 <= i <= n)")
    ap.add_argument("--list", action="store_true", help="print the selected mutants' labels and exit")
    ap.add_argument(
        "--check", action="store_true", help="vet the selected mutants (stale, ambiguous, uncompilable)"
    )
    ap.add_argument(
        "--table-timeout",
        type=float,
        help=f"seconds before a table counts as hung (default: {TIMEOUT_FACTOR}x its baseline, at least "
        f"{TIMEOUT_FLOOR:.0f} s; refused under {TIMEOUT_FACTOR}x any table's baseline)",
    )
    a = ap.parse_args()
    check_scopes()
    mutants = [
        m
        for f in sorted((ROOT / ".claude/scripts/mutants").glob("*.json"))
        for m in json.loads(f.read_text())
    ]
    if a.match:
        mutants = [m for m in mutants if a.match.lower() in m["label"].lower()]
    if a.changed:
        files = changed_files()
        if not files:
            sys.exit(
                "--changed found no changed files (untracked files don't count) — refusing a vacuous pass"
            )
        mutants = [m for m in mutants if m["file"] in files]
        if not mutants:
            msg = "no mutants cover the changed files — if you changed gate logic, add mutants"
            print(msg, file=sys.stderr if a.list else sys.stdout, flush=True)
    if a.shard is not None:
        i, n = parse_shard(a.shard)
        selected = len(mutants)
        mutants = shard(mutants, i, n)
        if not a.list:
            print(f"shard {i}/{n}: {len(mutants)} of {selected} mutants", flush=True)
    if a.list:
        for m in mutants:
            print(m["label"])
        return
    if a.check:
        # compiling is CPU-bound (about 6 s of it in all), so in processes
        with ProcessPoolExecutor(max_workers=a.jobs) as pool:
            bad = [
                (m, why)
                for m, why in zip(mutants, pool.map(vet, mutants, chunksize=32), strict=True)
                if why is not None
            ]
        for m, why in bad:
            print(f"  FAIL {why:8} {m['label']}")
        print(
            f"{len(mutants)} mutants: {len(bad)} can't be run as written (stale, ambiguous or uncompilable)"
        )
        sys.exit(1 if bad else 0)
    work = Path(tempfile.mkdtemp(prefix="op-mutate-"))
    try:
        base = work / "baseline"
        copy_tree(base)
        bad, _, took = run_tables(base, TABLES)
        if bad:
            sys.exit(f"baseline is not green ({bad}) — fix the tables before mutation-testing")
        shutil.rmtree(base)
        timeouts = table_timeouts(took, a.table_timeout)

        def one(item: tuple[int, dict]) -> tuple[dict, str, list[str]]:
            i, m = item
            if STOPPING.is_set():
                return m, "STOPPED", []
            if (why := vet(m)) is not None:
                return m, why, []
            tree = work / f"m{i}"
            copy_tree(tree)
            files = [m["file"], *m.get("also", [])]
            for f in files:
                p = tree / f
                p.write_text(p.read_text().replace(m["old"], m["new"], 1))
            failed, hung = killing_tables(tree, files, timeouts)
            shutil.rmtree(tree)
            status = "TIMEOUT" if hung and not failed else "KILLED" if failed else "SURVIVED"
            return m, status, failed + [f"{h} hung" for h in hung]

        problems = 0
        ex = ThreadPoolExecutor(max_workers=a.jobs)
        try:
            for m, status, bad in ex.map(one, enumerate(mutants)):
                equivalent = m.get("equivalent", False)
                ok = status in ("KILLED", "TIMEOUT") or (status == "SURVIVED" and equivalent)
                problems += not ok
                mark = "ok  " if ok else "FAIL"
                print(
                    f"  {mark} {status:8} {m['label']}" + (f"  ({', '.join(bad)})" if bad else ""), flush=True
                )
        except BaseException:  # Ctrl-C or CI's timeout (SIGINT): stop now, not after the queued mutants
            STOPPING.set()
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        ex.shutdown()
        print(
            f"{len(mutants)} mutants: {problems} problem(s) (survivors not marked equivalent, or mutants that can't "
            "be run as written)"
        )
        sys.exit(1 if problems else 0)
    finally:
        with LIVE_LOCK:
            live = list(LIVE)
        for p in live:  # interrupted (Ctrl-C, CI's timeout): no table outlives the run
            stop(p)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
