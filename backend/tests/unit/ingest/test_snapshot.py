"""Snapshots: layout, determinism, immutability, diff and the CLI (snapshots skill), on the synthetic RIS
fixture (decision-004)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from openproceedings import cli, storage
from openproceedings.ingest import snapshot as snap
from openproceedings.ingest.dedup import DedupResult, attribution, dedup
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import (
    DISPLAY,
    HASHED,
    RecordFile,
    SnapshotError,
    build,
    diff,
    ingest_ris,
    load_cache,
    load_records,
    record_line,
    render,
)

from tests.unit.ingest.test_dedup import H, paper

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ris"
BUILT = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
WORKSHOP, REJECTED = "op:icml:2026:AbCdEf1234", "op:iclr:2024:Rej_ected-1"
NEURIPS = "op:neurips:2025:nips-0123456789abcdef0123456789abcdef"
PMLR = "op:icml:2023:pmlr-v202-smith23a"


def source(tmp_path: Path, name: str = "search-a", edit: Callable[[str], str] = lambda t: t) -> Path:
    """A copy of the fixture in `<tmp>/src/<name>/`, both files passed through `edit`."""
    src = tmp_path / "src" / name
    src.mkdir(parents=True)
    for f in ("mended.ris", "resolved.json"):
        (src / f).write_text(edit((FIXTURE / f).read_text(encoding="utf-8")), encoding="utf-8")
    return src / "mended.ris"


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    ingest_ris([source(tmp_path)], tmp_path / "cache")
    return tmp_path / "cache"


def entries(directory: Path) -> list[str]:
    """What a directory holds, apart from its `.lock` file."""
    return sorted(p.name for p in directory.iterdir() if p.name != ".lock")


def writable_copy(snapshot: Path, out: Path) -> Path:
    shutil.copytree(snapshot, out)
    for p in [out, *out.iterdir()]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    return out


def rewrite(snapshot: Path, out: Path, edit: Callable[[dict[str, PaperRecord]], None]) -> Path:
    """A writable copy of `snapshot` whose records `edit` changed; its manifest hash is kept consistent."""
    records = load_records(snapshot)
    edit(records)
    writable_copy(snapshot, out)
    data = "".join(record_line(r) + "\n" for r in sorted(records.values(), key=lambda r: r.id)).encode(
        "utf-8"
    )
    (out / "records.jsonl").write_bytes(data)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["snapshot_hash"] = hashlib.sha256(data).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return out


# --- the cache ---------------------------------------------------------------------------------------------


def test_ingest_copies_both_files_and_is_idempotent(cache: Path, tmp_path: Path) -> None:
    cached = cache / "ris" / "search-a"
    assert sorted(p.name for p in cached.iterdir()) == ["mended.ris", "resolved.json"]
    assert (cached / "mended.ris").read_bytes() == (FIXTURE / "mended.ris").read_bytes()
    assert stat.S_IMODE(cached.stat().st_mode) == 0o555
    ingest_ris([tmp_path / "src" / "search-a" / "mended.ris"], cache)  # the same files again: no-op
    assert not list((cache / "ris").glob(".tmp-*"))


def test_ingest_refuses_different_files_under_a_cached_name(cache: Path, tmp_path: Path) -> None:
    changed = source(tmp_path / "other", edit=lambda t: t.replace("made-up", "invented"))
    with pytest.raises(SnapshotError, match="different files"):
        ingest_ris([changed], cache)


def test_a_cache_entry_missing_a_file_is_different(cache: Path, tmp_path: Path) -> None:
    entry = cache / "ris" / "search-a"
    entry.chmod(0o755)
    (entry / "resolved.json").chmod(0o644)
    (entry / "resolved.json").unlink()
    with pytest.raises(SnapshotError, match="different files"):
        ingest_ris([tmp_path / "src" / "search-a" / "mended.ris"], cache)


def test_ingest_is_all_or_nothing(tmp_path: Path) -> None:
    good = source(tmp_path, "search-a")
    bad = source(tmp_path, "search-b", edit=lambda t: "[]" if t.startswith("[") else t)
    with pytest.raises(ValueError, match="RIS records but"):
        ingest_ris([good, bad], tmp_path / "cache")
    assert entries(tmp_path / "cache" / "ris") == []  # nothing cached, no leftovers


def test_ingest_places_nothing_when_a_later_import_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    real = snap.import_ris

    def flaky(path: Path, **kw: Any) -> Any:
        calls.append(path)
        if len(calls) == 2:
            raise OSError(5, "disk error")
        return real(path, **kw)

    monkeypatch.setattr(snap, "import_ris", flaky)
    with pytest.raises(OSError):
        ingest_ris([source(tmp_path, "search-a"), source(tmp_path, "search-b")], tmp_path / "cache")
    assert entries(tmp_path / "cache" / "ris") == []


def test_ingest_needs_distinct_named_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = source(tmp_path / "x", "same")
    b = source(tmp_path / "y", "same")
    with pytest.raises(SnapshotError, match="share a directory name"):
        ingest_ris([a, b], tmp_path / "cache")
    monkeypatch.chdir(a.parent)  # a bare file name still resolves to its directory's name
    ingest_ris([Path("mended.ris")], tmp_path / "cache")
    assert (tmp_path / "cache" / "ris" / "same" / "mended.ris").exists()


def test_leftover_temp_and_hidden_directories_are_never_sources(cache: Path, tmp_path: Path) -> None:
    for hidden in (".tmp-crashed", ".hidden"):
        shutil.copytree(FIXTURE, cache / "ris" / hidden)
    _, reports = load_cache(cache)
    assert [r.file for r in reports] == ["search-a/mended.ris"]
    ingest_ris([tmp_path / "src" / "search-a" / "mended.ris"], cache)
    assert not (cache / "ris" / ".tmp-crashed").exists()  # swept


def test_reports_and_errors_name_the_cache_entry_not_the_staging_dir(tmp_path: Path) -> None:
    [report] = ingest_ris([source(tmp_path)], tmp_path / "cache")
    assert report.file == "search-a/mended.ris"
    bad = source(tmp_path / "b", "search-b", edit=lambda t: "[]" if t.startswith("[") else t)
    with pytest.raises(ValueError, match=r"^search-b/mended\.ris: 12 RIS records but 0"):
        ingest_ris([bad], tmp_path / "cache")


@pytest.mark.parametrize(
    ("resolved", "message"),
    [("{}", "not a list"), ("[{}]", "entry 0 lacks"), ('[{"title": "x", "claims": [{}]}]', "malformed claim"),
     ('[{"title": 1, "claims": []}]', "entry 0 lacks"), ("[1]", "entry 0 lacks")],
)  # fmt: skip
def test_a_malformed_resolved_json_is_a_clear_refusal(tmp_path: Path, resolved: str, message: str) -> None:
    src = source(tmp_path)
    (src.parent / "resolved.json").write_text(resolved, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        ingest_ris([src], tmp_path / "cache")


def test_names_that_differ_only_in_case_clash(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="ignoring case"):
        ingest_ris([source(tmp_path / "1", "CaseX"), source(tmp_path / "2", "casex")], tmp_path / "cache")
    ingest_ris([source(tmp_path / "3", "Search")], tmp_path / "cache")
    with pytest.raises(SnapshotError, match="only in case"):
        ingest_ris([source(tmp_path / "4", "search")], tmp_path / "cache")


def test_a_symlinked_input_reads_both_files_from_its_target(tmp_path: Path) -> None:
    real = source(tmp_path, "real-dir")
    link_dir = tmp_path / "links"
    link_dir.mkdir()
    (link_dir / "mended.ris").symlink_to(real)
    [report] = ingest_ris([link_dir / "mended.ris"], tmp_path / "cache")
    assert report.file == "real-dir/mended.ris"


def test_concurrent_builds_take_turns(cache: Path, tmp_path: Path) -> None:
    import threading

    results: list[Any] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(build(cache, tmp_path / "snapshots", BUILT))
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(r.created for r in results) == [False, False, False, True]
    [snapshot] = [p for p in (tmp_path / "snapshots").iterdir() if p.name != ".lock"]
    assert load_records(snapshot)  # complete and valid


def test_an_empty_cache_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="nothing cached"):
        build(tmp_path / "cache", tmp_path / "snapshots", BUILT)


# --- build -------------------------------------------------------------------------------------------------


def test_build_writes_the_layout(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT)
    assert result.created
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    lines = (result.path / "records.jsonl").read_bytes()
    assert result.snapshot_hash == manifest["snapshot_hash"] == hashlib.sha256(lines).hexdigest()
    assert result.path.name == f"2026-09-20-{result.snapshot_hash[:12]}"  # the newest claim's fetch date
    files = ["conflicts.csv", "manifest.json", "merges.csv", "records.jsonl"]
    assert sorted(p.name for p in result.path.iterdir()) == files
    assert stat.S_IMODE(result.path.stat().st_mode) == 0o555
    assert {stat.S_IMODE((result.path / f).stat().st_mode) for f in files} == {0o444}
    ids = [json.loads(line)["id"] for line in lines.decode("utf-8").splitlines()]
    assert ids == sorted(ids) and manifest["record_count"] == len(ids) == 6
    assert manifest["counts"]["ICLR"] == {
        "2024": {"main": {"rejected": 1}},
        "2025": {"main": {"accepted": 1}},
    }
    assert manifest["abstract_missing"] == {"ICLR": {"2024": 0, "2025": 1}, "ICML": {"2023": 1, "2026": 0},
                                            "NeurIPS": {"2024": 0, "2025": 0}}  # fmt: skip
    assert manifest["unknown_track"]["ICML"] == {"2023": 0, "2026": 0}
    assert (manifest["merges"], manifest["conflicts"]) == ({"total": 0}, {"total": 0})
    assert manifest["crawl_window"] == {
        "from": "2026-09-18T10:03:05+00:00",
        "to": "2026-09-20T08:00:00+00:00",
    }
    assert manifest["crawl_windows"] == {"ris": manifest["crawl_window"]}  # one source: the same window
    # TASK-082 (format 2): per track, the missing abstracts (0 included) and claim sources; per venue-year, the
    # statuses its sources can contain (every one: each venue-year here is one OpenReview holds)
    assert manifest["abstract_missing_by_track"] == {
        "ICLR": {"2024": {"main": 0}, "2025": {"main": 1}},
        "ICML": {"2023": {"main": 1}, "2026": {"workshop": 0}},
        "NeurIPS": {"2024": {"datasets_benchmarks": 0}, "2025": {"main": 0}},
    }
    assert {t: s for ys in manifest["sources_by_track"].values() for y in ys.values() for t, s in y.items()} == {
        "main": ["ris"], "workshop": ["ris"], "datasets_benchmarks": ["ris"],
    }  # fmt: skip
    every = ["accepted", "rejected", "withdrawn", "desk_rejected", "unknown"]
    assert manifest["statuses_indexed"] == {
        v: dict.fromkeys(ys, every) for v, ys in manifest["counts"].items()
    }
    assert (manifest["format_version"], manifest["record_schema_version"], manifest["tokenizer_version"]) == (
        "2",
        "7",
        "3",
    )
    assert manifest["openproceedings_version"]
    for name in ("merges.csv", "conflicts.csv"):
        assert manifest["files"][name] == hashlib.sha256((result.path / name).read_bytes()).hexdigest()
    [report] = manifest["sources"]["ris"]
    assert (report["file"], report["imported"], report["read"]) == ("search-a/mended.ris", 6, 12)
    assert report["utc_offset"] is None and manifest["query_dates"] == {"ris": "local"}  # not in the table
    assert manifest["built_at"] == "2026-09-26T12:00:00+00:00"
    assert (result.path / "merges.csv").read_text() == "survivor_id,merged_id,rule,key,venue,year,sources\n"
    assert not list((tmp_path / "snapshots").glob(".tmp-*"))


def test_query_dates_say_whether_the_ris_window_was_converted(tmp_path: Path) -> None:
    """TASK-077: an entry listed in `ris_offsets.toml` has its query dates converted, and the manifest says
    `utc`; with any entry unlisted the RIS window is `local` (offset unknown)."""
    [listed] = ingest_ris([source(tmp_path, "out-covidence")], tmp_path / "cache")
    assert listed.utc_offset == "-04:00"  # the check ran under the cache entry's name, not its temp dir's
    converted = build(tmp_path / "cache", tmp_path / "one", BUILT)
    manifest = json.loads((converted.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["query_dates"] == {"ris": "utc"}
    assert [r["utc_offset"] for r in manifest["sources"]["ris"]] == ["-04:00"]
    # the fixture's latest imported query date, 2026-09-20 08:00:00 local, is 12:00:00 UTC
    assert manifest["crawl_window"]["to"] == "2026-09-20T12:00:00+00:00"
    ingest_ris([source(tmp_path / "2", "search-a")], tmp_path / "cache")
    both = build(tmp_path / "cache", tmp_path / "two", BUILT)
    manifest = json.loads((both.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["query_dates"] == {"ris": "local"}
    assert [r["utc_offset"] for r in manifest["sources"]["ris"]] == ["-04:00", None]


def test_converting_query_dates_changes_only_fetched_at(tmp_path: Path) -> None:
    """decision-025: the same two searches, converted or not, give the same records, merges and conflicts;
    every RIS claim's `fetched_at` is 4 hours later, and so the snapshot hash differs."""

    def later(text: str) -> str:  # the second search a day later, with one author written differently
        return text.replace("2026-09-19 01:06:30", "2026-09-20 01:06:30").replace(
            "AU  - Doe, J", "AU  - Doe, Jane"
        )

    def snap(root: Path, names: tuple[str, str]) -> tuple[Path, list[dict[str, Any]]]:
        ingest_ris([source(root / "1", names[0]), source(root / "2", names[1], later)], root / "cache")
        path = build(root / "cache", root / "snapshots", BUILT).path
        return path, [json.loads(line) for line in (path / "records.jsonl").read_text().splitlines()]

    local, before = snap(tmp_path / "local", ("a-search", "b-search"))
    converted, after = snap(tmp_path / "utc", ("out-covidence", "out-covidence-2020-2024"))
    for name in ("merges.csv", "conflicts.csv"):
        assert (local / name).read_bytes() == (converted / name).read_bytes()
    assert "newest:ris" in (converted / "conflicts.csv").read_text()  # the later search's value still wins
    assert len(before) == len(after) > 0
    for old, new in zip(before, after, strict=True):
        shifted = [datetime.fromisoformat(c["fetched_at"]) + timedelta(hours=4) for c in old["provenance"]]
        assert [datetime.fromisoformat(c["fetched_at"]) for c in new["provenance"]] == shifted
        for c in (*old["provenance"], *new["provenance"]):
            del c["fetched_at"]
        assert old == new  # ids, content_hash, track, status, every other claim field
    assert local.name != converted.name


