"""`op record save` and `op record replay` (task-083; spec 08 §CLI): the CLI half of search records, over the
same functions as `POST /records` and `GET /records/{id}` (`openproceedings.records`).

A saved record is the one the API would write for the same query and index (every field but its id and
time); a replay prints the API's replay block, and exits 0 on `reproduced` or `drifted`, 3 on `mismatch`
(ERROR `API_REPLAY_MISMATCH`), 1 when the record isn't there. No log line holds query text.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.query import QUERY_VERSION
from openproceedings.query.parser import parse
from openproceedings.records import RECORD_ID, RECORDS_DIR, RecordStore

from tests.contract.conftest import SECRET, Store, make_app, point_current
from tests.contract.test_records import mismatched, replayed, tampered

Capsys = pytest.CaptureFixture[str]


def op(capsys: Capsys, data_dir: Path, *argv: str) -> tuple[int, str, str]:
    """Run `op --data-dir <data_dir> …` in-process: (exit code, stdout, stderr)."""
    code = cli.main(["--data-dir", str(data_dir), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def log_lines(err: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in err.splitlines() if line.startswith("{")]


def saved(capsys: Capsys, data_dir: Path, q: str, *argv: str) -> dict[str, Any]:
    code, out, err = op(capsys, data_dir, "record", "save", q, "--json", *argv)
    assert code == 0, err
    return json.loads(out)  # type: ignore[no-any-return]


def replay_json(capsys: Capsys, data_dir: Path, record_id: str) -> tuple[int, dict[str, Any], str]:
    code, out, err = op(capsys, data_dir, "record", "replay", record_id, "--json")
    return code, json.loads(out), err


# --- save -------------------------------------------------------------------------------------------------
def test_save_writes_the_record_post_records_writes(capsys: Capsys, data_dir: Path) -> None:
    """AC #1: every field equal to the API's record for the same query and index, but its id and time."""
    q = "trust AND calibrat* AND year:2020..2024"
    body = saved(capsys, data_dir, q)
    assert RECORD_ID.fullmatch(body["record_id"]) and body["page"] == f"/record/{body['record_id']}"
    with TestClient(make_app(data_dir)) as client:
        r = client.post("/api/v1/records", json={"q": q, "mode": "native"})
        assert r.status_code == 201, r.text
        api_id = r.json()["record_id"]
    store = RecordStore(data_dir / RECORDS_DIR)
    ours, theirs = store.get(body["record_id"]), store.get(api_id)
    assert ours is not None and theirs is not None
    volatile = {"record_id", "searched_at"}
    assert ours.model_dump(exclude=volatile) == theirs.model_dump(exclude=volatile)
    assert ours.ids and ours.total == len(ours.ids) > 0
    # what --json prints is the stored record (ids left out, as GET /records/{id} leaves them out)
    assert {k: v for k, v in body.items() if k != "page"} == ours.model_dump(mode="json", exclude={"ids"})


def test_save_in_scholar_mode_keeps_the_input_and_its_translations(capsys: Capsys, data_dir: Path) -> None:
    body = saved(capsys, data_dir, "trust source:PMLR", "--mode", "scholar")
    assert body["mode"] == "scholar" and body["input"] == "trust source:PMLR"
    assert [d["code"] for d in body["translations"]] == [
        d.code for d in parse("trust source:PMLR", "scholar").translations
    ]


def test_save_prints_a_human_summary(capsys: Capsys, data_dir: Path, store: Store) -> None:
    code, out, _err = op(capsys, data_dir, "record", "save", "trust")
    assert code == 0
    first = out.splitlines()[0]
    record_id = first.split()[2]
    assert first == f"saved record {record_id} · page /record/{record_id}"
    record = RecordStore(data_dir / RECORDS_DIR).get(record_id)
    assert record is not None
    assert f"index {store.big}" in out and f"query {QUERY_VERSION}" in out
    assert f"screened (total) {record.total}" in out and f"ids_hash {record.ids_hash}" in out
    assert f"canonical: {record.canonical}" in out


def test_save_on_a_named_index_pins_that_version(capsys: Capsys, data_dir: Path, store: Store) -> None:
    assert saved(capsys, data_dir, "trust", "--index", store.small)["index_version"] == store.small


@pytest.mark.parametrize("index", ["../big", "/tmp", "nope"])
def test_save_selects_only_an_index_under_the_data_dir(capsys: Capsys, data_dir: Path, index: str) -> None:
    """A record pins a version a replay must find by name, so --index is `current` or an index_version
    under <data-dir>/indexes (api.state.index_path), never an arbitrary directory."""
    code, out, err = op(capsys, data_dir, "record", "save", "trust", "--index", index)
    assert code == 1 and out == "" and "op record save:" in err
    assert not (data_dir / RECORDS_DIR).exists()


