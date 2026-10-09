"""The `op` CLI skeleton: every planned subcommand exists and says which task implements it."""

import argparse
import json
from pathlib import Path

import pytest
from openproceedings import cli

PLANNED = {
    "embed": "task-058",
}
PLANNED_EVALS = {"audit": "task-055", "near-miss": "task-061"}  # coverage: TASK-054, scholar: TASK-056
DEFERRED = {"embed", "eval near-miss"}  # the semantic layer, deferred to phase 2 (decision-017)


def test_help_lists_every_planned_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    listed = {line.split()[0] for line in out.splitlines() if line.startswith("    ") and line.split()}
    assert (
        set(PLANNED) | {"ingest", "snapshot", "index", "search", "record", "serve", "openapi", "eval"}
        <= listed
    )


@pytest.mark.parametrize(("name", "task"), sorted(PLANNED_EVALS.items()))
def test_eval_stubs_exit_2_and_name_their_task(
    name: str, task: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["eval", name]) == 2
    err = capsys.readouterr().err
    assert f"op eval {name}" in err and task in err and "not implemented yet" in err
    assert ("deferred to phase 2 (decision-017)" in err) == (f"eval {name}" in DEFERRED)
    assert ("planned in" in err) == (f"eval {name}" not in DEFERRED)


def test_eval_stub_list_matches_the_planned_table() -> None:
    assert cli.PLANNED_EVALS == PLANNED_EVALS


@pytest.mark.parametrize(("name", "task"), sorted(PLANNED.items()))
def test_stub_exits_2_and_names_its_task(name: str, task: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([name]) == 2
    err = capsys.readouterr().err
    assert f"op {name}" in err
    assert task in err
    assert "not implemented yet" in err
    assert ("deferred to phase 2 (decision-017)" in err) == (name in DEFERRED)


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


def test_ingest_neurips_offline_from_a_seeded_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.unit.ingest.test_neurips import seed_2013

    seed_2013(tmp_path / "cache")
    assert cli.main(["--data-dir", str(tmp_path), "ingest", "neurips", "--year", "2013", "--offline"]) == 0
    out = json.loads(capsys.readouterr().out)
    [listing] = out["listings"]
    assert (out["requests"], listing["records"], listing["tracks"]) == (0, 2, {"main": 2})
    assert (tmp_path / "cache" / "neurips" / "crawls" / "2013.json").is_file()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["ingest", "neurips", "--year", "2013", "--delay", "0.1"], "--delay must be at least"),
        (["ingest", "neurips", "--year", "2013", "--delay", "nan"], "--delay must be finite"),
        (["ingest", "neurips", "--year", "2013", "--delay", "inf"], "--delay must be finite"),
        (["ingest", "neurips", "--year", "2013", "--delay=-inf"], "--delay must be finite"),
        (["ingest", "pmlr", "--year", "2013", "--dry-run", "--offline"], "don't combine"),
        (["ingest", "pmlr", "--year", "2026", "--offline"], "no verified PMLR volume"),
        (["ingest", "neurips", "--year", "1986", "--offline"], "the first NIPS (decision-047)"),
        (["ingest", "dblp", "--year", "2013", "--offline"], "covers ICML 1988-2012 (PMLR from 2013)"),
        (["ingest", "dblp", "--year", "1990", "--offline"], "not in the cache (offline)"),
        (["ingest", "neurips", "--year", "2013", "--offline"], "not in the cache (offline)"),
    ],
)
def test_ingest_crawl_refusals_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    assert cli.main(["--data-dir", str(tmp_path), *argv]) == 1
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("year", ["13", "2013-2012", "2013-", "twenty", "2013-20145"])
def test_ingest_crawl_year_must_be_a_year_or_range(year: str) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "neurips", "--year", year, "--offline"])
    assert exc.value.code == 2


def test_ingest_crawl_years_and_ranges_combine() -> None:
    ns = cli.build_parser().parse_args(
        ["ingest", "pmlr", "--year", "2013-2015", "--year", "2014", "--year", "2020"]
    )
    assert sorted({y for chunk in ns.years for y in chunk}) == [2013, 2014, 2015, 2020]


@pytest.mark.parametrize(
    "argv", [["ingest"], ["snapshot"], ["ingest", "ris"], ["snapshot", "diff", "a"], ["ingest", "neurips"]]
)
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
        ["--log-level", "debug", "--log-format", "json", "eval", "audit", "old"],
        ["eval", "near-miss", "--query", "trust"],
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


def test_ingest_ojs_dispatches_the_journals_and_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.ingest.sources import crawl

    seen: dict[str, object] = {}

    def fake(journals: object, cache: Path, **kwargs: object) -> dict[str, object]:
        seen.update(journals=journals, cache=cache, **kwargs)
        return {"ok": True}

    monkeypatch.setattr(crawl, "ingest_ojs", fake)
    argv = ["--data-dir", str(tmp_path), "ingest", "ojs", "--journal", "AAAI", "--offline"]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert seen["journals"] == ["AAAI"]
    assert (seen["offline"], seen["dry_run"], seen["refresh"]) == (True, False, False)
    assert seen["cache"] == tmp_path / "cache"


def test_ingest_ojs_rejects_an_unknown_journal() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "ojs", "--journal", "AAAJ"])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (["--dry-run", "--offline"], "don't combine"),
        (["--delay", "0.1"], "--delay must be finite and at least"),
        (["--delay", "nan"], "--delay must be finite and at least"),
    ],
)
def test_ingest_ojs_usage_refusals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str], message: str
) -> None:
    assert cli.main(["--data-dir", str(tmp_path), "ingest", "ojs", *flags]) == 1
    assert message in capsys.readouterr().err


def test_ingest_ojs_oai_error_exits_nonzero_with_the_refresh_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.ingest.sources import ojs

    from tests.unit.ingest.ojs import oai
    from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _seed

    monkeypatch.setattr(ojs, "TABLE", TABLE)
    _seed(tmp_path / "cache", oai.error("badResumptionToken"))
    argv = ["--data-dir", str(tmp_path), "ingest", "ojs", "--journal", "AAAI", "--offline"]
    assert cli.main(argv) != 0
    assert "--refresh" in capsys.readouterr().err
