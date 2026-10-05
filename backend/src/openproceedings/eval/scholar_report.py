"""The Scholar comparison report (spec 07 §B, scholar-comparison-protocol skill; TASK-056): `op eval scholar`
writes `docs/results/<YYYY-MM-DD>-scholar-comparison.md` and, next to it, `<YYYY-MM-DD>-scholar-comparison-review.csv`
(the protocol's `review.csv`, dated like the report so a later run doesn't replace an earlier one's human calls).

Everything counted here comes from `scholar_compare`: this module only chooses the review rows, renders and
writes. A figure in the report is a count of rows of one run; nothing is typed in. Prose that belongs to one
set of inputs (why this export, what its searches returned) is read from a notes file and printed verbatim
under its sha256, as the coverage report reads its cause notes.

Once the review file is filled, the same command reads the calls back (`read_calls`): the file is left as it
is, and the report gains the calls, the roles they were made under (always printed beside the verdict: a call
weighs what its role does), the counts after them, and whether every disagreement is classified.

`review.csv` holds every row the automation couldn't settle, plus a tenth of each query's settled disagreements
as a spot check. The tenth is the rows whose sha256 (of query name, side and ids) sorts first: fixed for a
given run, unrelated to any field, and the same on every machine, so the file is reproducible. `human_class`,
`reviewer_role` and `note` are left empty for whoever makes the call.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openproceedings import storage
from openproceedings.eval.scholar_compare import (
    COMPAT_READING,
    COVERAGE_GAP,
    FILTERED,
    FULL_TEXT,
    ONLY_OP,
    ONLY_SCHOLAR,
    OUR_BUG,
    SCHOLAR_CAP,
    SCHOLAR_CAP_RESULTS,
    SCHOLAR_MISSED,
    STEMMING,
    UNSETTLED,
    MatchIndex,
    QueryComparison,
    Row,
    ScholarSide,
    Scope,
)
from openproceedings.export import csv_cell  # the one CSV-injection guard: titles come from anyone

SPOT_CHECK = 0.1  # the share of a query's settled disagreements a person re-checks
REVIEW_COLUMNS = (
    "query_name", "side", "scholar_key", "op_id", "title", "venue", "year", "auto_class", "auto_evidence",
    "human_class", "reviewer_role", "note", "row_kind", "index_version", "record_source", "abstract_source",
)  # fmt: skip
UNRESOLVED, SPOT = "unresolved", "spot_check"
BOM = chr(0xFEFF)
_MEANING = {
    OUR_BUG: "the oracle and the served engine disagree (must be 0)",
    FILTERED: "in the corpus; fails the default track or status filters and matches once they are removed",
    COMPAT_READING: "decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus",
    COVERAGE_GAP: "no record in the snapshot by forum id, proceedings id or title+venue+year",
    STEMMING: "matches title or abstract only with an inflected form added",
    FULL_TEXT: "in the corpus with an abstract; no reading matches its title or abstract, inflected forms included",
    UNSETTLED: "the automation can't tell (see the row's evidence)",
    SCHOLAR_CAP: "a Scholar search covering its venue and year returned the result cap",
    SCHOLAR_MISSED: "an exact title or abstract match that the Scholar set lacks",
}


# --- query files ---------------------------------------------------------------------------------------------


def parse_query_file(text: str, stem: str) -> list[tuple[str, str]]:
    """(name, query) pairs from a query file. In the Trust-Evals fixture's form, each `## name` line is followed
    by its query on the next non-blank line, and other `#` lines are comments; a file with no `## ` line is one
    query, named `stem`. ValueError for a name without a query, a repeated name, or an empty file."""
    lines = [ln.strip() for ln in text.splitlines()]
    if not any(ln.startswith("## ") for ln in lines):
        body = " ".join(ln for ln in lines if ln and not ln.startswith("#"))
        if not body:
            raise ValueError(f"{stem}: no query")
        return [(stem, body)]
    out: list[tuple[str, str]] = []
    name: str | None = None
    for ln in lines:
        if ln.startswith("## "):
            if name is not None:
                raise ValueError(f"query `{name}` has no query line")
            name = ln[3:].strip()
        elif ln and not ln.startswith("#") and name is not None:
            out.append((name, ln))
            name = None
    if name is not None:
        raise ValueError(f"query `{name}` has no query line")
    if repeated := [n for n, k in Counter(n for n, _ in out).items() if k > 1]:
        raise ValueError(f"query name used twice: {', '.join(repeated)}")
    return out


# --- review.csv ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewRow:
    query_name: str
    row: Row
    kind: str  # UNRESOLVED or SPOT


def _draw(name: str, row: Row) -> str:
    return hashlib.sha256("\0".join((name, row.side, row.scholar_key, row.op_id)).encode()).hexdigest()


def review_rows(comparisons: Sequence[QueryComparison]) -> list[ReviewRow]:
    """Per query, in its order: every unsettled disagreement, then the spot check (a tenth of the settled ones,
    rounded up, by `_draw`)."""
    out: list[ReviewRow] = []
    for c in comparisons:
        settled = sorted((r for r in c.disagreements if r.settled), key=lambda r: _draw(c.name, r))
        out += [ReviewRow(c.name, r, UNRESOLVED) for r in c.disagreements if not r.settled]
        out += [ReviewRow(c.name, r, SPOT) for r in settled[: math.ceil(len(settled) * SPOT_CHECK)]]
    return out


def render_review(rows: Sequence[ReviewRow], index_version: str) -> str:
    """`review.csv`: the protocol's twelve columns, then `row_kind` (why the row is here), `index_version`, and
    what the row's index record rests on: `record_source` (`crawled`, or `ris_only` for a record only an imported
    RIS set holds) and `abstract_source`."""
    buffer = io.StringIO()
    buffer.write(
        BOM
    )  # with CRLF rows, what a spreadsheet opens as UTF-8 and writes back (as `/compare`'s CSV)
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(REVIEW_COLUMNS)
    for x in rows:
        r = x.row
        cells = (
            x.query_name, r.side, r.scholar_key, r.op_id, r.title, r.venue, "" if r.year is None else r.year,
            r.auto_class, r.auto_evidence, "", "", "", x.kind, index_version,
            {True: "crawled", False: "ris_only", None: ""}[r.independent], r.abstract_source,
        )  # fmt: skip
        writer.writerow(csv_cell(c) for c in cells)
    return buffer.getvalue()


# --- the calls, read back -----------------------------------------------------------------------------------------

HUMAN_COLUMNS = ("human_class", "reviewer_role", "note")
IN_BOTH = "in_both"  # the record is the same paper as one in the result: no disagreement after all
OUT_OF_SCOPE = (
    "out_of_scope"  # the record is no paper of the scope's venues and years (Scholar's venue is wrong)
)
# what `human_class` may hold: a class of the protocol, or one of the two verdicts above
HUMAN_CLASSES = (
    OUR_BUG, FILTERED, COMPAT_READING, COVERAGE_GAP, STEMMING, FULL_TEXT, SCHOLAR_CAP, SCHOLAR_MISSED, IN_BOTH,
    OUT_OF_SCOPE,
)  # fmt: skip
_SIDE_VERDICTS = (
    IN_BOTH,
    OUT_OF_SCOPE,
)  # verdicts about a record of the compared set: Scholar-side rows only


@dataclass(frozen=True)
class Call:
    human_class: str
    reviewer_role: str
    note: str


@dataclass(frozen=True)
class HumanCalls:
    """The filled rows of a review file, with the file's name and sha256 for the report's header. `calls` is
    keyed by the row's place among the run's review rows (the file's rows are verified to be the run's, in its
    order), so no key is ever rebuilt from a cell a spreadsheet or the injection guard may have rewritten."""

    name: str
    sha256: str
    calls: Mapping[int, Call]

    @property
    def roles(self) -> list[tuple[str, int]]:
        """Each distinct `reviewer_role` with its rows, most rows first: whose calls these are."""
        return sorted(
            Counter(c.reviewer_role for c in self.calls.values()).items(), key=lambda x: (-x[1], x[0])
        )


def _blanked(text: str) -> list[list[str]]:
    """A review file's rows with the three call columns emptied: what the run itself wrote."""
    rows = list(csv.reader(io.StringIO(text.removeprefix(BOM))))
    if not rows:
        return rows
    at = [rows[0].index(c) for c in HUMAN_COLUMNS if c in rows[0]]
    return [rows[0], *([("" if k in at else v) for k, v in enumerate(r)] for r in rows[1:])]


