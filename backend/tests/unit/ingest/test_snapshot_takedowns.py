"""Takedowns in `op snapshot build` (TASK-136, decision-022; spec 08 §Deploy): the list withholds each listed
abstract from the snapshot, whatever the cache supplies; the manifest names and counts them apart from missing
abstracts; the reader checks them; a diff names them; a listed id the build doesn't have refuses it."""

from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.ingest.dedup import Conflict, DedupResult, Merge, dedup
from openproceedings.ingest.reconcile import crawled, reconcile
from openproceedings.ingest.snapshot import (
    WITHHELD_VALUE,
    RecordFile,
    SnapshotError,
    build,
    diff,
    ingest_ris,
    load_records,
    load_sources,
    with_crawl_conflicts,
    withhold,
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


def _result(cache: Path) -> DedupResult:
    """The fixture cache's dedup result, as `build` computes it before withholding."""
    records, _reports, crawls = load_sources(cache)
    return with_crawl_conflicts(reconcile(dedup(records), crawled(crawls)).result, crawls)


def test_a_listed_id_the_build_lacks_is_reported_never_refused(cache: Path, tmp_path: Path) -> None:
    """A paper gone from its sources stays listed for the older versions that hold it: the build goes on, and
    says which ids it doesn't hold (`op takedown check` names a typo)."""
    gone = "op:neurips:2019:GoneFromSources1"
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED, gone}))
    assert result.created and result.takedowns_unmatched == (gone,) and result.takedowns_followed == {}
    assert result.withheld == (REJECTED,) and manifest(result.path)["withheld"] == [REJECTED]


def test_a_rekeyed_listed_paper_is_followed_to_its_new_id(cache: Path) -> None:
    """Its year corrected, the paper has a new id: the old one (still on the list, since older versions hold it)
    leads to the new one, whose abstract is withheld too, so a rekey never brings the abstract back."""
    result = _result(cache)
    old = next(r for r in result.records if r.id == REJECTED)
    moved = old.model_copy(update={"id": "op:iclr:2025:Rej_ected-1", "year": 2025})
    rekeyed = replace(result, records=tuple(sorted((*(r for r in result.records if r.id != REJECTED), moved),
                                                   key=lambda r: r.id)))  # fmt: skip
    done = withhold(rekeyed, frozenset({REJECTED}))
    assert done.followed == {REJECTED: moved.id} and done.unmatched == ()
    assert done.withheld == {moved.id}
    [new] = [r for r in done.result.records if r.id == moved.id]
    assert new.abstract is None and new.claims("abstract") == ()


def test_a_listed_paper_merged_into_another_is_followed_to_the_survivor(cache: Path) -> None:
    result = _result(cache)
    merged = replace(
        result,
        records=tuple(r for r in result.records if r.id != REJECTED),
        merges=(Merge(NEURIPS, REJECTED, "title_venue_year", "x", "ICLR", 2024, "ris"),),
    )
    done = withhold(merged, frozenset({REJECTED}))
    assert done.followed == {REJECTED: NEURIPS} and done.withheld == {NEURIPS}
    assert next(r for r in done.result.records if r.id == NEURIPS).abstract is None


def test_a_paper_rekeyed_and_merged_is_followed_through_its_merge(cache: Path) -> None:
    """Its year corrected (a new id) and merged into another record: the merge names the new id, and the one
    merged-away id with the listed id's native id leads to the survivor."""
    result = _result(cache)
    moved = "op:iclr:2025:Rej_ected-1"
    merged = replace(
        result,
        records=tuple(r for r in result.records if r.id != REJECTED),
        merges=(Merge(NEURIPS, moved, "title_venue_year", "x", "ICLR", 2025, "ris"),),
    )
    done = withhold(merged, frozenset({REJECTED}))
    assert done.followed == {REJECTED: NEURIPS} and done.withheld == {NEURIPS}


