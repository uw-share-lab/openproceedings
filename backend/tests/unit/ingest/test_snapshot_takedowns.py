"""Takedowns in `op snapshot build` (TASK-136, decision-022; spec 08 §Deploy): the list withholds each listed
abstract from the snapshot, whatever the cache supplies; the manifest names and counts them apart from missing
abstracts; the reader checks them; a diff names them; a listed id the build doesn't have refuses it."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.ingest.snapshot import (
    WITHHELD_VALUE,
    RecordFile,
    SnapshotError,
    build,
    diff,
    ingest_ris,
    load_records,
)

from tests.unit.ingest.test_snapshot import BUILT, NEURIPS, REJECTED, source, writable_copy

REJECTED_ABSTRACT = "A synthetic abstract of a rejected submission."
RECRAWLED = "A recrawled abstract of a rejected submission."
NO_ABSTRACT = "op:icml:2023:pmlr-v202-smith23a"  # a record the fixture gives no abstract


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    ingest_ris([source(tmp_path)], tmp_path / "cache")
    return tmp_path / "cache"


def manifest(snapshot: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    return loaded


def test_a_listed_abstract_and_its_claims_are_withheld(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    records = load_records(result.path)  # every record re-validated, content_hash included
    withheld = records[REJECTED]
    assert withheld.abstract is None and withheld.claims("abstract") == ()
    assert withheld.title == "A Synthetic Rejected Submission"  # still found by its title
    assert REJECTED_ABSTRACT not in (result.path / "records.jsonl").read_text(encoding="utf-8")
    assert records[NEURIPS].abstract is not None  # nothing else changes
    m = manifest(result.path)
    assert m["withheld"] == [REJECTED]
    assert m["abstract_withheld"] == {"ICLR": {"2024": 1, "2025": 0}, "ICML": {"2023": 0, "2026": 0},
                                      "NeurIPS": {"2024": 0, "2025": 0}}  # fmt: skip
    assert m["abstract_withheld_by_track"] == {
        "ICLR": {"2024": {"main": 1}, "2025": {"main": 0}},
        "ICML": {"2023": {"main": 0}, "2026": {"workshop": 0}},
        "NeurIPS": {"2024": {"datasets_benchmarks": 0}, "2025": {"main": 0}},
    }
    # a withheld abstract is not a missing one: the counts stay those of the sources' own gaps
    assert m["abstract_missing"] == {"ICLR": {"2024": 0, "2025": 1}, "ICML": {"2023": 1, "2026": 0},
                                     "NeurIPS": {"2024": 0, "2025": 0}}  # fmt: skip
    assert m["abstract_missing_by_track"]["ICLR"]["2024"] == {"main": 0}  # type: ignore[index]


def test_the_snapshot_hash_covers_the_withholding(cache: Path, tmp_path: Path) -> None:
    plain = build(cache, tmp_path / "snapshots", BUILT)
    withheld = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    assert withheld.snapshot_hash != plain.snapshot_hash and withheld.path != plain.path
    assert "withheld" not in manifest(plain.path)  # nothing listed: the manifest a format-2 reader knows


def test_a_recrawl_and_rebuild_cannot_restore_a_listed_abstract(cache: Path, tmp_path: Path) -> None:
    """A second source re-supplies the paper's abstract (with other text, so dedup records a conflict); the
    rebuild still withholds it, and conflicts.csv holds neither text."""
    first = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    recrawl = source(tmp_path, "search-b", edit=lambda t: t.replace(REJECTED_ABSTRACT, RECRAWLED))
    ingest_ris([recrawl], cache)
    # (its own directory: the records are the ones `first` holds, the conflicts not, so the name is taken)
    again = build(cache, tmp_path / "rebuilt", BUILT, takedowns=frozenset({REJECTED}))
    assert again.snapshot_hash == first.snapshot_hash  # the withheld records read the same
    record = load_records(again.path)[REJECTED]
    assert record.abstract is None and record.claims("abstract") == ()
    for name in ("records.jsonl", "conflicts.csv", "manifest.json"):
        text = (again.path / name).read_text(encoding="utf-8")
        assert REJECTED_ABSTRACT not in text and RECRAWLED not in text
    conflicts = (again.path / "conflicts.csv").read_text(encoding="utf-8")
    assert f"{REJECTED},abstract,{WITHHELD_VALUE},ris,{WITHHELD_VALUE},ris," in conflicts
    unlisted = build(cache, tmp_path / "unlisted", BUILT)  # without the list, the same cache restores it
    assert load_records(unlisted.path)[REJECTED].abstract is not None


def test_a_listed_id_the_build_has_no_record_of_refuses_it(cache: Path, tmp_path: Path) -> None:
    """A rekeyed or merged paper would otherwise get its abstract back under its new id."""
    gone = "op:iclr:2025:Rej_ected-1"  # the same paper, had its year been corrected
    with pytest.raises(SnapshotError, match="1 id\\(s\\) no record of this build has") as e:
        build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED, gone}))
    assert e.value.reason == "takedown_unmatched" and gone in str(e.value)
    assert not (tmp_path / "snapshots").exists() or not [
        p for p in (tmp_path / "snapshots").iterdir() if p.name != ".lock"
    ]


def test_a_listed_record_without_an_abstract_is_withheld_not_missing(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({NO_ABSTRACT}))
    m = manifest(result.path)
    assert m["withheld"] == [NO_ABSTRACT]
    assert m["abstract_missing"]["ICML"]["2023"] == 0  # type: ignore[index]
    assert m["abstract_withheld"]["ICML"]["2023"] == 1  # type: ignore[index]


def test_an_existing_snapshot_withholding_other_ids_is_refused(cache: Path, tmp_path: Path) -> None:
    """The listed record had no abstract, so records.jsonl (and the directory name) are what an unlisted build
    writes: `_holds` compares `withheld`, so the unlisted snapshot isn't passed off as this one."""
    build(cache, tmp_path / "snapshots", BUILT)
    with pytest.raises(SnapshotError, match="isn't this snapshot"):
        build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({NO_ABSTRACT}))