def _difference(found: list[list[str]], expected: list[list[str]]) -> str:
    """Where a filled file first departs from the rows this run writes, for the refusal."""
    if found[:1] != expected[:1]:
        return "its header is not this run's"
    for n, (a, b) in enumerate(zip(found[1:], expected[1:], strict=False), 2):
        if a != b:
            column = next(
                (expected[0][k] for k, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), "its length"
            )
            return f"line {n}, column `{column}`"
    return f"it has {len(found) - 1} rows where this run writes {len(expected) - 1}"


def _paired(row: Row) -> str | None:
    """The index record an `in_both` call pairs a Scholar-side row with: its own record, or else the one
    same-title record its evidence names (`Row.near`). None when the row names none or several."""
    return row.op_id or (row.near[0] if len(row.near) == 1 else None)


def read_calls(review_file: Path, expected: str, review: Sequence[ReviewRow] = ()) -> HumanCalls | None:
    """The calls filled into `review_file`, or None when there is no file or nothing is filled. `expected` is
    the review text this run would write and `review` its rows, in order. ValueError when the file is not
    UTF-8, when its rows are not this run's (it belongs to another index, set or query, or a spreadsheet
    rewrote a cell: the first difference is named), when a `human_class` is not one of HUMAN_CLASSES, when a
    row has a role or a note without a class or a class without a `reviewer_role`, or when an `in_both` or
    `out_of_scope` call is on a row it can't apply to."""
    if not review_file.is_file():
        return None
    data = review_file.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(f"{review_file.name} is not UTF-8: save it as CSV UTF-8 and run again") from None
    found, wanted = _blanked(text), _blanked(expected)
    filled = [
        (n, tuple(row.get(c, "").strip() for c in HUMAN_COLUMNS))
        for n, row in enumerate(csv.DictReader(io.StringIO(text)))
    ]
    filled = [(n, cells) for n, cells in filled if any(cells)]
    if not filled:
        return None
    if found != wanted:
        raise ValueError(
            f"{review_file.name} holds calls for other rows than this run writes ({_difference(found, wanted)}): "
            "another index, set or query, or a cell the run wrote was changed. Move it, or write elsewhere "
            "(--out, --date)"
        )
    calls: dict[int, Call] = {}
    for n, (cls, role, note) in filled:
        where = f"{review_file.name} line {n + 2}"
        if cls not in HUMAN_CLASSES:
            raise ValueError(
                f"{where}: human_class must be one of {', '.join(HUMAN_CLASSES)}"
                + ("" if cls else " (the row has a role or a note but no class)")
            )
        if not role:
            raise ValueError(f"{where}: a human_class needs a reviewer_role (a role, not a name)")
        if review and cls in _SIDE_VERDICTS and review[n].row.side != "scholar":
            raise ValueError(
                f"{where}: `{cls}` is a call about a record of the compared set; make it on that row"
            )
        if review and cls == IN_BOTH and _paired(review[n].row) is None:
            raise ValueError(
                f"{where}: `in_both` needs the one index record the row is the same paper as, and its evidence "
                "names none or several"
            )
        calls[n] = Call(cls, role, note)
    return HumanCalls(review_file.name, hashlib.sha256(data).hexdigest(), calls)


