"""Tokenizer parity (spec 03 §Tokenizer, spec 07 §A; task-029): a built index holds exactly `normalize()`'s
tokens for every record of its snapshot.

Two reads of what Tantivy really has, not of what the build meant to write:
- per document, in id order: the stored field through the index's own analyzer (`exact_v1`) equals
  `normalize()` of the snapshot record's raw text;
- per term, from Tantivy's term dictionary: each term's document frequency in each text field equals the
  count of records whose `normalize()` tokens hold it (so a token Tantivy dropped or split shows up).
The first difference raises `ParityError`, naming the record (or term), the field and both tokens. Over the
real corpus this runs locally (`op index parity`; decision-004), never in CI.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import tantivy

from openproceedings.engine.index import TEXT, IndexBuildError, analyzer, open_index, verify_index
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import iter_records
from openproceedings.query.normalize import normalize


class ParityError(IndexBuildError):
    """The index doesn't hold `normalize()`'s tokens for its snapshot."""


@dataclass(frozen=True, slots=True)
class ParityReport:
    records: int
    terms: int  # distinct (field, term) pairs checked in the term dictionary


def check_parity(index: Path, snapshot: Path) -> ParityReport:
    manifest = verify_index(index)
    snapshot_hash = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))["snapshot_hash"]
    if manifest["snapshot_hash"] != snapshot_hash:
        raise ParityError(
            f"index {manifest['index_version']} was built from another snapshot than {snapshot.name}"
        )
    searcher = open_index(index).searcher()
    stored = dict(_stored(searcher))
    exact = analyzer()
    expected: Counter[tuple[str, str]] = Counter()
    n = 0
    for record in iter_records(snapshot):  # id order, so the first difference is the same every run
        n += 1
        if record.id not in stored:
            raise ParityError(f"{record.id}: in the snapshot, not in the index")
        fields = stored.pop(record.id)
        for field in TEXT:
            want = normalize(_raw(record, field))
            _first_difference(record.id, field, exact.analyze(fields[field]), want)
            expected.update((field, t) for t in set(want))
    if stored:
        raise ParityError(f"{min(stored)}: in the index, not in the snapshot")
    indexed = Counter({(f, term): df for f in TEXT for term, df in terms(searcher, f)})
    for key in sorted(expected.keys() | indexed.keys()):
        if expected[key] != indexed[key]:
            field, term = key
            raise ParityError(
                f"term {term!r} in {field}: {indexed[key]} documents in the index, {expected[key]} by normalize()"
            )
    return ParityReport(n, len(expected))


def terms(searcher: tantivy.Searcher, field: str) -> list[tuple[str, int]]:
    """Every term of `field` in the index with its document frequency (the term dictionary)."""
    return list(searcher.terms_with_prefix(field, ""))


def _stored(searcher: tantivy.Searcher) -> Iterator[tuple[str, dict[str, str]]]:
    hits = searcher.search(tantivy.Query.all_query(), max(1, searcher.num_docs)).hits
    for _score, address in hits:
        doc = searcher.doc(address).to_dict()
        yield doc["id"][0], {f: doc[f][0] if doc.get(f) else "" for f in TEXT}


def _raw(record: PaperRecord, field: str) -> str:
    return (record.title if field == "title" else record.abstract) or ""


def _first_difference(record_id: str, field: str, got: list[str], want: list[str]) -> None:
    if got == want:
        return
    i = next((k for k, (a, b) in enumerate(zip(got, want, strict=False)) if a != b), min(len(got), len(want)))
    has = repr(got[i]) if i < len(got) else "nothing"
    gives = repr(want[i]) if i < len(want) else "nothing"
    raise ParityError(f"{record_id}: {field} token {i}: the index has {has}, normalize() gives {gives}")
