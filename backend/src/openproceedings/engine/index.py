"""The Tantivy index (spec 03 §Tokenizer, §Index schema, §Versioning; tantivy-indexing and index-versioning
skills).

`build_index` turns one verified snapshot into `data/indexes/<index_version>/`. The index is fed the
token contract's output (`normalize()` joined by single spaces), and its analyzer, `exact_v1`, only
splits on whitespace: the Rust side does no normalization of its own. Every document's tokens are checked
through that analyzer while building, and a token Tantivy would silently drop (over `MAX_TOKEN_BYTES`)
refuses the build, so the index can never hold less than the reference engine matches.

`index_version = sha256(snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking_params)[:12]`, over a
canonical JSON serialization pinned by a test. An index is immutable: built under an exclusive lock into
a staging directory, synced, renamed into place, its files made read-only and hashed into its manifest;
`verify_index` re-hashes them. (The directory itself stays writable: Tantivy's readers take a lock file
in it.) A version that already exists is verified and reported, never rebuilt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import tantivy

from openproceedings import storage
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import load_records
from openproceedings.query.normalize import TOKENIZER_VERSION, normalize

log = logging.getLogger("openproceedings.engine.index")

# The schema table below, the analyzer and how fields are populated (a missing abstract is ""). Any
# change to them is a new SCHEMA_VERSION (index-versioning skill).
SCHEMA_VERSION = "1"
ANALYZER = "exact_v1"
TEXT = ("title", "abstract")
FACETS = ("venue", "track", "status")
# Tantivy drops a longer token without a word; a build refuses one instead (measured on tantivy 0.26.2).
MAX_TOKEN_BYTES = 65_530
# Ranking is part of what gets reproduced, so it is part of index_version (spec 03 §Ranking).
RANKING_PARAMS: dict[str, Any] = {
    "bm25": {"b": 0.75, "k1": 1.2},
    "field_weights": {"abstract": 1.0, "title": 2.0},
}
MANIFEST = "manifest.json"
_LOCKS = (".tantivy-meta.lock", ".tantivy-writer.lock")


class IndexBuildError(Exception):
    """An index build or check refused: the message says why (never record text)."""


@dataclass(frozen=True)
class IndexBuildResult:
    path: Path
    index_version: str
    created: bool  # False when this index version already existed (and verified)


def index_version(
    snapshot_hash: str,
    tokenizer_version: str = TOKENIZER_VERSION,
    schema_version: str = SCHEMA_VERSION,
    ranking_params: dict[str, Any] | None = None,
) -> str:
    """The index's id: sha256 of the canonical JSON of its four inputs, first 12 hex digits."""
    body = {
        "ranking_params": RANKING_PARAMS if ranking_params is None else ranking_params,
        "schema_version": schema_version,
        "snapshot_hash": snapshot_hash,
        "tokenizer_version": tokenizer_version,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def analyzer() -> tantivy.TextAnalyzer:
    """`exact_v1`: split on whitespace, and nothing else (no lower-casing, folding, stemming or length
    filter). Never Tantivy's `default` or `en_stem`."""
    return tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.whitespace()).build()


def schema() -> tantivy.Schema:
    """Spec 03 §Index schema."""
    b = tantivy.SchemaBuilder()
    b.add_text_field("id", stored=True, tokenizer_name="raw")
    for field in TEXT:
        b.add_text_field(field, stored=True, tokenizer_name=ANALYZER, index_option="position")
    for field in FACETS:
        b.add_text_field(field, stored=True, fast=True, tokenizer_name="raw")
    b.add_unsigned_field("year", stored=True, indexed=True, fast=True)
    b.add_json_field("record", stored=True)  # display data only: never indexed (guarantee 2)
    return b.build()


def open_index(path: Path) -> tantivy.Index:
    """An existing index, with `exact_v1` registered (a query must be analysed the same way)."""
    index = tantivy.Index.open(str(path))
    index.register_tokenizer(ANALYZER, analyzer())
    return index


PARALLEL_FROM = 2_000  # below this many records, normalizing in one process is faster than starting workers


def _normalize_pair(pair: tuple[str, str]) -> tuple[list[str], list[str]]:
    return normalize(pair[0]), normalize(pair[1])


def _normalize_all(records: list[PaperRecord], workers: int | None) -> list[tuple[list[str], list[str]]]:
    """Every record's (title, abstract) tokens, in order. `normalize()` is pure Python and dominates the
    build, so a large corpus is split across processes (results come back in order: deterministic)."""
    pairs = [(r.title, r.abstract or "") for r in records]  # a missing abstract indexes as ""
    workers = workers if workers is not None else os.cpu_count() or 1
    if workers <= 1 or len(pairs) < PARALLEL_FROM:
        return [_normalize_pair(p) for p in pairs]
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        return list(pool.map(_normalize_pair, pairs, chunksize=256))


