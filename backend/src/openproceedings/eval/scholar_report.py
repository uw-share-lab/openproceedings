"""The Scholar comparison report (spec 07 §B, scholar-comparison-protocol skill; TASK-056): `op eval scholar`
writes `docs/results/<YYYY-MM-DD>-scholar-comparison.md` and, next to it, `<YYYY-MM-DD>-scholar-comparison-review.csv`
(the protocol's `review.csv`, dated like the report so a later run doesn't replace an earlier one's human calls).

Everything counted here comes from `scholar_compare`: this module only chooses the review rows, renders and
writes. A figure in the report is a count of rows of one run; nothing is typed in. Prose that belongs to one
set of inputs (why this export, what its searches returned) is read from a notes file and printed verbatim
under its sha256, as the coverage report reads its cause notes.

`review.csv` holds every row the automation couldn't settle, plus a tenth of each query's settled disagreements
as a spot check. The tenth is the rows whose sha256 (of query name, side and ids) sorts first: fixed for a
given run, unrelated to any field, and the same on every machine, so the file is reproducible. `human_class`,
`reviewer_role` and `note` are left empty for a person.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from collections.abc import Sequence
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
from openproceedings.export import _cell as csv_cell  # the one CSV-injection guard: titles come from anyone

SPOT_CHECK = 0.1  # the share of a query's settled disagreements a person re-checks
REVIEW_COLUMNS = (
    "query_name", "side", "scholar_key", "op_id", "title", "venue", "year", "auto_class", "auto_evidence",
    "human_class", "reviewer_role", "note", "row_kind", "index_version",
)  # fmt: skip
UNRESOLVED, SPOT = "unresolved", "spot_check"
_MEANING = {
    OUR_BUG: "the oracle and the served engine disagree (must be 0)",
    FILTERED: "in the corpus; matches once the default track and status filters are removed",
    COMPAT_READING: "decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus",
    COVERAGE_GAP: "no record in the snapshot by forum id, proceedings id or title+venue+year",
    STEMMING: "matches title or abstract only with an inflected form added",
    FULL_TEXT: "in the corpus; no reading matches its title or abstract, inflected forms included",
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
    """`review.csv`: the protocol's twelve columns, then `row_kind` (why the row is here) and `index_version`."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(REVIEW_COLUMNS)
    for x in rows:
        r = x.row
        cells = (
            x.query_name, r.side, r.scholar_key, r.op_id, r.title, r.venue, "" if r.year is None else r.year,
            r.auto_class, r.auto_evidence, "", "", "", x.kind, index_version,
        )  # fmt: skip
        writer.writerow(csv_cell(c) for c in cells)
    return buffer.getvalue()


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


def _n(k: int) -> str:
    return f"{k:,}"


def _pct(part: int, whole: int) -> str:
    return "—" if not whole else f"{100 * part / whole:.1f}%"


def _md(text: str) -> str:
    """Text for a Markdown table cell: one line, no cell break."""
    return " ".join(text.split()).replace("|", "\\|")


def _class_table(counts: Counter[str], order: Sequence[str], of: int, of_label: str) -> list[str]:
    total = sum(counts.values())
    lines = [f"| class | records | of these | of {of_label} | meaning |", "|---|---|---|---|---|"]
    lines += [
        f"| `{cls}` | {_n(counts[cls])} | {_pct(counts[cls], total)} | {_pct(counts[cls], of)} | {_MEANING[cls]} |"
        for cls in order
        if counts[cls] or cls == OUR_BUG
    ]
    lines.append(f"| total | {_n(total)} | {_pct(total, total)} | {_pct(total, of)} | |")
    return lines


def _row_list(rows: Sequence[Row]) -> list[str]:
    lines = ["| record | title | venue | year | class | evidence |", "|---|---|---|---|---|---|"]
    lines += [
        f"| `{r.op_id or r.scholar_key}` | {_md(r.title)} | {_md(r.venue)} | {r.year or '—'} | `{r.auto_class}` "
        f"| {_md(r.auto_evidence)} |"
        for r in rows
    ]
    return lines


