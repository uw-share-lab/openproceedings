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

import gc
import hashlib
import json
import logging
import multiprocessing
import os
import re
import shutil
import tempfile
import time
import unicodedata
from collections.abc import Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType
from typing import Any

import tantivy

from openproceedings import storage
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import DISPLAY, iter_records
from openproceedings.logs import elapsed_ms
from openproceedings.query.normalize import SERVED_TOKENIZERS, TOKENIZER_VERSION, normalize
from openproceedings.vocab import TEXT_FIELDS

log = logging.getLogger(__name__)

# The schema table below, the analyzer and how fields are populated (a missing abstract is ""). Any
# change to them is a new SCHEMA_VERSION (index-versioning skill).
SCHEMA_VERSION = "3"  # 3: `ord` indexed too, so a verified clause's ids are a u64 term set (TASK-167)


# 2: the ord and title_rank fast columns (task-024/025). The schema versions this code serves: the current one,
# which new indexes are built at, and the one before it, so an index a search record pins keeps replaying
# (guarantee 4). A schema-2 index filters verified ids by a term set on the text `id`, as it always did
# (`TantivyEngine.ord_indexed`). Retire "2" (drop it here) only once no record pins a schema-2 index
# (`op index retire` refuses a pinned one; decision-030).
@dataclass(frozen=True, slots=True)
class SchemaForm:
    """What differs between the served schemas, read per index from its manifest's `schema_version`."""

    ord_indexed: bool  # `ord` indexed too: verified ids as a u64 term set on it, else on the text `id`


SERVED_SCHEMAS: Mapping[str, SchemaForm] = MappingProxyType(
    {"2": SchemaForm(ord_indexed=False), SCHEMA_VERSION: SchemaForm(ord_indexed=True)}
)
ANALYZER = "exact_v1"
TEXT: tuple[str, ...] = TEXT_FIELDS  # the searched fields (vocab), as the schema's field names
FACETS = ("venue", "track", "status")
# Tantivy drops a longer token without a word; a build refuses one instead (measured on tantivy 0.26.2).
MAX_TOKEN_BYTES = 65_530
# Ranking is part of what gets reproduced, so it is part of index_version (spec 03 §Ranking).
# field-weighted-bm25 skill: k1 and b are Tantivy's fixed BM25 constants (checked against a hand-computed
# score in the tests); the weights are applied as per-field boosts; every sort ends in the id.
RANKING_PARAMS: dict[str, Any] = {
    "bm25": {"b": 0.75, "k1": 1.2},
    "field_weights": {"abstract": 1.0, "title": 2.0},
    "sorts": {
        "relevance": "-score,id",
        "title": "casefold(nfkc(display title)),id",
        "year_asc": "year,id",
        "year_desc": "-year,id",
    },
}
MANIFEST = "manifest.json"
# an index directory's name: its index_version (hex; `-` allowed for hand-named copies). The one pattern the
# API's index selection, a pinned version, `/export?index_version=` and a record's replay all check
VERSION_NAME = re.compile(r"[0-9a-f][0-9a-f-]{0,63}")
IDS = "ids.txt"  # every record id in id order, one per line: `ord` indexes it
_LOCKS = (".tantivy-meta.lock", ".tantivy-writer.lock")


class IndexBuildError(Exception):
    """An index build or check refused: the message says why (never record text). `reason` is a constant a
    log line can carry instead (the message names paths): `unreadable`, `manifest_changed`,
    `files_mismatch`, `doc_count_mismatch` from `verify_index`; `invalid` otherwise."""

    def __init__(self, message: str, *, reason: str = "invalid") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class IndexBuildResult:
    path: Path
    index_version: str
    created: bool  # False when this index version already existed (and verified)


def _floats(value: Any) -> Any:
    """Numbers as floats, so `2` and `2.0` in ranking params give one index id."""
    if isinstance(value, dict):
        return {k: _floats(v) for k, v in value.items()}
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return value