def _document(r: PaperRecord, fields: dict[str, list[str]]) -> tantivy.Document:
    doc = tantivy.Document()
    doc.add_text("id", r.id)
    for field in TEXT:
        doc.add_text(field, " ".join(fields[field]))  # the token contract's output; "" for a missing abstract
    for field in FACETS:
        doc.add_text(field, getattr(r, field))
    doc.add_unsigned("year", r.year)
    doc.add_json(
        "record",
        {
            "title": r.title,  # display text: the indexed fields hold tokens, never shown
            "abstract": r.abstract,
            "authors": list(r.authors),
            "urls": r.urls.model_dump(),
            "presentation": r.presentation,
            "keywords": list(r.keywords),
            "venue_id_raw": r.venue_id_raw,
        },
    )
    return doc


def _check_tokens(r: PaperRecord, fields: dict[str, list[str]], exact: tantivy.TextAnalyzer) -> None:
    for field, tokens in fields.items():
        if any(len(t.encode("utf-8")) > MAX_TOKEN_BYTES for t in tokens):
            raise IndexBuildError(
                f"{r.id}: a {field} token is over {MAX_TOKEN_BYTES} bytes, which Tantivy would drop"
            )
        if exact.analyze(" ".join(tokens)) != tokens:
            raise IndexBuildError(
                f"{r.id}: the {field} analyzer output differs from normalize() (tokenizer parity)"
            )


def _file_hashes(path: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.iterdir())
        if p.is_file() and p.name not in _LOCKS and p.name != MANIFEST
    }


def verify_index(path: Path) -> dict[str, Any]:
    """The manifest of a complete, unchanged index: every file re-hashed, the doc count re-read."""
    try:
        manifest: dict[str, Any] = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise IndexBuildError(f"{path.name} is not an index ({type(e).__name__})") from None
    if _file_hashes(path) != manifest.get("files"):
        raise IndexBuildError(f"{path.name}: its files don't match its manifest (changed or incomplete)")
    if open_index(path).searcher().num_docs != manifest.get("doc_count"):
        raise IndexBuildError(f"{path.name}: the document count doesn't match its manifest")
    return manifest


def _seal(path: Path) -> None:
    """Make every index file read-only except Tantivy's lock files (readers write those)."""
    for p in path.iterdir():
        if p.is_file() and p.name not in _LOCKS:
            p.chmod(0o444)


def build_index(
    snapshot: Path, indexes: Path, built_at: datetime | None = None, workers: int | None = None
) -> IndexBuildResult:
    """Build `indexes/<index_version>/` from a snapshot, or verify and report the one that exists."""
    began = time.monotonic()
    snapshot_manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    records = load_records(snapshot)  # refuses a snapshot whose records don't verify
    version_id = index_version(snapshot_manifest["snapshot_hash"])
    target = indexes / version_id
    with storage.exclusive(indexes):
        storage.sweep(indexes)
        if target.exists():
            verify_index(target)
            log.info("index_exists", extra={"index_version": version_id})
            return IndexBuildResult(target, version_id, created=False)
        tmp = Path(tempfile.mkdtemp(dir=indexes, prefix=storage.TMP))
        try:
            index = tantivy.Index(schema(), path=str(tmp))
            exact = analyzer()
            index.register_tokenizer(ANALYZER, exact)
            writer = index.writer(num_threads=1)  # one thread: documents keep id order, deterministically
            ordered = [records[rid] for rid in sorted(records)]
            for r, (title, abstract) in zip(ordered, _normalize_all(ordered, workers), strict=True):
                fields = {"title": title, "abstract": abstract}
                _check_tokens(r, fields, exact)
                writer.add_document(_document(r, fields))
            writer.commit()
            writer.wait_merging_threads()
            index.reload()
            count = index.searcher().num_docs
            if count != len(records):
                raise IndexBuildError(f"the index holds {count} documents, the snapshot {len(records)}")
            manifest = {
                "index_version": version_id,
                "snapshot": snapshot.name,
                "snapshot_hash": snapshot_manifest["snapshot_hash"],
                "tokenizer_version": TOKENIZER_VERSION,
                "schema_version": SCHEMA_VERSION,
                "ranking_params": RANKING_PARAMS,
                "tantivy_version": version("tantivy"),
                "doc_count": count,
                "built_at": (built_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
                "build_ms": round((time.monotonic() - began) * 1000),
                "files": _file_hashes(tmp),
            }
            (tmp / MANIFEST).write_text(
                json.dumps(manifest, sort_keys=True, indent=1) + "\n", encoding="utf-8"
            )
            storage.sync(tmp)
            try:
                tmp.rename(target)
            except OSError as e:
                raise IndexBuildError(f"could not place {version_id} ({type(e).__name__})") from None
            _seal(target)
            verify_index(target)
        finally:
            if tmp.exists():
                storage.writable(tmp)
                shutil.rmtree(tmp, ignore_errors=True)
    log.info(
        "index_built",
        extra={"index_version": version_id, "docs": manifest["doc_count"], "ms": manifest["build_ms"]},
    )
    return IndexBuildResult(target, version_id, created=True)
