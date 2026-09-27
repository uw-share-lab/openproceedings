"""`ids_hash` known answers, the append-only record store, and the manifest reads a record freezes (spec 04
§Search records; search-records skill)."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from openproceedings import records
from openproceedings.diagnostics import DiagnosticCode, InternalError, http_status
from openproceedings.engine.index import RANKING_PARAMS, SCHEMA_VERSION
from openproceedings.engine.index import index_version as index_version_of
from openproceedings.ingest.dedup import Conflict, DedupResult, Merge
from openproceedings.ingest.snapshot import render
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse
from openproceedings.records import (
    BODY_VERSION,
    RECORD_ID,
    RECORDS_FILE,
    RecordStore,
    RecordStoreFull,
    SearchRecord,
    changed_inputs,
    ids_hash,
    index_inputs,
    snapshot_facts,
    valid_record_id,
)

from tests.corpus import Rec
from tests.golden.test_tantivy_200 import as_paper
from tests.unit.engine.test_exclusions import BUILT

FIXTURES = Path(__file__).parent.parent / "fixtures" / "records"


# --- ids_hash: pinned by known answers (changing it turns every stored record into a mismatch) ----------
@pytest.mark.parametrize(
    ("ids", "expected"),
    [
        ([], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),  # sha256(b"")
        (["a"], "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"),  # sha256(b"a")
        (["op:c", "op:a", "op:b"], "2253031ae5a0c51fba386c0ed99030028f6d2e9f1701112d77606aede36d8c2d"),
        (["É", "a", "B"], "221ed53eec4e450a204ded6fcb5cd136e474b50bf038b90f9848bc353739f2a5"),  # code points
    ],
)
def test_ids_hash_known_answers(ids: list[str], expected: str) -> None:
    assert ids_hash(ids) == expected
    assert ids_hash(reversed(ids)) == expected  # membership only: the order given never matters


def test_record_ids_are_12_url_safe_characters() -> None:
    drawn = {records.new_record_id() for _ in range(2000)}
    assert len(drawn) == 2000 and all(RECORD_ID.fullmatch(i) for i in drawn)
    for bad in (
        "",
        "abc",
        "a" * 11,
        "a" * 13,
        "abcdefghij.k",
        "../../etc/pa",
        "abcdefghijk\n",
        "ábcdefghijkl",
    ):
        assert not valid_record_id(bad)


# --- the store --------------------------------------------------------------------------------------------
IDS = ["op:a", "op:b"]


def fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "body_version": BODY_VERSION,
        "input": "trust",
        "mode": "native",
        "canonical": "(trust AND status:accepted)",
        "canonical_hash": "c" * 64,
        "identification_query": "trust",
        "index_version": "0123456789ab",
        "tokenizer_version": "t",
        "query_version": "1",
        "schema_version": "2",
        "ranking_params": {"bm25": {"b": 0.75, "k1": 1.2}},
        "snapshot_hash": "s" * 64,
        "crawl_dates": {"*": {"from": "2026-01-01T00:00:00+00:00", "to": "2026-01-02T00:00:00+00:00"}},
        "searched_at": "2026-09-27T12:00:00Z",
        "total": 2,
        "excluded": {"total": 1, "track": {"workshop": 1, "unknown": 0}, "status": {"unknown": 0}},
        "expansions": {},
        "translations": [],
        "warnings": [],
        "ids_hash": ids_hash(IDS),
        "dedup": {"merged": 0, "ambiguous_not_merged": 0, "track_not_merged": 0, "venue_year_not_merged": 0},
        "semantic_version": None,
        "sources": ["openreview_v2"],
        "identification_citable": True,
        "crawl_dates_kind": {"*": "crawl"},
    }
    return {**base, **overrides}


@pytest.fixture
def store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "records")


def raw(store: RecordStore) -> sqlite3.Connection:
    return sqlite3.connect(store.path)


def test_insert_then_get_round_trips_every_field(store: RecordStore) -> None:
    saved = store.insert(fields(), IDS)
    got = store.get(saved.record_id)
    assert got == saved and got is not None
    assert got.ids == IDS and got.body_version == BODY_VERSION
    assert list(got.excluded.track) == ["workshop", "unknown"]  # the stored bucket order is kept
    assert store.pinned("0123456789ab") == 1 and store.pinned("ffffffffffff") == 0
    without = store.get(saved.record_id, with_ids=False)
    assert without is not None and without.ids is None


def test_the_store_lives_in_its_own_private_directory(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records")
    store.insert(fields(), IDS)
    assert store.path == tmp_path / "records" / RECORDS_FILE
    assert stat.S_IMODE((tmp_path / "records").stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_a_read_never_creates_the_store(store: RecordStore) -> None:
    assert store.get("abcdefghijkl") is None and store.pinned("0123456789ab") == 0
    assert not store.path.exists()


def test_store_uses_wal_and_records_its_schema_version(store: RecordStore) -> None:
    store.insert(fields(), IDS)
    conn = raw(store)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    finally:
        conn.close()


def test_identical_id_sets_are_stored_once(store: RecordStore) -> None:
    """A repeated save costs its body, not another copy of the ids (content-addressed id_sets)."""
    big = [f"op:iclr:2024:{n:06d}" for n in range(20_000)]
    first = store.insert(fields(ids_hash=ids_hash(big), total=len(big)), big)
    size = store._used_bytes()
    for n in range(50):
        store.insert(fields(ids_hash=ids_hash(big), total=len(big), input=f"q{n}"), big)
    conn = raw(store)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        assert conn.execute("SELECT count(*) FROM id_sets").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 51
    finally:
        conn.close()
    grown = store._used_bytes() - size
    assert grown < 51 * 4096, grown  # ~1-2 KB per record, never another ~100 KB id blob
    assert store.get(first.record_id) == first


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE records SET body = '{}'",
        "UPDATE records SET index_version = 'ffffffffffff'",
        "DELETE FROM records",
        "UPDATE id_sets SET ids = x''",
        "DELETE FROM id_sets",
        "UPDATE schema_version SET version = 2",
        "DELETE FROM schema_version",
    ],
)
def test_update_and_delete_are_refused_by_the_triggers(store: RecordStore, statement: str) -> None:
    saved = store.insert(fields(), IDS)
    conn = raw(store)  # a plain connection: the triggers live in the file
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(statement)
    finally:
        conn.close()
    assert store.get(saved.record_id) == saved


@pytest.mark.parametrize("statement", ["INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE", "INSERT"])
@pytest.mark.parametrize("own", [True, False])
def test_an_existing_row_is_never_replaced(store: RecordStore, statement: str, own: bool) -> None:
    """SQLite's REPLACE deletes the old row without firing DELETE triggers unless `recursive_triggers` is on;
    BEFORE INSERT triggers refuse it from any client (`own`: the store's connection, else a plain one)."""
    saved = store.insert(fields(), IDS)
    conn = store._connect() if own else raw(store)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                f"{statement} INTO records VALUES (?, 'x', 'x', ?, '{{}}')", (saved.record_id, ids_hash(IDS))
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(f"{statement} INTO id_sets VALUES (?, x'')", (ids_hash(IDS),))
    finally:
        conn.close()
    assert store.get(saved.record_id) == saved


def test_a_taken_id_is_redrawn(store: RecordStore, monkeypatch: pytest.MonkeyPatch) -> None:
    draws = iter(["AAAAAAAAAAAA", "AAAAAAAAAAAA", "BBBBBBBBBBBB"])
    monkeypatch.setattr(records, "new_record_id", lambda: next(draws))
    first = store.insert(fields(), IDS)
    second = store.insert(fields(input="other"), IDS)
    assert (first.record_id, second.record_id) == ("AAAAAAAAAAAA", "BBBBBBBBBBBB")
    assert store.get("AAAAAAAAAAAA") == first  # never overwritten


def test_only_an_id_collision_is_retried(store: RecordStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.insert(fields(), IDS)
    conn = raw(store)
    conn.execute(
        "CREATE TRIGGER broken BEFORE INSERT ON records BEGIN SELECT RAISE(ABORT, 'disk says no'); END"
    )
    conn.commit()
    conn.close()
    drawn: list[str] = []
    real = records.new_record_id

    def draw() -> str:
        drawn.append(real())
        return drawn[-1]

    monkeypatch.setattr(records, "new_record_id", draw)
    with pytest.raises(sqlite3.IntegrityError, match="disk says no"):
        store.insert(fields(), IDS)
    assert len(drawn) == 1


@pytest.mark.parametrize("ids", [["op:b", "op:a"], ["op:a", "op:a"], ["op:a\nop:b"]])
def test_ids_must_be_strictly_increasing_and_one_line(store: RecordStore, ids: list[str]) -> None:
    with pytest.raises(InternalError):
        store.insert(fields(), ids)


def test_empty_id_list_round_trips(store: RecordStore) -> None:
    saved = store.insert(fields(total=0, ids_hash=ids_hash([])), [])
    assert store.get(saved.record_id) == saved and saved.ids == []


def test_a_store_whose_file_was_removed_is_recreated(store: RecordStore) -> None:
    store.insert(fields(), IDS)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{store.path}{suffix}").unlink(missing_ok=True)
    again = store.insert(fields(), IDS)
    assert store.get(again.record_id) == again


def test_a_store_from_a_newer_schema_is_refused(tmp_path: Path) -> None:
    RecordStore(tmp_path / "records").insert(fields(), IDS)
    conn = sqlite3.connect(tmp_path / "records" / RECORDS_FILE)
    conn.execute("INSERT INTO schema_version (version) VALUES (2)")
    conn.commit()
    conn.close()
    with pytest.raises(InternalError):
        RecordStore(tmp_path / "records").insert(fields(), IDS)


def test_a_full_store_refuses_saves_with_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert http_status(DiagnosticCode.API_RECORDS_STORE_FULL) == 503
    small = RecordStore(tmp_path / "small", max_bytes=1)
    small.insert(fields(), IDS)  # the first save finds an empty store
    with pytest.raises(RecordStoreFull) as e:
        small.insert(fields(), IDS)
    assert e.value.code == DiagnosticCode.API_RECORDS_STORE_FULL
    tight = RecordStore(tmp_path / "tight", min_free_bytes=1 << 62)  # more than any disk has free
    with pytest.raises(RecordStoreFull):
        tight.insert(fields(), IDS)
    assert tight.get("AAAAAAAAAAAA") is None


def test_a_store_at_exactly_its_cap_is_full(tmp_path: Path) -> None:
    """The cap is reached at `>=`: a store whose file is exactly `max_bytes` refuses the next save."""
    probe = RecordStore(tmp_path / "probe")
    probe.insert(fields(), IDS)
    size = probe._used_bytes()
    at_cap = RecordStore(tmp_path / "probe", max_bytes=size)
    with pytest.raises(RecordStoreFull):
        at_cap.insert(fields(), IDS)
    RecordStore(tmp_path / "probe", max_bytes=size + 1).insert(fields(), IDS)  # one byte under: taken


def test_insert_refuses_fields_whose_ids_hash_is_not_the_ids(store: RecordStore) -> None:
    """A record whose `ids_hash` doesn't name its own stored list can never be written (it could only
    replay as a mismatch)."""
    with pytest.raises(InternalError, match="ids_hash"):
        store.insert(fields(ids_hash=ids_hash(IDS[1:])), IDS)
    with pytest.raises(InternalError, match="ids_hash"):
        store.insert(fields(), IDS[1:])
    assert not store.path.exists()  # refused before anything was created


def test_the_stored_excluded_shape_is_the_live_one() -> None:
    """Replay compares the live `excluded` with the stored one whole, so a key added to `Excluded.to_json`
    would make every record a mismatch: a shape change must come with a `query_version` bump (search-records
    skill), and this test is where it's noticed."""
    from openproceedings.engine.exclusions import Excluded

    live = Excluded(total=0, track={"unknown": 0}, status={"unknown": 0}).to_json()
    assert set(live) == set(records.Excluded.model_fields)


def test_a_full_store_logs_on_each_change_of_state_not_per_refusal(tmp_path: Path) -> None:
    """`records_store_full` once when it fills, `records_store_recovered` once when a save fits again (M3a
    review): a client retrying a full store can't flood the log."""
    import io
    import json

    from openproceedings.logs import configure_logging

    stream = io.StringIO()
    configure_logging("DEBUG", "json", stream=stream)
    small = RecordStore(tmp_path / "small", max_bytes=1)
    small.insert(fields(), IDS)
    for _ in range(3):
        with pytest.raises(RecordStoreFull):
            small.insert(fields(), IDS)
    small.max_bytes = None  # room again (an operator raised the cap)
    small.insert(fields(), IDS)
    small.insert(fields(), IDS)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [(e["event"], e["level"]) for e in events if e["event"].startswith("records_store")] == [
        ("records_store_full", "WARNING"),
        ("records_store_recovered", "INFO"),
    ]


def test_concurrent_inserts_from_threads_each_get_their_own_row(store: RecordStore) -> None:
    saved: list[str] = []
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(10):
                saved.append(store.insert(fields(input=f"q{n}-{i}"), IDS).record_id)
        except BaseException as e:  # surfaced below
            errors.append(e)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(saved)) == 80
    assert all(store.get(i) is not None for i in saved)


# --- reading stored bodies: versioned, tolerant ----------------------------------------------------------
def insert_raw(store: RecordStore, record_id: str, body: str, ids: list[str], key: str | None = None) -> None:
    """A row written as an older (or broken) writer would have: straight into the file."""
    store.insert(fields(), IDS)  # creates the schema
    conn = raw(store)
    blob = zlib.compress("\n".join(ids).encode())
    key = key or ids_hash(ids)
    conn.execute(
        "INSERT INTO id_sets SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM id_sets WHERE ids_hash = ?)",
        (key, blob, key),
    )
    conn.execute("INSERT INTO records VALUES (?, 'x', 'x', ?, ?)", (record_id, key, body))
    conn.commit()
    conn.close()


def test_a_committed_v1_body_stays_readable(store: RecordStore) -> None:
    """The v1 body fixture was written by task-037's first writer. It holds a diagnostic code this code no
    longer registers: stored bodies are read with frozen, tolerant types, never the live enums."""
    body = (FIXTURES / "record-v1.json").read_text(encoding="utf-8")
    ids = ["op:iclr:2024:FxA", "op:neurips:2023:FxB"]
    insert_raw(store, "v1v1v1v1v1v1", body, ids)
    got = store.get("v1v1v1v1v1v1")
    assert got is not None and got.body_version == 1 and got.ids == ids
    assert [d.code for d in got.warnings] == ["WARN_RETIRED_FOR_THIS_TEST"]
    assert got.ids_hash == json.loads(body)["ids_hash"]
    # v1 never recorded its sources, its window's kind or the other not-merged counts: unknown, never guessed
    assert (got.sources, got.identification_citable, got.crawl_dates_kind) == (None, None, None)
    assert (got.dedup.merged, got.dedup.ambiguous_not_merged) == (12, 1)
    assert (got.dedup.track_not_merged, got.dedup.venue_year_not_merged) == (None, None)


@pytest.mark.parametrize("missing", ["sources", "identification_citable", "crawl_dates_kind"])
def test_a_v2_body_without_its_bootstrap_fields_is_refused(store: RecordStore, missing: str) -> None:
    body = {**fields(), "record_id": "v2v2v2v2v2v2"}
    del body[missing]
    insert_raw(store, "v2v2v2v2v2v2", json.dumps(body), IDS)
    with pytest.raises(InternalError):
        store.get("v2v2v2v2v2v2")


def test_a_record_whose_citability_contradicts_its_sources_is_never_written(store: RecordStore) -> None:
    with pytest.raises(InternalError, match="contradicts"):
        store.insert(fields(sources=["ris"], identification_citable=True), IDS)


def test_a_stored_record_reads_after_the_bootstrap_sources_change(
    store: RecordStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Citability is checked on write only (M3a round 2): a stored body outlives the code, so a later change
    to which sources are bootstrap ones must never make an earlier record unreadable (guarantee 4)."""
    import openproceedings.vocab as vocab

    saved = store.insert(fields(sources=["ris"], identification_citable=False), IDS)
    monkeypatch.setattr(vocab, "BOOTSTRAP_SOURCES", frozenset())  # `ris` is no longer a bootstrap source
    got = store.get(saved.record_id)
    assert got is not None and got.identification_citable is False  # as written, never recomputed


def test_a_body_from_a_newer_writer_is_refused(store: RecordStore) -> None:
    body = json.dumps({**fields(body_version=BODY_VERSION + 1), "record_id": "newnewnewnew"})
    insert_raw(store, "newnewnewnew", body, IDS)
    with pytest.raises(InternalError):
        store.get("newnewnewnew")


def test_a_body_naming_another_record_is_refused(store: RecordStore) -> None:
    body = json.dumps({**fields(), "record_id": "otherotherot"})
    insert_raw(store, "mineminemine", body, IDS)
    with pytest.raises(InternalError):
        store.get("mineminemine")


def test_an_id_set_that_does_not_hash_to_its_key_is_refused(store: RecordStore) -> None:
    body = json.dumps({**fields(), "record_id": "keykeykeykey"})
    insert_raw(store, "keykeykeykey", body, ["op:x"], key="0" * 64)
    with pytest.raises(InternalError):
        store.get("keykeykeykey")


def test_an_unreadable_body_is_refused(store: RecordStore) -> None:
    insert_raw(store, "junkjunkjunk", "{not json", IDS)
    with pytest.raises(InternalError):
        store.get("junkjunkjunk")


# --- the manifests a record freezes ---------------------------------------------------------------------
@pytest.fixture
def data_dir(tmp_path: Path) -> Iterator[Path]:
    """One index manifest and one snapshot manifest, rendered as the real builders write them, with two
    merges and four conflicts (one each ambiguous, track and venue-year not merged, one field precedence)."""
    papers = tuple(
        sorted(
            (as_paper(Rec(id=f"fx:{n:04d}", title=f"t{n}", abstract=None)) for n in range(3)),
            key=lambda p: p.id,
        )
    )
    merges = (
        Merge(papers[0].id, "op:iclr:2024:m1", "forum_id", "k", "ICLR", 2024, "ris"),
        Merge(papers[1].id, "op:iclr:2024:m2", "native_id", "k", "ICLR", 2024, "ris"),
    )
    conflicts = (
        Conflict(papers[0].id, "title_key", "a", "ris", "b", "ris", "ambiguous_not_merged"),
        Conflict(papers[1].id, "title", "a", "ris", "b", "ris", "precedence:ris"),
        Conflict(papers[2].id, "title_key", "a", "ris", "b", "ris", "track_not_merged"),
        Conflict(papers[2].id, "forum_id", "a", "ris", "b", "ris", "venue_year_not_merged"),
    )
    files = render(DedupResult(papers, merges, conflicts), [], BUILT)
    snapshot = json.loads(files["manifest.json"])
    root = tmp_path / "data"
    (root / "snapshots" / "snap").mkdir(parents=True)
    (root / "snapshots" / "snap" / "manifest.json").write_bytes(files["manifest.json"])
    version = index_version_of(snapshot["snapshot_hash"])
    (root / "indexes" / version).mkdir(parents=True)
    manifest = {
        "index_version": version,
        "snapshot": "snap",
        "snapshot_hash": snapshot["snapshot_hash"],
        "tokenizer_version": TOKENIZER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ranking_params": RANKING_PARAMS,
    }
    (root / "indexes" / version / "manifest.json").write_text(json.dumps(manifest))
    yield root


def the_version(data_dir: Path) -> str:
    return next(p.name for p in (data_dir / "indexes").iterdir())


def edit(path: Path, **changes: Any) -> None:
    doc = json.loads(path.read_text())
    doc.update(changes)
    os.chmod(path, 0o644)
    path.write_text(json.dumps(doc))


def test_index_inputs_and_snapshot_facts_read_the_manifests(data_dir: Path) -> None:
    inputs = index_inputs(data_dir, the_version(data_dir))
    assert inputs["schema_version"] == SCHEMA_VERSION and inputs["snapshot"] == "snap"
    facts = snapshot_facts(data_dir, inputs)
    window = json.loads((data_dir / "snapshots" / "snap" / "manifest.json").read_text())["crawl_window"]
    assert facts.crawl_dates == {"*": window}
    dedup = facts.dedup
    assert (dedup.merged, dedup.ambiguous_not_merged) == (2, 1)  # the manifest's merges.total, one ambiguous
    assert (dedup.track_not_merged, dedup.venue_year_not_merged) == (1, 1)


def test_a_ris_only_snapshot_is_not_citable_and_its_window_is_scholar_query_dates(data_dir: Path) -> None:
    """A bootstrap corpus (RIS only: an earlier Scholar search's output) is not a database: its counts are
    not PRISMA identification numbers, and its window is Publish or Perish's query dates, in local time."""
    facts = snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))
    assert facts.sources == ["ris"] and facts.identification_citable is False
    assert facts.crawl_dates_kind == {"*": "scholar_query_dates"}


def test_a_source_with_its_own_crawl_window_gets_its_own_key(data_dir: Path) -> None:
    path = data_dir / "snapshots" / "snap" / "manifest.json"
    own = {"from": "2026-03-01T00:00:00+00:00", "to": "2026-03-02T00:00:00+00:00"}
    edit(path, sources={"ris": [], "openreview_v2": {"crawl_window": own}})
    facts = snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))
    assert set(facts.crawl_dates) == {"*", "openreview_v2"} and facts.crawl_dates["openreview_v2"] == own
    assert facts.sources == ["openreview_v2", "ris"] and facts.identification_citable is True
    assert facts.crawl_dates_kind == {"*": "mixed", "openreview_v2": "crawl"}
    edit(path, sources={"openreview_v2": {"crawl_window": own}})
    crawled = snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))
    assert crawled.crawl_dates_kind == {"*": "crawl", "openreview_v2": "crawl"}