def test_an_ambiguous_rekey_is_not_followed_but_reported(cache: Path) -> None:
    """Two records with the listed id's native id: the build can't tell which is the paper, so it follows
    neither and reports the id (the operator lists the right one)."""
    result = _result(cache)
    old = next(r for r in result.records if r.id == REJECTED)
    twins = (old.model_copy(update={"id": "op:iclr:2025:Rej_ected-1", "year": 2025}),
             old.model_copy(update={"id": "op:iclr:2023:Rej_ected-1", "year": 2023}))  # fmt: skip
    rest = tuple(r for r in result.records if r.id != REJECTED)
    done = withhold(
        replace(result, records=tuple(sorted((*rest, *twins), key=lambda r: r.id))), frozenset({REJECTED})
    )
    assert (done.followed, done.unmatched, done.withheld) == ({}, (REJECTED,), frozenset())


def test_a_followed_successors_conflict_texts_are_withheld_too(cache: Path) -> None:
    result = _result(cache)
    old = next(r for r in result.records if r.id == REJECTED)
    moved = old.model_copy(update={"id": "op:iclr:2025:Rej_ected-1", "year": 2025})
    clash = Conflict(moved.id, "abstract", REJECTED_ABSTRACT, "ris", RECRAWLED, "ris", "tie:ris")
    rekeyed = replace(
        result,
        records=tuple(sorted((*(r for r in result.records if r.id != REJECTED), moved), key=lambda r: r.id)),
        conflicts=(clash,),
    )
    done = withhold(rekeyed, frozenset({REJECTED}))
    assert done.result.conflicts == (replace(clash, value_a=WITHHELD_VALUE, value_b=WITHHELD_VALUE),)


def test_a_listed_record_with_only_overruled_abstract_claims_loses_them(cache: Path) -> None:
    """No abstract, but claims whose values are an abstract's text (overruled by precedence): withheld too."""
    result = _result(cache)
    bare = next(r for r in result.records if r.id == NO_ABSTRACT)
    claim = next(c for r in result.records for c in r.claims("abstract"))
    with_claim = bare.model_copy(
        update={"provenance": (*bare.provenance, claim.model_copy(update={"value": "Overruled text."}))}
    )
    changed = replace(result, records=tuple(with_claim if r.id == NO_ABSTRACT else r for r in result.records))
    done = withhold(changed, frozenset({NO_ABSTRACT}))
    assert done.withheld == {NO_ABSTRACT}
    assert next(r for r in done.result.records if r.id == NO_ABSTRACT).claims("abstract") == ()


def test_listing_a_record_without_an_abstract_changes_nothing_in_the_snapshot(
    cache: Path, tmp_path: Path
) -> None:
    """Nothing to withhold, so the snapshot is the unlisted one, byte for byte (the API marks the id withheld
    from the list at serve time): listing it never blocks a rebuild."""
    plain = build(cache, tmp_path / "snapshots", BUILT)
    listed = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({NO_ABSTRACT}))
    assert (listed.path, listed.created, listed.withheld) == (plain.path, False, ())
    assert "withheld" not in manifest(listed.path)


def test_the_same_records_withholding_other_abstracts_is_refused_without_advising_retirement(
    cache: Path, tmp_path: Path
) -> None:
    """A directory holding these very records whose manifest names other withheld ids (as when a listed
    abstract went from its source after a build that withheld it): refused as `takedown_differs`, saying to
    serve it as it is, never to retire a snapshot a search record may pin."""
    first = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    first.path.chmod(0o755)
    m = manifest(first.path)
    for key in ("withheld", "abstract_withheld", "abstract_withheld_by_track"):
        del m[key]
    (first.path / "manifest.json").chmod(0o644)
    (first.path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(SnapshotError, match="serve it as it is") as e:
        build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED}))
    assert e.value.reason == "takedown_differs"


