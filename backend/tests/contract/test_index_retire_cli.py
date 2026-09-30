"""`op index retire <index_version>` (TASK-085; spec 08 §CLI): deletes `<data-dir>/indexes/<index_version>/`,
and refuses (exit 1, one line to stderr, nothing touched) while a search record pins the version, while
`current` points at it, or when the name isn't an index_version directory directly under indexes/."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from openproceedings import cli
from openproceedings.records import RECORDS_DIR, RecordStore

from tests.contract.conftest import Store, point_current

Capsys = pytest.CaptureFixture[str]


def op(capsys: Capsys, data_dir: Path, *argv: str) -> tuple[int, str, str]:
    code = cli.main(["--data-dir", str(data_dir), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def log_lines(err: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in err.splitlines() if line.startswith("{")]


def tree(root: Path) -> dict[str, int]:
    """Every path under `root` with its mtime (symlinks not followed): 'no files touched' is this unchanged.
    The record store is left out: SQLite's read-only open of a WAL database may create its -wal/-shm files."""
    return {
        str(p.relative_to(root)): p.lstat().st_mtime_ns
        for p in sorted(root.rglob("*"))
        if p.relative_to(root).parts[0] != RECORDS_DIR
    }


def save(capsys: Capsys, data_dir: Path, index: str) -> str:
    code, out, err = op(capsys, data_dir, "record", "save", "trust", "--index", index, "--json")
    assert code == 0, err
    return str(json.loads(out)["record_id"])


def test_a_pinned_version_is_refused_with_its_count(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """AC #1: non-zero exit, the count reported, the directory intact."""
    save(capsys, data_dir, store.small)
    save(capsys, data_dir, store.small)
    before = tree(data_dir)
    code, out, err = op(capsys, data_dir, "index", "retire", store.small)
    assert code == 1 and out == ""
    assert f"op index retire: 2 search records pin {store.small}" in err and "drifted" in err
    assert tree(data_dir) == before
    [line] = [x for x in log_lines(err) if x["event"].startswith("index_retire")]
    assert line["event"] == "index_retire_refused" and line["level"] == "WARNING"
    assert (line["index_version"], line["reason"], line["pinned"]) == (store.small, "pinned", 2)


def test_one_pinning_record_is_named_in_the_singular(capsys: Capsys, data_dir: Path, store: Store) -> None:
    save(capsys, data_dir, store.small)
    code, _out, err = op(capsys, data_dir, "index", "retire", store.small, "--dry-run")
    assert code == 1 and f"1 search record pins {store.small};" in err and "(dry run)" in err


def test_the_current_version_is_refused(capsys: Capsys, data_dir: Path, store: Store) -> None:
    before = tree(data_dir)
    code, out, err = op(capsys, data_dir, "index", "retire", store.big)
    assert code == 1 and out == ""
    assert f"`current` points at {store.big}" in err
    assert tree(data_dir) == before
    [line] = [x for x in log_lines(err) if x["event"] == "index_retire_refused"]
    assert line["reason"] == "current" and line["pinned"] is None


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("../x", "name_invalid"),
        ("..", "name_invalid"),
        ("current", "name_invalid"),
        ("a/b", "name_invalid"),
        ("/tmp", "name_invalid"),
        ("ABCDEF012345", "name_invalid"),
        (".tmp-retire-abc", "name_invalid"),
        ("", "name_invalid"),
        ("0123456789ab", "not_found"),  # well-formed, but no such index here
    ],
)
def test_an_unknown_or_malformed_version_is_refused(
    capsys: Capsys, data_dir: Path, name: str, reason: str
) -> None:
    (data_dir / "x").mkdir()  # what `../x` would name, from indexes/
    before = tree(data_dir)
    code, out, err = op(capsys, data_dir, "--log-level", "debug", "index", "retire", name)
    assert code == 1 and out == "" and err.count("op index retire:") == 1
    assert tree(data_dir) == before
    [line] = [x for x in log_lines(err) if x["event"] == "index_retire_refused"]
    assert line["reason"] == reason
    if reason == "name_invalid":  # the user's own input: DEBUG, and never logged
        assert line["level"] == "DEBUG" and "index_version" not in line


