"""Crash-safe, exclusive writes into immutable data directories (snapshots, the cache, indexes).

A run holds an exclusive lock on the directory it writes into (`.lock`), so concurrent runs take turns;
it stages in a `.tmp-` directory beside the target, syncs it to disk, renames it into place and checks
it; the next run sweeps `.tmp-` leftovers under the lock. Used by `ingest/snapshot.py` and
`engine/index.py`.
"""

from __future__ import annotations

import errno
import fcntl
import json
import logging
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

TMP = ".tmp-"

log = logging.getLogger(__name__)


class PlacementError(Exception):
    """A target couldn't be placed, or holds something else: the message says which."""


def writable(path: Path) -> None:
    for p in [path, *path.rglob("*")] if path.is_dir() else [path]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


@contextmanager
def exclusive(parent: Path, on_wait: Callable[[], None] | None = None) -> Iterator[None]:
    """Hold `<parent>/.lock` exclusively: one build or ingest at a time writes into `parent`. `on_wait` is
    called once if another run holds it, before blocking (so a command can say it is waiting)."""
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / ".lock").open("a") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if on_wait is not None:
                on_wait()
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def sweep(parent: Path) -> None:
    """Remove `.tmp-` directories a crashed run left behind. Called only under `exclusive(parent)`, so it
    never touches a live run's staging directory. A leftover it can't remove (a file it can't chmod) is logged
    once per sweep (WARNING `tmp_sweep_failed`, its name and the chmod's errno name, if any) and left, never raised: a stuck leftover
    must not fail every later build."""
    for leftover in parent.glob(f"{TMP}*"):
        reason = None
        try:
            writable(leftover)
        except OSError as e:  # rmtree below removes what it can; what survives is reported
            reason = errno.errorcode.get(e.errno or 0, type(e).__name__)
        shutil.rmtree(leftover, ignore_errors=True)
        if leftover.exists() or leftover.is_symlink():
            log.warning("tmp_sweep_failed", extra={"path": leftover.name, "reason": reason})


def sync(directory: Path) -> None:
    """Flush every file and the directory itself to disk (before the rename that publishes them)."""
    for f in directory.iterdir():
        with f.open("rb") as fh:
            fsync(fh.fileno())
    fd = os.open(directory, os.O_RDONLY)
    try:
        fsync(fd)
    finally:
        os.close(fd)


def fsync(fd: int) -> None:
    """fsync; on macOS F_FULLFSYNC, since its fsync doesn't reach the disk itself."""
    if hasattr(fcntl, "F_FULLFSYNC"):
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:  # a filesystem without it (e.g. some network mounts): plain fsync
            log.debug("fullfsync_unsupported")
    os.fsync(fd)


def lock(directory: Path) -> None:
    """Make a placed directory and its files read-only (after the rename: a read-only directory can't be
    renamed, since its `..` entry changes)."""
    for f in directory.iterdir():
        f.chmod(0o444)
    directory.chmod(0o555)


@contextmanager
def staging(parent: Path) -> Iterator[Path]:
    """A fresh `.tmp-` directory in `parent`, removed again unless the caller renamed it into place."""
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=parent, prefix=TMP))
    try:
        yield tmp
    finally:
        if tmp.exists():
            writable(tmp)
            shutil.rmtree(tmp, ignore_errors=True)


def place(tmp: Path, target: Path, same: Callable[[Path], bool]) -> bool:
    """Sync `tmp`, rename it to `target` and make it read-only; True if placed. If `target` appeared meanwhile, False when it
    holds the same content (`same(target)`), else refuse."""
    sync(tmp)
    if target.exists():
        if same(target):
            return False
        raise PlacementError(f"{target.name} exists with other contents; it is immutable")
    try:
        os.rename(tmp, target)
    except OSError as e:
        if target.exists() and same(target):
            return False
        raise PlacementError(f"could not place {target.name} ({type(e).__name__})") from None
    if not same(target):  # never report a snapshot that doesn't hold what was written
        raise PlacementError(f"{target.name} was placed but doesn't hold what was written; retire it")
    lock(target)
    return True


def write_json(path: Path, data: object) -> None:
    """One JSON file written atomically (`write_bytes`): sorted keys, one-space indent, UTF-8, a trailing
    newline."""
    write_bytes(path, (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def write_bytes(path: Path, body: bytes) -> None:
    """One file written atomically: a `.tmp-` file in the same directory, fsynced, then renamed over `path`. A
    crash leaves the old file or none, never half of one; a leftover temp file is hidden, so no reader takes it
    for an entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=TMP, suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