def human_bugs(calls: HumanCalls | None) -> int:
    """How many rows a call marks `our_bug`."""
    return 0 if calls is None else sum(c.human_class == OUR_BUG for c in calls.calls.values())


def _waiting(review: Sequence[ReviewRow], calls: HumanCalls | None) -> int:
    made = calls.calls if calls is not None else {}
    return sum(x.kind == UNRESOLVED and n not in made for n, x in enumerate(review))


def classified(
    comparisons: Sequence[QueryComparison], review: Sequence[ReviewRow], calls: HumanCalls | None
) -> bool:
    """Spec 07 §B's bar: no `our_bug`, by the automation or by a call, and a call on every row the automation
    left for one. Whose calls they are is not judged here: the report prints the roles beside the verdict."""
    return not (sum(c.our_bug for c in comparisons) or human_bugs(calls) or _waiting(review, calls))


@dataclass(frozen=True)
class Tally:
    """One query's sizes and class counts, for the automation alone or after the calls."""

    in_scope: int  # papers of the compared set in scope
    both: int
    scholar: Mapping[str, int]  # only in the set, by class
    result: Mapping[str, int]  # only in the result, by class


def tally(c: QueryComparison) -> Tally:
    return Tally(
        c.scholar_in_scope, len(c.kept), dict(c.counts("scholar")), dict(c.counts("openproceedings"))
    )


def after_calls(c: QueryComparison, review: Sequence[ReviewRow], calls: HumanCalls | None) -> Tally:
    """`c`'s tally once each call on one of its rows is applied (scholar-comparison-protocol §After the calls):
    a class moves the row to that class; `out_of_scope` takes the record out of the set, so out of the
    denominator; `in_both` moves it to "in both" and, when the record it is paired with (`_paired`) is among
    the rows only in the result, takes that row out of them, the two being one paper. Rows without a call keep
    the automation's class."""
    made = calls.calls if calls is not None else {}
    in_scope, both = c.scholar_in_scope, len(c.kept)
    scholar, result = c.counts("scholar"), c.counts("openproceedings")
    added = {r.op_id: r.auto_class for r in c.added}
    for n, x in enumerate(review):
        if x.query_name != c.name or n not in made:
            continue
        cls, side = made[n].human_class, (scholar if x.row.side == "scholar" else result)
        side[x.row.auto_class] -= 1
        if cls == OUT_OF_SCOPE:
            in_scope -= 1
        elif cls == IN_BOTH:
            both += 1
            if (pair := _paired(x.row)) in added:
                result[added.pop(pair)] -= 1
        else:
            side[cls] += 1
    return Tally(
        in_scope, both, {k: v for k, v in scholar.items() if v}, {k: v for k, v in result.items() if v}
    )


def _roles(calls: HumanCalls) -> str:
    return "; ".join(f"`{_md(role)}` ({_n(k)} row{'' if k == 1 else 's'})" for role, k in calls.roles)


def _after_table(c: QueryComparison, review: Sequence[ReviewRow], calls: HumanCalls) -> list[str]:
    before, after = tally(c), after_calls(c, review, calls)
    lines = [
        f"`{c.name}`, the automation's counts and the counts after the calls:",
        "",
        "| | automation | after the calls |",
        "|---|---|---|",
        f"| Scholar set, in scope | {_n(before.in_scope)} | {_n(after.in_scope)} |",
        f"| in both | {_n(before.both)} | {_n(after.both)} |",
        f"| only in the Scholar set | {_n(sum(before.scholar.values()))} | {_n(sum(after.scholar.values()))} |",
        *(
            f"| only in the Scholar set: `{cls}` | {_n(before.scholar.get(cls, 0))} | {_n(after.scholar.get(cls, 0))} |"
            for cls in (*ONLY_SCHOLAR, *(k for k in HUMAN_CLASSES if k not in ONLY_SCHOLAR))
            if before.scholar.get(cls) or after.scholar.get(cls)
        ),
        f"| only in openproceedings | {_n(sum(before.result.values()))} | {_n(sum(after.result.values()))} |",
        *(
            f"| only in openproceedings: `{cls}` | {_n(before.result.get(cls, 0))} | {_n(after.result.get(cls, 0))} |"
            for cls in (*ONLY_OP, *(k for k in HUMAN_CLASSES if k not in ONLY_OP))
            if before.result.get(cls) or after.result.get(cls)
        ),
        "",
    ]
    return lines


def _verdict(
    comparisons: Sequence[QueryComparison], review: Sequence[ReviewRow], calls: HumanCalls | None
) -> str:
    """The closing line: the verdict, never without whose calls it rests on."""
    bugs, waiting = sum(c.our_bug for c in comparisons), _waiting(review, calls)
    counts = (
        f"`our_bug` by the automation: {bugs}; by a call: {human_bugs(calls)}; rows left for a call that have "
        f"none yet: {_n(waiting)}."
    )
    if calls is None:
        return f"**Every disagreement classified: no.** {counts}"
    yes = classified(comparisons, review, calls)
    return (
        f"**Every disagreement classified: {'yes' if yes else 'no'}{', on the calls whose roles this line names' if yes else ''}.** "
        f"{counts} The {_n(len(calls.calls))} calls were made as: {_roles(calls)}. A call weighs what its role "
        "does: unless every role is an independent reviewer's, this verdict is provisional and spec 07 §B's bar "
        "is not closed."
    )


