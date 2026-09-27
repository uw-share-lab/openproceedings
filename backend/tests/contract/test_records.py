"""`POST /api/v1/records`, `GET /api/v1/records/{id}` and `/diff` (task-037; spec 04 §Search records, §Testing).

The replay matrix: reproduced (on the served index, and on a pinned older one loaded on demand), drifted
(a changed snapshot with the pinned index gone; a changed query version, replayed on the pinned index; the
method inputs; a removal-only drift is not membership-identical), refused (null counts), and mismatch
(fixture rows written straight into the store with a wrong `ids_hash`, `excluded`, one bucket,
`canonical_hash`, a non-canonical `canonical` spelling, or a stored list that isn't its `ids_hash`'s: 200,
`mismatch`, exactly one ERROR `API_REPLAY_MISMATCH` line, never `drifted`). Plus the diff and its pages, ids on request, the cost, a full store, the errors, and no
query text in any log line.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api import RateLimit
from openproceedings.api.state import IndexState
from openproceedings.query import QUERY_VERSION
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse
from openproceedings.records import (
    RECORD_ID,
    RECORDS_DIR,
    RecordStore,
    SearchRecord,
    ids_hash,
    new_record_id,
    replay,
)
from openproceedings.timestamps import utc_z

from tests.contract.conftest import SECRET, Store, build, make_app, point_current
from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper

Logs = Callable[[], list[dict[str, Any]]]
SPEC_FIELDS = {  # spec 04 §Search records, every row of the table
    "input", "mode", "canonical", "canonical_hash", "identification_query",
    "index_version", "tokenizer_version", "query_version", "snapshot_hash", "crawl_dates",
    "searched_at", "total", "excluded", "expansions", "translations", "warnings", "ids", "ids_hash", "dedup",
    "semantic_version", "sources", "identification_citable", "crawl_dates_kind",
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


def replayed(client: TestClient, record_id: str, *, ids: bool = False) -> dict[str, Any]:
    r = client.get(f"/api/v1/records/{record_id}", params={"include": "ids"} if ids else {})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def diffed(client: TestClient, record_id: str, **params: Any) -> dict[str, Any]:
    r = client.get(f"/api/v1/records/{record_id}/diff", params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def mismatch_lines(logs: Logs, level: str = "ERROR") -> list[dict[str, Any]]:
    return [x for x in logs() if x.get("code") == "API_REPLAY_MISMATCH" and x["level"] == level]


def store_of(data_dir: Path) -> RecordStore:
    return RecordStore(data_dir / RECORDS_DIR)


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    """The app over a private data directory (its record store is this test's own)."""
    with TestClient(make_app(data_dir)) as c:
        yield c


# --- POST /records: every field frozen --------------------------------------------------------------------
def test_post_freezes_every_field_of_spec_04s_table(client: TestClient, data_dir: Path, store: Store) -> None:
    q = "trust AND calibrat*"
    r = client.post("/api/v1/records", json={"q": q})
    assert r.status_code == 201, r.text
    created = r.json()
    assert RECORD_ID.fullmatch(created["record_id"])
    assert created["page"] == f"/record/{created['record_id']}" and "url" not in created
    assert r.headers["location"] == f"/api/v1/records/{created['record_id']}"  # the API resource
    assert client.get(r.headers["location"]).status_code == 200
    assert (created["index_version"], created["tokenizer_version"], created["query_version"]) == (
        store.big, TOKENIZER_VERSION, QUERY_VERSION,
    )  # fmt: skip

    record = replayed(client, created["record_id"], ids=True)["record"]
    assert set(record) == SPEC_FIELDS | {"record_id", "body_version", "schema_version", "ranking_params"}
    assert record["body_version"] == 2
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
    # the manifest's window, in the API's one timestamp form (UTC, `Z`; spec 04 §Conventions)
    assert record["crawl_dates"] == {"*": {k: utc_z(v) for k, v in snapshot["crawl_window"].items()}}
    assert all(v.endswith("Z") for v in record["crawl_dates"]["*"].values())
    assert record["dedup"] == {
        "merged": 0, "ambiguous_not_merged": 0, "track_not_merged": 0, "venue_year_not_merged": 0,
    }  # fmt: skip
    # the fixture snapshot is RIS-only (a bootstrap corpus): its counts are not identification numbers
    assert record["sources"] == sorted(snapshot["sources"]) == ["ris"]
    assert record["identification_citable"] is False
    assert record["crawl_dates_kind"] == {"*": "scholar_query_dates"}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", record["searched_at"])
    assert record["semantic_version"] is None
    assert (data_dir / RECORDS_DIR / "records.sqlite").is_file()  # its own writable directory


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
    assert not (data_dir / RECORDS_DIR).exists()


# --- replay: reproduced -----------------------------------------------------------------------------------
def test_replay_on_the_same_index_is_reproduced(client: TestClient, store: Store) -> None:
    record_id = save(client, "trust AND calibrat*")
    body = replayed(client, record_id)
    replay_ = body["replay"]
    assert replay_["status"] == "reproduced"
    assert replay_["index_version"] == body["index_version"] == store.big
    assert (
        replay_["ids_hash"] == body["record"]["ids_hash"]
        and replay_["ids_match"]
        and replay_["excluded_match"]
    )
    assert replay_["total"] == body["record"]["total"] and replay_["excluded"] == body["record"]["excluded"]
    assert (replay_["added_total"], replay_["removed_total"], replay_["membership_identical"]) == (0, 0, True)
    assert replay_["changed"] == [] and replay_["refused"] is None


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
    error(client.get("/api/v1/records/ab%2F..%2Fcdefg"), 404, "API_NOT_FOUND")  # `/` never reaches the route


def test_an_unknown_record_is_404_without_creating_the_store(client: TestClient, data_dir: Path) -> None:
    e = error(client.get("/api/v1/records/AAAAAAAAAAAA"), 404, "API_RECORD_NOT_FOUND")
    assert "AAAAAAAAAAAA" not in e["message"]
    error(client.get("/api/v1/records/AAAAAAAAAAAA/diff"), 404, "API_RECORD_NOT_FOUND")
    assert not (data_dir / RECORDS_DIR).exists()
    save(client, "trust")
    error(client.get("/api/v1/records/AAAAAAAAAAAA"), 404, "API_RECORD_NOT_FOUND")


# --- replay: mismatch (fixture rows; the store stays append-only) ----------------------------------------
def tampered(data_dir: Path, record_id: str, *, ids: list[str] | None = None, **changes: Any) -> str:
    """A fixture row: a copy of record `record_id` with `changes` (and, if given, another stored id list),
    written straight into records.sqlite as a broken or older writer would have: `RecordStore.insert`
    refuses a row whose `ids_hash` isn't its list's, and these rows exist to test what replay and export do
    when one is there anyway. The triggers allow a new row (and a new id set)."""
    store = store_of(data_dir)
    original = store.get(record_id)
    assert original is not None and original.ids is not None
    new_id = new_record_id()
    body = {**original.model_dump(mode="json", exclude={"ids"}), **changes, "record_id": new_id}
    stored = original.ids if ids is None else ids
    key = ids_hash(stored)
    conn = sqlite3.connect(store.path)
    try:
        conn.execute(
            "INSERT INTO id_sets SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM id_sets WHERE ids_hash = ?)",
            (key, zlib.compress("\n".join(stored).encode("utf-8")), key),
        )
        conn.execute(
            "INSERT INTO records (record_id, index_version, searched_at, id_set, body) VALUES (?, ?, ?, ?, ?)",
            (new_id, body["index_version"], body["searched_at"], key, json.dumps(body)),
        )
        conn.commit()
    finally:
        conn.close()
    return new_id


MISMATCHES = [
    "ids_hash", "excluded", "bucket", "canonical_hash", "canonical", "stored_ids", "total",
    "identification_query", "expansions", "snapshot_hash",
]  # fmt: skip


def mismatched(client: TestClient, data_dir: Path, good: str, what: str) -> str:
    """A copy of record `good` that replays as `mismatch` on its own index for reason `what`."""
    record = replayed(client, good, ids=True)["record"]
    excluded = json.loads(json.dumps(record["excluded"]))
    change: dict[str, Any]
    if what == "ids_hash":
        change = {"ids_hash": ids_hash([*record["ids"], "op:iclr:2024:forged"])}
    elif what == "excluded":
        excluded["total"] += 1
        excluded["track"]["unknown"] += 1
        change = {"excluded": excluded}
    elif what == "bucket":  # one record moved between buckets: the total still adds up
        moved = next(k for k, n in excluded["track"].items() if k != "unknown" and n > 0)
        excluded["track"][moved] -= 1
        excluded["track"]["unknown"] += 1
        change = {"excluded": excluded}
    elif what == "canonical_hash":
        change = {"canonical_hash": "0" * 64}
    elif what == "canonical":  # the same query, stored in a non-canonical spelling (its hash unchanged)
        assert " AND " in record["canonical"]
        change = {"canonical": record["canonical"].replace(" AND ", "  AND  ")}
    elif what == "total":  # the stored count isn't the stored list's length (an export sends the length)
        change = {"total": record["total"] + 100}
    elif what == "identification_query":  # quoted in a methods section
        change = {"identification_query": record["identification_query"] + " OR forged"}
    elif what == "expansions":
        change = {"expansions": {**record["expansions"], "forg*": ["forged"]}}
    elif what == "snapshot_hash":  # the corpus the record cites isn't the one its index was built from
        change = {"snapshot_hash": "0" * 64}
    else:  # the stored list is not the one `ids_hash` names (the replay itself still matches `ids_hash`)
        assert len(record["ids"]) > 1
        return tampered(data_dir, good, ids=record["ids"][1:])
    return tampered(data_dir, good, **change)


@pytest.mark.parametrize("what", MISMATCHES)
def test_a_tampered_record_is_a_mismatch_logged_once_never_drifted(
    client: TestClient, data_dir: Path, logs: Logs, what: str
) -> None:
    good = save(client, f"trust OR {SECRET}")
    bad = mismatched(client, data_dir, good, what)
    before = len(mismatch_lines(logs))

    body = replayed(client, bad)
    assert body["replay"]["status"] == "mismatch"
    assert body["replay"]["ids_match"] is (what != "ids_hash")
    assert body["replay"]["excluded_match"] is (what not in ("excluded", "bucket"))
    assert body["replay"]["changed"] == []  # same index, same query version: never drifted
    lines = mismatch_lines(logs)[before:]
    assert len(lines) == 1, lines
    assert lines[0]["record_id"] == bad
    assert lines[0]["canonical_match"] is (what not in ("canonical_hash", "canonical"))
    assert lines[0]["stored_ids_match"] is (
        what not in ("ids_hash", "stored_ids", "total")
    )  # a forged hash names no list
    assert lines[0]["identification_match"] is (what != "identification_query")
    assert lines[0]["expansions_match"] is (what != "expansions")
    assert lines[0]["inputs_match"] is (what != "snapshot_hash")
    assert lines[0]["refused"] is None
    assert SECRET not in json.dumps(logs())

    diff = client.get(f"/api/v1/records/{bad}/diff")
    assert diff.status_code == 200 and diff.json()["status"] == "mismatch"
    replayed(client, bad)
    # at ERROR once per record per process; its later replays are DEBUG with the same code
    assert len(mismatch_lines(logs)[before:]) == 1
    assert len([x for x in mismatch_lines(logs, "DEBUG") if x["record_id"] == bad]) == 2
    assert replayed(client, good)["replay"]["status"] == "reproduced"  # the original is untouched


# --- replay: drifted --------------------------------------------------------------------------------------
def test_a_changed_query_version_is_drifted_and_membership_identical(
    client: TestClient, data_dir: Path, logs: Logs
) -> None:
    good = save(client, "trust AND calibrat*")
    old = tampered(data_dir, good, query_version="0")
    replay_ = replayed(client, old)["replay"]
    assert replay_["status"] == "drifted"
    assert replay_["changed"] == [
        {"input": "query_version", "kind": "method", "recorded": "0", "current": QUERY_VERSION}
    ]
    assert (replay_["added_total"], replay_["removed_total"], replay_["membership_identical"]) == (0, 0, True)
    diff = diffed(client, old)
    assert (diff["added"], diff["removed"], diff["membership_identical"]) == ([], [], True)
    assert (diff["added_total"], diff["removed_total"], diff["refused"]) == (0, 0, None)
    assert mismatch_lines(logs) == []


def test_a_removal_only_drift_is_not_membership_identical(client: TestClient, data_dir: Path) -> None:
    """The record holds one id the replay no longer matches, and nothing was added: +0 / −1 is drifted
    membership, never "membership-identical"."""
    good = save(client, "trust AND calibrat*")
    ids = replayed(client, good, ids=True)["record"]["ids"]
    extra = sorted([*ids, "op:iclr:2024:zzGoneSince"])
    old = tampered(data_dir, good, ids=extra, ids_hash=ids_hash(extra), total=len(extra), query_version="0")
    replay_ = replayed(client, old)["replay"]
    assert replay_["status"] == "drifted"
    assert (replay_["added_total"], replay_["removed_total"], replay_["membership_identical"]) == (
        0,
        1,
        False,
    )
    diff = diffed(client, old)
    assert [x["id"] for x in diff["removed"]] == ["op:iclr:2024:zzGoneSince"] and diff["added"] == []
    assert diff["membership_identical"] is False


def test_method_drift_names_tokenizer_schema_and_ranking_inputs(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    good = save(client, "trust")
    manifest = json.loads((data_dir / "indexes" / store.big / "manifest.json").read_text())
    ranking = {"bm25": {"b": 0.5, "k1": 1.2}}
    old = tampered(
        data_dir, good, index_version="ffffffffffff", tokenizer_version="0", schema_version="1",
        ranking_params=ranking,
    )  # fmt: skip
    assert replayed(client, old)["replay"]["changed"] == [
        {"input": "tokenizer_version", "kind": "method", "recorded": "0", "current": TOKENIZER_VERSION},
        {"input": "schema_version", "kind": "method", "recorded": "1", "current": manifest["schema_version"]},
        {
            "input": "ranking_params",
            "kind": "method",
            "recorded": ranking,
            "current": manifest["ranking_params"],
        },
    ]


def test_an_engine_of_another_version_is_never_used_as_the_pinned_one(data_dir: Path, store: Store) -> None:
    """Defence in depth: a loader that hands back the wrong index counts as unavailable, never as a replay
    on the pinned version (which could report `reproduced` or `mismatch` for the wrong index)."""
    app = make_app(data_dir)
    with TestClient(app) as client:
        good = save(client, "trust")
        small = json.loads((data_dir / "indexes" / store.small / "manifest.json").read_text())
        # as if saved on the small index (same query, so on the big one its ids would still match)
        old = tampered(data_dir, good, index_version=store.small, snapshot_hash=small["snapshot_hash"])
        record = store_of(data_dir).get(old)
        served = app.state.index.engine
        assert record is not None and served is not None
        result = replay(record, served, lambda _v: served, data_dir)  # a loader that lies
    assert result.status == "drifted" and result.engine is served  # never "reproduced" on the wrong index
    assert [c.input for c in result.changed] == ["snapshot_hash"]


def test_a_canonical_that_no_longer_runs_is_refused_with_null_counts(
    client: TestClient, data_dir: Path, logs: Logs
) -> None:
    """No comparison happened, so added, removed and membership_identical are null, never "all removed"."""
    good = save(client, "trust")
    for query_version, status in (("0", "drifted"), (QUERY_VERSION, "mismatch")):
        bad = tampered(data_dir, good, canonical="(trust", query_version=query_version)
        replay_ = replayed(client, bad)["replay"]
        assert replay_["status"] == status and replay_["refused"] == "PARSE_UNBALANCED_PAREN"
        for k in ("added_total", "removed_total", "membership_identical", "total", "excluded", "ids_hash",
                  "ids_match", "excluded_match"):  # fmt: skip
            assert replay_[k] is None, k  # compared nothing: never a false that reads as "differed"
        diff = diffed(client, bad)
        assert diff["status"] == status and diff["refused"] == "PARSE_UNBALANCED_PAREN"
        assert (diff["added"], diff["removed"]) == ([], [])
        assert (diff["added_total"], diff["removed_total"], diff["membership_identical"]) == (
            None,
            None,
            None,
        )
    lines = mismatch_lines(logs)
    assert len(lines) == 1 and lines[0]["refused"] == "PARSE_UNBALANCED_PAREN"


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
    shutil.copytree(first / RECORDS_DIR, second / RECORDS_DIR)  # the record moves; its index doesn't

    added, removed = kept(drift.added), kept(drift.removed)
    assert added and len(removed) > 1  # the fixture really drifts under the defaults
    with TestClient(make_app(second)) as client:
        body = replayed(client, record_id)
        diff = diffed(client, record_id)
        page = diffed(client, record_id, offset=1, limit=1)
        error(client.get(f"/api/v1/records/{record_id}/diff", params={"limit": 201}), 422, "API_BAD_PARAM")
        error(client.get(f"/api/v1/records/{record_id}/diff", params={"offset": -1}), 422, "API_BAD_PARAM")
    replay_ = body["replay"]
    assert replay_["status"] == "drifted" and replay_["index_version"] == drift.after
    assert body["record"]["index_version"] == drift.before  # the stored record is unchanged
    before_manifest = json.loads((drift.root / "indexes" / drift.before / "manifest.json").read_text())
    after_manifest = json.loads((drift.root / "indexes" / drift.after / "manifest.json").read_text())
    assert replay_["changed"] == [
        {
            "input": "snapshot_hash",
            "kind": "corpus",
            "recorded": before_manifest["snapshot_hash"],
            "current": after_manifest["snapshot_hash"],
        }
    ]
    assert (replay_["added_total"], replay_["removed_total"]) == (len(added), len(removed))
    assert replay_["membership_identical"] is False and replay_["ids_match"] is False
    assert replay_["total"] == body["record"]["total"] + len(added) - len(removed)

    assert diff["status"] == "drifted" and diff["recorded_index_version"] == drift.before
    assert diff["changed"] == replay_["changed"] and diff["refused"] is None
    titles = {as_paper(r).id: as_paper(r).title for r in drift.added}
    assert diff["added"] == [{"id": i, "title": titles[i]} for i in added]
    # the removed papers are in no index this instance holds (the pinned one is gone): titles are null
    assert diff["removed"] == [{"id": i, "title": None} for i in removed]
    assert (diff["added_total"], diff["removed_total"]) == (len(added), len(removed))
    # a page: at most `limit` of each list from `offset`, the totals always in full
    assert page["removed"] == [{"id": i, "title": None} for i in removed[1:2]] and page["added"] == []
    assert (page["added_total"], page["removed_total"]) == (len(added), len(removed))
    assert mismatch_lines(logs) == []
    assert any(x["event"] == "pinned_index_unavailable" and x["reason"] == "absent" for x in logs())


def test_a_changed_query_version_replays_on_the_pinned_index_when_it_is_here(
    drift: Drift, tmp_path: Path
) -> None:
    """Only the query version drifted: the replay runs on the record's own index, so `changed` isolates the
    method drift instead of mixing in the corpus change of the served index."""
    both = only(drift, "before", drift.before, tmp_path / "both")
    shutil.copytree(drift.root / "snapshots" / "after", both / "snapshots" / "after")
    shutil.copytree(drift.root / "indexes" / drift.after, both / "indexes" / drift.after)
    with TestClient(make_app(both)) as client:
        good = save(client, EVERYTHING)
    point_current(both, drift.after)
    old = tampered(both, good, query_version="0")  # the pinned index is here, but not the query version
    with TestClient(make_app(both)) as client:
        body = replayed(client, old)
        diff = diffed(client, old)
    assert body["replay"]["status"] == "drifted" and body["replay"]["index_version"] == drift.before
    assert [c["input"] for c in diff["changed"]] == ["query_version"]
    assert diff["membership_identical"] is True and diff["removed"] == []


def test_diff_of_a_reproduced_record_is_empty(client: TestClient) -> None:
    record_id = save(client, "trust")
    diff = diffed(client, record_id)
    assert diff["status"] == "reproduced" and diff["changed"] == []
    assert (diff["added"], diff["removed"], diff["membership_identical"]) == ([], [], True)


# --- ids on request; cost; a full store ------------------------------------------------------------------
def test_ids_are_left_out_unless_asked_for(client: TestClient) -> None:
    record_id = save(client, "trust")
    assert replayed(client, record_id)["record"]["ids"] is None
    ids = replayed(client, record_id, ids=True)["record"]["ids"]
    assert ids and ids == sorted(ids)
    error(client.get(f"/api/v1/records/{record_id}", params={"include": "abstracts"}), 422, "API_BAD_PARAM")


def test_record_routes_cost_the_export_weight(data_dir: Path) -> None:
    limit = RateLimit(capacity=20, refill_per_second=0.001, export_weight=10)
    with TestClient(make_app(data_dir, rate_limit=limit)) as client:
        record_id = save(client, "trust")  # 10 of 20
        assert client.get(f"/api/v1/records/{record_id}").status_code == 200  # 20 of 20
        error(client.get(f"/api/v1/records/{record_id}/diff"), 429, "API_RATE_LIMITED")
    limit = RateLimit(capacity=10, refill_per_second=0.001, export_weight=10)
    with TestClient(make_app(data_dir, rate_limit=limit)) as client:
        assert client.get("/api/v1/meta").status_code == 200  # 1 of 10: a record route no longer fits
        error(client.post("/api/v1/records", json={"q": "trust"}), 429, "API_RATE_LIMITED")


@pytest.mark.parametrize("limits", [{"records_max_bytes": 1}, {"records_min_free_bytes": 1 << 62}])
def test_a_full_store_refuses_saves_with_503(data_dir: Path, limits: dict[str, int]) -> None:
    with TestClient(make_app(data_dir, **limits)) as client:
        if "records_max_bytes" in limits:
            first = save(client, "trust")  # an empty store takes the first
            assert replayed(client, first)["replay"]["status"] == "reproduced"
        e = error(client.post("/api/v1/records", json={"q": "trust"}), 503, "API_RECORDS_STORE_FULL")
        assert "full" in e["message"]


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
    stored = store_of(data_dir).get(record_id)
    assert isinstance(stored, SearchRecord) and SECRET in stored.input  # the record keeps what the logs don't


def test_a_record_still_replays_and_exports_after_the_bootstrap_sources_change(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Citability is checked on write only (M3a round 2): the fixture's `ris` source stops being a bootstrap
    one, and a record saved before still reads, replays and exports (guarantee 4), its citability as saved."""
    import openproceedings.vocab as vocab

    record_id = save(client, "trust")
    monkeypatch.setattr(vocab, "BOOTSTRAP_SOURCES", frozenset())
    body = replayed(client, record_id)
    assert body["replay"]["status"] == "reproduced" and body["record"]["identification_citable"] is False
    export = client.get("/api/v1/export", params={"record_id": record_id, "format": "ris"})
    assert export.status_code == 200


def test_an_add_only_drift_is_not_membership_identical(drift: Drift, tmp_path: Path) -> None:
    """Papers added, none removed (M3a round 2: a check of `removed` alone would call this identical)."""
    grown_version = build(list(records())[:320], tmp_path / "grown-src" / "snapshots", "grown",
                          tmp_path / "grown-src" / "indexes")  # fmt: skip
    first = only(drift, "before", drift.before, tmp_path / "first")
    with TestClient(make_app(first)) as client:
        record_id = save(client, EVERYTHING)
    second = tmp_path / "second"
    (second / "indexes").mkdir(parents=True)
    shutil.copytree(tmp_path / "grown-src" / "snapshots", second / "snapshots")
    shutil.copytree(tmp_path / "grown-src" / "indexes" / grown_version, second / "indexes" / grown_version)
    (second / "indexes" / "current").symlink_to(grown_version)
    shutil.copytree(first / RECORDS_DIR, second / RECORDS_DIR)
    with TestClient(make_app(second)) as client:
        replay_ = replayed(client, record_id)["replay"]
        diff = diffed(client, record_id)
    assert replay_["status"] == "drifted" and replay_["removed_total"] == 0 and replay_["added_total"] > 0
    assert replay_["membership_identical"] is False
    assert diff["removed"] == [] and diff["added"] and diff["membership_identical"] is False


def test_a_record_id_never_starts_with_a_csv_formula_character(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drawn id starting with `-` is drawn again (M3a round 2): the CSV formula guard would write it as
    `'-…`, and the export's record_id cell wouldn't read back as the id."""
    import csv
    import io

    import openproceedings.records as records_module

    draws = iter(["-AAAAAAAAAAA", "BBBBBBBBBBBB"])
    monkeypatch.setattr(records_module.secrets, "token_urlsafe", lambda n: next(draws))
    record_id = save(client, "trust")
    assert record_id == "BBBBBBBBBBBB"
    monkeypatch.undo()
    body = client.get("/api/v1/export", params={"record_id": record_id, "format": "csv"}).text
    rows = list(csv.DictReader(io.StringIO(body)))
    assert rows and {row["record_id"] for row in rows} == {record_id}  # round-trips as itself
