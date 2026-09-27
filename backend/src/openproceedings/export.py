"""Exports of a full matched set (spec 04 §Exports; task-030 for the CLI, task-036 for the API).

Each writer takes the engine's display records in id order (`TantivyEngine.documents`) and streams one
format to a text stream: nothing is paginated, truncated or held whole in memory. Every format carries its
provenance (`openproceedings <index_version> · query <canonical_hash> · <UTC date>`) and each record's
openproceedings id, so an export round-trips to the ids it came from.

- RIS (for Covidence): `TY  - CPAPER`, TI, AB, one AU per author, PY, T2 (the conference and that year's acronym), UR (forum,
  then pdf, then proceedings), DO, ID, KW (the track, then `status:<status>`), N1 (provenance), ER. RIS is
  line-based, so line breaks inside a value become single spaces.
- CSV: the record fields of spec 01 plus `index_version`, `canonical_hash` and `exported_at`, UTF-8 with a BOM (Excel).
  Lists (authors, keywords) are joined with "; ".
- BibTeX: `@inproceedings` for an accepted paper, `@unpublished` (no `booktitle`; `note` starts "Submitted to
  <venue>, status: <status>.") for any other; keyed `<first author's last name><year><first title word>`
  (ASCII, lower-case), a repeat key suffixed a, b, … (decision-007); `keywords` holds the track and
  `status:<status>`, `note` the provenance and `openproceedings_id` the id.
- JSONL: one JSON object per record, with `index_version`, `canonical_hash` and `exported_at`.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, TextIO

from openproceedings.vocab import CONFERENCES, venue_name

__all__ = ["CONFERENCES", "CSV_COLUMNS", "FORMATS", "Provenance", "bibtex_key", "venue_name", "write"]

FORMATS = ("ris", "csv", "bibtex", "jsonl")
CSV_COLUMNS = (
    "id", "title", "abstract", "authors", "venue", "year", "track", "status", "presentation",
    "venue_id_raw", "forum", "pdf", "proceedings", "doi", "keywords", "index_version", "canonical_hash",
    "exported_at",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Provenance:
    index_version: str
    canonical_hash: str
    date: str  # the UTC date of the export, YYYY-MM-DD

    def line(self) -> str:
        return f"openproceedings {self.index_version} · query {self.canonical_hash} · {self.date}"


def write(fmt: str, records: Iterable[dict[str, Any]], provenance: Provenance, out: TextIO) -> int:
    """Stream `records` to `out` as `fmt`; the number written. Each writer yields one string per record."""
    header, writer = {
        "ris": ("", _ris),
        "csv": ("\ufeff" + _csv_row(CSV_COLUMNS), _csv),  # the BOM, so Excel reads UTF-8
        "bibtex": ("", _bibtex),
        "jsonl": ("", _jsonl),
    }[fmt]
    out.write(header)
    n = 0
    for chunk in writer(records, provenance):
        out.write(chunk)
        n += 1
    return n


def _status(r: dict[str, Any]) -> str:
    """The record's status; a record without one is treated as `unknown`, never as accepted."""
    return r.get("status") or "unknown"


def _one_line(text: str) -> str:
    """One line: whitespace runs (line breaks included) become one space; control characters go."""
    return " ".join(_printable(text).split())


def _printable(text: str) -> str:
    return "".join(ch for ch in text if ch.isspace() or unicodedata.category(ch) != "Cc")


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
        lines += [("ID", r["id"]), ("KW", r["track"]), ("KW", f"status:{_status(r)}"), ("N1", p.line())]
        yield "".join(f"{tag}  - {value}\n" for tag, value in lines) + "ER  - \n\n"


def _csv_row(values: Iterable[object]) -> str:
    buffer = _Line()
    csv.writer(buffer, lineterminator="\r\n").writerow(values)
    return buffer.take()


def _csv(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    for r in records:
        urls = r.get("urls") or {}
        row = {
            **{k: r.get(k) for k in ("id", "title", "abstract", "venue", "year", "track", "status")},
            **{k: r.get(k) for k in ("presentation", "venue_id_raw")},
            **{k: urls.get(k) for k in ("forum", "pdf", "proceedings", "doi")},
            "authors": "; ".join(r.get("authors", [])),
            "keywords": "; ".join(r.get("keywords", [])),
            "index_version": p.index_version,
            "canonical_hash": p.canonical_hash,
            "exported_at": p.date,
        }
        yield _csv_row(_cell(row[c]) for c in CSV_COLUMNS)


def _cell(value: object) -> object:
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


_EVEN_BACKSLASHES = r"(?<!\\)((?:\\\\)*)"  # an even run (or none): the next character is not


def _braced(text: str) -> str:
    """A BibTeX `{…}` value every parser reads the same way. Braces stay when they balance and none is
    escaped (LaTeX such as `{BERT}` keeps its meaning); otherwise they are dropped, since BibTeX counts braces
    without regard to backslashes while other parsers honour `\\{`, and an entry that one reads differently
    can swallow the next. `&`, `%` and `#` are escaped (they break LaTeX and BibTeX); `$…$` math stays. A
    value never ends on a backslash, which would escape the closing brace."""
    text = _one_line(text)
    if not (_balances(text, escaped_count=True) and _balances(text, escaped_count=False)):
        text = _debraced(text)
    text = re.sub(_EVEN_BACKSLASHES + r"([&%#])", r"\1\\\2", text)  # `&` → `\\&`, `\\\\&` → `\\\\\\&`
    if text.endswith("\\"):
        text += " "
    return "{" + text + "}"


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
        urls = _urls(r)
        if urls:
            fields.append(("url", _braced(urls[0])))
        if (r.get("urls") or {}).get("doi"):
            fields.append(("doi", _braced(r["urls"]["doi"])))
        fields.append(("keywords", _braced(", ".join(k for k in (r.get("track"), f"status:{status}") if k))))
        note = p.line() if accepted else f"Submitted to {venue}, status: {status}. {p.line()}"
        fields += [("note", _braced(note)), ("openproceedings_id", _braced(r["id"]))]
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
        row = {
            **r,
            "index_version": p.index_version,
            "canonical_hash": p.canonical_hash,
            "exported_at": p.date,
        }
        text = json.dumps(row, ensure_ascii=False, sort_keys=True)
        # characters `str.splitlines()` breaks on, escaped so a record stays one line for every reader
        yield text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("\x85", "\\u0085") + "\n"