def test_a_query_that_does_not_parse_saves_nothing(capsys: Capsys, data_dir: Path) -> None:
    code, out, err = op(capsys, data_dir, "record", "save", "(trust")
    assert code == 1 and out == "" and "PARSE_UNBALANCED_PAREN" in err
    assert not (data_dir / RECORDS_DIR).exists()


def test_a_full_disk_refuses_the_save(
    capsys: Capsys, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's free-space floor applies to the CLI (the API's default, `records_min_free_bytes`)."""
    from collections import namedtuple

    import openproceedings.records as records

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(records.shutil, "disk_usage", lambda _p: usage(1 << 40, 1 << 40, 0))
    code, out, err = op(capsys, data_dir, "record", "save", "trust")
    assert code == 1 and out == ""
    assert "op record save: API_RECORDS_STORE_FULL: The search-record store on this instance is full" in err
    assert any(x["event"] == "records_store_full" for x in log_lines(err))
    assert RecordStore(data_dir / RECORDS_DIR).pinned("anything") == 0


# --- replay -----------------------------------------------------------------------------------------------
def test_replay_on_the_same_index_is_reproduced(capsys: Capsys, data_dir: Path, store: Store) -> None:
    record_id = saved(capsys, data_dir, "trust AND calibrat*")["record_id"]
    code, out, _err = op(capsys, data_dir, "record", "replay", record_id)
    assert code == 0
    assert out.splitlines()[0] == f"record {record_id}: reproduced"
    assert f"replayed on index {store.big}" in out and "membership-identical" in out


def test_replay_json_is_the_apis_replay_block(capsys: Capsys, data_dir: Path) -> None:
    """The same function as GET /records/{id}, and the same shape (api.records.replay_info)."""
    record_id = saved(capsys, data_dir, 'trust AND "calibrat* confidence"')["record_id"]
    code, body, _err = replay_json(capsys, data_dir, record_id)
    assert code == 0
    with TestClient(make_app(data_dir)) as client:
        api = replayed(client, record_id)
    assert body["record_id"] == record_id and body["recorded_index_version"] == api["record"]["index_version"]
    assert {k: v for k, v in body.items() if k not in ("record_id", "recorded_index_version")} == api[
        "replay"
    ]
    assert body["status"] == "reproduced" and body["verified_clauses"] == 1


def test_replay_loads_the_pinned_index_after_current_moves(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    record_id = saved(capsys, data_dir, "trust")["record_id"]
    point_current(data_dir, store.small)
    code, body, _err = replay_json(capsys, data_dir, record_id)
    assert (code, body["status"], body["index_version"]) == (0, "reproduced", store.big)


def test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """Spec 08: zero on `drifted`, so a script can tell a bug (mismatch) from drift."""
    record_id = saved(capsys, data_dir, "year:1900..2100")["record_id"]
    point_current(data_dir, store.small)
    shutil.rmtree(data_dir / "indexes" / store.big)
    code, body, _err = replay_json(capsys, data_dir, record_id)
    assert code == 0 and body["status"] == "drifted" and body["index_version"] == store.small
    assert [c["input"] for c in body["changed"]] == ["snapshot_hash"]
    assert body["removed_total"] > 0 and body["added_total"] == 0 and body["membership_identical"] is False
    code, out, _err = op(capsys, data_dir, "record", "replay", record_id)
    assert code == 0 and out.splitlines()[0] == f"record {record_id}: drifted"
    assert "changed: snapshot_hash (corpus)" in out
    assert f"added +0 · removed −{body['removed_total']}" in out


def test_a_changed_query_version_is_drifted(capsys: Capsys, data_dir: Path) -> None:
    good = saved(capsys, data_dir, "trust")["record_id"]
    old = tampered(data_dir, good, query_version="0")
    code, body, _err = replay_json(capsys, data_dir, old)
    assert code == 0 and body["status"] == "drifted" and body["membership_identical"] is True
    assert [c["input"] for c in body["changed"]] == ["query_version"]


@pytest.mark.parametrize("what", ["ids_hash", "excluded", "stored_ids"])
def test_a_mismatch_exits_3_and_logs_api_replay_mismatch_at_error(
    capsys: Capsys, data_dir: Path, what: str
) -> None:
    good = saved(capsys, data_dir, f"trust OR {SECRET}")["record_id"]
    with TestClient(make_app(data_dir)) as client:
        bad = mismatched(client, data_dir, good, what)
    capsys.readouterr()
    code, out, err = op(capsys, data_dir, "record", "replay", bad)
    assert code == cli.EXIT_MISMATCH == 3
    assert out.splitlines()[0] == f"record {bad}: mismatch"
    assert "do not cite" in out
    errors = [x for x in log_lines(err) if x.get("code") == "API_REPLAY_MISMATCH"]
    assert [x["level"] for x in errors] == ["ERROR"] and errors[0]["record_id"] == bad
    assert SECRET not in err


def test_a_canonical_that_no_longer_runs_is_refused_with_null_counts(capsys: Capsys, data_dir: Path) -> None:
    good = saved(capsys, data_dir, "trust")["record_id"]
    old = tampered(data_dir, good, canonical="(trust", query_version="0")
    code, body, _err = replay_json(capsys, data_dir, old)
    assert code == 0 and body["status"] == "drifted" and body["refused"] == "PARSE_UNBALANCED_PAREN"
    assert body["total"] is None and body["membership_identical"] is None
    code, out, _err = op(capsys, data_dir, "record", "replay", old)
    assert "not run: PARSE_UNBALANCED_PAREN" in out


def test_the_cli_does_not_withhold_a_replay_over_the_serving_limits(capsys: Capsys, data_dir: Path) -> None:
    """The verified-clause cap and the candidate ceiling are the API's serving policy (decision-010); the
    CLI runs on the operator's own machine and replays whatever the record holds, as `op search` runs it."""
    clauses = " OR ".join(f'"trust* {w}"' for w in ("model", "human", "system", "agent", "user"))
    record_id = saved(capsys, data_dir, clauses)["record_id"]
    with TestClient(make_app(data_dir, max_verified_clauses=2)) as client:
        assert replayed(client, record_id)["replay"]["refused"] == "API_TOO_MANY_VERIFIED_CLAUSES"
    code, body, _err = replay_json(capsys, data_dir, record_id)
    assert code == 0 and body["status"] == "reproduced" and body["refused"] is None
    assert body["verified_clauses"] == 5