def _matching(side: ScholarSide, index: MatchIndex, meta: Meta) -> list[str]:
    rules = Counter((e.match.rule or f"no match ({e.match.problem})").replace("_", " ") for e in side.entries)
    reasons = Counter(d.reason for d in side.out_of_scope)
    largest = max(side.searches.values(), default=0)
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
        f"| **papers in scope** | **{_n(len(side.entries))}** |",
        "",
        "| matched by | papers |",
        "|---|---|",
        *(f"| {rule} | {_n(k)} |" for rule, k in sorted(rules.items(), key=lambda x: (-x[1], x[0]))),
        "",
    ]  # fmt: skip
    if reasons:
        by_venue = Counter(d.record.venue_raw or "(no venue)" for d in side.out_of_scope)
        lines += [
            "Outside the scope: "
            + "; ".join(f"{_n(k)} {reason.replace('_', ' ')}" for reason, k in sorted(reasons.items()))
            + ". `venue unrecognised` means the record's venue string is not exactly one of Scholar mode's source "
            "names (Scholar cuts long venue names with `…`) and no URL of it names an indexed paper. Venue strings: "
            + "; ".join(f"{_md(v)} ({k})" for v, k in sorted(by_venue.items(), key=lambda x: (-x[1], x[0])))
            + ".",
            "",
        ]
    near = [d for d in side.out_of_scope if d.near]
    if near:
        lines += [
            f"{_n(len(near))} of them share a title key with an in-scope index record. That is never a match "
            "(no venue to check it against); a person may want to look:",
            "",
            "| Scholar record | title | venue string | year | index record with that title |",
            "|---|---|---|---|---|",
            *(
                f"| `{d.record.key}` | {_md(d.record.title)} | {_md(d.record.venue_raw) or '—'} "
                f"| {d.record.year or '—'} | "
                + ", ".join(f"`{i}` ({index.cells[i][0]} {index.cells[i][1]})" for i in d.near)
                + " |"
                for d in near
            ),
            "",
        ]
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


