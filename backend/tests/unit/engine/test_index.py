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
from openproceedings.ingest.snapshot import SnapshotError, render

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
    assert index_version("0" * 64, "2", "1") == "64bef1c5aeb6"


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
    [stored] = doc["record"]
    record = idx.record_of(stored)
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
        and manifest["schema_version"] == "3"
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
    rewrite_manifest(snap, {"snapshot_hash": "0" * 64})
    with pytest.raises(Exception, match="doesn't match its manifest"):
        build_index(snap, tmp_path / "indexes", BUILT)
    assert [p.name for p in (tmp_path / "indexes").iterdir() if p.name != ".lock"] == []  # nothing placed


def test_a_failed_build_releases_its_writer_before_removing_its_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failing frame's traceback keeps the writer alive; unless it is stopped first, Tantivy can rewrite
    its lock file after `rmtree` has walked the directory, and the `.tmp-*` survives (M3a review gate round
    2). Checked at the moment of removal: another writer can take the directory's lock, so none holds it."""
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    rewrite_manifest(snap, {"snapshot_hash": "0" * 64})
    rmtree = idx.shutil.rmtree
    checked: list[str] = []

    def removing(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path).name.startswith(".tmp-"):
            tantivy.Index.open(str(path)).writer(num_threads=1).wait_merging_threads()  # LockBusy if held
            checked.append(Path(path).name)
        rmtree(path, *args, **kwargs)

    monkeypatch.setattr(idx.shutil, "rmtree", removing)
    with pytest.raises(SnapshotError, match="doesn't match its manifest"):
        build_index(snap, tmp_path / "indexes", BUILT, workers=1)
    assert len(checked) == 1


def test_failed_builds_never_leave_their_directory(tmp_path: Path) -> None:
    """Many failing builds, each checked at once (the next build's sweep would hide a leftover)."""
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    rewrite_manifest(snap, {"snapshot_hash": "0" * 64})
    indexes = tmp_path / "indexes"
    for _ in range(40):
        with pytest.raises(SnapshotError):
            build_index(snap, indexes, BUILT, workers=1)
        assert [p.name for p in indexes.iterdir() if p.name != ".lock"] == []


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
    docs = [searcher.doc(a).to_dict() for _, a in searcher.search(tantivy.Query.all_query(), 10_000).hits]
    return {d["id"][0]: (d["title"], d["abstract"]) for d in docs}


def test_parallel_normalizing_builds_the_same_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    serial = build_index(snap, tmp_path / "one", BUILT, workers=1)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)  # force worker processes even for three records
    parallel = build_index(snap, tmp_path / "two", BUILT, workers=2)
    assert serial.index_version == parallel.index_version
    assert stored(serial.path) == stored(parallel.path) and len(stored(serial.path)) == 3


# --- review rows (task-023 review, 2026-09-26) ---------------------------------------------------------------


def test_the_record_field_is_never_indexed(built: Path) -> None:
    index = open_index(built)
    with pytest.raises(ValueError, match="not indexed"):
        index.searcher().search(tantivy.Query.term_query(index.schema, "record", b"trust"), 1)


def rewrite_manifest(path: Path, change: dict[str, Any]) -> None:
    manifest_path = path / "manifest.json"
    manifest_path.chmod(0o644)
    manifest = json.loads(manifest_path.read_text())
    manifest_path.write_text(json.dumps({**manifest, **change}))


@pytest.mark.parametrize(
    ("change", "message"),
    [({"snapshot_hash": "1" * 64}, "inputs don't give"), ({"ranking_params": {"bm25": {}}}, "inputs don't give"),
     ({"index_version": "000000000000"}, "inputs don't give"), ({"doc_count": 99}, "document count")],
)  # fmt: skip
def test_a_changed_manifest_is_refused(built: Path, change: dict[str, Any], message: str) -> None:
    rewrite_manifest(built, change)
    with pytest.raises(IndexBuildError, match=message):
        verify_index(built)


def test_a_rebuild_reseals_a_writable_index(built: Path, tmp_path: Path) -> None:
    victim = next(p for p in built.iterdir() if p.suffix == ".store")
    victim.chmod(0o644)  # as if a crash hit between placing and sealing
    build_index(tmp_path / "snap", tmp_path / "indexes", BUILT)
    assert stat.S_IMODE(victim.stat().st_mode) == 0o444