def index_version(
    snapshot_hash: str,
    tokenizer_version: str | None = None,
    schema_version: str | None = None,
    ranking_params: dict[str, Any] | None = None,
) -> str:
    """The index's id: sha256 of the canonical JSON of its four inputs, first 12 hex digits. An input
    left out is this code's current one (read when called, never frozen at import)."""
    body = {
        "ranking_params": _floats(RANKING_PARAMS if ranking_params is None else ranking_params),
        "schema_version": SCHEMA_VERSION if schema_version is None else schema_version,
        "snapshot_hash": snapshot_hash,
        "tokenizer_version": TOKENIZER_VERSION if tokenizer_version is None else tokenizer_version,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def analyzer() -> tantivy.TextAnalyzer:
    """`exact_v1`: split on whitespace, and nothing else (no lower-casing, folding, stemming or length
    filter). Never Tantivy's `default` or `en_stem`."""
    return tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.whitespace()).build()


def schema(version: str | None = None) -> tantivy.Schema:
    """Spec 03 §Index schema at `version` (one of SERVED_SCHEMAS; the schema-2 form only for tests that build
    an index as it was). `record` is stored bytes (canonical JSON), not a JSON field: tantivy-py indexes a
    JSON field's text by default, and the record must never be searchable (guarantee 2)."""
    version = SCHEMA_VERSION if version is None else version
    if version not in SERVED_SCHEMAS:
        raise ValueError(f"schema version {version} is not one this code builds")
    b = tantivy.SchemaBuilder()
    b.add_text_field("id", stored=True, tokenizer_name="raw")
    for field in TEXT:
        b.add_text_field(field, stored=True, tokenizer_name=ANALYZER, index_option="position")
    for field in FACETS:
        b.add_text_field(field, stored=True, fast=True, tokenizer_name="raw")
    b.add_unsigned_field("year", stored=True, indexed=True, fast=True)
    # the record's position in id order (a fast column), so a match set reads back as ids without
    # fetching stored documents: ids.txt holds the ids in that order. Indexed from schema 3, so a verified
    # clause names its ids as a u64 term set, which Tantivy resolves faster than one on the text `id`
    b.add_unsigned_field("ord", stored=False, indexed=SERVED_SCHEMAS[version].ord_indexed, fast=True)
    # the record's position in (title_key(display title), id) order: `sort=title` without fetching documents
    b.add_unsigned_field("title_rank", stored=False, indexed=False, fast=True)
    b.add_bytes_field("record", stored=True, indexed=False)
    return b.build()


def open_index(path: Path) -> tantivy.Index:
    """An existing index, with `exact_v1` registered (a query must be analysed the same way), read with a
    manual reload policy: a built index never changes, so nothing reloads it. tantivy-py's `Index.open` starts
    a reader that its meta.json watcher thread reloads at its first poll, and the reload takes
    `.tantivy-meta.lock`, creating the file again; it landed after `open` returned (190 of 200 opens, TASK-165
    notes) and could fall inside an `rmtree` of the directory. Replacing that reader at once leaves the watcher
    no one to reload, unless its first poll beats this call (12 of 200, within 9 ms): so tests take an index
    away by renaming it (`test_record_cli.take_away`), never `rmtree` right after an open."""
    index = tantivy.Index.open(str(path))
    index.config_reader(reload_policy="manual")
    index.register_tokenizer(ANALYZER, analyzer())
    return index


def record_of(stored: bytes) -> dict[str, Any]:
    """The display record stored with a document (its original title and abstract, authors, urls, …)."""
    value: dict[str, Any] = json.loads(stored.decode("utf-8"))
    return value


PROGRESS_EVERY = 10_000  # documents between index_build_progress lines
PARALLEL_FROM = 2_000  # below this many records, normalizing in one process is faster than starting workers
# records normalized and added per step (never all at once). Must be ≥ PARALLEL_FROM, so a first chunk
# smaller than PARALLEL_FROM is the whole corpus.
CHUNK = 4_096