def test_the_reader_counts_withheld_apart_from_missing(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED, NO_ABSTRACT}))
    records = RecordFile(result.path)
    assert records.withheld == {REJECTED, NO_ABSTRACT}
    assert dict(records.abstract_withheld) == {("ICLR", 2024): 1, ("ICML", 2023): 1}
    assert dict(records.track_withheld) == {("ICLR", 2024, "main"): 1, ("ICML", 2023, "main"): 1}
    assert dict(records.abstract_missing) == {("ICLR", 2025): 1}
    assert records.attributions[REJECTED] is None  # no abstract, so nothing to attribute


def _edited(snapshot: Path, out: Path, edit_manifest: object) -> Path:
    copy = writable_copy(snapshot, out)
    m = manifest(copy)
    assert callable(edit_manifest)
    edit_manifest(m)
    (copy / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return copy


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (
            lambda m: m.update(withheld=[REJECTED, NEURIPS]),
            "withheld_abstract_present",
        ),  # it has its abstract
        (lambda m: m.update(withheld=["op:iclr:2024:NotHere001"]), "withheld_invalid"),  # no such record
        (lambda m: m.update(withheld="op:iclr:2024:Rej_ected-1"), "withheld_invalid"),  # not a list
    ],
)
def test_the_reader_refuses_a_manifest_whose_withheld_ids_dont_hold(
    cache: Path, tmp_path: Path, edit: object, reason: str
) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    copy = _edited(result.path, tmp_path / "copy", edit)
    with pytest.raises(SnapshotError) as e:
        RecordFile(copy)
    assert e.value.reason == reason


def test_diff_names_the_abstracts_withheld_and_lifted(cache: Path, tmp_path: Path) -> None:
    before = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({NO_ABSTRACT})).path
    after = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED})).path
    got = diff(before, after)
    assert got["abstract_withheld"] == {"added": [REJECTED], "lifted": [NO_ABSTRACT]}
    assert got["changed"] == {REJECTED: ["abstract"]}
    assert diff(after, after)["abstract_withheld"] == {"added": [], "lifted": []}


def test_cli_build_reads_the_list_from_the_data_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    (data / "takedowns").mkdir()
    (data / "takedowns" / "withheld.txt").write_text(
        f"# takedowns (ids only; the log holds the rest)\n\n{REJECTED}  # 2026-09-30 request\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["abstracts_withheld"] == 1
    assert load_records(Path(built["path"]))[REJECTED].abstract is None
    assert stat.S_IMODE(Path(built["path"]).stat().st_mode) == 0o555


def test_cli_build_refuses_a_malformed_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    listed = tmp_path / "list.txt"
    listed.write_text(f"{REJECTED}\nRej_ected-1\n", encoding="utf-8")  # a native id, not a record id
    capsys.readouterr()
    assert cli.main(["--data-dir", str(data), "snapshot", "build", "--takedowns", str(listed)]) == 1
    err = capsys.readouterr().err
    assert "list.txt line 2" in err and "not a record id" in err
    assert not (data / "snapshots").exists()  # refused before anything was built


def test_cli_build_without_a_list_withholds_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    capsys.readouterr()
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 0
    assert json.loads(capsys.readouterr().out)["abstracts_withheld"] == 0
