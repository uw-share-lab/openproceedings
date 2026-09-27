"""API additions the UI design needs (TASK-090, TASK-091; spec 04, docs/design/2026-09-27-*.md), all additive
under /api/v1:

- `identified_total` and `unclassified_total` on `/search`, on a search record and on its replay: exactly the
  counts `op search` and `op record save` print (`identified`, `unclassified`), `identified_total` being the
  identification tree's own count;
- `POST /records`'s optional `index_version` pin (409 `API_INDEX_VERSION_UNAVAILABLE`, nothing saved or
  charged for a save);
- `GET /records/{id}?replay=false`: the stored record, `replay` null, one token, answered while every
  verification slot is taken;
- `/coverage`'s `crawl_dates_kind` and `identification_citable` (their derivation is a record's:
  `tests/unit/test_records.py`); `/parse`'s `blocking_spans` (their rule: `tests/unit/test_clauses.py`).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.query.parser import parse
from openproceedings.records import RECORDS_DIR, RECORDS_FILE, SearchRecord

from tests.contract.conftest import SECRET, Store, make_app, point_current
from tests.contract.test_abuse_limits import VERIFIED
from tests.contract.test_records import error
from tests.contract.test_search import QUERIES, engine_of, ok

Logs = Callable[[], list[dict[str, Any]]]
RECORDS = "/api/v1/records"


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    """The app over a private data directory (its record store is this test's own)."""
    with TestClient(make_app(data_dir)) as c:
        yield c


def printed(out: str) -> tuple[int, int]:
    """(identified, unclassified) as `op search` / `op record save` print them."""
    identified = re.search(r"^identified (\d+) ", out, re.M)
    unclassified = re.search(r", unclassified (\d+) \(track unknown", out)
    assert identified is not None and unclassified is not None, out
    return int(identified.group(1)), int(unclassified.group(1))


# --- TASK-090: identified_total, unclassified_total ---------------------------------------------------------
@pytest.mark.parametrize("q", QUERIES)
def test_search_totals_are_the_identification_count_and_the_unknown_buckets(
    client: TestClient, q: str
) -> None:
    body = ok(client, q, limit=0)
    engine = engine_of(client)
    identification = parse(q).identification_ast
    counted = len(engine.ids) if identification is None else len(engine.match_ids(identification))
    assert body["identified_total"] == counted == body["total"] + body["excluded"]["total"]
    ex = body["excluded"]
    assert body["unclassified_total"] == ex["track"]["unknown"] + ex["status"]["unknown"]


def test_an_unrestricted_query_identifies_every_record(client: TestClient) -> None:
    body = ok(client, "year:1900..2100", limit=0)  # every record, then the defaults
    assert body["identified_total"] == len(engine_of(client).ids)


@pytest.mark.parametrize("q", ["trust", "trust AND calibrat*", "trust track:workshop status:rejected"])
def test_a_record_and_its_replay_carry_the_counts_op_record_save_prints(
    capsys: pytest.CaptureFixture[str], data_dir: Path, q: str
) -> None:
    assert cli.main(["--data-dir", str(data_dir), "record", "save", q]) == 0
    out = capsys.readouterr().out
    record_id = out.splitlines()[0].split()[2]
    with TestClient(make_app(data_dir)) as c:
        body = c.get(f"{RECORDS}/{record_id}").json()
        search = ok(c, q, limit=0)
    record, replay = body["record"], body["replay"]
    assert replay["status"] == "reproduced"
    assert (record["identified_total"], record["unclassified_total"]) == printed(out)
    assert (replay["identified_total"], replay["unclassified_total"]) == printed(out)
    assert (search["identified_total"], search["unclassified_total"]) == printed(out)


def test_the_derived_counts_are_never_stored(client: TestClient, data_dir: Path) -> None:
    """Computed at read time from `total` and `excluded`, so every body version has them and none can
    contradict its own counts."""
    record_id = client.post(RECORDS, json={"q": "trust"}).json()["record_id"]
    conn = sqlite3.connect(data_dir / RECORDS_DIR / RECORDS_FILE)
    try:
        (body,) = conn.execute("SELECT body FROM records WHERE record_id = ?", (record_id,)).fetchone()
    finally:
        conn.close()
    assert '"identified_total"' not in body and '"unclassified_total"' not in body
    assert "identified_total" in client.get(f"{RECORDS}/{record_id}").json()["record"]


def test_a_refused_replay_has_null_derived_counts(client: TestClient, data_dir: Path) -> None:
    """A replay that didn't run compares and counts nothing (spec 04 §Search records)."""
    limited = make_app(data_dir, max_verification_candidates=1)  # the replay is withheld here
    record_id = client.post(RECORDS, json={"q": VERIFIED}).json()["record_id"]
    with TestClient(limited) as c:
        replay = c.get(f"{RECORDS}/{record_id}").json()["replay"]
    assert replay["refused"] is not None
    assert replay["identified_total"] is None and replay["unclassified_total"] is None


# --- TASK-091 (1): the save's index_version pin -------------------------------------------------------------
def test_a_save_pinned_to_the_served_index_is_saved(client: TestClient, store: Store) -> None:
    r = client.post(RECORDS, json={"q": "trust", "index_version": store.big})
    assert r.status_code == 201, r.text
    assert r.json()["index_version"] == store.big


def test_a_save_pinned_to_another_index_is_409_and_saves_nothing(
    data_dir: Path, store: Store, logs: Logs
) -> None:
    """The hot swap between search and save (design pre-pass M3): nothing is written, and no save is spent."""
    with TestClient(make_app(data_dir)) as c:
        shown = ok(c, f"trust {SECRET}", limit=0)["index_version"]
        point_current(data_dir, store.small)
        assert c.app.state.index.load()  # type: ignore[attr-defined]
        assert engine_of(c).index_version == store.small
        r = c.post(RECORDS, json={"q": f"trust {SECRET}", "index_version": shown})
        body = error(r, 409, "API_INDEX_VERSION_UNAVAILABLE")
        assert SECRET not in body["message"] and "diagnostics" not in body
    assert not (data_dir / RECORDS_DIR / RECORDS_FILE).exists()  # never created: nothing was saved
    assert all(SECRET not in str(line) for line in logs())
    access = [x for x in logs() if x["event"] == "request" and x.get("route") == RECORDS]
    assert access[-1]["status"] == 409 and access[-1]["code"] == "API_INDEX_VERSION_UNAVAILABLE"


def test_a_refused_pin_costs_no_save(data_dir: Path, store: Store) -> None:
    """The pin is checked before a save is taken from the ceilings, so a stale page can retry after a new search."""
    with TestClient(make_app(data_dir, record_saves_network_burst=1)) as c:
        for _ in range(3):
            error(
                c.post(RECORDS, json={"q": "trust", "index_version": store.small}),
                409,
                "API_INDEX_VERSION_UNAVAILABLE",
            )
        assert c.post(RECORDS, json={"q": "trust", "index_version": store.big}).status_code == 201


@pytest.mark.parametrize("version", ["current", "ABC", "", "../x", "a" * 65, 12])
def test_a_malformed_pin_is_422(client: TestClient, version: Any) -> None:
    error(client.post(RECORDS, json={"q": "trust", "index_version": version}), 422, "API_BAD_PARAM")


def test_a_null_pin_is_the_served_index(client: TestClient, store: Store) -> None:
    r = client.post(RECORDS, json={"q": "trust", "index_version": None})
    assert r.status_code == 201 and r.json()["index_version"] == store.big


# --- TASK-091 (2): the stored record without a replay -------------------------------------------------------
def test_replay_false_is_the_stored_record_with_a_null_replay(client: TestClient, store: Store) -> None:
    record_id = client.post(RECORDS, json={"q": "trust AND calibrat*"}).json()["record_id"]
    full = client.get(f"{RECORDS}/{record_id}").json()
    r = client.get(f"{RECORDS}/{record_id}", params={"replay": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == set(full) and body["replay"] is None
    assert body["record"] == full["record"] and body["record"]["ids"] is None
    assert (body["index_version"], body["tokenizer_version"], body["query_version"]) == (
        full["index_version"],
        full["tokenizer_version"],
        full["query_version"],
    )
    with_ids = client.get(f"{RECORDS}/{record_id}", params={"replay": "false", "include": "ids"}).json()
    assert with_ids["record"]["ids"] and with_ids["replay"] is None
    assert client.get(f"{RECORDS}/{record_id}", params={"replay": "true"}).json()["replay"] is not None


def test_replay_false_runs_nothing_and_logs_no_query(client: TestClient, logs: Logs) -> None:
    record_id = client.post(RECORDS, json={"q": f"trust {SECRET}"}).json()["record_id"]
    engine = engine_of(client)
    compile_ = engine.compile

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("replay=false compiled a query")

    engine.compile = refuse  # type: ignore[method-assign]
    try:
        assert client.get(f"{RECORDS}/{record_id}", params={"replay": "false"}).status_code == 200
    finally:
        engine.compile = compile_  # type: ignore[method-assign]
    assert all(SECRET not in str(line) for line in logs())
    access = [x for x in logs() if x["event"] == "request" and x.get("route") == RECORDS + "/{id}"]
    assert access[-1]["status"] == 200 and "canonical_hash" in access[-1]


def test_replay_false_of_an_unknown_or_malformed_id(client: TestClient) -> None:
    error(client.get(f"{RECORDS}/AAAAAAAAAAAA", params={"replay": "false"}), 404, "API_RECORD_NOT_FOUND")
    error(client.get(f"{RECORDS}/short", params={"replay": "false"}), 422, "API_BAD_PARAM")
    error(client.get(f"{RECORDS}/AAAAAAAAAAAA", params={"replay": "maybe"}), 422, "API_BAD_PARAM")
    error(client.get(f"{RECORDS}/AAAAAAAAAAAA?replay=false&replay=false"), 422, "API_BAD_PARAM")  # repeated


def test_replay_false_costs_one_token_not_the_export_weight(data_dir: Path) -> None:
    limit = RateLimit(capacity=12, refill_per_second=0.001, export_weight=10)
    with TestClient(make_app(data_dir)) as c:
        record_id = c.post(RECORDS, json={"q": "trust"}).json()["record_id"]
    with TestClient(make_app(data_dir, rate_limit=limit)) as c:
        for _ in range(12):  # 12 reads at one token each; with the export weight the second would be a 429
            assert c.get(f"{RECORDS}/{record_id}", params={"replay": "false"}).status_code == 200
        error(c.get(f"{RECORDS}/{record_id}", params={"replay": "false"}), 429, "API_RATE_LIMITED")
    with TestClient(make_app(data_dir, rate_limit=limit)) as c:
        assert c.get(f"{RECORDS}/{record_id}").status_code == 200  # a replay: 10 of 12
        error(c.get(f"{RECORDS}/{record_id}"), 429, "API_RATE_LIMITED")
        assert (
            c.get(f"{RECORDS}/{record_id}", params={"replay": "0"}).status_code == 200
        )  # the route's bool rule


@pytest.mark.parametrize("query", ["replay=false&replay=false", "replay=nope", "replay=false&x=1"])
def test_a_request_the_route_refuses_is_charged_in_full(data_dir: Path, query: str) -> None:
    """Only a read the route answers without a replay is cheap; anything else pays the record route's weight."""
    limit = RateLimit(capacity=15, refill_per_second=0.001, export_weight=10)
    with TestClient(make_app(data_dir, rate_limit=limit)) as c:
        error(c.get(f"{RECORDS}/AAAAAAAAAAAA?{query}"), 422, "API_BAD_PARAM")
        error(c.get(f"{RECORDS}/AAAAAAAAAAAA?{query}"), 429, "API_RATE_LIMITED")


def test_replay_false_is_answered_while_every_verification_slot_is_taken(data_dir: Path) -> None:
    """The record page renders the recorded fields while a replay would be 503 `API_BUSY` (design pre-pass S4)."""
    with TestClient(make_app(data_dir)) as c:
        record_id = c.post(RECORDS, json={"q": '"calibrat* model"'}).json()["record_id"]
    with TestClient(make_app(data_dir)) as c:  # a fresh engine: the record's clause is cold again
        engine = engine_of(c)
        read = engine.read
        entered, release = threading.Event(), threading.Event()

        def slow(*args: Any) -> Any:
            entered.set()
            assert release.wait(10)
            return read(*args)

        engine.read = slow  # type: ignore[method-assign]
        try:
            with ThreadPoolExecutor(1) as pool:
                first = pool.submit(c.get, "/api/v1/search", params={"q": VERIFIED})
                assert entered.wait(10)
                error(c.get(f"{RECORDS}/{record_id}"), 503, "API_BUSY")
                r = c.get(f"{RECORDS}/{record_id}", params={"replay": "false"})
                assert r.status_code == 200 and r.json()["replay"] is None
                release.set()
                assert first.result(10).status_code == 200
        finally:
            engine.read = read  # type: ignore[method-assign]


def test_every_replay_is_still_non_null_without_the_parameter(client: TestClient) -> None:
    """decision-014: `replay` is null only when the client asked `replay=false`."""
    record_id = client.post(RECORDS, json={"q": VERIFIED}).json()["record_id"]
    assert client.get(f"{RECORDS}/{record_id}").json()["replay"] is not None
    assert client.get(f"{RECORDS}/{record_id}/diff").status_code == 200  # the diff has no such parameter
    error(client.get(f"{RECORDS}/{record_id}/diff", params={"replay": "false"}), 422, "API_BAD_PARAM")


# --- TASK-091 (3), (4): coverage and parse ------------------------------------------------------------------
def test_coverage_carries_the_window_kind_and_citability(client: TestClient) -> None:
    snapshot = client.get("/api/v1/coverage").json()["snapshot"]
    assert set(snapshot["crawl_dates_kind"]) == set(snapshot["crawl_dates"])
    assert isinstance(snapshot["identification_citable"], bool)


@pytest.mark.parametrize(
    ("q", "field", "texts"),
    [
        (
            "track:workshop llm AND (venue:NeurIPS track:workshop)",
            "track",
            ["track:workshop", "track:workshop"],
        ),
        ("𝔘ber (a OR track:workshop)", "track", ["(a OR track:workshop)"]),
        ("x (track:workshop OR venue:ICLR)", "venue", ["(track:workshop OR venue:ICLR)"]),
    ],
)
def test_parse_gives_the_code_point_spans_of_the_blocking_clauses(
    client: TestClient, q: str, field: str, texts: list[str]
) -> None:
    filters = client.post("/api/v1/parse", json={"q": q}).json()["filters"]
    clause = filters[field]
    assert clause["toggleable"] is False and clause["span"] is None
    assert [q[a:b] for a, b in clause["blocking_spans"]] == texts  # code points: 𝔘 is one
    assert all(filters[f]["blocking_spans"] == [] for f in filters if filters[f]["reason"] is None)


def test_an_old_body_reads_with_the_derived_counts() -> None:
    """A v1 body (committed fixture) gains both counts at read time from its own `total` and `excluded`
    (`RecordStore.get` reads every body through this model)."""
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "records" / "record-v1.json"
    body = json.loads(fixture.read_text(encoding="utf-8"))
    record = SearchRecord.model_validate(body)
    ex = body["excluded"]
    assert record.identified_total == body["total"] + ex["total"]
    assert record.unclassified_total == ex["track"]["unknown"] + ex["status"]["unknown"]
