"""The Tantivy index: version id, analyzer, schema, build, immutability (tantivy-indexing and
index-versioning skills). Built from synthetic records only (decision-004)."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import tantivy
from openproceedings import cli
from openproceedings.engine import index as idx
from openproceedings.engine.index import (
    MAX_TOKEN_BYTES,
    RANKING_PARAMS,
    IndexBuildError,
    analyzer,
    build_index,
    index_version,
    open_index,
    verify_index,
)
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import render

from tests.unit.ingest.test_dedup import H, paper

BUILT = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def snapshot_of(records: list[PaperRecord], directory: Path) -> Path:
    """A snapshot directory holding exactly `records` (no dedup: they are the corpus)."""
    directory.mkdir(parents=True)
    for name, data in render(DedupResult(tuple(records), (), ()), [], BUILT).items():
        (directory / name).write_bytes(data)
    return directory


CORPUS = [
    paper("AbCd1234", "Trust in Ørsted's Models", abstract="We study trust calibration."),
    paper("EfGh5678", "LLM-as-a-Judge", abstract=None, venue="ICLR", track="workshop"),
    paper(
        f"nips-{H[1]}",
        "Naïve Bayes Benchmarks",
        source="neurips_proceedings",
        abstract="A $\\alpha$-DP bound.",
    ),
]


@pytest.fixture
def built(tmp_path: Path) -> Path:
    return build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT).path


def hits(index: tantivy.Index, field: str, term: str) -> int:
    return int(index.searcher().search(tantivy.Query.term_query(index.schema, field, term), 10).count)


# --- the version id ----------------------------------------------------------------------------------------


def test_index_version_serialization_is_pinned() -> None:
    # sha256 of {"ranking_params":…,"schema_version":"1","snapshot_hash":"0…0","tokenizer_version":"2"}
    # with sorted keys and no whitespace; changing the serialization changes every index id
    assert index_version("0" * 64, "2", "1") == "6208c84b36b6"


@pytest.mark.parametrize(
    "change",
    [{"snapshot_hash": "1" * 64}, {"tokenizer_version": "3"}, {"schema_version": "2"},
     {"ranking_params": {**RANKING_PARAMS, "bm25": {"b": 0.75, "k1": 1.3}}}],
)  # fmt: skip
def test_every_input_changes_the_version(change: dict[str, Any]) -> None:
    base = {
        "snapshot_hash": "0" * 64,
        "tokenizer_version": "2",
        "schema_version": "1",
        "ranking_params": RANKING_PARAMS,
    }
    assert index_version(**{**base, **change}) != index_version(**base)


# --- the analyzer and schema -------------------------------------------------------------------------------


def test_exact_v1_only_splits_on_whitespace() -> None:
    a = analyzer()
    assert a.analyze("Ørsted ørsted LLM α1 naïve") == ["Ørsted", "ørsted", "LLM", "α1", "naïve"]  # no folding
    assert a.analyze("a  b\tc\nd") == ["a", "b", "c", "d"]
    assert a.analyze("x" * 70_000) == ["x" * 70_000]  # no length filter in the analyzer itself


def test_the_index_holds_the_token_contracts_output(built: Path) -> None:
    index = open_index(built)
    assert hits(index, "title", "ørsted") == 1 and hits(index, "title", "orsted") == 0  # never ASCII-folded
    assert hits(index, "title", "naive") == 1  # normalize() folded the accent, the analyzer kept it
    assert hits(index, "title", "Trust") == 0 and hits(index, "title", "trust") == 1  # lower-cased upstream
    assert hits(index, "abstract", "α") == 1 and hits(index, "abstract", "alpha") == 0  # decision-006
    assert hits(index, "venue", "ICLR") == 1 and hits(index, "venue", "iclr") == 0  # facets are raw
    assert hits(index, "id", "op:neurips:2024:AbCd1234") == 1


def test_phrases_use_positions(built: Path) -> None:
    index = open_index(built)
    phrase = tantivy.Query.phrase_query(index.schema, "title", ["as", "a", "judge"])
    assert index.searcher().search(phrase, 10).count == 1


def test_stored_display_text_and_the_unindexed_record(built: Path) -> None:
    index = open_index(built)
    searcher = index.searcher()
    [(_, address)] = searcher.search(tantivy.Query.term_query(index.schema, "title", "ørsted"), 1).hits
    doc = searcher.doc(address).to_dict()
    assert doc["title"] == ["trust in ørsted s models"]  # the indexed field stores the token stream
    [record] = doc["record"]
    assert record["title"] == "Trust in Ørsted's Models"  # the display text lives in the stored record
    assert doc["year"] == [2024]


def test_a_missing_abstract_is_an_empty_field(built: Path) -> None:
    index = open_index(built)
    searcher = index.searcher()
    [(_, address)] = searcher.search(tantivy.Query.term_query(index.schema, "title", "judge"), 1).hits
    assert searcher.doc(address).to_dict()["abstract"] == [""]


# --- build, verify, immutability ---------------------------------------------------------------------------


def test_build_writes_a_verified_manifest(built: Path) -> None:
    manifest = verify_index(built)
    assert built.name == manifest["index_version"]
    assert (
        manifest["doc_count"] == 3
        and manifest["tokenizer_version"] == "2"
        and manifest["schema_version"] == "1"
    )
    assert manifest["ranking_params"] == RANKING_PARAMS and manifest["tantivy_version"] == "0.26.2"
    assert manifest["built_at"] == "2026-09-26T12:00:00+00:00"
    assert manifest["files"] and all(
        stat.S_IMODE((built / f).stat().st_mode) == 0o444 for f in manifest["files"]
    )


def test_a_rebuild_verifies_and_reports_the_existing_index(built: Path, tmp_path: Path) -> None:
    again = build_index(tmp_path / "snap", tmp_path / "indexes", datetime(2027, 1, 1, tzinfo=UTC))
    assert (again.path, again.created) == (built, False)
    assert not list((tmp_path / "indexes").glob(".tmp-*"))


def test_a_changed_index_is_refused(built: Path, tmp_path: Path) -> None:
    victim = next(p for p in built.iterdir() if p.suffix == ".store")
    victim.chmod(0o644)
    victim.write_bytes(victim.read_bytes() + b"x")
    with pytest.raises(IndexBuildError, match="don't match its manifest"):
        verify_index(built)
    with pytest.raises(IndexBuildError, match="don't match its manifest"):
        build_index(tmp_path / "snap", tmp_path / "indexes", BUILT)


def test_the_same_snapshot_builds_the_same_documents_in_the_same_order(tmp_path: Path) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    a = open_index(build_index(snap, tmp_path / "one", BUILT).path)
    b = open_index(build_index(snap, tmp_path / "two", BUILT).path)

    def ids(index: tantivy.Index) -> list[str]:
        searcher = index.searcher()
        found = searcher.search(tantivy.Query.all_query(), 10).hits
        return [
            searcher.doc(address).to_dict()["id"][0]
            for _, address in sorted(found, key=lambda h: (h[1].segment_ord, h[1].doc))
        ]

    assert ids(a) == ids(b) == sorted(r.id for r in CORPUS)


def test_a_token_tantivy_would_drop_refuses_the_build(tmp_path: Path) -> None:
    long = paper("AbCd1234", "x" * (MAX_TOKEN_BYTES + 1))
    with pytest.raises(IndexBuildError, match="over 65530 bytes"):
        build_index(snapshot_of([long], tmp_path / "snap"), tmp_path / "indexes", BUILT)
    assert [p.name for p in (tmp_path / "indexes").iterdir() if p.name != ".lock"] == []
    ok = paper("AbCd1234", "x" * MAX_TOKEN_BYTES)  # the limit itself is kept
    built = build_index(snapshot_of([ok], tmp_path / "snap2"), tmp_path / "indexes", BUILT).path
    assert hits(open_index(built), "title", "x" * MAX_TOKEN_BYTES) == 1


def test_an_analyzer_that_disagrees_with_normalize_refuses_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folding = (
        tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.whitespace())
        .filter(tantivy.Filter.ascii_fold())
        .build()
    )
    monkeypatch.setattr(idx, "analyzer", lambda: folding)
    with pytest.raises(IndexBuildError, match="tokenizer parity"):
        build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT)


def test_a_tampered_snapshot_is_refused(tmp_path: Path) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    (snap / "records.jsonl").write_bytes((snap / "records.jsonl").read_bytes() + b"\n")
    with pytest.raises(Exception, match="doesn't match its manifest"):
        build_index(snap, tmp_path / "indexes", BUILT)


# --- CLI ---------------------------------------------------------------------------------------------------


def test_cli_index_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "data" / "snapshots" / "2026-09-01-abc")
    data = ["--data-dir", str(tmp_path / "data")]
    manifest = json.loads((snap / "manifest.json").read_text())
    for spec in (str(snap), snap.name, manifest["snapshot_hash"][:8]):  # a path, a name, a hash prefix
        assert cli.main([*data, "index", "build", "--snapshot", spec]) == 0
        out = json.loads(capsys.readouterr().out)
        assert Path(out["path"]).parent == tmp_path / "data" / "indexes"
    assert cli.main([*data, "index", "build", "--snapshot", "nope"]) == 1
    assert "no snapshot matches" in capsys.readouterr().err


def stored(path: Path) -> dict[str, tuple[Any, Any]]:
    index = open_index(path)
    searcher = index.searcher()
    docs = [searcher.doc(a).to_dict() for _, a in searcher.search(tantivy.Query.all_query(), 100).hits]
    return {d["id"][0]: (d["title"], d["abstract"]) for d in docs}


def test_parallel_normalizing_builds_the_same_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    serial = build_index(snap, tmp_path / "one", BUILT, workers=1)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)  # force worker processes even for three records
    parallel = build_index(snap, tmp_path / "two", BUILT, workers=2)
    assert serial.index_version == parallel.index_version
    assert stored(serial.path) == stored(parallel.path) and len(stored(serial.path)) == 3