def _normalize_pair(pair: tuple[str, str], tokenizer: str) -> tuple[list[str], list[str]]:
    return normalize(pair[0], tokenizer), normalize(pair[1], tokenizer)


def _cpus() -> int:
    """CPUs this process may run on (its affinity mask; a cgroup `--cpus` quota isn't reflected)."""
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _document(r: PaperRecord, fields: dict[str, list[str]], ord_: int, title_rank: int) -> tantivy.Document:
    doc = tantivy.Document()
    doc.add_text("id", r.id)
    doc.add_unsigned("ord", ord_)
    doc.add_unsigned("title_rank", title_rank)
    for field in TEXT:
        doc.add_text(field, " ".join(fields[field]))  # the token contract's output; "" for a missing abstract
    for field in FACETS:
        doc.add_text(field, getattr(r, field))
    doc.add_unsigned("year", r.year)
    # the display text (the indexed fields hold tokens, never shown) and every display-only field (DISPLAY)
    display = {f: _plain(getattr(r, f)) for f in ("title", "abstract", *DISPLAY)}
    compact = json.dumps(display, sort_keys=True, separators=(",", ":"), ensure_ascii=False)  # canonical JSON
    doc.add_bytes("record", compact.encode("utf-8"))
    return doc


def _check_tokens(r: PaperRecord, fields: dict[str, list[str]], exact: tantivy.TextAnalyzer) -> None:
    if len(r.id.encode("utf-8")) > MAX_TOKEN_BYTES:  # the `raw` id is one term (a pmlr key is unbounded)
        raise IndexBuildError(
            f"{r.id[:80]}…: the id is over {MAX_TOKEN_BYTES} bytes, which Tantivy would drop"
        )
    # facets can't reach the limit: they come from the vocabulary
    for field, tokens in fields.items():
        # a code point is at most 4 bytes, so only a token over a quarter of the limit needs encoding
        if any(len(t) * 4 > MAX_TOKEN_BYTES and len(t.encode("utf-8")) > MAX_TOKEN_BYTES for t in tokens):
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
    """The manifest of a complete, unchanged index: its id recomputed from the manifest's four inputs and
    matched to the manifest and the directory name, every file re-hashed, the doc count re-read."""
    try:
        manifest: dict[str, Any] = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
        recomputed = index_version(
            manifest["snapshot_hash"], manifest["tokenizer_version"], manifest["schema_version"],
            manifest["ranking_params"],
        )  # fmt: skip
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise IndexBuildError(
            f"{path.name} is not an index ({type(e).__name__})", reason="unreadable"
        ) from None
    if not recomputed == manifest.get("index_version") == path.resolve().name:  # `current` is a symlink
        raise IndexBuildError(
            f"{path.name}: its manifest's inputs don't give its index_version (changed)",
            reason="manifest_changed",
        )
    if _file_hashes(path) != manifest.get("files"):
        raise IndexBuildError(
            f"{path.name}: its files don't match its manifest (changed or incomplete)",
            reason="files_mismatch",
        )
    if open_index(path).searcher().num_docs != manifest.get("doc_count"):
        raise IndexBuildError(
            f"{path.name}: the document count doesn't match its manifest", reason="doc_count_mismatch"
        )
    return manifest


def _plain(value: Any) -> Any:
    """A record field as JSON holds it: a tuple as a list, a model as its dict."""
    if isinstance(value, tuple):
        return list(value)
    return value.model_dump() if hasattr(value, "model_dump") else value


def _seal(path: Path) -> None:
    """Make every index file read-only except Tantivy's lock files (readers write those). The directory
    itself stays writable, unlike a snapshot's: a reader takes `.tantivy-meta.lock` in it (tantivy-indexing
    skill); `verify_index` re-hashes every file, so an added or swapped one is caught anyway."""
    for p in path.iterdir():
        if p.is_file() and p.name not in _LOCKS:
            p.chmod(0o444)