def test_built_at_is_stored_in_utc(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "s", datetime(2026, 9, 26, 7, 0, tzinfo=timezone(timedelta(hours=-5))))
    assert json.loads((result.path / "manifest.json").read_text())["built_at"] == "2026-09-26T12:00:00+00:00"


def test_same_inputs_give_byte_identical_files(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "one", BUILT)
    b = build(cache, tmp_path / "two", datetime(2027, 1, 1, tzinfo=UTC))
    assert a.path.name == b.path.name
    for name in ("records.jsonl", "merges.csv", "conflicts.csv"):
        assert (a.path / name).read_bytes() == (b.path / name).read_bytes()
    ma, mb = (json.loads((p / "manifest.json").read_text(encoding="utf-8")) for p in (a.path, b.path))
    assert {k for k in ma if ma[k] != mb[k]} == {"built_at"}


def test_text_is_written_as_utf8_not_escapes(tmp_path: Path) -> None:
    accented = source(
        tmp_path,
        "suche-ä",
        edit=lambda t: t.replace("Synthetic Trust Benchmark", "Synthetic Trust Bénchmark"),
    )
    ingest_ris([accented], tmp_path / "cache")
    result = build(tmp_path / "cache", tmp_path / "snapshots", BUILT)
    assert "Bénchmark".encode() in (result.path / "records.jsonl").read_bytes()
    assert "suche-ä".encode() in (result.path / "manifest.json").read_bytes()