def _human(
    comparisons: Sequence[QueryComparison], review: Sequence[ReviewRow], calls: HumanCalls | None
) -> list[str]:
    """The section that reads the review file back: the calls per query and under which roles, the counts after
    them, and whether every disagreement is now classified."""
    made = calls.calls if calls is not None else {}
    lines = ["## Human calls", ""]
    if calls is None:
        lines += [
            "None yet: no row of the review file has a `human_class`. Whoever makes a call fills `human_class` "
            "(one of "
            + ", ".join(f"`{c}`" for c in HUMAN_CLASSES)
            + "), `reviewer_role` (their role, never a name; it is printed here beside the verdict) and, if "
            "wanted, `note`; running the same command again then reads the calls back into this section and "
            "leaves the file as it is.",
            "",
        ]
    else:
        lines += [
            f"Read from `{calls.name}` (sha256 `{calls.sha256}`): {_n(len(made))} of its {_n(len(review))} rows "
            f"have a call. **Who made them** (the file's `reviewer_role`, as written): {_roles(calls)}. Every "
            "figure in this section rests on those roles; the tables above this section are the automation's "
            "alone. `in_both` means the record is the same paper as one in the result; `out_of_scope` that it is "
            "no paper of the scope's venues and years.",
            "",
            "| query | unresolved rows | called | spot-check rows | called | agree with the automated class |",
            "|---|---|---|---|---|---|",
        ]
        for c in comparisons:
            mine = [(n, x) for n, x in enumerate(review) if x.query_name == c.name]
            open_rows = [n for n, x in mine if x.kind == UNRESOLVED]
            spot = [(n, x) for n, x in mine if x.kind == SPOT]
            spot_called = [(n, x) for n, x in spot if n in made]
            agree = sum(made[n].human_class == x.row.auto_class for n, x in spot_called)
            lines.append(
                f"| `{c.name}` | {_n(len(open_rows))} | {_n(sum(n in made for n in open_rows))} | {_n(len(spot))} "
                + (f"| {_n(len(spot_called))} | {_n(agree)} |" if spot_called else "| none called | — |")
            )
        pairs = Counter(
            (x.query_name, x.row.auto_class, made[n].human_class) for n, x in enumerate(review) if n in made
        )
        lines += [
            "",
            "| query | automated class | human class | rows |",
            "|---|---|---|---|",
            *(f"| `{q}` | `{auto}` | `{human}` | {_n(k)} |" for (q, auto, human), k in sorted(pairs.items())),
            "",
            "### After the calls",
            "",
            "Each call moves its row: a class puts the row in that class; `out_of_scope` takes the record out of "
            'the Scholar set, so out of the denominator; `in_both` moves it to "in both" and takes the index '
            "record it is paired with (the row's own record, or the one same-title record its evidence names) out "
            "of the rows only in openproceedings. Rows without a call keep the automation's class.",
            "",
        ]
        for c in comparisons:
            lines += _after_table(c, review, calls)
        flagged = [x for n, x in enumerate(review) if n in made and made[n].human_class == OUR_BUG]
        if flagged:
            lines += [
                f"**{_n(len(flagged))} row(s) are called `our_bug`.** Each is a Must-fix with a golden case "
                "(spec 07 §Error handling): "
                + "; ".join(f"`{x.query_name}` `{x.row.op_id or x.row.scholar_key}`" for x in flagged)
                + ".",
                "",
            ]
    lines += [_verdict(comparisons, review, calls), ""]
    return lines


# --- the report -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RisFile:
    name: str  # the file's name, never its directory (a path can name a person)
    sha256: str
    records: int


@dataclass(frozen=True)
class Meta:
    """What the numbers depend on, for the header."""

    date: date
    index_version: str
    tokenizer_version: str
    snapshot: str
    snapshot_hash: str
    records: int  # in the snapshot
    ris: tuple[RisFile, ...]
    scope: Scope
    command: str
    notes: str | None = None  # the notes file's text, printed verbatim
    notes_name: str | None = None
    notes_sha256: str | None = None
    query_files: tuple[tuple[str, str], ...] = ()  # (file name, sha256) of each query file read
    answers: str | None = (
        None  # the query the Scholar set is the answer to, when the caller says (`--answers`)
    )


def _n(k: int) -> str:
    return f"{k:,}"


def _pct(part: int, whole: int) -> str:
    return "—" if not whole else f"{100 * part / whole:.1f}%"


def _md(text: str) -> str:
    """Text for a Markdown table cell: one line, no cell break."""
    return " ".join(text.split()).replace("|", "\\|")


def _class_table(rows: Sequence[Row], order: Sequence[str], of: int, of_label: str) -> list[str]:
    """Class counts, and under each how many of its records a crawl holds and how many only the imported set."""
    counts = Counter(r.auto_class for r in rows)
    crawled = Counter(r.auto_class for r in rows if r.independent is True)
    imported = Counter(r.auto_class for r in rows if r.independent is False)
    total = len(rows)
    lines = [
        f"| class | records | of these | of {of_label} | crawled record | RIS-only record | meaning |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| `{cls}` | {_n(counts[cls])} | {_pct(counts[cls], total)} | {_pct(counts[cls], of)} | {_n(crawled[cls])} "
        f"| {_n(imported[cls])} | {_MEANING[cls]} |"
        for cls in order
        if counts[cls] or cls == OUR_BUG
    ]
    lines.append(
        f"| total | {_n(total)} | {_pct(total, total)} | {_pct(total, of)} | {_n(sum(crawled.values()))} "
        f"| {_n(sum(imported.values()))} | |"
    )
    return lines


def _row_list(rows: Sequence[Row]) -> list[str]:
    lines = ["| record | title | venue | year | class | evidence |", "|---|---|---|---|---|---|"]
    lines += [
        f"| `{r.op_id or r.scholar_key}` | {_md(r.title)} | {_md(r.venue)} | {r.year or '—'} | `{r.auto_class}` "
        f"| {_md(r.auto_evidence)} |"
        for r in rows
    ]
    return lines