def test_the_cli_and_the_record_share_one_bootstrap_test() -> None:
    from openproceedings import cli, vocab

    assert records.bootstrap_only is vocab.bootstrap_only and cli.bootstrap_only is vocab.bootstrap_only
    assert vocab.bootstrap_only(["ris"]) and not vocab.bootstrap_only(["ris", "openreview_v2"])
    assert not vocab.bootstrap_only([])  # no sources named: not known to be a bootstrap corpus


@pytest.mark.parametrize(
    "window",
    [
        {"from": None, "to": "2026-01-01T00:00:00+00:00"},
        {"from": "yesterday", "to": "2026-01-01"},
        {"from": "2026-01-01"},
    ],
)
def test_a_crawl_window_that_is_not_iso_dates_is_refused(data_dir: Path, window: dict[str, Any]) -> None:
    edit(data_dir / "snapshots" / "snap" / "manifest.json", crawl_window=window)
    with pytest.raises(InternalError):
        snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))


@pytest.mark.parametrize(
    "inputs_change",
    [
        {"snapshot": "../snap"},
        {"snapshot": ".hidden"},
        {"snapshot": ""},
        {"snapshot_hash": "0" * 64},
        {"snapshot": "gone"},
    ],
)
def test_snapshot_facts_refuse_a_snapshot_that_is_not_the_indexs(
    data_dir: Path, inputs_change: dict[str, Any]
) -> None:
    inputs = {**index_inputs(data_dir, the_version(data_dir)), **inputs_change}
    with pytest.raises(InternalError):
        snapshot_facts(data_dir, inputs)


