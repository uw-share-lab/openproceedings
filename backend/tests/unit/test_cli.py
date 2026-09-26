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
    for name in PLANNED:
        assert name in out


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