@pytest.mark.parametrize("record_id", ["AAAAAAAAAAAA", "short", "../../etc/pw"])
def test_an_unknown_or_malformed_record_exits_1(capsys: Capsys, data_dir: Path, record_id: str) -> None:
    code, out, err = op(capsys, data_dir, "record", "replay", record_id)
    assert code == 1 and out == ""
    assert "op record replay:" in err and record_id not in err.split("op record replay:")[1]
    assert not (data_dir / RECORDS_DIR).exists()  # a read never creates the store


def test_replay_needs_an_index_when_its_own_is_gone(capsys: Capsys, data_dir: Path, store: Store) -> None:
    record_id = saved(capsys, data_dir, "trust")["record_id"]
    shutil.rmtree(data_dir / "indexes")
    (data_dir / "indexes").mkdir()
    code, out, err = op(capsys, data_dir, "record", "replay", record_id)
    assert code == 1 and out == "" and "op record replay:" in err and "--index" in err


def test_no_query_text_in_any_log_line(capsys: Capsys, data_dir: Path) -> None:
    code, _out, err = op(capsys, data_dir, "--log-level", "debug", "record", "save", f"trust OR {SECRET}")
    assert code == 0
    lines = log_lines(err)
    saved_line = next(x for x in lines if x["event"] == "record_saved")
    record_id = saved_line["record_id"]
    code, _out, err2 = op(capsys, data_dir, "--log-level", "debug", "record", "replay", record_id)
    assert code == 0
    replayed_line = next(x for x in log_lines(err2) if x["event"] == "record_replayed")
    assert replayed_line["status"] == "reproduced" and replayed_line["record_id"] == record_id
    assert SECRET not in err and SECRET not in err2


def test_the_exit_code_holds_across_a_real_process(capsys: Capsys, data_dir: Path) -> None:
    """The console script's exit status, not only `main`'s return value: 0 reproduced, 3 mismatch."""
    good = saved(capsys, data_dir, "trust")["record_id"]
    with TestClient(make_app(data_dir)) as client:
        bad = mismatched(client, data_dir, good, "ids_hash")

    def run(record_id: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", "from openproceedings.cli import main_entry; main_entry()",
             "--data-dir", str(data_dir), "record", "replay", record_id],
            capture_output=True, text=True, check=False, timeout=300,
        )  # fmt: skip

    assert run(good).returncode == 0
    assert run(bad).returncode == 3