def test_snapshot_facts_refuse_a_manifest_that_names_no_sources(data_dir: Path) -> None:
    """No `sources` key is not evidence of a crawl (it would read as citable with a crawl window): a 500."""
    path = data_dir / "snapshots" / "snap" / "manifest.json"
    doc = json.loads(path.read_text())
    del doc["sources"]
    os.chmod(path, 0o644)
    path.write_text(json.dumps(doc))
    with pytest.raises(InternalError):
        snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))


def test_a_v2_body_whose_window_kinds_name_other_keys_is_refused(store: RecordStore) -> None:
    body = {**fields(), "record_id": "kindkindkind", "crawl_dates_kind": {"other": "crawl"}}
    insert_raw(store, "kindkindkind", json.dumps(body), IDS)
    with pytest.raises(InternalError):
        store.get("kindkindkind")


def test_a_drawn_record_id_starting_with_a_formula_character_is_drawn_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draws = iter(["-abcdefghijk", "_abcdefghijk", "Zabcdefghijk"])
    monkeypatch.setattr(records.secrets, "token_urlsafe", lambda n: next(draws))
    assert records.new_record_id() == "Zabcdefghijk"


def test_snapshot_facts_refuse_a_manifest_without_merge_counts(data_dir: Path) -> None:
    edit(data_dir / "snapshots" / "snap" / "manifest.json", merges={})
    with pytest.raises(InternalError):
        snapshot_facts(data_dir, index_inputs(data_dir, the_version(data_dir)))


