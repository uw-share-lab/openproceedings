"""The Tantivy index: version id, analyzer, schema, build, immutability (tantivy-indexing and
index-versioning skills). Built from synthetic records only (decision-004)."""

from __future__ import annotations

import ast
import json
import logging
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

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
from openproceedings.query.normalize import SERVED_TOKENIZERS, TOKENIZER_VERSION

from tests.golden.test_tantivy_200 import as_paper
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
        and manifest["tokenizer_version"] == TOKENIZER_VERSION == "3"
        and manifest["schema_version"] == "4"
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
    before = victim.stat()
    original = victim.read_bytes()
    victim.chmod(0o644)
    # Tantivy may still map this inode: write_bytes truncates it to zero before writing, which can
    # SIGBUS a live reader on Linux. Append the same corruption without shrinking the mapped file.
    with victim.open("ab") as store:
        store.write(b"x")
    assert victim.stat().st_ino == before.st_ino
    assert victim.stat().st_size == before.st_size + 1
    assert victim.read_bytes() == original + b"x"
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


class Recorded(idx.ProcessPoolExecutor):
    """The real pool, recording each start (its worker count) and each shutdown in `events`."""

    events: ClassVar[list[str]] = []

    def __init__(self, **kw: Any) -> None:
        Recorded.events.append(f"start {kw['max_workers']}")
        super().__init__(**kw)

    def shutdown(self, *a: Any, **kw: Any) -> None:
        Recorded.events.append("shutdown")
        super().shutdown(*a, **kw)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(Recorded, "events", [])
    monkeypatch.setattr(idx, "ProcessPoolExecutor", Recorded)
    return Recorded.events


def test_the_conftest_override_keeps_default_builds_and_checks_in_one_process(
    tmp_path: Path, recorded: list[str]
) -> None:
    """TASK-284: in the test session (conftest's `_serial_index_builds`), a build or parity check at its default
    workers starts no pool, even for a corpus at the product's PARALLEL_FROM (10,000 records). This checks the
    override, not the product's boundary (the 40/41 rows below do that at a patched threshold). At the old 2,000,
    each of about 60 builds of the 5k fixture started a spawn pool of `os.cpu_count()` workers inside every xdist
    worker: at 5,000 fixture records, 0.45 s wall against 0.33 s serial and 2.17 s CPU against 0.33 s
    (docs/results/2026-10-24-parallel-normalize-crossover.md)."""
    from openproceedings.engine.parity import check_parity

    snap = snapshot_of(many(10_000), tmp_path / "snap")
    built = build_index(snap, tmp_path / "indexes", BUILT)
    assert check_parity(built.path, snap).records == 10_000
    assert recorded == []


def test_the_products_threshold_is_the_measured_one() -> None:
    """`PARALLEL_FROM` as the module source sets it (conftest overrides the attribute): the crossover note's
    10,000. Changing it needs a new measurement in that note."""
    tree = ast.parse(Path(idx.__file__).read_text(encoding="utf-8"))
    (value,) = (
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and [getattr(t, "id", None) for t in node.targets] == ["PARALLEL_FROM"]
        and isinstance(node.value, ast.Constant)
    )
    assert value == 10_000


@pytest.mark.parametrize(("records", "pools"), [(40, []), (41, ["start 2", "shutdown"])])
def test_the_record_count_not_the_first_chunk_decides_on_a_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: list[str], records: int, pools: list[str]
) -> None:
    """The manifest's record count against PARALLEL_FROM, read before the first chunk: a corpus over it gets its
    pool though every chunk is smaller (TASK-284), and the index is the serial one (guarantee 4)."""
    snap = snapshot_of(many(records), tmp_path / "snap")
    serial = stored(build_index(snap, tmp_path / "one", BUILT, workers=1).path)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 41)
    monkeypatch.setattr(idx, "CHUNK", 16)
    assert stored(build_index(snap, tmp_path / "two", BUILT, workers=2).path) == serial
    assert recorded == pools