def test_a_symlink_named_like_a_version_is_not_an_index(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """An alias is not the version: retiring through it could delete the index it points at."""
    alias = "abcdef"
    (data_dir / "indexes" / alias).symlink_to(store.small)
    before = tree(data_dir)
    code, _out, err = op(capsys, data_dir, "index", "retire", alias)
    assert code == 1 and "no index directory abcdef" in err
    assert tree(data_dir) == before


def test_a_version_an_alias_points_at_is_refused(capsys: Capsys, data_dir: Path, store: Store) -> None:
    (data_dir / "indexes" / "previous").symlink_to(store.small)
    code, _out, err = op(capsys, data_dir, "index", "retire", store.small)
    assert code == 1 and f"`previous` points at {store.small}" in err
    assert (data_dir / "indexes" / store.small / "manifest.json").is_file()


def test_an_unreadable_record_store_is_refused(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """Never "unpinned" guessed from a store that can't be read."""
    (data_dir / RECORDS_DIR).mkdir()
    (data_dir / RECORDS_DIR / "records.sqlite").write_bytes(b"not a database" * 100)
    code, _out, err = op(capsys, data_dir, "index", "retire", store.small)
    assert code == 1 and "search-record store can't be read (DatabaseError)" in err
    assert (data_dir / "indexes" / store.small / "manifest.json").is_file()


def test_an_unpinned_version_is_retired(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """AC #2: the directory is gone, the other versions and `current` are intact, nothing is left behind."""
    save(capsys, data_dir, "current")  # a record pinning another version doesn't stop this one
    big = tree(data_dir / "indexes" / store.big)
    code, out, err = op(capsys, data_dir, "index", "retire", store.small)
    assert code == 0, err
    assert json.loads(out) == {"index_version": store.small, "pinned": 0, "retired": True, "dry_run": False}
    indexes = data_dir / "indexes"
    assert not (indexes / store.small).exists()
    assert sorted(p.name for p in indexes.iterdir() if not p.name.startswith(".")) == [store.big, "current"]
    assert not list(indexes.glob(".tmp-*"))
    assert tree(indexes / store.big) == big and (indexes / "current").resolve().name == store.big
    [line] = [x for x in log_lines(err) if x["event"].startswith("index_retire")]
    assert line["event"] == "index_retired" and line["level"] == "INFO"
    assert (line["index_version"], line["pinned"], line["outcome"]) == (store.small, 0, "retired")
    assert isinstance(line["ms"], float)


def test_a_dry_run_reports_and_deletes_nothing(capsys: Capsys, data_dir: Path, store: Store) -> None:
    before = tree(data_dir)
    code, out, err = op(capsys, data_dir, "index", "retire", store.small, "--dry-run")
    assert code == 0 and json.loads(out)["dry_run"] is True and json.loads(out)["retired"] is False
    assert tree(data_dir) == before
    [line] = [x for x in log_lines(err) if x["event"].startswith("index_retire")]
    assert (line["event"], line["outcome"], line["pinned"]) == ("index_retire_checked", "would_retire", 0)


def test_a_replay_on_a_kept_version_still_reproduces(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """Retiring one version leaves a record pinned to another replayable on its own index."""
    record_id = save(capsys, data_dir, store.big)
    point_current(data_dir, store.big)
    assert op(capsys, data_dir, "index", "retire", store.small)[0] == 0
    point_current(data_dir, store.big)
    code, out, err = op(capsys, data_dir, "record", "replay", record_id, "--json")
    assert code == 0, err
    body = json.loads(out)
    assert (body["status"], body["index_version"]) == ("reproduced", store.big)


def test_a_version_pinned_after_moving_current_is_still_refused(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """Promoting another index doesn't unpin the old one: its records still need it."""
    save(capsys, data_dir, "current")  # pins big
    point_current(data_dir, store.small)
    code, _out, err = op(capsys, data_dir, "index", "retire", store.big)
    assert code == 1 and f"1 search record pins {store.big}" in err
    assert RecordStore(data_dir / RECORDS_DIR).pinned(store.big) == 1
    assert (data_dir / "indexes" / store.big / "manifest.json").is_file()


def test_a_leftover_from_a_cut_short_retire_is_swept(capsys: Capsys, data_dir: Path, store: Store) -> None:
    leftover = data_dir / "indexes" / ".tmp-retire-dead"
    leftover.mkdir()
    (leftover / "f").write_text("x")
    os.chmod(leftover / "f", 0o444)
    assert op(capsys, data_dir, "index", "retire", store.small)[0] == 0
    assert not leftover.exists()


def test_the_store_is_opened_read_only(capsys: Capsys, data_dir: Path, store: Store) -> None:
    """A retire with no store creates none."""
    assert op(capsys, data_dir, "index", "retire", store.small)[0] == 0
    assert not (data_dir / RECORDS_DIR).exists()


def test_index_help_lists_retire_as_implemented(capsys: Capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["index", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "retire" in out and "pins it" in out and "planned" not in out