def _provenance(side: ScholarSide, index: MatchIndex, meta: Meta) -> list[str]:
    """What the matches rest on: per venue and year, the matched papers a crawl holds and those only the imported
    set holds, beside the crawled records the index has there at all."""
    matched = [e.match.op_id for e in side.entries if e.match.op_id is not None]
    own = [i for i in matched if i not in index.independent]
    cells = sorted({index.cells[i] for i in matched})
    per = Counter(index.cells[i] for i in matched)
    per_own = Counter(index.cells[i] for i in own)
    abstracts = Counter(index.abstracts.get(i, "") for i in matched)
    years = range(meta.scope.years[0], meta.scope.years[1] + 1) if meta.scope.years else ()
    empty = [f"{v} {y}" for v in sorted(meta.scope.venues) for y in years if not index.crawled.get((v, y))]
    shared = [e for e in side.entries if e.match.shared]
    same_cell = sum(
        any(index.cells[i] == index.cells[e.match.op_id] for i in e.match.shared)
        for e in shared
        if e.match.op_id is not None
    )
    lines = [
        "### What the matches rest on",
        "",
        f"Matched to a record with an independent source (a crawl of OpenReview or the proceedings): "
        f"**{_n(len(matched) - len(own))}**. Matched to a record whose only source is an imported RIS set "
        f"(RIS-only): **{_n(len(own))}**.",
        "",
        "A RIS-only record is in the index because a Scholar set was imported into it. When the set compared here "
        "is that set, such a match is the set matching itself: it shows nothing about coverage, and the title and "
        "abstract the classes are judged on are the ones the import carried. Counts below are given for both "
        "kinds.",
        "",
        "| venue | year | matched papers | crawled record | RIS-only record | crawled records the index holds |",
        "|---|---|---|---|---|---|",
        *(
            f"| {v} | {y} | {_n(per[(v, y)])} | {_n(per[(v, y)] - per_own[(v, y)])} | {_n(per_own[(v, y)])} "
            f"| {_n(index.crawled.get((v, y), 0))} |"
            for v, y in cells
        ),
        "",
        "Abstract source of the matched records: "
        + "; ".join(f"`{src or 'unknown'}` {_n(k)}" for src, k in sorted(abstracts.items(), key=lambda x: (-x[1], x[0])))
        + ". `ris:` is text the import carried (what scholarmend read from the proceedings page or the OpenReview "
        "API), not a crawl of this project.",
        "",
    ]  # fmt: skip
    if empty:
        lines += [
            f"The index holds **no crawled record** for {', '.join(empty)}. There, every match is to a RIS-only "
            "record, and no record can be only in openproceedings: that side of the comparison is empty by "
            "construction, not by agreement.",
            "",
        ]
    if shared:
        lines += [
            f"{_n(len(shared))} papers matched a RIS-only record whose title key another index record has "
            f"too ({_n(same_cell)} in the same venue and year: one paper under two ids, so the set can count it "
            "twice; the others in another venue or year: the import's venue or year may be wrong). The match is "
            "kept, and each such row that is a disagreement is `unsettled`, for a reviewer.",
            "",
        ]
    return lines


def _matching(side: ScholarSide, index: MatchIndex, meta: Meta) -> list[str]:
    rules = Counter((e.match.rule or f"no match ({e.match.problem})").replace("_", " ") for e in side.entries)
    reasons = Counter(d.reason for d in side.out_of_scope)
    largest = max(side.searches.values(), default=0)
    unvenued = sum(e.match.problem == "no_venue" for e in side.entries)
    lines = [
        "## Matching the Scholar set to the index",
        "",
        "Each Scholar record is matched by spec 01's merge rules, in their order: the OpenReview forum id its URL "
        "names, else the proceedings paper its URL names (the native id within that venue and year), else the "
        "dedup title key within the same venue and year. A title alone never matches. A matched record is scoped "
        "by its index record's venue and year, an unmatched one by its own; records outside the scope are dropped "
        "before comparing.",
        "",
        "| | records |",
        "|---|---|",
        f"| read | {_n(side.read)} |",
        f"| outside the scope ({meta.scope.describe()}) | {_n(len(side.out_of_scope))} |",
        f"| in scope | {_n(side.read - len(side.out_of_scope))} |",
        f"| repeats of a paper already counted | {_n(side.duplicates)} |",
        f"| **papers in scope** (the denominator of every percentage of the Scholar set) | **{_n(len(side.entries))}** |",
        "",
        "| matched by | papers |",
        "|---|---|",
        *(f"| {rule} | {_n(k)} |" for rule, k in sorted(rules.items(), key=lambda x: (-x[1], x[0]))),
        "",
    ]  # fmt: skip
    if unvenued:
        lines += [
            f"`no match (no venue)`: {_n(unvenued)} records whose venue string is empty or cut by Scholar (`…`) "
            "and whose URLs name no indexed paper, but whose title key an in-scope index record of the same year "
            "has. "
            "A title alone is never a match, so they are counted in scope and listed as `unsettled` for a reviewer, "
            "with that record named.",
            "",
        ]
    if reasons:
        by_venue = Counter(d.record.venue_raw or "(no venue)" for d in side.out_of_scope)
        lines += [
            "Outside the scope: "
            + "; ".join(f"{_n(k)} {reason.replace('_', ' ')}" for reason, k in sorted(reasons.items()))
            + ". `venue unrecognised` means the record's venue string is not exactly one of Scholar mode's source "
            "names and no URL of it names an indexed paper: it names another venue in full, or it is empty or cut "
            "(`…`) and no in-scope index record of its year has its title. Venue strings: "
            + "; ".join(f"{_md(v)} ({k})" for v, k in sorted(by_venue.items(), key=lambda x: (-x[1], x[0])))
            + ".",
            "",
        ]
    lines += _provenance(side, index, meta)
    lines += [
        f"Scholar searches in the set (Publish or Perish query dates): {_n(len(side.searches))}; the largest holds "
        f"{_n(largest)} records. Google Scholar returns at most {_n(SCHOLAR_CAP_RESULTS)} per search; a search at "
        "the cap makes every record only in openproceedings from its venues and years `scholar_cap`. "
        + (
            f"{_n(len(side.capped))} venue-year(s) are covered by a capped search."
            if side.capped
            else "No search in this set reached it."
        ),
        "",
    ]
    return lines


