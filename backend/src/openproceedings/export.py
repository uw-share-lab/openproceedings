"""Exports of a full matched set (spec 04 §Exports; task-030 for the CLI, task-036 for the API).

Each writer takes the engine's display records in id order (`TantivyEngine.documents`) and streams one
format to a text stream: nothing is paginated, truncated or held whole in memory. Every format carries its
provenance (`openproceedings <index_version> · query <canonical_hash> · exported <UTC date>`, plus
` · record <record_id> · searched <UTC date>` for an export pinned by a search record) and each record's
openproceedings id, so an export round-trips to the ids it came from.

- RIS (for Covidence): `TY  - CPAPER`, TI, AB, one AU per author, PY, T2 (the conference and that year's acronym), UR (forum,
  then pdf, then proceedings), DO, ID, KW (the track, then `status:<status>`), N1 (for a paper not accepted,
  first `Submitted to <venue>; status: <status in words> (not in its proceedings).`), N1 (`See also: <twin
  ids> (…)`, only for a record with a twin, TASK-162), N1 (`Abstract source: <site> <url>`, when the abstract
  has one; or the withheld sentence), N1 (provenance), ER. RIS is line-based, so line breaks inside a value
  become single spaces.
- CSV: the record fields of spec 01 plus `index_version`, `canonical_hash`, `exported_at`, `record_id` and
  `searched_at` (the last two empty unless pinned by a record), then `abstract_source`, `abstract_origin` and
  `abstract_url`, then `abstract_withheld` (`true`/`false`), then `abstract_withheld_reason` (`takedown`,
  `source_unavailable` or empty), then `twins` (the record's twins' ids, empty for most; TASK-162), UTF-8 with a
  BOM (Excel). Lists (authors, keywords, twins) are joined with "; ".
- BibTeX: `@inproceedings` for an accepted paper, `@unpublished` (no `booktitle`; `note` starts "Submitted to
  <venue>, status: <status in words>.") for any other; keyed `<first author's last name><year><first title
  word>` (ASCII, lower-case), a repeat key suffixed a, b, … (decision-007); `keywords` holds the track and
  `status:<status>`, `abstract_source` the abstract's source (`<site> <url>`), `abstract_withheld` the withheld
  sentence (only when withheld), `note` the provenance, `openproceedings_id` the id and `openproceedings_twins`
  its twins' ids (only for a record with a twin, TASK-162). Every `@` is written `{@}`.
- JSONL: one JSON object per record, with `index_version`, `canonical_hash`, `exported_at`, `record_id` and
  `searched_at` (null unless pinned by a record), `abstract_source` (`{source, origin, url}` or null),
  `abstract_withheld` (a boolean) and `abstract_withheld_reason` (`takedown`, `source_unavailable` or null), and
  `twins` (a list of ids) only on a record with a twin (TASK-162).

A record's twins (decision-029: an ICLR 2017 workshop copy and its conference submission, two records of one
paper, never merged) are the ids its `twin` claims name (`RecordFile.twins`, the same ones `GET /search` sends as
`twins`). A record without one exports byte for byte as before in RIS, BibTeX and JSONL; CSV, whose columns are
fixed, has one more column, empty for it.

The abstract's source (decision-018, TASK-138) is each record's `Attribution`, computed once per record when
the snapshot is loaded (`RecordFile.attributions`, the same one `GET /search` sends as `abstract_source`):
`entries` and `write` take that mapping, and a record the index holds but the mapping lacks is an internal
error, never an export without its attribution. `sources=None` means the attribution is unavailable (a pinned
index whose snapshot can't be verified, decision-021): every abstract is withheld (no RIS `AB`, no BibTeX
`abstract`, CSV/JSONL `abstract` empty/null, no source) and each record says so (`WITHHELD`: an RIS `N1`, a
BibTeX `abstract_withheld` field, CSV/JSONL `abstract_withheld` true). Only additions: no field, line or
column that existed before changed (decision-021; spec 04 §Exports). A record with no abstract, or none a
claim holds, names no source.

A takedown (TASK-136, decision-022): each record whose id is in `withheld` (the deployment's takedown list,
plus the ids the exported index's snapshot withheld) goes out the same way, marked withheld, its reason
`takedown` and its sentence `TAKEDOWN` (RIS `N1`, BibTeX `abstract_withheld`). A record both listed and in an
unattributable export says `takedown`.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TextIO

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.ingest.dedup import Attribution
from openproceedings.takedowns import NONE, Withheld
from openproceedings.vocab import venue_name

__all__ = [
    "CSV_COLUMNS", "FORMATS", "ORIGIN_NAMES", "SENTENCES", "TAKEDOWN", "WITHHELD", "WITHHELD_REASONS", "Provenance", "Sources", "Twins", "bibtex_key", "check_count",
    "credit", "entries", "header", "see_also", "utc_date", "write",
]  # fmt: skip

FORMATS = ("ris", "csv", "bibtex", "jsonl")
CSV_COLUMNS = (
    "id", "title", "abstract", "authors", "venue", "year", "track", "status", "presentation",
    "venue_id_raw", "forum", "pdf", "proceedings", "doi", "keywords", "index_version", "canonical_hash",
    "exported_at", "record_id", "searched_at", "abstract_source", "abstract_origin", "abstract_url",
    "abstract_withheld", "abstract_withheld_reason", "twins",
)  # fmt: skip
# (TASK-138's four abstract columns, then TASK-136's reason, then TASK-162's twins, are appended last: every
# earlier column keeps its position)
# each record id → its abstract's attribution (`RecordFile.attributions`, computed at snapshot load)
type Sources = Mapping[str, Attribution | None]
# each record id with a twin → its twins' ids (`RecordFile.twins`: its `twin` claims, decision-029, TASK-162)
type Twins = Mapping[str, tuple[str, ...]]
# the site that published an abstract, in words: the results list's names (`hit-item.tsx`'s ORIGIN_NAMES)
ORIGIN_NAMES = {
    "openreview": "OpenReview",
    "neurips_proceedings": "NeurIPS Proceedings",
    "iclr_proceedings": "ICLR Proceedings",
    "pmlr": "PMLR",
    "iclr_archive": "ICLR archive",
}
_SOURCE = "abstract_source"  # the key `entries` adds to each record it hands a writer
_WITHHELD = "abstract_withheld"  # likewise: True when the record's abstract is withheld
_REASON = "abstract_withheld_reason"  # likewise: why (`WITHHELD_REASONS`), None when it isn't
_TWINS = "twins"  # likewise: the record's twins' ids, () when it has none (TASK-162)

# what a record says when its abstract is withheld (decision-021): RIS `N1`, BibTeX `abstract_withheld`
WITHHELD = (
    "Abstract withheld: its source could not be attributed on this instance (the index's snapshot is "
    "unavailable), so no abstract is exported (decision-018)."
)
# what a record says when a takedown withholds its abstract (TASK-136, decision-022)
TAKEDOWN = (
    "Abstract withheld: removed from this site at a rights holder's request, so no abstract is exported "
    "(decision-022)."
)
# why an abstract is withheld (the CSV/JSONL `abstract_withheld_reason`) → what the record says: a takedown
# (TASK-136), or an export whose snapshot can't attribute it (decision-021)
SENTENCES = {"takedown": TAKEDOWN, "source_unavailable": WITHHELD}
WITHHELD_REASONS = tuple(SENTENCES)


def see_also(twins: tuple[str, ...]) -> str:
    """What a record with twins says of them (RIS `N1`; TASK-162): the same paper's other OpenReview record or
    records (decision-029: an ICLR 2017 workshop copy and its conference submission, never merged)."""
    other = "other record" if len(twins) == 1 else "other records"
    return f"See also: {'; '.join(twins)} (the same paper's {other} on OpenReview, decision-029)."


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where an export came from. `record_id` and `searched_at` (the record's, UTC ISO 8601) are set together,
    only for an export pinned by a search record (`GET /export?record_id=`)."""

    index_version: str
    canonical_hash: str
    date: str  # the UTC date of the export, YYYY-MM-DD
    record_id: str | None = None
    searched_at: str | None = None

    def __post_init__(self) -> None:
        if (self.record_id is None) != (self.searched_at is None):
            raise ValueError("a record-pinned export names both record_id and searched_at")

    def line(self) -> str:
        line = f"openproceedings {self.index_version} · query {self.canonical_hash} · exported {self.date}"
        if self.record_id is not None and self.searched_at is not None:
            line += f" · record {self.record_id} · searched {self.searched_at[:10]}"
        return line


