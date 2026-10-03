"""`op record save` and `op record replay` (task-083; spec 08 §CLI): the CLI half of search records, over the
same functions as `POST /records` and `GET /records/{id}` (`openproceedings.records`).

A saved record is the one the API would write for the same query and index (every field but its id and
time); a replay prints the API's replay block, and exits 0 on `reproduced` or `drifted`, 3 on `mismatch`
(ERROR `API_REPLAY_MISMATCH`), 1 when the record isn't there. No log line holds query text.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
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


def take_away(data_dir: Path, path: Path) -> None:
    """Remove an index directory as one atomic rename out of the data directory (TASK-165). An earlier
    in-process `op` call's Tantivy reader can still be finishing the reload its meta.json watcher thread starts
    at open, which creates `.tantivy-meta.lock` again (`engine.index.open_index`); landing inside an `rmtree`
    it failed it with "Directory not empty". After a rename it lands in the moved directory, which the test's
    tmp_path cleanup removes."""
    path.rename(data_dir.parent / f"gone-{path.name}")


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
    take_away(data_dir, data_dir / "indexes" / store.big)
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
    take_away(data_dir, data_dir / "indexes")
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


# --- round-1 review (feat/m3-followups gate) --------------------------------------------------------------
def pinned_refusals(err: str) -> list[dict[str, Any]]:
    return [x for x in log_lines(err) if x["event"] == "pinned_index_unavailable"]


def test_a_store_at_its_size_cap_refuses_the_save(
    capsys: Capsys, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's size cap applies to the CLI too (the API's default, `records_max_bytes`)."""
    import openproceedings.records as records
    from openproceedings.api.config import ApiConfig

    saved(capsys, data_dir, "trust")  # the store exists, well under its cap
    cap = ApiConfig.model_fields["records_max_bytes"].default
    monkeypatch.setattr(records.RecordStore, "_used_bytes", lambda _self: cap)
    code, out, err = op(capsys, data_dir, "record", "save", "trust")
    assert code == 1 and out == ""
    assert "op record save: API_RECORDS_STORE_FULL" in err
    (full,) = [x for x in log_lines(err) if x["event"] == "records_store_full"]
    assert full["max_bytes"] == cap


def test_save_refuses_an_index_directory_not_named_for_its_index(
    capsys: Capsys, data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record pins the engine's index_version, which a replay finds by directory name: an index whose
    engine reports another version (a copied directory is caught earlier, by its manifest) is refused."""
    import openproceedings.engine.tantivy_engine as tantivy_engine

    monkeypatch.setattr(
        tantivy_engine, "TantivyEngine", lambda _path: SimpleNamespace(index_version="ffff00")
    )
    code, out, err = op(capsys, data_dir, "record", "save", "trust", "--index", store.big)
    assert code == 1 and out == ""
    assert f"indexes/{store.big} holds index ffff00, not one named for it" in err
    assert not (data_dir / RECORDS_DIR).exists()


def test_replay_skips_an_alias_named_like_the_records_index(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """A symlink named like the record's version is not that version (`open_pinned`'s rule, shared with
    `IndexState.pinned`): absent, one DEBUG line, and the replay runs on `current` as drift."""
    record_id = saved(capsys, data_dir, "trust")["record_id"]
    point_current(data_dir, store.small)
    take_away(data_dir, data_dir / "indexes" / store.big)
    (data_dir / "indexes" / store.big).symlink_to(store.small)
    code, out, err = op(capsys, data_dir, "--log-level", "debug", "record", "replay", record_id, "--json")
    assert code == 0 and json.loads(out)["index_version"] == store.small
    (line,) = pinned_refusals(err)
    assert (line["level"], line["reason"], line["cause_reason"]) == ("DEBUG", "absent", "alias")
    assert "error" not in line


def test_replay_of_a_record_naming_no_index_version_is_absent(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """`current` (or any name that isn't an index_version) is never opened as a record's own index."""
    good = saved(capsys, data_dir, "trust")["record_id"]
    odd = tampered(data_dir, good, index_version="current")
    point_current(data_dir, store.small)
    code, out, err = op(capsys, data_dir, "--log-level", "debug", "record", "replay", odd, "--json")
    assert (code, json.loads(out)["status"], json.loads(out)["index_version"]) == (0, "drifted", store.small)
    (line,) = pinned_refusals(err)
    assert (line["level"], line["reason"], line["cause_reason"]) == ("DEBUG", "absent", "name_invalid")


def test_replay_refuses_a_tampered_record_index_at_error(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """The record's own index no longer verifies: one ERROR line (the load failure's reason, never its
    message), and the replay runs on `current` as drift."""
    record_id = saved(capsys, data_dir, "trust")["record_id"]
    point_current(data_dir, store.small)
    victim = data_dir / "indexes" / store.big / "ids.txt"  # as test_lifecycle tampers an index
    victim.chmod(0o644)
    victim.write_text("forged\n", encoding="utf-8")
    code, out, err = op(capsys, data_dir, "record", "replay", record_id, "--json")
    assert code == 0 and json.loads(out)["index_version"] == store.small
    (line,) = pinned_refusals(err)
    assert (line["level"], line["reason"], line["error"]) == ("ERROR", "tampered", "IndexBuildError")
    assert line["cause_reason"] and str(data_dir) not in json.dumps(line)


def test_replay_refuses_a_record_index_whose_engine_reports_another_version(
    capsys: Capsys, data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openproceedings.engine.tantivy_engine as tantivy_engine

    record_id = saved(capsys, data_dir, "trust")["record_id"]
    point_current(data_dir, store.small)
    real = tantivy_engine.TantivyEngine

    def opener(path: Path) -> Any:
        return SimpleNamespace(index_version="ffff00") if path.name == store.big else real(path)

    monkeypatch.setattr(tantivy_engine, "TantivyEngine", opener)
    code, out, err = op(capsys, data_dir, "record", "replay", record_id, "--json")
    assert code == 0 and json.loads(out)["index_version"] == store.small
    (line,) = pinned_refusals(err)
    assert (line["level"], line["reason"], line["cause_reason"]) == (
        "ERROR",
        "tampered",
        "index_version_mismatch",
    )


def test_replay_with_its_own_index_here_never_needs_current(
    capsys: Capsys, data_dir: Path, store: Store
) -> None:
    """The record's own index is opened first; `current` (removed here) and --index are never read."""
    record_id = saved(capsys, data_dir, "trust")["record_id"]
    (data_dir / "indexes" / "current").unlink()
    code, body, _err = replay_json(capsys, data_dir, record_id)
    assert (code, body["status"], body["index_version"]) == (0, "reproduced", store.big)