def _other_set(c: QueryComparison, meta: Meta) -> str | None:
    """The caveat for a query the Scholar set is not the answer to."""
    if meta.answers is None or meta.answers == c.name:
        return None
    return (
        f"The Scholar set is Google Scholar's answer to `{meta.answers}`, not to this string. The numbers below "
        "are what this string keeps, drops and adds against that set; they say nothing about what Scholar would "
        "return for it."
    )


def _query(
    c: QueryComparison, review: Sequence[ReviewRow], meta: Meta, calls: HumanCalls | None = None
) -> list[str]:
    only = c.counts("scholar")
    scholar_rows = [r for r in c.disagreements if r.side == "scholar"]
    unresolved = sum(x.query_name == c.name and x.kind == UNRESOLVED for x in review)
    spot = sum(x.query_name == c.name and x.kind == SPOT for x in review)
    lines = [f"## Query `{c.name}`", ""]
    if (caveat := _other_set(c, meta)) is not None:
        lines += [caveat, ""]
    lines += [
        f"Run in `mode={c.mode}`, exactly as written (`canonical_hash` `{c.canonical_hash}`):",
        "",
        "```",
        c.query,
        "```",
        "",
        "Canonical form, as run:",
        "",
        "```",
        c.canonical,
        "```",
        "",
        "Notices: " + (", ".join(f"`{code}` × {k}" for code, k in c.notices.items()) or "none") + ".",
        "",
    ]
    if c.scholar_reading is not None:
        lines += [
            "Google Scholar reads this string differently from Scholar mode. Scholar's reading, written natively:",
            "",
            "```",
            c.scholar_reading,
            "```",
            "",
        ]
    if c.notices.get("COMPAT_POP_PHRASE"):
        lines += [
            f"**Decision-002.** This string has {c.notices['COMPAT_POP_PHRASE']} unquoted multi-word `|` items. "
            "Scholar mode reads each as a phrase, which is what the review meant; Google Scholar itself ORs only "
            "the neighbouring words. Every difference that comes from that reading is classed `compat_reading`: "
            "it is not a record either side missed.",
            "",
        ]
    kept_own = sum(r.independent is False for r in c.kept)
    kept_shared = sum(r.shared_title for r in c.kept)
    lines += [
        "| | records |",
        "|---|---|",
        f"| Scholar set, in scope | {_n(c.scholar_in_scope)} |",
        f"| openproceedings `total` (default filters; every venue and year) | {_n(c.total)} |",
        f"| openproceedings, in scope | {_n(c.in_scope)} |",
        f"| in both | {_n(len(c.kept))} ({_n(len(c.kept) - kept_own)} crawled records, {_n(kept_own)} RIS-only) |",
        f"| in both, matched to a RIS-only record whose title another index record has | {_n(kept_shared)} |",
        f"| only in the Scholar set | {_n(len(c.only_scholar))} |",
        f"| only in openproceedings | {_n(len(c.added))} |",
        "",
        "### Only in the Scholar set",
        "",
        *_class_table(scholar_rows, ONLY_SCHOLAR, c.scholar_in_scope, "the Scholar set"),
        "",
        "`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index "
        "record is in neither).",
        "",
        "### Only in openproceedings",
        "",
        *_class_table(c.added, ONLY_OP, c.in_scope, "the result"),
        "",
        f"`our_bug`: **{c.our_bug}**. Rows of `review.csv`: {_n(unresolved)} left for a call, {_n(spot)} spot check.",
        "",
    ]
    if c.added and c.notices.get("COMPAT_POP_DOLLAR"):
        lines += [
            "Read the table above with care. A `compat_reading` row decided by `$` matches only through a plural, "
            "the same forms the `stemming` class credits Google Scholar with, so it is no evidence that Scholar "
            "would not return the paper. `scholar_missed` counts exact matches only: it is a floor for what "
            "Scholar's set lacks, not the whole of it.",
            "",
        ]
    if c.groups:
        lines += [
            f"### Concept groups, over the {_n(c.matched)} Scholar papers the index holds",
            "",
            "How many of them hold each top-level group of the string in title or abstract, whatever their track "
            "and status:",
            "",
            "| group | as run | with inflected forms |",
            "|---|---|---|",
            *(
                f"| {k}. `{_md(g.text)}` | {_n(g.exact)} | {_n(g.with_forms)} |"
                for k, g in enumerate(c.groups, 1)
            ),
            "",
        ]
    if c.variants:
        lines += [
            "Inflected forms added for the `stemming` test (the forms the compared records hold): "
            + "; ".join(f"`{t}` → {', '.join(forms)}" for t, forms in c.variants.items())
            + ".",
            "",
        ]
    listed = [r for r in c.only_scholar if r.auto_class in (COVERAGE_GAP, UNSETTLED, OUR_BUG, FILTERED)]
    if listed:
        lines += ["### Scholar-only records listed", "", *_row_list(listed), ""]
    if c.added:
        lines += ["### Records only in openproceedings", "", *_row_list(c.added), ""]
    full_rows = [r for r in scholar_rows if r.auto_class == FULL_TEXT]
    full, stem = len(full_rows), only[STEMMING]
    full_own = sum(r.independent is False for r in full_rows)
    full_filtered = sum(r.fails_filters for r in full_rows)
    prefix = (
        "not computed: a prefix expands past the engine's cap"
        if c.full_text_by_prefix is None
        else f"{_n(c.full_text_by_prefix)} of the {_n(full)} ({_pct(c.full_text_by_prefix, full)})"
    )
    lines += [
        f"**Finding.** Of the {_n(c.scholar_in_scope)} in-scope papers of the Scholar set, {_n(full)} "
        f"({_pct(full, c.scholar_in_scope)}) match this string nowhere in title or abstract, inflected forms "
        f"included (`full_text`), and {_n(stem)} ({_pct(stem, c.scholar_in_scope)}) match only through an inflected "
        f"form (`stemming`). {_n(len(c.kept))} ({_pct(len(c.kept), c.scholar_in_scope)}) are in the exact result.",
        "",
        f"- Of the {_n(full)} `full_text` papers, {_n(full - full_own)} rest on a crawled record and {_n(full_own)} "
        "on a RIS-only record, whose title and abstract are the import's own.",
        f"- {_n(full_filtered)} of them also fail the default track or status filters.",
        f"- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in, kept by "
        f"decision-038 (see Method); it is not Google Scholar's stemmer, which is undocumented. With every searched "
        f"word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → "
        f"`evaluat*`), {prefix} `full_text` papers would match title or abstract. That is all this figure "
        "measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) "
        "or rewrites the stem could move more.",
    ]
    if calls is not None and any(x.query_name == c.name and n in calls.calls for n, x in enumerate(review)):
        after = after_calls(c, review, calls)
        full_after, stem_after = after.scholar.get(FULL_TEXT, 0), after.scholar.get(STEMMING, 0)
        lines += [
            f"- **After the calls** (section Human calls, made as: {_roles(calls)}): {_n(full_after)} of "
            f"{_n(after.in_scope)} ({_pct(full_after, after.in_scope)}) `full_text`, {_n(stem_after)} "
            f"({_pct(stem_after, after.in_scope)}) `stemming`, {_n(after.both)} ({_pct(after.both, after.in_scope)}) "
            "in the exact result. The figures above this bullet are the automation's and are the ones to cite. "
            "Cite the after-calls figures only with those roles beside them, and as reviewed only if every role is "
            "an independent reviewer's.",
        ]
    return [*lines, ""]