@pytest.mark.parametrize("tokenizer", sorted(SERVED_TOKENIZERS))
def test_a_pool_normalizes_by_the_builds_tokenizer_as_the_serial_path_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: list[str], tokenizer: str
) -> None:
    """Guarantee 4 on the pool path, at every served tokenizer: text the tokenizers read differently (an NFD
    accent after a backslash, a full-width dollar: FORMS_CORPUS) gives the pool build the serial build's documents
    and index_version. The test session builds serially (conftest), so this row is what keeps a pinned older
    tokenizer's pool build covered (TASK-284 review)."""
    from tests.contract.test_records import FORMS_CORPUS

    snap = snapshot_of(
        sorted([*many(40), *(as_paper(r) for r in FORMS_CORPUS)], key=lambda p: p.id), tmp_path / "snap"
    )
    serial = build_index(snap, tmp_path / "one", BUILT, workers=1, tokenizer_version=tokenizer)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    monkeypatch.setattr(idx, "CHUNK", 16)
    pool = build_index(snap, tmp_path / "two", BUILT, workers=2, tokenizer_version=tokenizer)
    assert recorded == ["start 2", "shutdown"]
    assert pool.index_version == serial.index_version
    assert stored(pool.path) == stored(serial.path)


def test_a_pool_builds_the_5k_fixture_as_the_serial_path_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: list[str]
) -> None:
    """The synthetic 5k corpus (its LaTeX and Unicode), once through a pool and once serially: the same
    documents (guarantee 4), the coverage its pool builds gave before tests built serially (TASK-284)."""
    from tests.fixtures.corpus.synthetic_5k import records

    snap = snapshot_of(sorted((as_paper(r) for r in records()), key=lambda p: p.id), tmp_path / "snap")
    serial = build_index(snap, tmp_path / "one", BUILT, workers=1)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    pool = build_index(snap, tmp_path / "two", BUILT, workers=2)
    assert recorded == ["start 2", "shutdown"]
    assert pool.index_version == serial.index_version
    assert stored(pool.path) == stored(serial.path) and len(stored(pool.path)) == 5_000


def test_a_build_that_fails_part_way_has_shut_its_pool_when_the_error_arrives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: list[str]
) -> None:
    """The refusal reaches the caller with the pool already shut down, while its traceback still holds the
    failed build's frames (no garbage collection needed)."""
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    monkeypatch.setattr(idx, "CHUNK", 16)  # the bad record is in the third chunk: two were yielded
    over = paper("Zz999999", "ø" * (MAX_TOKEN_BYTES // 2) + "x")  # sorts after every `Id…` record
    snap = snapshot_of([*many(40), over], tmp_path / "snap")
    with pytest.raises(IndexBuildError, match="over 65530 bytes") as failed:
        build_index(snap, tmp_path / "indexes", BUILT, workers=2)
    assert failed.traceback and recorded == ["start 2", "shutdown"]


def test_a_parity_check_that_fails_part_way_has_shut_its_pool_when_the_error_arrives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: list[str]
) -> None:
    """`check_parity`'s twin of the row above: the index loses its 41st document (in the third chunk of 16), so
    ParityError is raised after two chunks were yielded, and the pool is already shut down when it arrives."""
    from openproceedings.engine import parity

    snap = snapshot_of(many(48), tmp_path / "snap")
    built = build_index(snap, tmp_path / "indexes", BUILT, workers=1)
    real = parity._stored

    def losing_one(*a: Any, **kw: Any) -> Any:
        for n, item in enumerate(real(*a, **kw)):
            if n != 40:
                yield item

    monkeypatch.setattr(parity, "_stored", losing_one)
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    monkeypatch.setattr(idx, "CHUNK", 16)
    with pytest.raises(parity.ParityError, match="Id000040: in the snapshot, not in the index") as failed:
        parity.check_parity(built.path, snap, workers=2)
    assert failed.traceback and recorded == ["start 2", "shutdown"]


def logged(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == event]


@pytest.mark.parametrize(("records", "parallel"), [(40, False), (41, True)])
def test_the_build_and_the_parity_check_log_their_workers_and_whether_they_pooled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    records: int,
    parallel: bool,
) -> None:
    from openproceedings.engine.parity import check_parity

    monkeypatch.setattr(idx, "PARALLEL_FROM", 41)
    snap = snapshot_of(many(records), tmp_path / "snap")
    with caplog.at_level(logging.INFO, logger="openproceedings"):
        built = build_index(snap, tmp_path / "indexes", BUILT, workers=2)
        check_parity(built.path, snap, workers=2)
    for event in ("index_build_started", "index_parity_ok"):
        (line,) = logged(caplog, event)
        assert (line.workers, line.parallel) == (2, parallel), event  # type: ignore[attr-defined]