def check_count(written: int, total: int) -> None:
    """An export wrote exactly the `total` records its query matched, or it failed: EngineInternalError, never
    a silently shorter or longer file (`op export` and `GET /export` both end with it)."""
    if written != total:
        raise EngineInternalError(
            DiagnosticCode.API_INTERNAL, f"exported {written} records, but {total} match"
        )


def utc_date() -> str:
    """Today's UTC date, YYYY-MM-DD: an export's provenance date (`op export` and `GET /export` both)."""
    return datetime.now(UTC).date().isoformat()


def header(fmt: str) -> str:
    """What `fmt` writes before its first record: CSV's BOM (so Excel reads UTF-8) and column row."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format {fmt!r}")
    return "\ufeff" + _csv_row(CSV_COLUMNS) if fmt == "csv" else ""


def entries(
    fmt: str,
    records: Iterable[dict[str, Any]],
    provenance: Provenance,
    *,
    sources: Sources | None,
    withheld: Withheld = NONE,
    twins: Twins | None = None,
) -> Iterator[str]:
    """One string per record of `records`, as `fmt` writes it (after `header(fmt)`), each naming its abstract's
    source from `sources` (the snapshot's `RecordFile.attributions`); `None` withholds every abstract, each
    record saying so (the attribution is unavailable, decision-021). Each record whose id is in `withheld` (a
    takedown, TASK-136) goes out without its abstract, saying so. Each record `twins` holds names its twins
    (TASK-162); `None` (the snapshot can't be verified) names none."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format {fmt!r}")
    writer = {"ris": _ris, "csv": _csv, "bibtex": _bibtex, "jsonl": _jsonl}[fmt]
    return writer(_attributed(records, sources, withheld, twins or {}), provenance)


def _attributed(
    records: Iterable[dict[str, Any]], sources: Sources | None, withheld: Withheld, twins: Twins
) -> Iterator[dict[str, Any]]:
    """Each record with its abstract's attribution under `abstract_source`. A record `sources` doesn't hold is
    an invariant broken (the index and its snapshot disagree): EngineInternalError, as on `GET /search`.
    Without `sources`, each record's abstract is dropped and it is marked withheld; so is a record `withheld`
    lists, whatever `sources` says (its reason `takedown`)."""
    for r in records:
        if sources is not None and r["id"] not in sources:  # checked for every record, withheld or not
            raise EngineInternalError(
                DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
            )
        linked = twins.get(r["id"], ())
        if r["id"] in withheld:
            yield {**r, "abstract": None, _SOURCE: None, _WITHHELD: True, _REASON: "takedown", _TWINS: linked}
        elif sources is None:
            yield {**r, "abstract": None, _SOURCE: None, _WITHHELD: True, _REASON: "source_unavailable",
                   _TWINS: linked}  # fmt: skip
        else:
            yield {**r, _SOURCE: sources[r["id"]], _WITHHELD: False, _REASON: None, _TWINS: linked}


def write(
    fmt: str,
    records: Iterable[dict[str, Any]],
    provenance: Provenance,
    out: TextIO,
    *,
    sources: Sources | None,
    withheld: Withheld = NONE,
    twins: Twins | None = None,
) -> int:
    """Stream `records` to `out` as `fmt`; the number written. `op export` writes a file or stdout with
    it; `GET /api/v1/export` streams the same `header` and `entries`, so both give the same bytes."""
    out.write(header(fmt))
    n = 0
    for chunk in entries(fmt, records, provenance, sources=sources, withheld=withheld, twins=twins):
        out.write(chunk)
        n += 1
    return n


def _status(r: dict[str, Any]) -> str:
    """The record's status; a record without one is treated as `unknown`, never as accepted."""
    return r.get("status") or "unknown"


def _status_words(status: str) -> str:
    """A status as a sentence reads it (`desk_rejected` → `desk rejected`); keywords keep the machine form."""
    return status.replace("_", " ")


def _not_accepted(venue: str, status: str) -> str:
    """RIS's first `N1` for a paper that was not accepted: the venue it was submitted to, and that it is not in
    that venue's proceedings (for `unknown`, not known to be)."""
    where = "not known to be in its proceedings" if status == "unknown" else "not in its proceedings"
    return f"Submitted to {venue}; status: {_status_words(status)} ({where})."


def _credit_of(r: dict[str, Any]) -> Attribution | None:
    """The record's abstract attribution (`entries` put it there), None when it has no abstract to credit."""
    found: Attribution | None = r.get(_SOURCE)
    return found if r.get("abstract") else None


def credit(a: Attribution) -> str:
    """An abstract's source in words, as the results list names it (`hit-item.tsx`'s `attributionText`): the
    site (`PMLR`), ` (via RIS import)` when the claim came through an imported RIS file, then its page's url
    when it has one: `PMLR https://proceedings.mlr.press/v202/okafor23a.html`. A route that names no known
    site is `an imported RIS file` (or the claim's source as it came)."""
    text: str
    if a.origin is None:
        text = "an imported RIS file" if a.source == "ris" else a.source
    else:
        text = ORIGIN_NAMES.get(a.origin, a.origin) + (" (via RIS import)" if a.source == "ris" else "")
    return _one_line(f"{text} {a.url}" if a.url else text)


def _one_line(text: str) -> str:
    """One line: whitespace runs (line breaks included) become one space; control characters go."""
    return " ".join(_printable(text).split())


# the control characters (Unicode Cc) that aren't whitespace: \t \n \v \f \r, \x1c-\x1f and \x85 are
# `str.isspace`, so they stay (one regex pass: a per-character generator was ~60% of an export's CPU)
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1b\x7f-\x84\x86-\x9f]")


def _printable(text: str) -> str:
    """`text` without its non-whitespace control characters (equal, on every code point, to keeping `ch`
    when `ch.isspace() or unicodedata.category(ch) != "Cc"`; pinned by an exhaustive test)."""
    return _CONTROL.sub("", text)


def _urls(r: dict[str, Any]) -> list[str]:
    urls = r.get("urls") or {}
    return [urls[k] for k in ("forum", "pdf", "proceedings") if urls.get(k)]


def _ris(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    for r in records:
        lines = [("TY", "CPAPER"), ("TI", _one_line(r["title"]))]
        if r.get("abstract"):
            lines.append(("AB", _one_line(r["abstract"])))
        lines += [("AU", _one_line(a)) for a in r.get("authors", [])]
        lines += [("PY", str(r["year"])), ("T2", venue_name(r["venue"], r["year"]))]
        lines += [("UR", _one_line(u)) for u in _urls(r)]  # validated at ingest; one line here regardless
        if (r.get("urls") or {}).get("doi"):
            lines.append(("DO", _one_line(r["urls"]["doi"])))
        status = _status(r)
        lines += [("ID", r["id"]), ("KW", r["track"]), ("KW", f"status:{status}")]
        if status != "accepted":
            lines.append(("N1", _not_accepted(venue_name(r["venue"], r["year"]), status)))
        if r.get(_TWINS):  # after the status sentence, before the abstract's line (TASK-162)
            lines.append(("N1", see_also(r[_TWINS])))
        if (source := _credit_of(r)) is not None:  # after the status sentence, before the provenance line
            lines.append(("N1", f"Abstract source: {credit(source)}"))
        elif r.get(_WITHHELD):
            lines.append(("N1", SENTENCES[r[_REASON]]))
        lines.append(("N1", p.line()))
        yield "".join(f"{tag}  - {value}\n" for tag, value in lines) + "ER  - \n\n"


def _csv_row(values: Iterable[object]) -> str:
    buffer = _Line()
    csv.writer(buffer, lineterminator="\r\n").writerow(values)
    return buffer.take()


def _csv(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    for r in records:
        urls = r.get("urls") or {}
        source = _credit_of(r)
        row = {
            **{k: r.get(k) for k in ("id", "title", "abstract", "venue", "year", "track", "status")},
            **{k: r.get(k) for k in ("presentation", "venue_id_raw")},
            **{k: urls.get(k) for k in ("forum", "pdf", "proceedings", "doi")},
            "authors": "; ".join(r.get("authors", [])),
            "keywords": "; ".join(r.get("keywords", [])),
            "index_version": p.index_version,
            "canonical_hash": p.canonical_hash,
            "exported_at": p.date,
            "record_id": p.record_id,
            "searched_at": p.searched_at,
            "abstract_source": source.source if source else None,
            "abstract_origin": source.origin if source else None,
            "abstract_url": source.url if source else None,
            "abstract_withheld": "true" if r.get(_WITHHELD) else "false",
            "abstract_withheld_reason": r.get(_REASON),
            "twins": "; ".join(r.get(_TWINS) or ()),
        }
        yield _csv_row(csv_cell(row[c]) for c in CSV_COLUMNS)


def csv_cell(value: object) -> object:
    """A CSV cell a spreadsheet won't run: text starting with `=`, `+`, `-`, `@`, a tab or a carriage return
    is prefixed with `'` (OWASP's CSV-injection guard; titles and abstracts come from anyone)."""
    if value is None:
        return ""
    if isinstance(value, str):
        value = _printable(value)
        head = unicodedata.normalize("NFKC", value.lstrip()[:1])  # full-width `＝` and ` =` too
        if head in ("=", "+", "-", "@") or value[:1] in ("\t", "\r"):
            return "'" + value
    return value


class _Line:
    """A write target for csv.writer that hands back each row as it's written."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, s: str) -> int:
        self.parts.append(s)
        return len(s)

    def take(self) -> str:
        out, self.parts = "".join(self.parts), []
        return out


# letters NFKD doesn't decompose into ASCII (`Ørsted` → `orsted`, not `rsted`)
_LETTERS = str.maketrans({"ø": "o", "Ø": "O", "ß": "ss", "ł": "l", "Ł": "L", "æ": "ae", "Æ": "AE",
                          "œ": "oe", "Œ": "OE", "đ": "d", "Đ": "D", "ð": "d", "þ": "th", "ı": "i"})  # fmt: skip


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text.translate(_LETTERS)).encode("ascii", "ignore").decode().lower()


def _family(name: str) -> str:
    """The family name: before the comma in "Family, Given" (how every stored author is written), else the
    last word ("Given Family")."""
    return name.split(",", 1)[0] if "," in name else name.split()[-1]


def bibtex_key(r: dict[str, Any]) -> str:
    """`<first author's family name><year><first title word>`, ASCII and lower-case; the title word is the first
    run of letters and digits (`=HYPERLINK("…")` gives `hyperlink`)."""
    authors = [a for a in r.get("authors") or [] if a.split()]
    last = re.sub(r"[^a-z0-9]", "", _ascii(_family(authors[0]))) if authors else ""
    word = re.search(r"[a-z0-9]+", _ascii(r["title"]))
    return f"{last or 'anon'}{r['year']}{word.group() if word else 'untitled'}"


_BRACE = re.compile(r"(\\*)[{}]")  # a brace and the backslash run before it


def _balances(text: str, *, escaped_count: bool) -> bool:
    """Do the braces nest? Counted as BibTeX does (every brace, `escaped_count`) or as parsers that honour
    `\\{` do (escaped ones skipped). A value is kept as written only when both agree it nests, and never when
    a brace follows two or more backslashes (`\\\\{`), which readers disagree on (bibtexparser 2 reads it as
    escaped)."""
    if "{" not in text and "}" not in text:
        return True  # most values: nothing to count (the loop below would find nothing and say so)
    depth = 0
    for m in _BRACE.finditer(text):
        if len(m.group(1)) >= 2:
            return False
        if not escaped_count and len(m.group(1)) % 2 == 1:
            continue
        depth += 1 if text[m.end() - 1] == "{" else -1
        if depth < 0:
            return False
    return depth == 0


def _debraced(text: str) -> str:
    """`text` with every brace dropped, and the backslash that escaped one, so no `\\x` command is left."""
    return _one_line(_BRACE.sub(lambda m: m.group(1)[: len(m.group(1)) // 2 * 2], _one_line(text)))


# a special character and the whole backslash run before it (the match starts at the run's first backslash,
# `\\*` being greedy); an even run (or none) leaves the character bare, so it is escaped
_SPECIAL = re.compile(r"(\\*)([&%#])")
_AT = re.compile(r"(\\*)@")  # an `@` and the backslash run before it
_BARE_UNDERSCORE = re.compile(r"(?<!\\)_")


def _braced(text: str) -> str:
    """A BibTeX `{…}` value every parser reads the same way. Braces stay when they balance and none is
    escaped (LaTeX such as `{BERT}` keeps its meaning); otherwise they are dropped, since BibTeX counts braces
    without regard to backslashes while other parsers honour `\\{`, and an entry that one reads differently
    can swallow the next. `&`, `%` and `#` are escaped (they break LaTeX and BibTeX); `$…$` math stays. Every
    `@` is written `{@}`: BibTeX and refaudit start an entry at a bare `@` wherever it stands, so
    `@article{x,` in a title would become an entry of its own. An odd backslash run before it loses one
    backslash (as `_debraced` does before a brace), so the added brace is never escaped. A value never ends
    on a backslash, which would escape the closing brace."""
    text = _one_line(text)
    if not (_balances(text, escaped_count=True) and _balances(text, escaped_count=False)):
        text = _debraced(text)
    # each pass only when its character occurs (most values have none): the same output, a fraction of the CPU
    if "&" in text or "%" in text or "#" in text:
        text = _SPECIAL.sub(_escape_special, text)  # `&` → `\&`, `\\&` → `\\\&`, `\&` stays
    if "@" in text:
        text = _AT.sub(lambda m: m.group(1)[: len(m.group(1)) // 2 * 2] + "{@}", text)
    if text.endswith("\\"):
        text += " "
    return "{" + text + "}"


def _escape_special(m: re.Match[str]) -> str:
    """`&`, `%` or `#` after an even backslash run (or none) gets one more backslash; after an odd run it is
    already escaped and stays."""
    run, char = m.group(1), m.group(2)
    return m.group(0) if len(run) % 2 else run + "\\" + char


def _bibtex(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    issued: set[str] = set()  # every key given out, so a suffixed key never meets a real one
    for r in records:
        base = key = bibtex_key(r)
        n = 0
        while key in issued:
            key, n = base + _suffix(n), n + 1
        issued.add(key)
        fields = [("title", _braced(r["title"]))]
        # each name brace-free before it's protected, so one stray brace can't unbrace the others
        # (and no trailing backslash, which would escape the brace `_name` may close it with)
        names = [_name(n) for n in (_debraced(a).rstrip("\\ ") for a in r.get("authors") or []) if n]
        if names:
            fields.append(("author", _braced(" and ".join(names))))
        # only an accepted paper is cited as in its conference; any other status (rejected, withdrawn,
        # desk-rejected, unknown) is `@unpublished`, the venue string moved into `note` (spec 04 §Exports)
        status, venue = _status(r), venue_name(r["venue"], r["year"])
        accepted = status == "accepted"
        if accepted:
            fields.append(("booktitle", _braced(venue)))
        fields.append(("year", str(r["year"])))
        if r.get("abstract"):
            fields.append(("abstract", _braced(r["abstract"])))
        if (source := _credit_of(r)) is not None:
            fields.append(("abstract_source", _braced(credit(source))))
        elif r.get(_WITHHELD):
            fields.append(("abstract_withheld", _braced(SENTENCES[r[_REASON]])))
        urls = _urls(r)
        if urls:
            fields.append(("url", _braced(urls[0])))
        if (r.get("urls") or {}).get("doi"):
            fields.append(("doi", _braced(r["urls"]["doi"])))
        fields.append(("keywords", _braced(", ".join(k for k in (r.get("track"), f"status:{status}") if k))))
        note = p.line() if accepted else f"Submitted to {venue}, status: {_status_words(status)}. {p.line()}"
        # a styled `note` is typeset: a record id's `_` would be a subscript outside math, so it is escaped
        fields += [
            ("note", _braced(_BARE_UNDERSCORE.sub(r"\\_", note))),
            ("openproceedings_id", _braced(r["id"])),
        ]
        if r.get(_TWINS):  # the twins' ids, as `openproceedings_id` names this one (TASK-162)
            fields.append(("openproceedings_twins", _braced("; ".join(r[_TWINS]))))
        body = ",\n".join(f"  {name} = {value}" for name, value in fields)
        yield f"@{'inproceedings' if accepted else 'unpublished'}{{{key},\n{body}\n}}\n\n"


def _name(author: str) -> str:
    """An author (brace-free, from `_debraced`) as BibTeX's name list reads one: a name that holds a
    standalone `and`, or is `others`, is braced so it isn't split into two people or read as et al."""
    if re.search(r"(?i)\band\b", author) or author.strip().lower() == "others":
        return "{" + author + "}"
    return author


def _suffix(n: int) -> str:
    """a, b, …, z, aa, ab, … for the second, third, … use of a key."""
    letters = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def _jsonl(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    for r in records:
        source = _credit_of(r)
        row = {
            **{k: v for k, v in r.items() if k != _TWINS},
            **({_TWINS: list(r[_TWINS])} if r.get(_TWINS) else {}),  # only on a record with a twin (TASK-162)
            _SOURCE: None
            if source is None
            else {"source": source.source, "origin": source.origin, "url": source.url},
            _WITHHELD: bool(r.get(_WITHHELD)),
            _REASON: r.get(_REASON),
            "index_version": p.index_version,
            "canonical_hash": p.canonical_hash,
            "exported_at": p.date,
            "record_id": p.record_id,
            "searched_at": p.searched_at,
        }
        text = json.dumps(row, ensure_ascii=False, sort_keys=True)
        # characters `str.splitlines()` breaks on, escaped so a record stays one line for every reader
        yield text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("\x85", "\\u0085") + "\n"