_METHOD = """## Method

- **Order of the tests** (scholar-comparison-protocol). Only in the Scholar set: `our_bug`, `filtered`,
  `compat_reading`, `coverage_gap`, `stemming`, then `full_text`. Only in openproceedings: `our_bug`, `scholar_cap`,
  `compat_reading`, then `scholar_missed`. A record gets the first class whose test it passes, and a second cause
  is named in its evidence. The filters come before the text: a record that fails the default track or status
  filters and matches with them removed, as run, as Scholar reads the string or with an inflected form, is
  `filtered`, and its evidence says which (`also stemming`, `also compat_reading`).
- **Oracle.** Every class rests on `ReferenceEngine`, built over the compared records only: each matched paper of
  the Scholar set and each in-scope match of the served index. A wildcard (`$`, `*`) therefore expands over the
  compared records' vocabulary, not the snapshot's; for these records the matches are the same. `our_bug` counts
  every compared record on which the oracle and the served index disagree about the query as run. A record
  neither side holds is not compared, so a disagreement about one is outside this report (the differential suite
  covers it).
- **`compat_reading`.** The string is rewritten as Google Scholar reads it (`$` is no wildcard; an unquoted
  multi-word `|` item is separate words, with `|` binding tighter than juxtaposition) and run again. The evidence
  names the rewrite that decides the record.
- **`stemming`.** Each searched word also matches its other English inflections found in the compared records:
  plural or third-person `s`/`es`/`ies`, `ed`, `ing` (`eval.scholar_compare.inflection_stem`). Inflection only: no
  derivation (`trustworthy` is not a form of `trust`), and it over-pairs in places (`suite` with `suit`). Google
  Scholar's stemmer is undocumented, so this is a stated stand-in, not Scholar's rule; quoted words get forms too.
  A wider stemmer would move papers from `full_text` to `stemming`; each query's sensitivity line says how many
  would move if every word were replaced by its inflection stem read as a prefix, and nothing more than that.
  Decision-038 keeps this stand-in and adopts no published stemmer, because that figure is at or near zero for
  the review's strings; the `stemming` and `full_text` counts are relative to the stand-in, and the decision is
  revisited for any string whose sensitivity is not near zero.
- **`full_text`** is the residue: the record is in the corpus with an abstract, and the oracle confirms that no
  reading above matches its title or abstract. It may also fail the filters (counted under each finding). A
  record the corpus holds without an abstract is `unsettled`.
- **Provenance.** Each row says whether its index record has an independent source or only an imported RIS set
  (`crawled record`, `RIS-only record`), and `review.csv` carries it with the abstract's source.
- **`scholar_missed`** rows all go to `review.csv`: a reviewer confirms the exact tokens are in the title or abstract.
- **`coverage_gap`** rows all go to `review.csv` too: a record the corpus lacks and a record Scholar filed under
  the wrong venue or year look the same to the matching, so a reviewer checks each against the coverage report.
- **`review.csv`** also holds a spot check: a tenth of each query's settled disagreements, chosen by a hash of
  the row's ids. The tool never fills `human_class`: whoever makes a call writes it with their role in
  `reviewer_role`, and the Human calls section prints those roles beside every figure that rests on them. A call
  made by anyone but an independent reviewer (the analyst, or software acting for the project) is recorded
  like any other and leaves the verdict provisional.
"""


