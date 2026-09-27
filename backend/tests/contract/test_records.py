"""`POST /api/v1/records`, `GET /api/v1/records/{id}` and `/diff` (task-037; spec 04 §Search records, §Testing).

The replay matrix: reproduced (on the served index, and on a pinned older one loaded on demand), drifted
(a changed snapshot with the pinned index gone; a changed query_version), and mismatch (fixture rows
inserted with a wrong `ids_hash`, and separately a wrong `excluded`: 200, `mismatch`, exactly one ERROR
`API_REPLAY_MISMATCH` line, never `drifted`). Plus the diff, the errors, and no query text in any log line.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from openproceedings.api import records as api_records
from openproceedings.api.state import IndexState
from openproceedings.query import QUERY_VERSION
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse
from openproceedings.records import RECORD_ID, RecordStore, SearchRecord, ids_hash

from tests.contract.conftest import SECRET, Store, build, make_app, point_current
from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper

Logs = Callable[[], list[dict[str, Any]]]
SPEC_FIELDS = {  # spec 04 §Search records, every row of the table
    "input", "mode", "canonical", "canonical_hash", "identification_query",
    "index_version", "tokenizer_version", "query_version", "snapshot_hash", "crawl_dates",
    "searched_at", "total", "excluded", "expansions", "translations", "warnings", "ids", "ids_hash", "dedup",
    "semantic_version",
}  # fmt: skip
EVERYTHING = "year:1900..2100"  # every record, then the defaults


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == code
    return r.json()["error"]  # type: ignore[no-any-return]


def save(client: TestClient, q: str, mode: str = "native") -> str:
    r = client.post("/api/v1/records", json={"q": q, "mode": mode})
    assert r.status_code == 201, r.text
    return str(r.json()["record_id"])


def replayed(client: TestClient, record_id: str) -> dict[str, Any]:
    r = client.get(f"/api/v1/records/{record_id}")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def mismatch_lines(logs: Logs) -> list[dict[str, Any]]:
    return [x for x in logs() if x.get("code") == "API_REPLAY_MISMATCH"]


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    """The app over a private data directory (its records.sqlite is this test's own)."""
    with TestClient(make_app(data_dir)) as c:
        yield c


# --- POST /records: every field frozen --------------------------------------------------------------------
def test_post_freezes_every_field_of_spec_04s_table(client: TestClient, data_dir: Path, store: Store) -> None:
    q = "trust AND calibrat*"
    r = client.post("/api/v1/records", json={"q": q})
    assert r.status_code == 201, r.text
    created = r.json()
    assert RECORD_ID.fullmatch(created["record_id"])
    assert created["url"] == f"/record/{created['record_id']}"
    assert (created["index_version"], created["tokenizer_version"], created["query_version"]) == (
        store.big, TOKENIZER_VERSION, QUERY_VERSION,
    )  # fmt: skip

    record = replayed(client, created["record_id"])["record"]
    assert set(record) == SPEC_FIELDS | {"record_id", "schema_version", "ranking_params"}
    search = client.get("/api/v1/search", params={"q": q, "limit": 200}).json()
    parsed = parse(q)
    assert record["input"] == q and record["mode"] == "native"
    for f in ("canonical", "canonical_hash", "identification_query"):
        assert record[f] == getattr(parsed, f)
    assert record["total"] == search["total"] > 0
    assert record["excluded"] == search["excluded"]
    assert list(record["excluded"]["track"]) == list(search["excluded"]["track"])  # the pinned order too
    assert record["expansions"] == search["query"]["expansions"] and record["expansions"]
    assert record["warnings"] == search["query"]["warnings"]
    assert record["translations"] == search["query"]["translations"]
    assert record["ids"] == sorted(record["ids"]) and len(record["ids"]) == record["total"]
    assert set(record["ids"]) >= {h["id"] for h in search["hits"]}
    assert record["ids_hash"] == ids_hash(record["ids"])
    manifest = json.loads((data_dir / "indexes" / store.big / "manifest.json").read_text())
    snapshot = json.loads((data_dir / "snapshots" / manifest["snapshot"] / "manifest.json").read_text())
    assert record["index_version"] == store.big
    assert (record["tokenizer_version"], record["query_version"]) == (TOKENIZER_VERSION, QUERY_VERSION)
    for f in ("snapshot_hash", "schema_version", "ranking_params"):
        assert record[f] == manifest[f]
    assert record["crawl_dates"] == {"all": snapshot["crawl_window"]}
    assert record["dedup"] == {"merged": 0, "ambiguous_not_merged": 0}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", record["searched_at"])
    assert record["semantic_version"] is None


def test_post_scholar_mode_keeps_input_and_translations_and_reproduces(client: TestClient) -> None:
    q = "trust source:PMLR"
    record_id = save(client, q, "scholar")
    body = replayed(client, record_id)
    assert body["record"]["input"] == q and body["record"]["mode"] == "scholar"
    assert [d["code"] for d in body["record"]["translations"]] == [
        d.code for d in parse(q, "scholar").translations
    ]
    assert body["replay"]["status"] == "reproduced"


def test_post_refuses_what_search_refuses_and_writes_nothing(client: TestClient, data_dir: Path) -> None:
    e = error(client.post("/api/v1/records", json={"q": "(trust"}), 422, "PARSE_UNBALANCED_PAREN")
    assert e["diagnostics"]
    error(client.post("/api/v1/records", json={"q": "x" * 2001}), 422, "PARSE_TOO_LONG")
    error(client.post("/api/v1/records", json={"q": "trust", "total": 3}), 422, "API_BAD_PARAM")
    error(client.post("/api/v1/records", json={"q": "trust", "mode": "wos"}), 422, "API_BAD_PARAM")
    assert not (data_dir / "records.sqlite").exists()


# --- replay: reproduced -----------------------------------------------------------------------------------
def test_replay_on_the_same_index_is_reproduced(client: TestClient, store: Store) -> None:
    record_id = save(client, "trust AND calibrat*")
    body = replayed(client, record_id)
    replay = body["replay"]
    assert replay["status"] == "reproduced"
    assert replay["index_version"] == body["index_version"] == store.big
    assert (
        replay["ids_hash"] == body["record"]["ids_hash"] and replay["ids_match"] and replay["excluded_match"]
    )
    assert replay["total"] == body["record"]["total"] and replay["excluded"] == body["record"]["excluded"]
    assert (replay["added"], replay["removed"], replay["membership_identical"]) == (0, 0, True)
    assert replay["changed"] == [] and replay["refused"] is None


def test_replay_loads_the_pinned_index_after_a_swap(data_dir: Path, store: Store, logs: Logs) -> None:
    app = make_app(data_dir)
    with TestClient(app) as client:
        record_id = save(client, "trust AND calibrat*")
        point_current(data_dir, store.small)
        state: IndexState = app.state.index
        assert state.load() and state.engine is not None and state.engine.index_version == store.small
        body = replayed(client, record_id)
    assert body["replay"]["status"] == "reproduced"  # the pinned version is still here: loaded on demand
    assert body["replay"]["index_version"] == body["index_version"] == store.big
    access = [x for x in logs() if x["event"] == "request" and x["route"] == "/api/v1/records/{id}"]
    assert access[-1]["index_version"] == store.big  # the access line names the index the replay ran on


def test_a_record_id_is_never_a_path(client: TestClient) -> None:
    for bad in ("short", "abcdefghijk.", "abcdefghijklm", "abcdef%20ghij", "abcdefghijk%C3%A9"):
        e = error(client.get(f"/api/v1/records/{bad}"), 422, "API_BAD_PARAM")
        assert bad not in e["message"]
        error(client.get(f"/api/v1/records/{bad}/diff"), 422, "API_BAD_PARAM")
    error(
        client.get("/api/v1/records/ab%2F..%2Fcdefg"), 404, "API_NOT_FOUND"
    )  # a `/` never reaches the route


def test_an_unknown_record_is_404_without_creating_the_store(client: TestClient, data_dir: Path) -> None:
    e = error(client.get("/api/v1/records/AAAAAAAAAAAA"), 404, "API_RECORD_NOT_FOUND")
    assert "AAAAAAAAAAAA" not in e["message"]
    error(client.get("/api/v1/records/AAAAAAAAAAAA/diff"), 404, "API_RECORD_NOT_FOUND")
    assert not (data_dir / "records.sqlite").exists()
    save(client, "trust")
    error(client.get("/api/v1/records/AAAAAAAAAAAA"), 404, "API_RECORD_NOT_FOUND")


# --- replay: mismatch (fixture rows; the store stays append-only) ----------------------------------------
def tampered(data_dir: Path, record_id: str, **changes: Any) -> str:
    """A fixture row: a copy of record `record_id` with `changes`, inserted as a new record."""
    store = RecordStore(data_dir / "records.sqlite")
    original = store.get(record_id)
    assert original is not None
    fields = original.model_dump(exclude={"record_id", "ids"})
    return store.insert({**fields, **changes}, original.ids).record_id


@pytest.mark.parametrize("what", ["ids_hash", "excluded"])
def test_a_tampered_record_is_a_mismatch_logged_once_never_drifted(
    client: TestClient, data_dir: Path, logs: Logs, what: str
) -> None:
    good = save(client, f"trust OR {SECRET}")
    record = replayed(client, good)["record"]
    if what == "ids_hash":
        change: dict[str, Any] = {"ids_hash": ids_hash([*record["ids"], "op:iclr:2024:forged"])}
    else:
        excluded = json.loads(json.dumps(record["excluded"]))
        excluded["total"] += 1
        excluded["track"]["unknown"] += 1
        change = {"excluded": excluded}
    bad = tampered(data_dir, good, **change)
    before = len(mismatch_lines(logs))

    body = replayed(client, bad)
    assert body["replay"]["status"] == "mismatch"
    assert body["replay"]["ids_match"] is (what != "ids_hash")
    assert body["replay"]["excluded_match"] is (what != "excluded")
    assert body["replay"]["changed"] == []  # same index, same query version: never drifted
    lines = mismatch_lines(logs)[before:]
    assert len(lines) == 1, lines
    assert lines[0]["level"] == "ERROR" and lines[0]["record_id"] == bad
    assert SECRET not in json.dumps(logs())

    diff = client.get(f"/api/v1/records/{bad}/diff")
    assert diff.status_code == 200 and diff.json()["status"] == "mismatch"
    assert len(mismatch_lines(logs)[before:]) == 2  # one per replay
    assert replayed(client, good)["replay"]["status"] == "reproduced"  # the original is untouched


def test_export_hook_refuses_a_mismatch_record_with_409(data_dir: Path) -> None:
    """The function TASK-036's `/export?record_id=` calls before streaming (a stand-in route here)."""
    app: FastAPI = make_app(data_dir)

    @app.get("/api/v1/_probe/citable/{record_id}")
    def probe(request: Request, record_id: str) -> dict[str, str]:
        record = api_records.require_citable(request, record_id)
        return {"record_id": record.record_id, "status": api_records.replay_status(request, record_id)}

    with TestClient(app) as client:
        good = save(client, "trust")
        bad = tampered(data_dir, good, ids_hash="0" * 64)
        assert client.get(f"/api/v1/_probe/citable/{good}").json() == {
            "record_id": good,
            "status": "reproduced",
        }
        error(client.get(f"/api/v1/_probe/citable/{bad}"), 409, "API_RECORD_MISMATCH")
        error(client.get("/api/v1/_probe/citable/nope"), 422, "API_BAD_PARAM")
        error(client.get("/api/v1/_probe/citable/AAAAAAAAAAAA"), 404, "API_RECORD_NOT_FOUND")


# --- replay: drifted --------------------------------------------------------------------------------------
def test_a_changed_query_version_is_drifted_and_membership_identical(
    client: TestClient, data_dir: Path, logs: Logs
) -> None:
    good = save(client, "trust AND calibrat*")
    old = tampered(data_dir, good, query_version="0")
    body = replayed(client, old)
    replay = body["replay"]
    assert replay["status"] == "drifted"
    assert replay["changed"] == [
        {"input": "query_version", "kind": "method", "recorded": "0", "current": QUERY_VERSION}
    ]
    assert (replay["added"], replay["removed"], replay["membership_identical"]) == (0, 0, True)
    diff = client.get(f"/api/v1/records/{old}/diff").json()
    assert (diff["added"], diff["removed"], diff["membership_identical"]) == ([], [], True)
    assert mismatch_lines(logs) == []


@dataclass(frozen=True)
class Drift:
    root: Path  # snapshots/{before,after}, indexes/{<before>,<after>}
    before: str  # the first 300 fixture records
    after: str  # records 20..319: twenty removed, twenty added
    removed: list[Rec]
    added: list[Rec]


@pytest.fixture(scope="module")
def drift(tmp_path_factory: pytest.TempPathFactory) -> Drift:
    root = tmp_path_factory.mktemp("drift")
    corpus = list(records())
    before = build(corpus[:300], root / "snapshots", "before", root / "indexes")
    after = build(corpus[20:320], root / "snapshots", "after", root / "indexes")
    return Drift(root, before, after, corpus[:20], corpus[300:320])


def only(drift: Drift, snapshot: str, version: str, dest: Path) -> Path:
    """A data directory holding one index (and its snapshot), served as `current`."""
    (dest / "indexes").mkdir(parents=True)
    (dest / "snapshots").mkdir()
    shutil.copytree(drift.root / "snapshots" / snapshot, dest / "snapshots" / snapshot)
    shutil.copytree(drift.root / "indexes" / version, dest / "indexes" / version)
    (dest / "indexes" / "current").symlink_to(version)
    return dest


def kept(recs: list[Rec]) -> list[str]:
    """The ids of `recs` that pass the default filters (what EVERYTHING matches), by hand."""
    return sorted(
        as_paper(r).id
        for r in recs
        if r.track in DEFAULT_CLAUSES["track"] and r.status in DEFAULT_CLAUSES["status"]
    )


def test_a_changed_snapshot_with_the_pinned_index_gone_is_drifted_with_exact_counts(
    drift: Drift, tmp_path: Path, logs: Logs
) -> None:
    first = only(drift, "before", drift.before, tmp_path / "first")
    with TestClient(make_app(first)) as client:
        record_id = save(client, EVERYTHING)
        assert replayed(client, record_id)["replay"]["status"] == "reproduced"
    second = only(drift, "after", drift.after, tmp_path / "second")
    shutil.copy(first / "records.sqlite", second / "records.sqlite")  # the record moves; its index doesn't

    added, removed = kept(drift.added), kept(drift.removed)
    assert added and removed  # the fixture really drifts under the defaults
    with TestClient(make_app(second)) as client:
        body = replayed(client, record_id)
        diff = client.get(f"/api/v1/records/{record_id}/diff").json()
    replay = body["replay"]
    assert replay["status"] == "drifted" and replay["index_version"] == drift.after
    assert body["record"]["index_version"] == drift.before  # the stored record is unchanged
    before_manifest = json.loads((drift.root / "indexes" / drift.before / "manifest.json").read_text())
    after_manifest = json.loads((drift.root / "indexes" / drift.after / "manifest.json").read_text())
    assert replay["changed"] == [
        {
            "input": "snapshot_hash",
            "kind": "corpus",
            "recorded": before_manifest["snapshot_hash"],
            "current": after_manifest["snapshot_hash"],
        }
    ]
    assert (replay["added"], replay["removed"]) == (len(added), len(removed))
    assert replay["membership_identical"] is False and replay["ids_match"] is False
    assert replay["total"] == body["record"]["total"] + len(added) - len(removed)

    assert diff["status"] == "drifted" and diff["recorded_index_version"] == drift.before
    assert diff["changed"] == replay["changed"]
    titles = {as_paper(r).id: as_paper(r).title for r in drift.added}
    assert diff["added"] == [{"id": i, "title": titles[i]} for i in added]
    # the removed papers are in no index this instance holds (the pinned one is gone): titles are null
    assert diff["removed"] == [{"id": i, "title": None} for i in removed]
    assert mismatch_lines(logs) == []
    assert any(x["event"] == "pinned_index_unavailable" and x["reason"] == "absent" for x in logs())


def test_diff_titles_removed_papers_from_the_pinned_index_when_it_is_still_here(
    drift: Drift, tmp_path: Path
) -> None:
    both = only(drift, "before", drift.before, tmp_path / "both")
    shutil.copytree(drift.root / "snapshots" / "after", both / "snapshots" / "after")
    shutil.copytree(drift.root / "indexes" / drift.after, both / "indexes" / drift.after)
    with TestClient(make_app(both)) as client:
        good = save(client, EVERYTHING)
    point_current(both, drift.after)
    old = tampered(both, good, query_version="0")  # the pinned index is here, but not the query version
    with TestClient(make_app(both)) as client:
        diff = client.get(f"/api/v1/records/{old}/diff").json()
    assert diff["status"] == "drifted"
    assert [c["input"] for c in diff["changed"]] == ["snapshot_hash", "query_version"]
    titles = {as_paper(r).id: as_paper(r).title for r in drift.removed}
    assert diff["removed"] == [{"id": i, "title": titles[i]} for i in kept(drift.removed)]


def test_diff_of_a_reproduced_record_is_empty(client: TestClient) -> None:
    record_id = save(client, "trust")
    diff = client.get(f"/api/v1/records/{record_id}/diff").json()
    assert diff["status"] == "reproduced" and diff["changed"] == []
    assert (diff["added"], diff["removed"], diff["membership_identical"]) == ([], [], True)


# --- privacy ----------------------------------------------------------------------------------------------
def test_no_query_text_in_any_log_line(client: TestClient, logs: Logs) -> None:
    record_id = save(client, f"{SECRET} OR trust")
    replayed(client, record_id)
    client.get(f"/api/v1/records/{record_id}/diff")
    client.post("/api/v1/records", json={"q": f"({SECRET}"})
    raw = logs.raw.getvalue()  # type: ignore[attr-defined]
    assert SECRET not in raw
    lines = [x for x in logs() if x["event"] == "request" and "/records" in (x.get("route") or "")]
    assert len(lines) == 4 and all("canonical_hash" in x for x in lines[:3])  # the 4th didn't parse


def test_the_stored_record_holds_the_query_text(client: TestClient, data_dir: Path) -> None:
    record_id = save(client, f"{SECRET} OR trust")
    stored = RecordStore(data_dir / "records.sqlite").get(record_id)
    assert isinstance(stored, SearchRecord) and SECRET in stored.input  # the record keeps what the logs don't
