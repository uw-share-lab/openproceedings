"""Tokenizer parity (spec 03 §Tokenizer, spec 07 §A; task-029): a built index holds exactly `normalize()`'s
tokens for every record of its snapshot.

Record by record, in id order, against `normalize()` of the snapshot's raw text (normalized as the build
does, across worker processes):
- the stored field, through the index's analyzer (`exact_v1`), gives the same tokens. This checks that the
  text round-trips; it is not yet a read-back of what Tantivy indexed;
- each field of 2+ tokens is found by a phrase query for its whole token stream, restricted to the record's
  id. That is a read-back of the positions Tantivy indexed, which phrases and NEAR rely on;
- each term's document frequency in Tantivy's term dictionary equals the count of records holding it, in
  both directions (a term Tantivy dropped, split or invented shows up).
Term frequencies within a document are not checked beyond what the phrase read-back implies.

The first difference raises `ParityError`. Unlike other errors, its message quotes the differing tokens:
it is printed to the local terminal of the person checking their own index, and never logged
(`cli_refused` logs only the error type). Over the real corpus this runs locally (`op index parity`;
decision-004), never in CI.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tantivy

from openproceedings.engine.index import (
    TEXT,
    IndexBuildError,
    _cpus,
    analyzer,
    normalized,
    open_index,
    verify_index,
)
from openproceedings.logs import elapsed_ms
from openproceedings.query.normalize import SERVED_TOKENIZERS

log = logging.getLogger(__name__)


class ParityError(IndexBuildError):
    """The index doesn't hold `normalize()`'s tokens for its snapshot. Its message quotes the tokens (local
    output only; see the module docstring)."""


@dataclass(frozen=True, slots=True)
class ParityReport:
    records: int
    terms: int  # distinct (field, term) pairs checked in the term dictionary
    phrases: int  # fields read back by position


def check_parity(
    index: Path, snapshot: Path, workers: int | None = None, manifest: dict[str, Any] | None = None
) -> ParityReport:
    """`manifest`: the index's, from a `verify_index` the caller already ran (so files aren't hashed twice)."""
    started = time.perf_counter()
    manifest = manifest if manifest is not None else verify_index(index)
    snapshot_hash = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))["snapshot_hash"]
    if manifest["snapshot_hash"] != snapshot_hash:
        raise IndexBuildError(  # operator error, not a broken guarantee: a WARNING, not a ParityError
            f"index {manifest['index_version']} was built from another snapshot than {snapshot.name}"
        )
    if manifest["tokenizer_version"] not in SERVED_TOKENIZERS:  # this code can't normalize as it was built
        raise IndexBuildError(
            f"index {manifest['index_version']} was built with tokenizer {manifest['tokenizer_version']}, which "
            f"this code no longer has (it serves {', '.join(SERVED_TOKENIZERS)})"
        )
    tantivy_index = open_index(index)
    searcher = tantivy_index.searcher()
    exact = analyzer()
    expected: Counter[tuple[str, str]] = Counter()
    stored = _stored(searcher)  # in id order, like the snapshot
    n = phrases = 0
    # a tampered snapshot may stop this loop with ParityError before iter_records reaches its own hash check
    # by the tokenizer the index was built with (an older served one, for an index a record pins)
    workers = workers if workers is not None else _cpus()
    for record, fields in normalized(snapshot, workers, manifest["tokenizer_version"]):
        n += 1
        doc_id, doc = next(stored, (None, {}))
        if doc_id != record.id:
            missing = record.id if doc_id is None or doc_id > record.id else doc_id
            side = (
                "the snapshot, not in the index" if missing == record.id else "the index, not in the snapshot"
            )
            raise ParityError(f"{missing}: in {side}")
        for field in TEXT:
            _first_difference(record.id, field, exact.analyze(doc[field]), fields[field])
            if len(fields[field]) >= 2:
                phrases += 1
                _positions(tantivy_index, searcher, record.id, field, fields[field])
            expected.update((field, t) for t in set(fields[field]))
    extra = next(stored, None)
    if extra is not None:
        raise ParityError(f"{extra[0]}: in the index, not in the snapshot")
    indexed = Counter({(f, term): df for f in TEXT for term, df in terms(searcher, f)})
    for key in sorted(expected.keys() | indexed.keys()):
        if expected[key] != indexed[key]:
            field, term = key
            raise ParityError(
                f"term {term!r} in {field}: {indexed[key]} documents in the index, {expected[key]} by normalize()"
            )
    report = ParityReport(n, len(expected), phrases)
    log.info(
        "index_parity_ok",
        extra={"index_version": manifest["index_version"], "records": n, "terms": report.terms,
               "phrases": phrases, "ms": elapsed_ms(started)},
    )  # fmt: skip
    return report


def terms(searcher: tantivy.Searcher, field: str) -> list[tuple[str, int]]:
    """Every term of `field` in the index with its document frequency (the whole term dictionary, summed
    over segments, deleted documents left out)."""
    return list(searcher.terms_with_prefix(field, ""))


def _stored(searcher: tantivy.Searcher) -> Iterator[tuple[str, dict[str, str]]]:
    """Each document's id and stored text fields, one at a time in `ord` (= id) order."""
    addresses = [
        a for _score, a in searcher.search(tantivy.Query.all_query(), max(1, searcher.num_docs)).hits
    ]
    if not addresses:
        return
    ords = [o if isinstance(o, int) else -1 for o in searcher.fast_field_values("ord", addresses)]
    if -1 in ords:
        raise ParityError("a document has no ord: the index predates it; build it again")
    for _ord, address in sorted(zip(ords, addresses, strict=True), key=lambda pair: pair[0]):
        doc = searcher.doc(address).to_dict()
        yield doc["id"][0], {f: doc[f][0] if doc.get(f) else "" for f in TEXT}


def _positions(
    index: tantivy.Index, searcher: tantivy.Searcher, record_id: str, field: str, tokens: list[str]
) -> None:
    """The record's field holds `tokens` at consecutive positions (read back from Tantivy's postings)."""
    query = tantivy.Query.boolean_query(
        [
            (tantivy.Occur.Must, tantivy.Query.term_query(index.schema, "id", record_id)),
            (
                tantivy.Occur.Must,
                tantivy.Query.phrase_query(index.schema, field, list[str | tuple[int, str]](tokens), 0),
            ),
        ]
    )
    if not searcher.search(query, 1).hits:  # ids are unique: one hit or none
        raise ParityError(
            f"{record_id}: {field}'s {len(tokens)} tokens aren't at consecutive positions in the index"
        )


def _first_difference(record_id: str, field: str, got: list[str], want: list[str]) -> None:
    if got == want:
        return
    i = next((k for k, (a, b) in enumerate(zip(got, want, strict=False)) if a != b), min(len(got), len(want)))
    has = repr(got[i]) if i < len(got) else "nothing"
    gives = repr(want[i]) if i < len(want) else "nothing"
    raise ParityError(f"{record_id}: {field} token {i}: the index has {has}, normalize() gives {gives}")
