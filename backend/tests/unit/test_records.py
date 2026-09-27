"""`ids_hash` known answers and the append-only record store (spec 04 §Search records; search-records skill)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from openproceedings import records
from openproceedings.diagnostics import InternalError
from openproceedings.records import RECORD_ID, RecordStore, ids_hash, valid_record_id


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
def fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
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
        "crawl_dates": {"all": {"from": "2026-01-01T00:00:00+00:00", "to": "2026-01-02T00:00:00+00:00"}},
        "searched_at": "2026-09-27T12:00:00Z",
        "total": 2,
        "excluded": {"total": 1, "track": {"workshop": 1, "unknown": 0}, "status": {"unknown": 0}},
        "expansions": {},
        "translations": [],
        "warnings": [],
        "ids_hash": ids_hash(["op:a", "op:b"]),
        "dedup": {"merged": 0, "ambiguous_not_merged": 0},
        "semantic_version": None,
    }
    return {**base, **overrides}


def test_insert_then_get_round_trips_every_field(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    saved = store.insert(fields(), ["op:a", "op:b"])
    got = store.get(saved.record_id)
    assert got == saved and got is not None
    assert got.ids == ["op:a", "op:b"]
    assert list(got.excluded.track) == ["workshop", "unknown"]  # the stored bucket order is kept
    assert store.pinned("0123456789ab") == 1 and store.pinned("ffffffffffff") == 0


def test_a_read_never_creates_the_store(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    assert store.get("abcdefghijkl") is None and store.pinned("0123456789ab") == 0
    assert not (tmp_path / "records.sqlite").exists()


def test_store_uses_wal_and_records_its_schema_version(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    store.insert(fields(), ["op:a", "op:b"])
    conn = sqlite3.connect(tmp_path / "records.sqlite")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    finally:
        conn.close()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE records SET body = '{}'",
        "UPDATE records SET index_version = 'ffffffffffff'",
        "DELETE FROM records",
        "UPDATE schema_version SET version = 2",
        "DELETE FROM schema_version",
    ],
)
def test_update_and_delete_are_refused_by_the_triggers(tmp_path: Path, statement: str) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    saved = store.insert(fields(), ["op:a", "op:b"])
    conn = sqlite3.connect(tmp_path / "records.sqlite")  # a plain connection: the triggers live in the file
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(statement)
    finally:
        conn.close()
    assert store.get(saved.record_id) == saved


@pytest.mark.parametrize("statement", ["INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE", "INSERT"])
@pytest.mark.parametrize("own", [True, False])
def test_an_existing_id_is_never_replaced(tmp_path: Path, statement: str, own: bool) -> None:
    """SQLite's REPLACE deletes the old row without firing DELETE triggers unless `recursive_triggers` is on;
    the BEFORE INSERT trigger refuses it from any client (`own`: the store's connection, else a plain one)."""
    store = RecordStore(tmp_path / "records.sqlite")
    saved = store.insert(fields(), ["op:a", "op:b"])
    conn = store._connect() if own else sqlite3.connect(tmp_path / "records.sqlite")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(f"{statement} INTO records VALUES (?, 'x', 'x', '{{}}', x'')", (saved.record_id,))
    finally:
        conn.close()
    assert store.get(saved.record_id) == saved


def test_a_taken_id_is_redrawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    draws = iter(["AAAAAAAAAAAA", "AAAAAAAAAAAA", "BBBBBBBBBBBB"])
    monkeypatch.setattr(records, "new_record_id", lambda: next(draws))
    first = store.insert(fields(), ["op:a", "op:b"])
    second = store.insert(fields(input="other"), ["op:a", "op:b"])
    assert (first.record_id, second.record_id) == ("AAAAAAAAAAAA", "BBBBBBBBBBBB")
    assert store.get("AAAAAAAAAAAA") == first  # never overwritten


def test_ids_must_be_sorted_and_one_line(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    for ids in (["op:b", "op:a"], ["op:a\nop:b"]):
        with pytest.raises(InternalError):
            store.insert(fields(), ids)


def test_empty_id_list_round_trips(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    saved = store.insert(fields(total=0, ids_hash=ids_hash([])), [])
    assert store.get(saved.record_id) == saved and saved.ids == []


def test_concurrent_inserts_from_threads_each_get_their_own_row(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records.sqlite")
    saved: list[str] = []
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(10):
                saved.append(store.insert(fields(input=f"q{n}-{i}"), ["op:a", "op:b"]).record_id)
        except BaseException as e:  # surfaced below
            errors.append(e)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(saved)) == 80
    assert all(store.get(i) is not None for i in saved)