def test_a_malformed_and_an_unknown_record_id_are_told_apart(capsys: Capsys, data_dir: Path) -> None:
    saved(capsys, data_dir, "trust")
    _code, _out, malformed = op(capsys, data_dir, "record", "replay", "short")
    _code, _out, unknown = op(capsys, data_dir, "record", "replay", "AAAAAAAAAAAA")
    assert "a record id is 12 characters from A–Z, a–z, 0–9, `-` and `_`" in malformed
    assert "no search record with that id" in unknown and "12 characters" not in unknown


def test_record_replayed_carries_the_hash_versions_and_counts(capsys: Capsys, data_dir: Path) -> None:
    """The search-records skill (§The CLI): the id, versions, `canonical_hash` and counts, never the query."""
    record_id = saved(capsys, data_dir, f"trust OR {SECRET}")["record_id"]
    record = RecordStore(data_dir / RECORDS_DIR).get(record_id)
    assert record is not None
    code, _out, err = op(capsys, data_dir, "record", "replay", record_id)
    assert code == 0
    (line,) = [x for x in log_lines(err) if x["event"] == "record_replayed"]
    assert line["canonical_hash"] == record.canonical_hash and line["query_version"] == QUERY_VERSION
    assert (line["total"], line["added_total"], line["removed_total"]) == (record.total, 0, 0)
    assert SECRET not in err


def test_record_saved_is_logged_before_the_output(
    capsys: Capsys, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record is in the store once `insert` returns: a reader that went away (a broken pipe while
    printing) still leaves its log line."""

    def gone(_value: object) -> None:
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_print", gone)
    code, _out, err = op(capsys, data_dir, "record", "save", "trust", "--json")
    assert code == 0
    (line,) = [x for x in log_lines(err) if x["event"] == "record_saved"]
    assert RecordStore(data_dir / RECORDS_DIR).get(line["record_id"]) is not None


def test_a_parse_refusal_names_the_full_command(capsys: Capsys, data_dir: Path) -> None:
    _code, _out, err = op(capsys, data_dir, "--log-level", "debug", "record", "save", "(trust")
    (line,) = [x for x in log_lines(err) if x["event"] == "cli_refused"]
    assert line["command"] == "record save"


def test_save_notes_a_query_a_default_api_would_refuse_as_too_many_verified_clauses(
    capsys: Capsys, data_dir: Path
) -> None:
    """The CLI saves it (its serving policy is left out), but says so: a default instance refuses it (422)
    and withholds its replay."""
    from openproceedings.api.config import ApiConfig

    cap = ApiConfig.model_fields["max_verified_clauses"].default
    q = " OR ".join(f'"trust* w{i}"' for i in range(cap + 1))
    code, _out, err = op(capsys, data_dir, "record", "save", q)
    assert code == 0
    assert "note: a default-configured API instance refuses this query (API_TOO_MANY_VERIFIED_CLAUSES" in err
    at_cap = " OR ".join(f'"trust* w{i}"' for i in range(cap))
    code, _out, err = op(capsys, data_dir, "record", "save", at_cap)
    assert code == 0 and "note:" not in err  # at the cap: a default instance runs it
    with TestClient(make_app(data_dir)) as client:
        r = client.post("/api/v1/records", json={"q": q, "mode": "native"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "API_TOO_MANY_VERIFIED_CLAUSES"


def test_save_notes_a_query_a_default_api_would_refuse_as_too_costly(
    capsys: Capsys, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.api.config import ApiConfig

    monkeypatch.setattr(ApiConfig.model_fields["max_verification_candidates"], "default", 10)
    q = '"trust* model"'
    code, _out, err = op(capsys, data_dir, "record", "save", q)
    assert code == 0 and "(API_QUERY_TOO_COSTLY" in err
    with TestClient(make_app(data_dir, max_verification_candidates=10)) as client:
        r = client.post("/api/v1/records", json={"q": q, "mode": "native"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "API_QUERY_TOO_COSTLY"
    code, _out, err = op(capsys, data_dir, "record", "save", "trust")
    assert code == 0 and "note:" not in err  # no position check: nothing to say
