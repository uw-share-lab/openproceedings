"""The takedown list and log (decision-018, decision-022; spec 08 §Deploy "Takedown procedure"; TASK-136).

A deployment withholds an abstract a rights holder asked it to remove. Two files, both under the data
directory and never in git (`data/` is gitignored, and `protect-data-dir.sh` refuses `git add` of any
`takedowns/` path):

- **The list**, `<data-dir>/takedowns/withheld.txt`: UTF-8 (a leading byte order mark is ignored), one record
  id (`op:<venue>:<year>:<native>`) per line; blank lines and everything from a `#` are ignored. It holds ids only, never who asked, so the API's
  service user may read it (mode 0644 or 0640 with the API's group). `op snapshot build` withholds each listed
  abstract from the snapshot it writes (`ingest/snapshot.py::withhold`), and the API withholds each one at
  serve time from every index version it loads, under any id that version holds the paper under (`same_paper`,
  TASK-067; `api/state.py`: the list is re-read on every load and SIGHUP), and on its twins (a `twin` claim,
  decision-029: two records of one paper, never merged; TASK-163, owner decision 2026-10-02).
  A missing file is an empty list, unless the path was named (`required`), or the API already applies a list or
  loads a snapshot that withheld abstracts (`api/state.py`): then it is `takedowns_missing`. A line that isn't a
  record id makes the whole list unusable (`TakedownError`): a build is refused, and the API keeps what it
  serves (or serves nothing at startup), so a typo never silently lets an abstract through.
- **The log**, `<data-dir>/takedowns/log.jsonl`: one JSON object per request (`LOG_FIELDS`), kept by the
  operator, owned by the operator's account and mode 0600, since it holds the requester's details. Nothing in
  the API reads it; `op takedown check` checks that it is the checking account's, its mode, that each listed
  id's latest entry is `withheld`, and that each id whose latest entry is `withheld` is listed.

Withholding a record (`withhold_record`) sets its `abstract` to null and drops its abstract claims, whose
values are the abstract's text; everything else stays, so it is still found by its title (spec 01 §Error
handling). Its `content_hash` is recomputed for what remains.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from openproceedings.diagnostics import clip
from openproceedings.ingest.record import PROCEEDINGS_NATIVE, PaperRecord, is_paper_id

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
        # every record id is printable ASCII: an invisible character (U+200B, U+3164, a BOM mid-file) would make
        # an id that matches nothing (TASK-067)
        if not is_paper_id(line) or not (line.isascii() and line.isprintable()):
            raise TakedownError(
                f"{name} line {n}: {clip(line, 40)!r} is not a record id (op:<venue>:<year>:<native>); "
                "write one id per line, with notes after a `#`"
            )
        ids.add(line)
    return frozenset(ids)


def load(path: Path, *, required: bool = False) -> Withheld:
    """The list at `path`; empty when there is no such file, unless `required` (a path the operator named, or
    a list the API was already applying: a missing file then lifts nothing silently). TakedownError when it
    can't be read or parsed, or is required and missing (reason `takedowns_missing`)."""
    try:
        text = path.read_text(encoding="utf-8-sig")  # an editor's byte order mark is not part of the first id
    except FileNotFoundError:
        if required:
            raise TakedownError(
                f"{path.name} is missing: restore the takedown list (or empty it to lift every takedown)",
                reason="takedowns_missing",
            ) from None
        return NONE
    except (OSError, UnicodeDecodeError) as e:
        raise TakedownError(
            f"{path.name} can't be read ({type(e).__name__})", reason="takedowns_unreadable"
        ) from None
    return parse(text, name=path.name)


# native ids unique only within their venue-year: a proceedings hash is md5 of a per-year paper number
# the proceedings hash forms (`record.PROCEEDINGS_NATIVE` but PMLR's, whose key names its volume)
_LOCAL_NATIVE = tuple(f"{prefix}-" for prefix in PROCEEDINGS_NATIVE if prefix != "pmlr")


def global_native(rid: str) -> str | None:
    """A record id's native part (`op:<venue>:<year>:<native>`) when it names one paper in every venue and year,
    so a corrected venue or year leaves the paper recognisable by it: an OpenReview forum id or a PMLR volume
    and key. None for a proceedings hash (`nips-…`, `iclr-…`), which names one paper only within its
    venue-year (TASK-067 review, measured): a NeurIPS hash is md5 of a per-year paper number, and 1,281 of them
    name two to five papers each in the 2026-09-29 snapshot; ICLR proceedings hashes collided across years too
    (5 in the 2026-09-23 snapshot). The 2014-2016 ICLR archive's `iclr-<sha256(target)>` ids are unique but share
    the form, so they lose the rekey link too (a merge still links them)."""
    native = rid.split(":", 3)[-1]
    return None if native.startswith(_LOCAL_NATIVE) else native


