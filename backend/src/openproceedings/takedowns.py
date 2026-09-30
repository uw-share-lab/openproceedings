"""The takedown list and log (decision-018, decision-022; spec 08 §Deploy "Takedown procedure"; TASK-136).

A deployment withholds an abstract a rights holder asked it to remove. Two files, both under the data
directory and never in git (`data/` is gitignored, and `protect-data-dir.sh` refuses `git add` of any
`takedowns/` path):

- **The list**, `<data-dir>/takedowns/withheld.txt`: UTF-8, one record id (`op:<venue>:<year>:<native>`) per
  line; blank lines and everything from a `#` are ignored. It holds ids only, never who asked, so the API's
  service user may read it (mode 0644 or 0640 with the API's group). `op snapshot build` withholds each listed
  abstract from the snapshot it writes (`ingest/snapshot.py::withhold`), and the API withholds each one at
  serve time from every index version it loads (`api/state.py`: the list is re-read on every load and SIGHUP).
  A missing file is an empty list. A line that isn't a record id makes the whole list unusable
  (`TakedownError`): a build is refused, and the API keeps what it serves (or serves nothing at startup), so a
  typo never silently lets an abstract through.
- **The log**, `<data-dir>/takedowns/log.jsonl`: one JSON object per request (`LOG_FIELDS`), kept by the
  operator, owned by the operator's account and mode 0600, since it holds the requester's details. Nothing in
  the API reads it; `op takedown check` checks its mode and that every listed id has a `withheld` entry.

Withholding a record (`withhold_record`) sets its `abstract` to null and drops its abstract claims, whose
values are the abstract's text; everything else stays, so it is still found by its title (spec 01 §Error
handling). Its `content_hash` is recomputed for what remains.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openproceedings.diagnostics import clip
from openproceedings.ingest.record import PaperRecord, is_paper_id

LIST = Path("takedowns") / "withheld.txt"  # relative to the data directory
LOG = Path("takedowns") / "log.jsonl"
# every log entry's keys (spec 08 §Deploy): the record, when the request came, who made it and on what basis,
# what was decided, when it was applied, and the first index_version built without the abstract
LOG_FIELDS = ("record_id", "received", "requester", "basis", "decision", "applied", "first_index_version")
DECISIONS = ("withheld", "declined", "lifted")

type Withheld = frozenset[str]
NONE: Withheld = frozenset()


class TakedownError(Exception):
    """The takedown list (or log) can't be used: the message says where and why. `reason` is a constant a log
    line may carry."""

    def __init__(self, message: str, *, reason: str = "takedowns_invalid") -> None:
        super().__init__(message)
        self.reason = reason


def list_path(data_dir: Path) -> Path:
    return data_dir / LIST


def log_path(data_dir: Path) -> Path:
    return data_dir / LOG


def parse(text: str, *, name: str = "withheld.txt") -> Withheld:
    """The record ids a takedown list names. TakedownError on a line that isn't one id."""
    ids: set[str] = set()
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not is_paper_id(line):
            raise TakedownError(
                f"{name} line {n}: {clip(line, 40)!r} is not a record id (op:<venue>:<year>:<native>); "
                "write one id per line, with notes after a `#`"
            )
        ids.add(line)
    return frozenset(ids)


def load(path: Path) -> Withheld:
    """The list at `path`; empty when there is no such file. TakedownError when it can't be read or parsed."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return NONE
    except (OSError, UnicodeDecodeError) as e:
        raise TakedownError(
            f"{path.name} can't be read ({type(e).__name__})", reason="takedowns_unreadable"
        ) from None
    return parse(text, name=path.name)


def withhold_record(record: PaperRecord) -> PaperRecord:
    """`record` with its abstract withheld: `abstract` null and no abstract claim (each claim's value is the
    abstract's text), its content_hash recomputed."""
    return record.model_copy(
        update={
            "abstract": None,
            "provenance": tuple(c for c in record.provenance if c.field != "abstract"),
        }
    )


def withhold_display(record: Mapping[str, Any]) -> dict[str, Any]:
    """An index's display record (`TantivyEngine.display`) with its abstract withheld."""
    return {**record, "abstract": None}


@dataclass(frozen=True, slots=True)
class LogProblem:
    """What `check_log` found wrong, for `op takedown check` to print (never a requester's details)."""

    message: str


def check_log(path: Path, listed: Withheld) -> list[LogProblem]:
    """The log's problems: readable by anyone but its owner (mode & 0o077), not JSON Lines of `LOG_FIELDS`
    with a `decision` in `DECISIONS`, or a listed id with no `withheld` entry. A list with no log is a problem
    only when the list names an id. Messages name line numbers and record ids, never other values."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return [LogProblem(f"{path.name} is missing: log each listed takedown")] if listed else []
    problems: list[LogProblem] = []
    if stat.S_IMODE(mode) & 0o077:
        problems.append(
            LogProblem(
                f"{path.name} is readable by others (mode {stat.S_IMODE(mode):o}): it holds requesters' "
                "details; chmod 600 it, owned by the operator's account"
            )
        )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return [*problems, LogProblem(f"{path.name} can't be read ({type(e).__name__})")]
    logged: set[str] = set()
    for n, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            problems.append(LogProblem(f"{path.name} line {n}: not a JSON object"))
            continue
        if not isinstance(entry, dict) or set(entry) != set(LOG_FIELDS):
            problems.append(LogProblem(f"{path.name} line {n}: its keys must be {', '.join(LOG_FIELDS)}"))
            continue
        rid, decision = entry["record_id"], entry["decision"]
        if not isinstance(rid, str) or not is_paper_id(rid) or decision not in DECISIONS:
            problems.append(
                LogProblem(f"{path.name} line {n}: record_id or decision ({'/'.join(DECISIONS)}) is invalid")
            )
            continue
        if decision == "withheld":
            logged.add(rid)
    problems += [
        LogProblem(f"{rid} is listed but {path.name} has no `withheld` entry for it")
        for rid in sorted(listed - logged)
    ]
    return problems