def _chunks(records: Iterator[PaperRecord]) -> Iterator[list[PaperRecord]]:
    chunk: list[PaperRecord] = []
    for r in records:
        chunk.append(r)
        if len(chunk) == CHUNK:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def title_key(title: str) -> str:
    """The `sort=title` key: NFKC then casefold, so a composed and a decomposed `École` sort together."""
    return unicodedata.normalize("NFKC", title).casefold()


def _title_ranks(snapshot: Path) -> dict[str, int]:
    """Each record's position in (title key, id) order, from a light first pass over the raw lines, read
    as bytes exactly as the validating pass reads them (which refuses a snapshot that doesn't verify)."""
    keys = []
    with (snapshot / "records.jsonl").open("rb") as fh:
        for line in fh:
            try:
                raw = json.loads(line)
                keys.append((title_key(str(raw["title"])), str(raw["id"])))
            except (ValueError, KeyError, TypeError):
                continue  # not a record: the validating pass refuses it
    return {rid: rank for rank, (_, rid) in enumerate(sorted(keys))}


def normalized(
    snapshot: Path, workers: int, tokenizer: str = TOKENIZER_VERSION
) -> Iterator[tuple[PaperRecord, dict[str, list[str]]]]:
    """The snapshot's records (in id order, verified), each with its `normalize()`d title and abstract (a
    missing abstract is ""; by tokenizer version `tokenizer`), a chunk at a time, across `workers` processes
    once the corpus is big enough to repay starting them. Shared by the build and the parity check, so both
    normalize alike."""
    pool = None
    each = partial(_normalize_pair, tokenizer=tokenizer)
    try:
        for chunk in _chunks(iter_records(snapshot)):
            pairs = [(r.title, r.abstract or "") for r in chunk]
            if pool is None and workers > 1 and len(pairs) >= PARALLEL_FROM:
                pool = ProcessPoolExecutor(
                    max_workers=workers, mp_context=multiprocessing.get_context("spawn")
                )
            # a pool's results come back in order: deterministic
            results = [each(p) for p in pairs] if pool is None else list(pool.map(each, pairs, chunksize=64))
            for r, (title, abstract) in zip(chunk, results, strict=True):
                yield r, {"title": title, "abstract": abstract}
    except BrokenProcessPool:
        raise IndexBuildError("a normalizing worker process died (out of memory?); try again") from None
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)


def _add_all(
    snapshot: Path,
    writer: Any,
    exact: tantivy.TextAnalyzer,
    workers: int,
    ids: Any,
    commit_every: int | None = None,
    tokenizer: str = TOKENIZER_VERSION,
) -> int:
    """Stream the snapshot's records through normalize() into the writer."""
    ranks = _title_ranks(snapshot)
    added = 0
    started = time.perf_counter()
    for r, fields in normalized(snapshot, workers, tokenizer):
        _check_tokens(r, fields, exact)
        if r.id not in ranks:  # can't happen for a valid line; refuse rather than guess a rank
            raise IndexBuildError(f"{r.id}: no title rank (the snapshot's lines didn't read the same twice)")
        writer.add_document(_document(r, fields, added, ranks[r.id]))
        if commit_every and (added + 1) % commit_every == 0:
            writer.commit()  # tests: several segments
        ids.write(r.id + "\n")
        added += 1
        if added % PROGRESS_EVERY == 0:  # a long build says it's alive (logging-standards: at most every 10k)
            log.info(
                "index_build_progress",
                extra={"docs": added, "ms": elapsed_ms(started)},
            )
    return added


def _release(writer: Any) -> None:
    """Stop a failed build's writer before its directory is removed: roll back what it added, wait for its
    merge threads, which drops Tantivy's writer and its directory lock. Left alive (the failing frame's
    traceback holds it), Tantivy could write `.tantivy-meta.lock` again after `rmtree` had walked the
    directory, and the `.tmp-*` would survive the build (M3a review gate round 2: 9 leaks in 320 failed
    builds). Best effort: the build's own error is the one raised."""
    if writer is None:
        return
    for step in (writer.rollback, writer.wait_merging_threads):
        try:
            step()
        except Exception:  # already failing: the directory is removed either way
            log.debug("index_build_release_failed", extra={"step": step.__name__})
    gc.collect()  # anything else the failure left holding the index's files