def twin_ids(record: PaperRecord) -> tuple[str, ...]:
    """The ids a record's `twin` claims name (decision-029, TASK-159: an ICLR 2017 workshop copy and its
    conference twin), sorted, without its own."""
    return tuple(
        sorted(
            {t for c in record.claims("twin") if isinstance(c.value, tuple) for t in c.value} - {record.id}
        )
    )


def same_paper(
    listed: Withheld,
    merges: Iterable[tuple[str, str]],
    ids: Iterable[str],
    twins: Iterable[tuple[str, str]] = (),
) -> Withheld:
    """Which of `ids` (one index version's records) are a listed paper, under its listed id or any other
    (TASK-067): linked to a listed id by `merges` ((survivor, merged) pairs, from any build: the same paper
    found twice), or by `twins` ((record, twin) pairs of `twin` claims: decision-029's two records of one
    paper, never merged, which a takedown follows too, TASK-163), or holding its globally unique native id
    (`global_native`: the same paper rekeyed by a corrected venue or year), transitively. The list names one
    id; an older version may hold the paper under an id it had before, or as a duplicate a later build merged,
    and a newer one under the id it has now: each is withheld. A proceedings hash links nothing by itself: in
    another year it is another paper."""
    if not listed:
        return NONE
    held = list(ids)
    linked: dict[str, set[str]] = {}
    for survivor, merged in (*merges, *twins):
        linked.setdefault(survivor, set()).add(merged)
        linked.setdefault(merged, set()).add(survivor)
    by_native: dict[str, set[str]] = {}
    for rid in (*held, *linked, *listed):
        if (native := global_native(rid)) is not None:
            by_native.setdefault(native, set()).add(rid)
    found, todo = set(listed), list(listed)
    while todo:
        at = todo.pop()
        native = global_native(at)
        for rid in linked.get(at, set()) | (by_native[native] if native is not None else set()):
            if rid not in found:
                found.add(rid)
                todo.append(rid)
    return frozenset(rid for rid in held if rid in found)


def withhold_record(record: PaperRecord) -> PaperRecord:
    """`record` with its abstract withheld: `abstract` null and no abstract claim (each claim's value is the
    abstract's text), its content_hash recomputed."""
    return record.model_copy(
        update={
            "abstract": None,
            "provenance": tuple(c for c in record.provenance if c.field != "abstract"),
        }
    )


@dataclass(frozen=True, slots=True)
class LogProblem:
    """What `check_log` found wrong, for `op takedown check` to print (never a requester's details)."""

    message: str


def check_log(path: Path, listed: Withheld) -> list[LogProblem]:
    """The log's problems: readable by anyone but its owner (mode & 0o077), owned by another account than the
    one checking it (the operator's), not JSON Lines of `LOG_FIELDS` with a `decision` in `DECISIONS`, or a
    listed id whose latest entry (the last line naming it) isn't `withheld`, or an id whose latest entry is
    `withheld` that isn't listed (a line dropped from the list). A list with no log is a problem only when the
    list names an id. Messages name line numbers and record ids, never other values."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return [LogProblem(f"{path.name} is missing: log each listed takedown")] if listed else []
    mode = st.st_mode
    problems: list[LogProblem] = []
    if st.st_uid != os.getuid():
        problems.append(
            LogProblem(
                f"{path.name} is owned by another account: it belongs to the operator's, who runs this check"
            )
        )
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
    latest: dict[str, str] = {}
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
        latest[rid] = decision
    problems += [
        LogProblem(f"{rid} is listed but its latest entry in {path.name} is not `withheld`")
        for rid in sorted(listed)
        if latest.get(rid) != "withheld"
    ]
    problems += [  # the other direction: a line dropped from the list silently lifts a takedown (TASK-067)
        LogProblem(
            f"{rid}'s latest entry in {path.name} is `withheld`, but the list doesn't name it: list it again, "
            "or log it lifted"
        )
        for rid, decision in sorted(latest.items())
        if decision == "withheld" and rid not in listed
    ]
    return problems