def test_sources_are_listed_in_cached_name_order(tmp_path: Path) -> None:
    ingest_ris([source(tmp_path, "b-search"), source(tmp_path / "2", "a-search")], tmp_path / "cache")
    result = build(tmp_path / "cache", tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert [r["file"] for r in manifest["sources"]["ris"]] == ["a-search/mended.ris", "b-search/mended.ris"]
    assert manifest["merges"] == {"total": 6, "forum_id": 2, "native_id": 4}  # each paper and its copy
    rows = (result.path / "merges.csv").read_text().splitlines()[1:]
    assert rows == sorted(rows) and len(rows) == 6


def test_render_sorts_rows_and_counts_conflicts_by_kind() -> None:
    orv = paper("AbCd1234", status="rejected")
    proc = paper(f"nips-{H[1]}", source="neurips_proceedings")
    copy = paper(f"nips-{H[1]}", source="ris")
    result = dedup([orv, proc, copy])
    assert len(result.merges) == 2
    shuffled = DedupResult(result.records, tuple(reversed(result.merges)), tuple(reversed(result.conflicts)))
    files = render(shuffled, [], BUILT)
    manifest = json.loads(files["manifest.json"])
    assert manifest["conflicts"] == {"total": 1, "precedence": 1}
    assert files["merges.csv"] == render(result, [], BUILT)["merges.csv"]
    with pytest.raises(SnapshotError, match="no records"):
        render(DedupResult((), (), ()), [], BUILT)
    bare = PaperRecord.build(id="op:iclr:2024:AbCd1234", title="T", abstract=None, authors=(), venue="ICLR",
                             year=2024, track="main", status="accepted")  # fmt: skip
    with pytest.raises(SnapshotError, match="no provenance"):
        render(DedupResult((bare,), (), ()), [], BUILT)


def test_a_rebuild_reports_the_existing_snapshot(cache: Path, tmp_path: Path) -> None:
    first = build(cache, tmp_path / "snapshots", BUILT)
    again = build(cache, tmp_path / "snapshots", datetime(2027, 1, 1, tzinfo=UTC))
    assert (again.path, again.created) == (first.path, False)
    manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["built_at"] == "2026-09-26T12:00:00+00:00"  # never rewritten


@pytest.mark.parametrize("contents", ["other records\n", None])  # different records; no records at all
def test_an_occupied_target_is_never_overwritten(cache: Path, tmp_path: Path, contents: str | None) -> None:
    records, reports = load_cache(cache)
    manifest = json.loads(render(dedup(records), reports, BUILT)["manifest.json"])
    target = tmp_path / "snapshots" / f"{manifest['crawl_date']}-{manifest['snapshot_hash'][:12]}"
    target.mkdir(parents=True)
    if contents is not None:
        (target / "records.jsonl").write_text(contents, encoding="utf-8")
    with pytest.raises(SnapshotError, match="immutable"):
        build(cache, tmp_path / "snapshots", BUILT)
    assert sorted(p.name for p in target.iterdir()) == ([] if contents is None else ["records.jsonl"])


def test_a_target_that_appears_during_the_build(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = build(cache, tmp_path / "a", BUILT)

    def racing(src: Any, dst: Any) -> None:  # another build places the same snapshot first
        shutil.copytree(first.path, dst)
        raise FileExistsError(17, "exists")

    monkeypatch.setattr(storage.os, "rename", racing)
    result = build(cache, tmp_path / "b", BUILT)
    assert not result.created and result.path.name == first.path.name
    assert not list((tmp_path / "b").glob(".tmp-*"))


def test_an_old_format_snapshot_is_refused_with_advice(cache: Path, tmp_path: Path) -> None:
    first = build(cache, tmp_path / "snapshots", BUILT).path
    first.chmod(0o755)
    (first / "manifest.json").chmod(0o644)
    manifest = json.loads((first / "manifest.json").read_text())
    del manifest["format_version"]
    (first / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match="retire it"):
        build(cache, tmp_path / "snapshots", BUILT)


def test_a_complete_but_writable_snapshot_is_locked_on_rebuild(cache: Path, tmp_path: Path) -> None:
    first = build(cache, tmp_path / "snapshots", BUILT).path
    first.chmod(0o755)  # as if a crash hit between placing and locking
    again = build(cache, tmp_path / "snapshots", BUILT)
    assert not again.created and stat.S_IMODE(first.stat().st_mode) == 0o555


def test_a_placed_snapshot_is_checked_before_it_is_reported(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = storage.os.rename

    def lossy(src: Any, dst: Any) -> None:
        (Path(src) / "records.jsonl").write_text("lost\n")
        real(src, dst)

    monkeypatch.setattr(storage.os, "rename", lossy)
    with pytest.raises(SnapshotError, match="doesn't hold what was written"):
        build(cache, tmp_path / "snapshots", BUILT)


def test_a_build_sweeps_what_a_crashed_build_left(cache: Path, tmp_path: Path) -> None:
    leftover = tmp_path / "snapshots" / ".tmp-crashed"
    leftover.mkdir(parents=True)
    (leftover / "records.jsonl").write_text("half", encoding="utf-8")
    build(cache, tmp_path / "snapshots", BUILT)
    assert not leftover.exists()


def test_a_failed_write_leaves_no_target_and_no_temp(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Path.write_bytes
    calls = []

    def failing(self: Path, data: bytes) -> int:
        calls.append(self)
        if len(calls) == 2:
            raise OSError(28, "no space")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing)
    with pytest.raises(OSError):
        build(cache, tmp_path / "snapshots", BUILT)
    assert entries(tmp_path / "snapshots") == []


# --- reading and diffing ---------------------------------------------------------------------------------


def test_records_round_trip(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT)
    records = load_records(result.path)
    lines = (result.path / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert [record_line(records[json.loads(line)["id"]]) for line in lines] == lines


def test_a_snapshot_whose_records_do_not_match_its_hash_is_refused(cache: Path, tmp_path: Path) -> None:
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    manifest = json.loads((copy / "manifest.json").read_text())
    (copy / "manifest.json").write_text(json.dumps({**manifest, "snapshot_hash": "0" * 64}))
    with pytest.raises(SnapshotError, match="doesn't match its manifest"):
        load_records(copy)
    (copy / "records.jsonl").write_bytes((copy / "records.jsonl").read_bytes() + b"\n")
    with pytest.raises(SnapshotError, match="invalid record"):  # a blank line is no record
        load_records(copy)


def test_one_pass_reads_the_file_it_checks(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the file is hashed as it is read, so there is no window to swap it between a check and a read
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    opened = []
    real = Path.open

    def counting(self: Path, *a: Any, **kw: Any) -> Any:
        if self.name == "records.jsonl":
            opened.append(self)
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "open", counting)
    load_records(copy)
    assert len(opened) == 1


def test_a_record_may_hold_unicode_line_separators(tmp_path: Path) -> None:
    from openproceedings.ingest.dedup import DedupResult

    from tests.unit.ingest.test_dedup import paper

    r = paper(
        "AbCd1234", "Trust\u2028in\u0085AI".replace("\u2028", " ").replace("\u0085", " "), abstract="a\u2028b"
    )
    snap = tmp_path / "snap"
    snap.mkdir()
    for name, data in render(DedupResult((r,), (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    assert load_records(snap)[r.id].abstract == "a\u2028b"  # JSON keeps it raw; a line split would break it


def test_a_tampered_record_is_caught_without_quoting_it(cache: Path, tmp_path: Path) -> None:
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    data = (
        (copy / "records.jsonl").read_text(encoding="utf-8").replace('"track":"workshop"', '"track":"main"')
    )
    (copy / "records.jsonl").write_text(data, encoding="utf-8")
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["snapshot_hash"] = hashlib.sha256(data.encode()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match=r"line \d+: invalid record \(value_error\)") as err:
        load_records(copy)
    assert "Synthetic" not in str(err.value) and "abstract" not in str(err.value)


def test_duplicate_ids_are_refused(cache: Path, tmp_path: Path) -> None:
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    first = (copy / "records.jsonl").read_bytes().split(b"\n")[0] + b"\n"
    data = first + (copy / "records.jsonl").read_bytes()
    (copy / "records.jsonl").write_bytes(data)
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["snapshot_hash"] = hashlib.sha256(data).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match="line 2: duplicate id"):
        load_records(copy)


def _corrupt(copy: Path, change: Callable[[list[bytes]], list[bytes]]) -> None:
    """Rewrite records.jsonl through `change` and re-seal the manifest's hash, so only the lines are wrong."""
    lines = (copy / "records.jsonl").read_bytes().splitlines(keepends=True)
    data = b"".join(change(lines))
    (copy / "records.jsonl").write_bytes(data)
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["snapshot_hash"] = hashlib.sha256(data).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest))


def _drop_id(lines: list[bytes]) -> list[bytes]:
    record = json.loads(lines[0])
    del record["id"]
    return [json.dumps(record).encode() + b"\n", *lines[1:]]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda ls: [ls[0], *ls], "line 2: duplicate id"),
        (lambda ls: [ls[1], ls[0], *ls[2:]], "line 2: records are not sorted by id"),
        (lambda ls: [b"{not json\n", *ls[1:]], "line 1: invalid record (json_invalid)"),
        (_drop_id, "line 1: invalid record (missing)"),
    ],
    ids=["duplicate", "unsorted", "not-json", "no-id"],
)
@pytest.mark.parametrize("loader", [load_records, RecordFile], ids=["load_records", "RecordFile"])
def test_both_snapshot_readers_name_a_bad_line_the_same_way(
    cache: Path,
    tmp_path: Path,
    loader: Callable[[Path], object],
    change: Callable[[list[bytes]], list[bytes]],
    message: str,
) -> None:
    # the API's RecordFile skips full validation for speed, but names a bad line exactly as iter_records does
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    _corrupt(copy, change)
    with pytest.raises(SnapshotError, match=re.escape(message)):
        loader(copy)


@pytest.mark.parametrize("value", ["op:iclr:2017:Hy-Conf01", ["op:iclr:2017:Hy-Conf01", 7], {"id": "x"}])
def test_record_file_refuses_a_twin_claim_that_isnt_a_list_of_ids(
    cache: Path, tmp_path: Path, value: object
) -> None:
    """TASK-162: a string would otherwise be read character by character into made-up twin ids."""
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")

    def with_twin(lines: list[bytes]) -> list[bytes]:
        record = json.loads(lines[0])
        claim = {**record["provenance"][0], "field": "twin", "value": value}
        record["provenance"] = [*record["provenance"], claim]
        return [json.dumps(record).encode() + b"\n", *lines[1:]]

    _corrupt(copy, with_twin)
    with pytest.raises(SnapshotError, match=re.escape("line 1: invalid record (type_error)")):
        RecordFile(copy)


def test_record_file_reads_each_records_twins(cache: Path, tmp_path: Path) -> None:
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    ids = [json.loads(line)["id"] for line in (copy / "records.jsonl").read_bytes().splitlines()]

    def with_twin(lines: list[bytes]) -> list[bytes]:
        record = json.loads(lines[0])
        claim = {**record["provenance"][0], "field": "twin", "value": [ids[1], ids[0]]}
        record["provenance"] = [*record["provenance"], claim]
        return [json.dumps(record).encode() + b"\n", *lines[1:]]

    _corrupt(copy, with_twin)
    records = RecordFile(copy)
    assert records.twins == {ids[0]: (ids[1],)}  # its own id left out
    assert list(records.twin_pairs()) == [(ids[0], ids[1])]


def test_the_field_lists_cover_the_record() -> None:
    fields = set(PaperRecord.model_fields) - {"id", "content_hash", "provenance"}
    assert set(HASHED) | set(DISPLAY) == fields and not set(HASHED) & set(DISPLAY)


def test_diff_names_every_kind_of_change(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path

    def edit(rs: dict[str, PaperRecord]) -> None:
        rs[WORKSHOP] = rs[WORKSHOP].model_copy(update={"title": "A Renamed Paper", "status": "rejected"})
        rs[NEURIPS] = rs[NEURIPS].model_copy(update={"authors": ("Doe, J",)})
        p = rs[PMLR]
        rs[PMLR] = p.model_copy(
            update={"provenance": tuple(c.model_copy(update={"evidence": "x"}) for c in p.provenance)}
        )
        moved = rs.pop(REJECTED).model_copy(update={"id": "op:iclr:2025:Rej_ected-1", "year": 2025})
        rs[moved.id] = moved  # the same paper, its year corrected
        new = rs[WORKSHOP].model_copy(update={"id": "op:iclr:2024:NewPaper01", "venue": "ICLR", "year": 2024})
        rs[new.id] = new
        del rs["op:iclr:2025:iclr-fedcba9876543210fedcba9876543210"]

    b = rewrite(a, tmp_path / "b", edit)
    assert diff(a, b) == {
        "from": a.name,
        "to": "b",
        "added": ["op:iclr:2024:NewPaper01"],
        "removed": ["op:iclr:2025:iclr-fedcba9876543210fedcba9876543210"],
        "rekeyed": {REJECTED: {"to": "op:iclr:2025:Rej_ected-1", "fields": ["year"]}},
        "changed": {WORKSHOP: ["title", "status"]},
        "display_only": 1,
        "provenance_only": 1,
        "abstract_withheld": {"added": [], "lifted": []},  # TASK-136
    }
    same = diff(a, a)
    assert (same["added"], same["removed"], same["rekeyed"], same["changed"]) == ([], [], {}, {})


def test_diff_never_reads_a_proceedings_hash_in_another_year_as_a_rekey(cache: Path, tmp_path: Path) -> None:
    """TASK-067 review: a NeurIPS hash is md5 of a per-year paper number, so the same hash in another year is
    another paper: one removed and one added are reported as such, never as one paper rekeyed."""
    a = build(cache, tmp_path / "snapshots", BUILT).path
    other = NEURIPS.replace(":2025:", ":2013:")

    def edit(rs: dict[str, PaperRecord]) -> None:
        moved = rs.pop(NEURIPS).model_copy(update={"id": other, "year": 2013})
        rs[moved.id] = moved

    result = diff(a, rewrite(a, tmp_path / "b", edit))
    assert (result["added"], result["removed"], result["rekeyed"]) == ([other], [NEURIPS], {})


@pytest.mark.parametrize("field", DISPLAY)
def test_every_display_field_is_a_display_only_change(cache: Path, tmp_path: Path, field: str) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path
    value: Any = {"authors": ("X, Y",), "urls": {"doi": "10.1/x"}, "keywords": ("k",), "presentation": "oral",
                  "venue_id_raw": "ICML.cc/2026/Conference"}[field]  # fmt: skip
    b = rewrite(
        a, tmp_path / "b", lambda rs: rs.update({WORKSHOP: rs[WORKSHOP].model_copy(update={field: value})})
    )
    got = diff(a, b)
    assert (got["display_only"], got["changed"]) == (1, {})


# --- CLI ---------------------------------------------------------------------------------------------------


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = ["--data-dir", str(tmp_path / "data")]
    assert cli.main([*data, "ingest", "ris", str(source(tmp_path))]) == 0
    [report] = json.loads(capsys.readouterr().out)
    assert report["imported"] == 6
    assert cli.main([*data, "snapshot", "build"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["created"] and Path(built["path"]).parent == tmp_path / "data" / "snapshots"
    assert cli.main([*data, "snapshot", "diff", built["path"], built["path"]]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] == {}


def test_cli_from_and_out_override_the_data_dir(
    cache: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "elsewhere"
    argv = [
        "--data-dir",
        str(tmp_path / "unused"),
        "snapshot",
        "build",
        "--from",
        str(cache),
        "--out",
        str(out),
    ]
    assert cli.main(argv) == 0
    assert Path(json.loads(capsys.readouterr().out)["path"]).parent == out


def test_cli_data_dir_defaults_to_the_environment_then_the_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OP_DATA_DIR", str(tmp_path))
    assert cli.default_data_dir() == tmp_path
    monkeypatch.delenv("OP_DATA_DIR")
    repo = cli.default_data_dir().parent
    assert (repo / "backend").is_dir() and (repo / "pyproject.toml").is_file()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["snapshot", "build"], "nothing cached"),
        (["snapshot", "diff", "missing-a", "missing-b"], "not a snapshot"),
        (["ingest", "ris", "missing/mended.ris"], "FileNotFoundError"),
    ],
)
def test_cli_reports_a_refusal_with_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    assert cli.main(["--data-dir", str(tmp_path), *argv]) == 1
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err
    assert err.splitlines()[-1].startswith(f"op {' '.join(argv[:2])}:")  # logs come first, on stderr too


def test_cli_diff_of_a_file_is_refused_not_a_traceback(
    cache: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = build(cache, tmp_path / "s", BUILT).path / "records.jsonl"
    assert cli.main(["snapshot", "diff", str(path), str(path)]) == 1
    assert "not a snapshot" in capsys.readouterr().err


def test_cli_never_prints_record_text(
    cache: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy = writable_copy(build(cache, tmp_path / "s", BUILT).path, tmp_path / "copy")
    data = (
        (copy / "records.jsonl").read_text(encoding="utf-8").replace('"track":"workshop"', '"track":"main"')
    )
    (copy / "records.jsonl").write_text(data, encoding="utf-8")
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["snapshot_hash"] = hashlib.sha256(data.encode()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest))
    assert cli.main(["snapshot", "diff", str(copy), str(copy)]) == 1
    err = capsys.readouterr().err
    assert "invalid record" in err and "made-up" not in err and "Synthetic" not in err


@pytest.mark.parametrize(
    "argv",
    [["snapshot", "build", "--form", "x"], ["--bogus", "export"], ["--bogus", "export", "--bogus"],
     ["ingest", "--bogus", "openreview"]],
)  # fmt: skip
def test_cli_rejects_unknown_options(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_diff_never_hides_a_lost_record_behind_a_rekey(cache: Path, tmp_path: Path) -> None:
    # two papers sharing a native id collapse into one: both are reported removed and the survivor added,
    # never as two rekeys to one id (which would hide the lost paper)
    a = build(cache, tmp_path / "snapshots", BUILT).path

    def twin(rs: dict[str, PaperRecord]) -> None:
        other = rs[REJECTED].model_copy(update={"id": "op:iclr:2023:Rej_ected-1", "year": 2023})
        rs[other.id] = other

    a2 = rewrite(a, tmp_path / "a2", twin)

    def collapse(rs: dict[str, PaperRecord]) -> None:
        moved = rs.pop(REJECTED).model_copy(update={"id": "op:iclr:2025:Rej_ected-1", "year": 2025})
        del rs["op:iclr:2023:Rej_ected-1"]
        rs[moved.id] = moved

    result = diff(a2, rewrite(a2, tmp_path / "b", collapse))
    assert result["rekeyed"] == {}
    assert result["removed"] == ["op:iclr:2023:Rej_ected-1", REJECTED]
    assert result["added"] == ["op:iclr:2025:Rej_ected-1"]


def test_audit_files_are_checked_against_the_manifest(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path
    copy = writable_copy(a, tmp_path / "copy")
    with (copy / "conflicts.csv").open("a", encoding="utf-8") as fh:
        fh.write("forged,row\n")
    with pytest.raises(SnapshotError, match=r"merges\.csv or conflicts\.csv doesn't match its manifest"):
        load_records(copy)


def test_a_rebuild_refuses_a_snapshot_whose_audit_files_this_code_wouldnt_write(
    cache: Path, tmp_path: Path
) -> None:
    # the records hash the same, but merges.csv differs from what this build renders (a dedup change that
    # kept the records): the old snapshot is never reported as this one, even when self-consistent
    snapshots = tmp_path / "snapshots"
    a = build(cache, snapshots, BUILT).path
    for p in [a, *a.iterdir()]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    data = (a / "merges.csv").read_bytes() + b"forged,row\n"
    (a / "merges.csv").write_bytes(data)
    manifest = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["merges.csv"] = hashlib.sha256(data).hexdigest()
    (a / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotError, match="immutable"):
        build(cache, snapshots, BUILT)


def test_a_rebuild_refuses_an_audit_file_changed_behind_its_manifest(cache: Path, tmp_path: Path) -> None:
    # merges.csv edited, the manifest left alone: its `files` no longer hold, so this isn't the snapshot
    snapshots = tmp_path / "snapshots"
    a = build(cache, snapshots, BUILT).path
    for p in [a, *a.iterdir()]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    (a / "merges.csv").write_bytes((a / "merges.csv").read_bytes() + b"forged,row\n")
    with pytest.raises(SnapshotError, match="immutable"):
        build(cache, snapshots, BUILT)


def test_diff_never_calls_a_split_a_rekey(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path

    def split(rs: dict[str, PaperRecord]) -> None:
        one = rs.pop(REJECTED)
        for year in (2023, 2025):
            copy = one.model_copy(update={"id": f"op:iclr:{year}:Rej_ected-1", "year": year})
            rs[copy.id] = copy

    result = diff(a, rewrite(a, tmp_path / "b", split))
    assert result["rekeyed"] == {} and result["removed"] == [REJECTED]
    assert result["added"] == ["op:iclr:2023:Rej_ected-1", "op:iclr:2025:Rej_ected-1"]


def test_a_manifest_that_stops_listing_its_audit_files_is_refused(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path
    for edit in ("drop", "empty", "list"):
        copy = writable_copy(a, tmp_path / edit)
        manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
        if edit == "drop":
            del manifest["files"]
            (copy / "merges.csv").unlink()
        else:
            manifest["files"] = {} if edit == "empty" else []
        (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(SnapshotError, match="doesn't match its manifest"):
            load_records(copy)


def test_the_reader_computes_each_records_attribution_once_at_load(cache: Path, tmp_path: Path) -> None:
    """`GET /search` looks attributions up (TASK-134): one per record, equal to `attribution` over the record
    a lookup validates, so the raw-JSON pass and the validated record agree."""
    records = RecordFile(build(cache, tmp_path / "s", BUILT).path)
    assert set(records.attributions) == set(records._at) and records.attributions
    for rid, found in records.attributions.items():
        r = records.get(rid)
        assert r is not None
        expected = attribution(
            r.abstract,
            r.claims("abstract"),
            forum=r.urls.forum,
            proceedings=r.urls.proceedings,
            native=r.native,
        )
        assert found == expected
    assert any(a is not None for a in records.attributions.values())


def test_build_replays_a_marked_ojs_crawl(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.ingest.sources import crawl, ojs

    from tests.unit.ingest.ojs import oai
    from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _seed

    monkeypatch.setattr(ojs, "TABLE", TABLE)  # the replay reads the shipped table
    _seed(cache, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    crawl.ingest_ojs(["AAAI"], cache, offline=True, table=TABLE)
    result = build(cache, tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    lines = (result.path / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ids = {json.loads(line)["id"] for line in lines}
    assert {f"op:aaai:2020:ojs-{n}" for n in (1, 2, 3)} <= ids
    [listing] = manifest["sources"]["ojs"]["listings"]
    assert listing["count_ok"] is True


def test_build_replays_a_marked_crossref_crawl(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.ingest import acm_table
    from openproceedings.ingest.sources import crawl

    from tests.unit.ingest.crossref import api
    from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, TABLE, _whole

    monkeypatch.setattr(acm_table, "TABLE", TABLE)  # the replay and urls.native read the shipped table
    _whole(cache, api.work(D1), api.work(D2), api.work(NP), total=3)
    crawl.ingest_crossref([("FAccT", 2023)], cache, offline=True, table=TABLE)
    result = build(cache, tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    lines = (result.path / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ids = {json.loads(line)["id"] for line in lines}
    assert {"op:facct:2023:doi-3593013.3594011", "op:facct:2023:doi-3593013.3594012"} <= ids
    [listing] = manifest["sources"]["crossref"]["listings"]
    assert listing["count_ok"] is True