def build_index(
    snapshot: Path,
    indexes: Path,
    built_at: datetime | None = None,
    workers: int | None = None,
    commit_every: int | None = None,  # tests only: commit every N documents, to build several segments
    schema_version: str | None = None,  # tests only: build at an older served schema (a pinned index)
    tokenizer_version: str | None = None,  # tests only: build with an older served tokenizer (a pinned index)
) -> IndexBuildResult:
    """Build `indexes/<index_version>/` from a snapshot, or verify and report the one that exists. Records
    stream through in chunks, never all loaded at once."""
    began = time.monotonic()
    try:
        snapshot_manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        snapshot_hash = snapshot_manifest["snapshot_hash"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise IndexBuildError(f"{snapshot.name} is not a snapshot ({type(e).__name__})") from None
    schema_version = SCHEMA_VERSION if schema_version is None else schema_version  # read when called
    if schema_version not in SERVED_SCHEMAS:
        raise IndexBuildError(f"schema version {schema_version} is not one this code builds")
    tokenizer = TOKENIZER_VERSION if tokenizer_version is None else tokenizer_version  # read when called
    if tokenizer not in SERVED_TOKENIZERS:
        raise IndexBuildError(f"tokenizer version {tokenizer} is not one this code builds")
    version_id = index_version(snapshot_hash, tokenizer_version=tokenizer, schema_version=schema_version)
    target = indexes / version_id
    with storage.exclusive(indexes):
        storage.sweep(indexes)
        if target.exists():
            try:
                verify_index(target)
            except IndexBuildError as e:
                raise IndexBuildError(f"{e}; it is immutable: retire it and build again") from None
            _seal(target)  # a crash between placing and sealing left it writable
            log.info("index_exists", extra={"index_version": version_id})
            return IndexBuildResult(target, version_id, created=False)
        log.info("index_build_started", extra={"index_version": version_id, "snapshot_hash": snapshot_hash})
        tmp = Path(tempfile.mkdtemp(dir=indexes, prefix=storage.TMP))
        index: tantivy.Index | None = None
        writer: Any = None
        try:
            index = tantivy.Index(schema(schema_version), path=str(tmp))
            index.config_reader(reload_policy="manual")  # reloaded once, below; never by a watcher (TASK-165)
            exact = analyzer()
            index.register_tokenizer(ANALYZER, exact)
            writer = index.writer(num_threads=1)  # one thread: documents keep id order, deterministically
            with (tmp / IDS).open("w", encoding="utf-8") as ids:
                added = _add_all(
                    snapshot,
                    writer,
                    exact,
                    workers if workers is not None else _cpus(),
                    ids,
                    commit_every,
                    tokenizer,
                )
            writer.commit()
            writer.wait_merging_threads()
            index.reload()
            count = index.searcher().num_docs
            if count != added:
                raise IndexBuildError(f"the index holds {count} documents, the snapshot {added}")
            manifest = {
                "index_version": version_id,
                "snapshot": snapshot.name,
                "snapshot_hash": snapshot_hash,
                "tokenizer_version": tokenizer,
                "schema_version": schema_version,
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
            try:
                verify_index(target)
            except IndexBuildError as e:
                raise IndexBuildError(f"{e}; the placed index is broken: retire it and build again") from None
        finally:
            if tmp.exists():  # the build failed before placing it
                _release(writer)
                index = writer = None
                storage.writable(tmp)
                shutil.rmtree(tmp, ignore_errors=True)
                if tmp.exists():  # the next build's sweep removes it; say so rather than hide it
                    log.warning("index_build_tmp_left", extra={"index_version": version_id, "path": tmp.name})
    log.info(
        "index_built",
        extra={"index_version": version_id, "docs": manifest["doc_count"], "ms": float(manifest["build_ms"])},
    )
    return IndexBuildResult(target, version_id, created=True)