@pytest.mark.parametrize("count", ['"80000"', None, "true", "80000.0"])
def test_an_unreadable_record_count_builds_serially_the_same_index_and_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    recorded: list[str],
    count: str | None,
) -> None:
    """A readable manifest whose `record_count` is missing or not a whole number: `iter_records` doesn't check it,
    so the build goes on serially, gives the serial index, and logs one WARNING naming the snapshot directory and
    the value's type (never the value)."""
    snap = snapshot_of(many(41), tmp_path / "snap")
    serial = stored(build_index(snap, tmp_path / "one", BUILT, workers=1).path)
    manifest = json.loads((snap / "manifest.json").read_text())
    if count is None:
        del manifest["record_count"]
    else:
        manifest["record_count"] = json.loads(count)
    (snap / "manifest.json").chmod(0o644)
    (snap / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(idx, "PARALLEL_FROM", 1)
    with caplog.at_level(logging.INFO, logger="openproceedings"):
        assert stored(build_index(snap, tmp_path / "two", BUILT, workers=2).path) == serial
    assert recorded == []
    (warning,) = logged(caplog, "snapshot_record_count_unreadable")
    assert warning.levelno == logging.WARNING and warning.snapshot == "snap"  # type: ignore[attr-defined]
    assert warning.error == type(manifest.get("record_count")).__name__  # type: ignore[attr-defined]


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


def test_an_id_tantivy_would_drop_refuses_the_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # no valid record's id comes near Tantivy's limit since ingest bounds native ids (decision-055: a key of at most
    # 200 characters), so the guard is shown at a limit lowered below the longest id one can hold
    key = "k" * 200
    long = paper(f"pmlr-v202-{key}", venue="ICML", source="pmlr",
                 urls_proceedings=None, urls_pdf=f"https://proceedings.mlr.press/v202/{key}.pdf")  # fmt: skip
    monkeypatch.setattr(idx, "MAX_TOKEN_BYTES", len(long.id) - 1)
    with pytest.raises(IndexBuildError, match="the id is over"):
        build_index(snapshot_of([long], tmp_path / "snap"), tmp_path / "indexes", BUILT)
    monkeypatch.setattr(idx, "MAX_TOKEN_BYTES", len(long.id))
    build_index(snapshot_of([long], tmp_path / "snap2"), tmp_path / "indexes", BUILT)  # at the limit: built


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


def test_a_build_reads_its_index_with_a_manual_reload_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-165: the build's own reader is manual too (it reloads once, explicitly, after the commit)."""
    calls: list[dict[str, Any]] = []
    real = tantivy.Index.config_reader

    def spy(self: tantivy.Index, *args: Any, **kwargs: Any) -> None:
        calls.append(kwargs)
        real(self, *args, **kwargs)

    monkeypatch.setattr(tantivy.Index, "config_reader", spy)
    monkeypatch.setattr(idx, "verify_index", lambda path: {})  # only the build's own reader is counted
    build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT, workers=1)
    assert calls == [{"reload_policy": "manual"}]