def test_the_token_limit_counts_utf8_bytes(tmp_path: Path) -> None:
    kept = paper("AbCd1234", "ø" * (MAX_TOKEN_BYTES // 2))  # 65,530 bytes
    built = build_index(snapshot_of([kept], tmp_path / "a"), tmp_path / "ia", BUILT).path
    assert hits(open_index(built), "title", "ø" * (MAX_TOKEN_BYTES // 2)) == 1
    over = paper("AbCd1234", "ø" * (MAX_TOKEN_BYTES // 2) + "x")  # 65,531 bytes, but only 32,766 characters
    with pytest.raises(IndexBuildError, match="over 65530 bytes"):
        build_index(snapshot_of([over], tmp_path / "b"), tmp_path / "ib", BUILT)


def test_records_out_of_id_order_are_refused(tmp_path: Path) -> None:
    snap = snapshot_of(CORPUS, tmp_path / "snap")
    lines = (snap / "records.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    data = "".join(reversed(lines)).encode("utf-8")
    (snap / "records.jsonl").write_bytes(data)
    rewrite_manifest(snap, {"snapshot_hash": __import__("hashlib").sha256(data).hexdigest()})
    with pytest.raises(Exception, match="not sorted by id"):
        build_index(snap, tmp_path / "indexes", BUILT)


def many(n: int) -> list[PaperRecord]:
    words = ["trust", "calibration", "reliance", "benchmark", "judge", "agent"]
    return [
        paper(
            f"Id{i:06d}",
            f"{words[i % 6]} {words[(i * 7) % 6]} study {i}",
            abstract=f"We {words[i % 5]} it {i}.",
        )
        for i in range(n)
    ]


def test_parallel_chunks_keep_every_record_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = snapshot_of(many(600), tmp_path / "snap")
    serial = stored(build_index(snap, tmp_path / "one", BUILT, workers=1).path)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    monkeypatch.setattr(idx, "CHUNK", 128)  # several chunks, several pool.map calls
    parallel = stored(build_index(snap, tmp_path / "two", BUILT, workers=3).path)
    assert parallel == serial and len(parallel) == 600


def test_two_builds_give_the_same_scores(tmp_path: Path) -> None:
    snap = snapshot_of(many(300), tmp_path / "snap")

    def scores(path: Path) -> dict[str, float]:
        index = open_index(path)
        searcher = index.searcher()
        q = tantivy.Query.term_query(index.schema, "title", "trust")
        return {searcher.doc(a).to_dict()["id"][0]: s for s, a in searcher.search(q, 500).hits}

    a, b = (
        scores(build_index(snap, tmp_path / "one", BUILT).path),
        scores(build_index(snap, tmp_path / "two", BUILT).path),
    )
    assert a == b and len(a) > 10


def test_a_dead_worker_is_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures.process import BrokenProcessPool

    class Dying:
        def __init__(self, **kw: Any) -> None:
            pass

        def map(self, *a: Any, **kw: Any) -> Any:
            raise BrokenProcessPool("killed")

        def shutdown(self, **kw: Any) -> None:
            pass

    monkeypatch.setattr(idx, "ProcessPoolExecutor", Dying)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    with pytest.raises(IndexBuildError, match="worker process died"):
        build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT, workers=2)
    assert [p.name for p in (tmp_path / "indexes").iterdir() if p.name != ".lock"] == []


def test_ranking_numbers_are_canonical() -> None:
    as_int = {**RANKING_PARAMS, "field_weights": {"abstract": 1, "title": 2}}
    assert index_version("0" * 64, "2", "1", as_int) == index_version("0" * 64, "2", "1", RANKING_PARAMS)


def test_cli_hash_prefix_never_matches_a_staging_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snaps = tmp_path / "data" / "snapshots"
    snap = snapshot_of(CORPUS, snaps / "2026-09-01-abc")
    import shutil

    shutil.copytree(snap, snaps / ".tmp-crashed")  # a crashed build's leftover with the same hash
    prefix = json.loads((snap / "manifest.json").read_text())["snapshot_hash"][:8]
    assert cli.resolve_snapshot(prefix, snaps) == snap


# --- verification rows (task-023, 2026-09-26) --------------------------------------------------------------


def test_verify_follows_the_current_symlink(built: Path) -> None:
    current = built.parent / "current"
    current.symlink_to(built.name)
    assert verify_index(current)["index_version"] == built.name


def test_an_index_under_another_name_is_refused(built: Path, tmp_path: Path) -> None:
    import shutil

    copy = tmp_path / "copy"
    shutil.copytree(built, copy)
    with pytest.raises(IndexBuildError, match="inputs don't give"):
        verify_index(copy)


def test_an_id_tantivy_would_drop_refuses_the_build(tmp_path: Path) -> None:
    long = paper("pmlr-v202-" + "k" * MAX_TOKEN_BYTES, venue="ICML", source="pmlr",
                 urls_proceedings=None, urls_pdf="https://proceedings.mlr.press/v202/" + "k" * MAX_TOKEN_BYTES + ".pdf")  # fmt: skip
    with pytest.raises(IndexBuildError, match="the id is over"):
        build_index(snapshot_of([long], tmp_path / "snap"), tmp_path / "indexes", BUILT)


def test_every_display_field_is_stored(tmp_path: Path) -> None:
    rich = paper("AbCd1234", "Trust", abstract="An abstract.", authors=("Doe, J", "Roe, R"),
                 keywords=("trust", "llm"), presentation="oral", venue_id_raw="NeurIPS.cc/2024/Conference",
                 urls_forum="https://openreview.net/forum?id=AbCd1234")  # fmt: skip
    path = build_index(snapshot_of([rich], tmp_path / "snap"), tmp_path / "indexes", BUILT).path
    index = open_index(path)
    searcher = index.searcher()
    [(_, address)] = searcher.search(tantivy.Query.all_query(), 1).hits
    [raw] = searcher.doc(address).to_dict()["record"]
    assert idx.record_of(raw) == {
        "title": "Trust", "abstract": "An abstract.", "authors": ["Doe, J", "Roe, R"],
        "urls": rich.urls.model_dump(), "presentation": "oral", "keywords": ["trust", "llm"],
        "venue_id_raw": "NeurIPS.cc/2024/Conference",
    }  # fmt: skip
    compact = json.dumps(idx.record_of(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert raw == compact.encode("utf-8")  # compact canonical JSON


def test_a_bool_is_not_a_ranking_number() -> None:
    assert index_version("0" * 64, "2", "1", {"b": True}) != index_version("0" * 64, "2", "1", {"b": 1.0})


def test_a_placed_index_that_fails_verification_says_to_retire_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = idx.verify_index
    calls = []

    def failing_once(path: Path) -> Any:
        calls.append(path)
        if len(calls) == 1:
            raise IndexBuildError("simulated")
        return real(path)

    monkeypatch.setattr(idx, "verify_index", failing_once)
    with pytest.raises(IndexBuildError, match="retire it and build again"):
        build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT)
    with pytest.raises(IndexBuildError, match="retire it and build again"):  # and so does every later build
        monkeypatch.setattr(
            idx, "verify_index", lambda p: (_ for _ in ()).throw(IndexBuildError("still broken"))
        )
        build_index(tmp_path / "snap", tmp_path / "indexes", BUILT)


def test_an_opened_index_is_read_with_a_manual_reload_policy(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-165: tantivy-py's `Index.open` starts a reader that a meta.json watcher thread reloads, and each
    reload creates `.tantivy-meta.lock` again, a write that lands in the directory after `open` returns
    (measured: 190 of 200 opens) and failed an `rmtree` of it. `open_index` replaces that reader at once with a
    manual one, so a built index is never reloaded behind the caller's back (the watcher's first poll can still
    beat it: 12 of 200, within 9 ms; tests remove an index by renaming it away, `test_record_cli.take_away`).
    The watcher's timing can't be observed from Python, so this checks the call, not the race."""
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real = tantivy.Index.config_reader

    def spy(self: tantivy.Index, *args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))
        real(self, *args, **kwargs)

    monkeypatch.setattr(tantivy.Index, "config_reader", spy)
    index = open_index(built)
    assert calls == [((), {"reload_policy": "manual"})]
    assert index.searcher().num_docs == len(CORPUS)
