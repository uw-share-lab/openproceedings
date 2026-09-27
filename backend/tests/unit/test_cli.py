"""The `op` CLI skeleton: every planned subcommand exists and says which task implements it."""

import argparse
import json
from pathlib import Path

import pytest
from openproceedings import cli

PLANNED = {
    "embed": "task-058",
    "eval": "task-054",
}


def test_help_lists_every_planned_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    listed = {line.split()[0] for line in out.splitlines() if line.startswith("    ") and line.split()}
    assert set(PLANNED) | {"ingest", "snapshot", "index", "search", "record", "serve", "openapi"} <= listed


@pytest.mark.parametrize(("name", "task"), sorted(PLANNED.items()))
def test_stub_exits_2_and_names_its_task(name: str, task: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([name]) == 2
    err = capsys.readouterr().err
    assert f"op {name}" in err
    assert task in err
    assert "not implemented yet" in err


@pytest.mark.parametrize(("name", "found"), [("snap", True), ("../outside", False), (".hidden", False)])
def test_the_search_header_finds_its_snapshot_by_the_one_rule(tmp_path: Path, name: str, found: bool) -> None:
    """`op search`'s header reads the index's snapshot through `indexed_snapshot` (M3a round 2): a plain
    directory name under <data-dir>/snapshots, never a path that leaves it."""
    data = tmp_path / "data"
    for where in (data / "snapshots" / "snap", data / "outside", data / "snapshots" / ".hidden"):
        where.mkdir(parents=True)
        (where / "manifest.json").write_text(json.dumps({"snapshot_hash": "h"}), encoding="utf-8")
    index = data / "indexes" / "abc"
    index.mkdir(parents=True)
    manifest = {"snapshot": name, "snapshot_hash": "h"}
    (index / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    got = cli._snapshot_of(argparse.Namespace(data_dir=data), index)
    assert got == ({"snapshot_hash": "h"} if found else None)


@pytest.mark.parametrize(("source", "task"), [("openreview", "task-050"), ("proceedings", "task-052")])
def test_planned_ingest_sources_name_their_task(
    source: str, task: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["ingest", source, "--venue", "ICLR"]) == 2
    err = capsys.readouterr().err
    assert f"op ingest {source}" in err and task in err and "not implemented yet" in err


@pytest.mark.parametrize("argv", [["ingest"], ["snapshot"], ["ingest", "ris"], ["snapshot", "diff", "a"]])
def test_implemented_commands_need_their_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_no_subcommand_prints_help_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert "usage: op" in capsys.readouterr().err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("op ")


def test_stub_list_matches_the_planned_table() -> None:
    assert set(cli.PLANNED) == set(PLANNED)


def test_bad_log_level_is_a_usage_error_not_a_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--log-level", "verbose", "embed"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "--log-level" in err


def test_log_level_is_case_insensitive() -> None:
    assert cli.main(["--log-level", "debug", "embed"]) == 2  # the stub's exit code, not a usage error


def test_default_log_format_is_json() -> None:
    assert cli.build_parser().parse_args(["embed"]).log_format == "json"


@pytest.mark.parametrize(
    "argv",
    [
        ["embed", "build", "--index", "current"],
        ["--log-level", "debug", "--log-format", "json", "index", "retire", "old"],
        ["eval", "scholar", "--query", "trust"],
    ],
)
def test_stub_accepts_the_future_arguments_of_its_command(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_subcommand_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["export", "--help"])
    assert exc.value.code == 0
    assert "usage: op export" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv", [["record"], ["record", "save"], ["record", "replay"], ["record", "delete", "x"]]
)
def test_record_needs_an_action_and_its_argument(argv: list[str]) -> None:
    """`op record` is implemented (task-083): a missing action or argument is a usage error, not a stub."""
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_record_actions_take_their_options() -> None:
    parser = cli.build_parser()
    ns = parser.parse_args(["record", "save", "trust", "--mode", "scholar", "--index", "abc", "--json"])
    assert (ns.query, ns.mode, ns.index, ns.json, ns.action) == ("trust", "scholar", "abc", True, "save")
    ns = parser.parse_args(["record", "replay", "AAAAAAAAAAAA"])
    assert (ns.record_id, ns.index, ns.json, ns.action) == ("AAAAAAAAAAAA", None, False, "replay")
    assert cli.EXIT_MISMATCH not in (0, 1, 2)  # a mismatch is told apart from drift, refusal and usage