def test_index_inputs_refuse_a_bad_name_and_a_manifest_that_does_not_give_its_version(data_dir: Path) -> None:
    for name in ("current", "../x", "ABC"):
        with pytest.raises(InternalError):
            index_inputs(data_dir, name)
    version = the_version(data_dir)
    edit(data_dir / "indexes" / version / "manifest.json", schema_version="999")
    with pytest.raises(InternalError):
        index_inputs(data_dir, version)


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("snapshot_hash", "0" * 64, "corpus"),
        ("tokenizer_version", "old", "method"),
        ("schema_version", "1", "method"),
        ("ranking_params", {"bm25": {"b": 0.5, "k1": 1.2}}, "method"),
    ],
)
def test_changed_inputs_name_each_input_and_its_kind(field: str, value: Any, kind: str) -> None:
    current = {
        k: fields()[k] for k in ("snapshot_hash", "tokenizer_version", "schema_version", "ranking_params")
    }
    record = SearchRecord.model_validate(
        {**fields(**{field: value}), "record_id": "AAAAAAAAAAAA", "ids": IDS}
    )
    changed = changed_inputs(record, current, "1")
    assert [(c.input, c.kind, c.recorded, c.current) for c in changed] == [
        (field, kind, value, current[field])
    ]
    assert [c.input for c in changed_inputs(record, current, "2")] == [field, "query_version"]


@dataclass(frozen=True)
class NoEngine:
    """Only an index_version: `freeze` must refuse before it ever searches."""

    index_version: str


def test_freeze_refuses_a_query_that_did_not_parse(data_dir: Path) -> None:
    engine: Any = NoEngine(the_version(data_dir))
    with pytest.raises(InternalError):
        records.freeze(engine, parse("(trust"), "(trust", data_dir)


def test_freeze_refuses_an_index_built_with_another_tokenizer(data_dir: Path) -> None:
    version = the_version(data_dir)
    manifest = json.loads((data_dir / "indexes" / version / "manifest.json").read_text())
    old = index_version_of(manifest["snapshot_hash"], "0")
    (data_dir / "indexes" / old).mkdir()
    (data_dir / "indexes" / old / "manifest.json").write_text(
        json.dumps({**manifest, "index_version": old, "tokenizer_version": "0"})
    )
    assert index_inputs(data_dir, old)["tokenizer_version"] == "0"
    engine: Any = NoEngine(old)
    with pytest.raises(InternalError):
        records.freeze(engine, parse("trust"), "trust", data_dir)
