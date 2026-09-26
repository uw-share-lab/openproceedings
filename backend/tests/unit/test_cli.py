"""The `op` CLI skeleton: every planned subcommand exists and says which task implements it."""

import pytest
from openproceedings import cli

PLANNED = {
    "ingest": "task-019",
    "snapshot": "task-022",
    "index": "task-023",
    "search": "task-030",
    "export": "task-030",
    "serve": "task-034",
    "record": "task-037",
    "openapi": "task-040",
    "embed": "task-058",
    "eval": "task-054",
}


def test_help_lists_every_planned_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    listed = {line.split()[0] for line in out.splitlines() if line.startswith("    ") and line.split()}
    assert set(PLANNED) <= listed


@pytest.mark.parametrize(("name", "task"), sorted(PLANNED.items()))
def test_stub_exits_2_and_names_its_task(name: str, task: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([name]) == 2
    err = capsys.readouterr().err
    assert f"op {name}" in err
    assert task in err
    assert "not implemented yet" in err


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
        cli.main(["--log-level", "verbose", "search"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "--log-level" in err


def test_log_level_is_case_insensitive() -> None:
    assert cli.main(["--log-level", "debug", "search"]) == 2  # the stub's exit code, not a usage error


def test_default_log_format_is_json() -> None:
    assert cli.build_parser().parse_args(["search"]).log_format == "json"


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "trust AND x", "--explain"],
        ["--log-level", "debug", "--log-format", "json", "index", "build"],
        ["export", "q", "--format", "ris"],
    ],
)
def test_stub_accepts_the_future_arguments_of_its_command(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_subcommand_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["search", "--help"])
    assert exc.value.code == 0
    assert "usage: op search" in capsys.readouterr().out