def test_the_reader_counts_withheld_apart_from_missing(cache: Path, tmp_path: Path) -> None:
    result = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED, NEURIPS}))
    records = RecordFile(result.path)
    assert records.withheld == {REJECTED, NEURIPS}
    assert dict(records.abstract_withheld) == {("ICLR", 2024): 1, ("NeurIPS", 2025): 1}
    assert dict(records.track_withheld) == {("ICLR", 2024, "main"): 1, ("NeurIPS", 2025, "main"): 1}
    assert dict(records.abstract_missing) == {("ICLR", 2025): 1, ("ICML", 2023): 1}
    assert records.attributions[REJECTED] is None  # no abstract, so nothing to attribute
    assert REJECTED in records and "op:iclr:2024:NotHere001" not in records


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
    before = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({NEURIPS})).path
    after = build(cache, tmp_path / "snapshots", BUILT, takedowns=frozenset({REJECTED})).path
    got = diff(before, after)
    assert got["abstract_withheld"] == {"added": [REJECTED], "lifted": [NEURIPS]}
    assert got["changed"] == {NEURIPS: ["abstract"], REJECTED: ["abstract"]}
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
    assert built["withheld_ids"] == [REJECTED]
    assert (built["takedowns_followed"], built["takedowns_unmatched"]) == ({}, [])
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
    assert json.loads(capsys.readouterr().out)["withheld_ids"] == []


def test_cli_build_refuses_a_named_list_that_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mistyped --takedowns path is never read as "nothing listed"."""
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    capsys.readouterr()
    argv = [
        "--data-dir",
        str(data),
        "snapshot",
        "build",
        "--takedowns",
        str(tmp_path / "takedown" / "list.txt"),
    ]
    assert cli.main(argv) == 1
    assert "list.txt is missing" in capsys.readouterr().err
    assert not (data / "snapshots").exists()


def test_cli_build_says_which_listed_ids_it_lacks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    (data / "takedowns").mkdir()
    (data / "takedowns" / "withheld.txt").write_text("op:iclr:2024:GoneAway01\n", encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["takedowns_unmatched"] == ["op:iclr:2024:GoneAway01"]
    assert "1 listed id(s) no record of this build has: op:iclr:2024:GoneAway01" in out.err


def test_cli_build_refuses_a_missing_list_once_a_snapshot_withheld(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TASK-067: a snapshot on disk that withheld an abstract proves this deployment has takedowns, so a
    missing default list (an unmounted or renamed takedowns/) never builds the abstract back in."""
    data = tmp_path / "data"
    assert cli.main(["--data-dir", str(data), "ingest", "ris", str(source(tmp_path))]) == 0
    (data / "takedowns").mkdir()
    (data / "takedowns" / "withheld.txt").write_text(f"{REJECTED}\n", encoding="utf-8")
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 0
    (data / "takedowns" / "withheld.txt").unlink()
    capsys.readouterr()
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 1
    assert "withheld.txt is missing" in capsys.readouterr().err
    (data / "takedowns" / "withheld.txt").write_text("", encoding="utf-8")  # emptied: lifted on purpose
    assert cli.main(["--data-dir", str(data), "snapshot", "build"]) == 0


def test_a_proceedings_hash_in_another_year_is_another_paper(cache: Path) -> None:
    """TASK-067 review: a NeurIPS hash is md5 of a per-year paper number, so `op:neurips:2019:nips-H` and
    `op:neurips:2013:nips-H` are two papers (1,281 such hashes in the 2026-09-29 snapshot). Listing one never
    follows to the other."""
    result = _result(cache)
    other_year = next(r for r in result.records if r.id == NEURIPS).model_copy(
        update={"id": NEURIPS.replace(":2025:", ":2013:"), "year": 2013}
    )
    rest = tuple(r for r in result.records if r.id != NEURIPS)
    done = withhold(
        replace(result, records=tuple(sorted((*rest, other_year), key=lambda r: r.id))), frozenset({NEURIPS})
    )
    assert (done.followed, done.unmatched, done.withheld) == ({}, (NEURIPS,), frozenset())