def render(
    meta: Meta,
    side: ScholarSide,
    index: MatchIndex,
    comparisons: Sequence[QueryComparison],
    review: Sequence[ReviewRow],
    calls: HumanCalls | None = None,
) -> str:
    """The report's Markdown. `calls` are the calls read back from the review file (`read_calls`)."""
    bugs = sum(c.our_bug for c in comparisons)
    unresolved = sum(x.kind == UNRESOLVED for x in review)
    matched = [e.match.op_id for e in side.entries if e.match.op_id is not None]
    own = sum(i not in index.independent for i in matched)
    others = [c.name for c in comparisons if meta.answers is not None and c.name != meta.answers]
    lines = [
        f"# Scholar comparison, {meta.date.isoformat()}",
        "",
        f"- Index: `index_version` `{meta.index_version}`, `tokenizer_version` `{meta.tokenizer_version}`",
        f"- Snapshot: `{meta.snapshot}`, `snapshot_hash` `{meta.snapshot_hash}` ({_n(meta.records)} records)",
        *(f"- Scholar set: `{f.name}`, sha256 `{f.sha256}` ({_n(f.records)} records)" for f in meta.ris),
        f"- Scope, both sides: {meta.scope.describe()}",
        "- Queries: " + ", ".join(f"`{c.name}`" for c in comparisons),
        *(f"- Query file: `{name}`, sha256 `{sha}`" for name, sha in meta.query_files),
        "- Notes: " + (f"`{meta.notes_name}`, sha256 `{meta.notes_sha256}`" if meta.notes_sha256 else "none"),
        f"- Command: `{meta.command}`",
        f"- Review rows: `{review_name(meta.date)}` ({_n(len(review))} rows; {_n(unresolved)} left for a call, "
        f"{_n(unresolved - _waiting(review, calls))} called)",
        "",
        f"**`our_bug`: {bugs}** across {len(comparisons)} quer{'y' if len(comparisons) == 1 else 'ies'}"
        + (
            "."
            if not bugs
            else ". Each one is a Must-fix with a golden case before this report is cited (spec 07 §Error handling)."
        ),
        "",
        f"**What the matches rest on.** Of the {_n(len(side.entries))} in-scope papers of the Scholar set, "
        f"{_n(len(matched))} match an index record: {_n(len(matched) - own)} a record with an independent source "
        f"(a crawl), {_n(own)} a record whose only source is an imported RIS set. A match of the second kind is the "
        "set matching its own import, and says nothing about coverage (see Matching).",
        "",
        "| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings "
        "| `full_text` | of them RIS-only | `stemming` | unresolved |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *(
            f"| `{c.name}`{' †' if c.name in others else ''} | {_n(c.scholar_in_scope)} | {_n(c.in_scope)} "
            f"| {_n(len(c.kept))} | {_n(len(c.only_scholar))} | {_n(len(c.added))} "
            f"| {_n(c.counts('scholar')[FULL_TEXT])} ({_pct(c.counts('scholar')[FULL_TEXT], c.scholar_in_scope)}) "
            f"| {_n(sum(r.auto_class == FULL_TEXT and r.independent is False for r in c.dropped))} "
            f"| {_n(c.counts('scholar')[STEMMING])} ({_pct(c.counts('scholar')[STEMMING], c.scholar_in_scope)}) "
            f"| {_n(sum(not r.settled for r in c.disagreements))} |"
            for c in comparisons
        ),
        "",
    ]
    if others:
        lines += [
            f"† The Scholar set is Google Scholar's answer to `{meta.answers}` only. For "
            + ", ".join(f"`{n}`" for n in others)
            + " the columns are what the string keeps, drops and adds against that same set, not a comparison with "
            "what Scholar returns for it.",
            "",
        ]
    lines += _matching(side, index, meta)
    for c in comparisons:
        lines += _query(c, review, meta, calls)
    lines += _human(comparisons, review, calls)
    lines += [_METHOD]
    if meta.notes:
        lines += ["## Notes on these inputs", "", meta.notes.strip(), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def report_name(day: date) -> str:
    return f"{day.isoformat()}-scholar-comparison.md"


def review_name(day: date) -> str:
    return f"{day.isoformat()}-scholar-comparison-review.csv"


def human_calls(review_file: Path) -> int:
    """How many rows of an existing review file have a call column filled (0 when there is no file). A file
    that is not UTF-8 counts as filled: it is never overwritten on a guess."""
    if not review_file.is_file():
        return 0
    try:
        text = review_file.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        return 1
    return sum(
        any((row.get(c) or "").strip() for c in HUMAN_COLUMNS) for row in csv.DictReader(io.StringIO(text))
    )


def write(
    text: str, review: str, out_dir: Path, day: date, *, keep_review: bool = False
) -> tuple[Path, Path, bool]:
    """The report and its review rows under `out_dir`, each written atomically; whether a report was replaced.
    With `keep_review` (the file there holds calls for exactly these rows: `read_calls`), only the
    report is written and the review file is left byte for byte. Otherwise ValueError, and nothing written,
    when the review file there already holds calls: a re-run never erases them."""
    path, rows = out_dir / report_name(day), out_dir / review_name(day)
    if keep_review:
        replaced = path.exists()
        storage.write_bytes(path, text.encode("utf-8"))
        return path, rows, replaced
    if filled := human_calls(rows):
        raise ValueError(
            f"{rows.name} holds {filled} filled row(s); move it, or write elsewhere (--out, --date)"
        )
    replaced = path.exists()
    storage.write_bytes(rows, review.encode("utf-8"))
    storage.write_bytes(path, text.encode("utf-8"))
    return path, rows, replaced
