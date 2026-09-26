"""Snapshots: layout, determinism, immutability, diff and the CLI (snapshots skill), on the synthetic RIS
fixture (decision-004)."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.snapshot import (
    SnapshotError,
    build,
    diff,
    ingest_ris,
    load_cache,
    load_records,
    record_line,
    render,
)
from pydantic import ValidationError

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ris"
BUILT = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "search-a"
    src.mkdir(parents=True)
    for name in ("mended.ris", "resolved.json"):
        shutil.copyfile(FIXTURE / name, src / name)
    ingest_ris([src / "mended.ris"], tmp_path / "cache")
    return tmp_path / "cache"


def test_ingest_copies_both_files_and_is_idempotent(cache: Path, tmp_path: Path) -> None:
    cached = cache / "ris" / "search-a"
    assert sorted(p.name for p in cached.iterdir()) == ["mended.ris", "resolved.json"]
    assert (cached / "mended.ris").read_bytes() == (FIXTURE / "mended.ris").read_bytes()
    ingest_ris([tmp_path / "src" / "search-a" / "mended.ris"], cache)  # the same files again: no-op
    assert not list((cache / "ris").glob(".tmp-*"))


def test_ingest_refuses_different_files_under_a_cached_name(cache: Path, tmp_path: Path) -> None:
    src = tmp_path / "src" / "search-a"
    (src / "resolved.json").write_text(
        (src / "resolved.json").read_text(encoding="utf-8").replace("made-up", "invented"), encoding="utf-8"
    )
    with pytest.raises(SnapshotError, match="different files"):
        ingest_ris([src / "mended.ris"], cache)


def test_ingest_refuses_a_file_that_does_not_import(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    shutil.copyfile(FIXTURE / "mended.ris", bad / "mended.ris")
    (bad / "resolved.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="RIS records but"):
        ingest_ris([bad / "mended.ris"], tmp_path / "cache")
    assert not (tmp_path / "cache" / "ris" / "bad").exists()


def test_build_writes_the_layout(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT)
    assert result.created
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    lines = (result.path / "records.jsonl").read_bytes()
    assert result.snapshot_hash == manifest["snapshot_hash"] == hashlib.sha256(lines).hexdigest()
    assert result.path.name == f"2026-09-20-{result.snapshot_hash[:12]}"  # the newest claim's fetch date
    assert sorted(p.name for p in result.path.iterdir()) == [
        "conflicts.csv",
        "manifest.json",
        "merges.csv",
        "records.jsonl",
    ]
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
    [report] = manifest["sources"]["ris"]
    assert (report["file"], report["imported"], report["read"]) == ("search-a/mended.ris", 6, 12)
    assert manifest["built_at"] == "2026-09-26T12:00:00+00:00"
    assert (result.path / "merges.csv").read_text() == "survivor_id,merged_id,rule,key,venue,year,sources\n"
    assert not list((tmp_path / "snapshots").glob(".tmp-*"))


def test_same_inputs_give_byte_identical_files(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "one", BUILT)
    b = build(cache, tmp_path / "two", datetime(2027, 1, 1, tzinfo=UTC))
    assert a.path.name == b.path.name
    for name in ("records.jsonl", "merges.csv", "conflicts.csv"):
        assert (a.path / name).read_bytes() == (b.path / name).read_bytes()
    ma, mb = (json.loads((p / "manifest.json").read_text(encoding="utf-8")) for p in (a.path, b.path))
    assert {k for k in ma if ma[k] != mb[k]} == {"built_at"}


def test_merges_and_conflicts_are_written_sorted(cache: Path, tmp_path: Path) -> None:
    # the same search cached twice: every paper merges with its copy
    shutil.copytree(cache / "ris" / "search-a", cache / "ris" / "search-b")
    result = build(cache, tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 6 and len(manifest["sources"]["ris"]) == 2
    assert manifest["merges"] == {"total": 6, "forum_id": 2, "native_id": 4}
    rows = (result.path / "merges.csv").read_text().splitlines()[1:]
    assert rows == sorted(rows) and len(rows) == 6


def test_a_rebuild_reports_the_existing_snapshot(cache: Path, tmp_path: Path) -> None:
    first = build(cache, tmp_path / "snapshots", BUILT)
    again = build(cache, tmp_path / "snapshots", datetime(2027, 1, 1, tzinfo=UTC))
    assert (again.path, again.created) == (first.path, False)
    manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["built_at"] == "2026-09-26T12:00:00+00:00"  # never rewritten


def test_an_occupied_target_is_never_overwritten(cache: Path, tmp_path: Path) -> None:
    files = render(dedup(load_cache(cache)[0]), load_cache(cache)[1], BUILT)
    manifest = json.loads(files["manifest.json"])
    target = tmp_path / "snapshots" / f"{manifest['crawl_date']}-{manifest['snapshot_hash'][:12]}"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(json.dumps({"snapshot_hash": "other"}), encoding="utf-8")
    with pytest.raises(SnapshotError, match="immutable"):
        build(cache, tmp_path / "snapshots", BUILT)
    assert json.loads((target / "manifest.json").read_text(encoding="utf-8")) == {"snapshot_hash": "other"}


def test_an_empty_cache_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="nothing cached"):
        build(tmp_path / "cache", tmp_path / "snapshots", BUILT)


def test_records_round_trip_and_a_tampered_line_is_caught(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT)
    records = load_records(result.path)
    lines = (result.path / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert [record_line(records[json.loads(line)["id"]]) for line in lines] == lines
    tampered = tmp_path / "tampered"
    shutil.copytree(result.path, tampered)
    text = (tampered / "records.jsonl").read_text(encoding="utf-8")
    (tampered / "records.jsonl").write_text(
        text.replace('"track":"workshop"', '"track":"main"'), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="content_hash"):
        load_records(tampered)


def _edit(snapshot: Path, out: Path, edit: object) -> Path:
    """A copy of `snapshot` whose records were changed by `edit(dict_by_id)` (content hashes recomputed)."""
    records = load_records(snapshot)
    edit(records)  # type: ignore[operator]
    out.mkdir()
    (out / "records.jsonl").write_text(
        "".join(record_line(r) + "\n" for r in sorted(records.values(), key=lambda r: r.id)), encoding="utf-8"
    )
    return out


def test_diff_names_every_kind_of_change(cache: Path, tmp_path: Path) -> None:
    a = build(cache, tmp_path / "snapshots", BUILT).path
    workshop, rejected = "op:icml:2026:AbCdEf1234", "op:iclr:2024:Rej_ected-1"
    neurips = "op:neurips:2025:nips-0123456789abcdef0123456789abcdef"
    pmlr = "op:icml:2023:pmlr-v202-smith23a"

    def edit(rs: dict) -> None:  # type: ignore[type-arg]
        rs[workshop] = rs[workshop].model_copy(update={"title": "A Renamed Paper", "status": "rejected"})
        rs[neurips] = rs[neurips].model_copy(update={"authors": ("Doe, J",)})
        p = rs[pmlr]
        rs[pmlr] = p.model_copy(
            update={"provenance": tuple(c.model_copy(update={"evidence": "x"}) for c in p.provenance)}
        )
        del rs[rejected]
        rs["op:iclr:2024:NewPaper01"] = rs[workshop].model_copy(
            update={"id": "op:iclr:2024:NewPaper01", "venue": "ICLR", "year": 2024}
        )

    b = _edit(a, tmp_path / "b", edit)
    assert diff(a, b) == {
        "from": a.name,
        "to": "b",
        "added": ["op:iclr:2024:NewPaper01"],
        "removed": [rejected],
        "changed": {workshop: ["title", "status"]},
        "display_only": 1,
        "provenance_only": 1,
    }
    assert diff(a, a)["changed"] == {} and diff(a, a)["added"] == []


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "search-a"
    src.mkdir()
    for name in ("mended.ris", "resolved.json"):
        shutil.copyfile(FIXTURE / name, src / name)
    data = ["--data-dir", str(tmp_path / "data")]
    assert cli.main([*data, "ingest", "ris", str(src / "mended.ris")]) == 0
    [report] = json.loads(capsys.readouterr().out)
    assert report["imported"] == 6
    assert cli.main([*data, "snapshot", "build"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["created"] and Path(built["path"]).parent == tmp_path / "data" / "snapshots"
    assert cli.main([*data, "snapshot", "diff", built["path"], built["path"]]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] == {}


def test_cli_reports_a_refusal_with_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--data-dir", str(tmp_path), "snapshot", "build"]) == 1
    assert "nothing cached" in capsys.readouterr().err