def _query(c: QueryComparison, review: Sequence[ReviewRow]) -> list[str]:
    only = c.counts("scholar")
    extra = c.counts("openproceedings")
    unresolved = sum(x.query_name == c.name and x.kind == UNRESOLVED for x in review)
    spot = sum(x.query_name == c.name and x.kind == SPOT for x in review)
    lines = [
        f"## Query `{c.name}`",
        "",
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
    lines += [
        "| | records |",
        "|---|---|",
        f"| Scholar set, in scope | {_n(c.scholar_in_scope)} |",
        f"| openproceedings `total` (default filters; every venue and year) | {_n(c.total)} |",
        f"| openproceedings, in scope | {_n(c.in_scope)} |",
        f"| in both | {_n(len(c.kept))} |",
        f"| only in the Scholar set | {_n(len(c.only_scholar))} |",
        f"| only in openproceedings | {_n(len(c.added))} |",
        "",
        "### Only in the Scholar set",
        "",
        *_class_table(only, ONLY_SCHOLAR, c.scholar_in_scope, "the Scholar set"),
        "",
        "### Only in openproceedings",
        "",
        *_class_table(extra, ONLY_OP, c.in_scope, "the result"),
        "",
        f"`our_bug`: **{c.our_bug}**. Rows for a person in `review.csv`: {_n(unresolved)} unresolved, {_n(spot)} "
        "spot check.",
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
    full, stem = only[FULL_TEXT], only[STEMMING]
    lines += [
        f"**Finding.** Of the {_n(c.scholar_in_scope)} in-scope papers of the Scholar set, {_n(full)} "
        f"({_pct(full, c.scholar_in_scope)}) match this string nowhere in title or abstract, inflected forms "
        f"included (`full_text`), and {_n(stem)} ({_pct(stem, c.scholar_in_scope)}) match only through an inflected "
        f"form (`stemming`). {_n(len(c.kept))} ({_pct(len(c.kept), c.scholar_in_scope)}) are in the exact result.",
        "",
    ]
    return lines


_METHOD = """## Method

- **Order of the tests** (scholar-comparison-protocol). Only in the Scholar set: `our_bug`, `filtered`,
  `compat_reading`, `coverage_gap`, `stemming`, then `full_text`. Only in openproceedings: `our_bug`, `scholar_cap`,
  `compat_reading`, then `scholar_missed`. A record gets the first class whose test it passes; a second cause is
  named in its evidence (`also filtered`).
- **Oracle.** Every class rests on `ReferenceEngine`, built over the compared records: each matched paper of the
  Scholar set and each in-scope match of the served index. `our_bug` counts every compared record on which the
  oracle and the served index disagree about the query as run.
- **`compat_reading`.** The string is rewritten as Google Scholar reads it (`$` is no wildcard; an unquoted
  multi-word `|` item is separate words, with `|` binding tighter than juxtaposition) and run again. The evidence
  names the rewrite that decides the record.
- **`stemming`.** Each searched word also matches its other English inflections found in the compared records:
  plural or third-person `s`/`es`/`ies`, `ed`, `ing` (`eval.scholar_compare.inflection_stem`). Inflection only: no
  derivation (`trustworthy` is not a form of `trust`). Google Scholar's stemmer is undocumented, so this is a
  stated stand-in; it errs towards `stemming` (it pairs `suite` with `suit`), which keeps `full_text` a lower
  bound. Quoted words get forms too, for the same reason.
- **`full_text`** is the residue: the record is in the corpus with an abstract, and the oracle confirms that no
  reading above matches its title or abstract. A record the corpus holds without an abstract is `unsettled`.
- **`scholar_missed`** rows all go to `review.csv`: a person confirms the exact tokens are in the title or abstract.
- **`coverage_gap`** rows all go to `review.csv` too: a record the corpus lacks and a record Scholar filed under
  the wrong venue or year look the same to the matching, so a person checks each against the coverage report.
- **`review.csv`** also holds a spot check: a tenth of each query's settled disagreements, chosen by a hash of
  the row's ids. `human_class` is filled by a person, never by the analyst.
"""


def render(
    meta: Meta,
    side: ScholarSide,
    index: MatchIndex,
    comparisons: Sequence[QueryComparison],
    review: Sequence[ReviewRow],
) -> str:
    """The report's Markdown."""
    bugs = sum(c.our_bug for c in comparisons)
    unresolved = sum(x.kind == UNRESOLVED for x in review)
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
        f"- Review rows: `{review_name(meta.date)}` ({_n(len(review))} rows, {_n(unresolved)} unresolved)",
        "",
        f"**`our_bug`: {bugs}** across {len(comparisons)} quer{'y' if len(comparisons) == 1 else 'ies'}"
        + (
            "."
            if not bugs
            else ". Each one is a Must-fix with a golden case before this report is cited (spec 07 §Error handling)."
        ),
        "",
        "| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings "
        "| `full_text` | `stemming` | unresolved |",
        "|---|---|---|---|---|---|---|---|---|",
        *(
            f"| `{c.name}` | {_n(c.scholar_in_scope)} | {_n(c.in_scope)} | {_n(len(c.kept))} "
            f"| {_n(len(c.only_scholar))} | {_n(len(c.added))} "
            f"| {_n(c.counts('scholar')[FULL_TEXT])} ({_pct(c.counts('scholar')[FULL_TEXT], c.scholar_in_scope)}) "
            f"| {_n(c.counts('scholar')[STEMMING])} ({_pct(c.counts('scholar')[STEMMING], c.scholar_in_scope)}) "
            f"| {_n(sum(not r.settled for r in c.disagreements))} |"
            for c in comparisons
        ),
        "",
        *_matching(side, index, meta),
    ]
    for c in comparisons:
        lines += _query(c, review)
    lines += [_METHOD]
    if meta.notes:
        lines += ["## Notes on these inputs", "", meta.notes.strip(), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def report_name(day: date) -> str:
    return f"{day.isoformat()}-scholar-comparison.md"


def review_name(day: date) -> str:
    return f"{day.isoformat()}-scholar-comparison-review.csv"


def human_calls(review_file: Path) -> int:
    """How many rows of an existing review file a person has filled in (0 when there is no file)."""
    if not review_file.is_file():
        return 0
    with review_file.open(encoding="utf-8", newline="") as fh:
        return sum(
            any(row.get(c) for c in ("human_class", "reviewer_role", "note")) for row in csv.DictReader(fh)
        )


def write(text: str, review: str, out_dir: Path, day: date) -> tuple[Path, Path, bool]:
    """The report and its review rows under `out_dir`, each written atomically; whether a report was replaced.
    ValueError, and nothing written, when the review file there already holds a person's calls: a re-run never
    erases them."""
    path, rows = out_dir / report_name(day), out_dir / review_name(day)
    if filled := human_calls(rows):
        raise ValueError(
            f"{rows.name} holds {filled} row(s) a person filled in; move it, or write elsewhere (--out, --date)"
        )
    replaced = path.exists()
    storage.write_bytes(rows, review.encode("utf-8"))
    storage.write_bytes(path, text.encode("utf-8"))
    return path, rows, replaced
