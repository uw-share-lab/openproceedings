"""Exports of a full matched set (spec 04 §Exports; task-030 for the CLI, task-036 for the API).

Each writer takes the engine's display records in id order (`TantivyEngine.documents`) and streams one
format to a text stream: nothing is paginated, truncated or held whole in memory. Every format carries its
provenance (`openproceedings <index_version> · query <canonical_hash> · <UTC date>`) and each record's
openproceedings id, so an export round-trips to the ids it came from.

- RIS (for Covidence): `TY  - CPAPER`, TI, AB, one AU per author, PY, T2 (the proceedings name), UR (forum,
  then pdf, then proceedings), DO, ID, KW (the track), N1 (provenance), ER. RIS is line-based, so line
  breaks inside a value become single spaces.
- CSV: the record fields of spec 01 plus `index_version` and `canonical_hash`, UTF-8 with a BOM (Excel).
  Lists (authors, keywords) are joined with "; ".
- BibTeX: `@inproceedings`, keyed `<first author's last name><year><first title word>` (ASCII, lower-case),
  a repeat key suffixed a, b, …; `note` holds the provenance and `openproceedings_id` the id.
- JSONL: one JSON object per record, with `index_version` and `canonical_hash`.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, TextIO

FORMATS = ("ris", "csv", "bibtex", "jsonl")
PROCEEDINGS = {
    "NeurIPS": "Conference on Neural Information Processing Systems",
    "ICLR": "International Conference on Learning Representations",
    "ICML": "International Conference on Machine Learning",
}
CSV_COLUMNS = (
    "id", "title", "abstract", "authors", "venue", "year", "track", "status", "presentation",
    "venue_id_raw", "forum", "pdf", "proceedings", "doi", "keywords", "index_version", "canonical_hash",
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


def proceedings_name(venue: str, year: int) -> str:
    return f"{PROCEEDINGS[venue]} ({venue} {year})"


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _urls(r: dict[str, Any]) -> list[str]:
    urls = r.get("urls") or {}
    return [urls[k] for k in ("forum", "pdf", "proceedings") if urls.get(k)]


def _ris(records: Iterable[dict[str, Any]], p: Provenance) -> Iterator[str]:
    for r in records:
        lines = [("TY", "CPAPER"), ("TI", _one_line(r["title"]))]
        if r.get("abstract"):
            lines.append(("AB", _one_line(r["abstract"])))
        lines += [("AU", _one_line(a)) for a in r.get("authors", [])]
        lines += [("PY", str(r["year"])), ("T2", proceedings_name(r["venue"], r["year"]))]
        lines += [("UR", u) for u in _urls(r)]
        if (r.get("urls") or {}).get("doi"):
            lines.append(("DO", r["urls"]["doi"]))
        lines += [("ID", r["id"]), ("KW", r["track"]), ("N1", p.line())]
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
        }
        yield _csv_row(_cell(row[c]) for c in CSV_COLUMNS)


def _cell(value: object) -> object:
    """A CSV cell a spreadsheet won't run: text starting with `=`, `+`, `-`, `@`, a tab or a carriage return
    is prefixed with `'` (OWASP's CSV-injection guard; titles and abstracts come from anyone)."""
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
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


def _ascii_word(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def bibtex_key(r: dict[str, Any]) -> str:
    authors = r.get("authors") or []
    last = _ascii_word(authors[0].split()[-1]) if authors and authors[0].split() else ""
    words = [w for w in (_ascii_word(t) for t in r["title"].split()) if w]
    return f"{last or 'anon'}{r['year']}{words[0] if words else 'untitled'}"


_ODD_BACKSLASHES = r"(?<!\\)\\(?:\\\\)*"  # an odd run of backslashes: the next character is escaped
_EVEN_BACKSLASHES = r"(?<!\\)((?:\\\\)*)"  # an even run (or none): the next character is not


def _braced(text: str) -> str:
    """A BibTeX `{…}` value every parser reads the same way. Braces stay when they balance and none is
    escaped (LaTeX such as `{BERT}` keeps its meaning); otherwise they are dropped, since BibTeX counts braces
    without regard to backslashes while other parsers honour `\\{`, and an entry that one reads differently
    can swallow the next. `&`, `%` and `#` are escaped (they break LaTeX and BibTeX); `$…$` math stays. A
    value never ends on a backslash, which would escape the closing brace."""
    text = _one_line(text)
    escaped = re.search(_ODD_BACKSLASHES + r"[{}]", text) is not None  # `\\{`, not `\\\\{`
    depth, balanced = 0, not escaped
    for ch in text:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        balanced = balanced and depth >= 0
    if not (balanced and depth == 0):
        text = _one_line(text.replace("{", "").replace("}", ""))
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
        if r.get("authors"):
            fields.append(("author", _braced(" and ".join(r["authors"]))))
        fields += [("booktitle", _braced(proceedings_name(r["venue"], r["year"]))), ("year", str(r["year"]))]
        if r.get("abstract"):
            fields.append(("abstract", _braced(r["abstract"])))
        urls = _urls(r)
        if urls:
            fields.append(("url", _braced(urls[0])))
        if (r.get("urls") or {}).get("doi"):
            fields.append(("doi", _braced(r["urls"]["doi"])))
        fields += [("note", _braced(p.line())), ("openproceedings_id", _braced(r["id"]))]
        body = ",\n".join(f"  {name} = {value}" for name, value in fields)
        yield f"@inproceedings{{{key},\n{body}\n}}\n\n"


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
        row = {**r, "index_version": p.index_version, "canonical_hash": p.canonical_hash}
        yield json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
