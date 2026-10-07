"""`POST /api/v1/parse`, `GET /api/v1/papers/{id}` and `GET /api/v1/meta` (task-035; spec 04 §Endpoints)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.ingest.snapshot import load_records
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import FILTER_FIELDS
from openproceedings.query.clauses import filter_clauses
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import MAX_QUERY_LENGTH, parse
from openproceedings.query.wordforms import report
from openproceedings.vocab import STATUSES, TRACKS, VENUES, venue_name

from tests.contract.conftest import SECRET, Store, make_app

Logs = Callable[[], list[dict[str, Any]]]
VERSIONS = {"index_version", "tokenizer_version", "query_version"}


def versions_of(body: dict[str, Any], store: Store) -> None:
    assert (body["index_version"], body["tokenizer_version"], body["query_version"]) == (
        store.big,
        TOKENIZER_VERSION,
        QUERY_VERSION,
    )


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == code
    return r.json()["error"]  # type: ignore[no-any-return]


# --- /parse -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("q", "mode"),
    [
        ("trust AND calibrat*", "native"),
        ("(trust AND track:workshop) OR calibration", "native"),  # WARN_NESTED_FILTER
        ("𝔸I trust or model", "native"),  # an astral character before a warning's span
        ("trust source:PMLR", "scholar"),  # translations
        ("(trust", "native"),  # errors: still a 200
        ("", "native"),
    ],
)
def test_parse_is_02s_parse_result_without_identification_ast_plus_filters(
    client: TestClient, store: Store, q: str, mode: str
) -> None:
    r = client.post("/api/v1/parse", json={"q": q, "mode": mode})
    assert r.status_code == 200, r.text
    body = r.json()
    versions_of(body, store)
    result = parse(q, mode)  # type: ignore[arg-type]
    # the tokenizer it was read with is the served index's, among the response's versions
    assert body["tokenizer_version"] == result.tokenizer_version
    expected = result.model_dump(mode="json", exclude={"identification_ast", "tokenizer_version"})
    filters = filter_clauses(q, result)  # TASK-078: served beside the ParseResult
    expected["filters"] = None if filters is None else filters.model_dump(mode="json")
    forms = report(q, result)  # TASK-175, TASK-192: served beside it too
    expected["word_forms"] = None if forms is None else [f.model_dump(mode="json") for f in forms.forms]
    expected["word_forms_skipped"] = (
        None if forms is None else [s.model_dump(mode="json") for s in forms.skipped]
    )
    assert {k: v for k, v in body.items() if k not in VERSIONS} == expected


def test_the_mixed_and_or_warning_carries_its_reading_as_a_field(client: TestClient) -> None:
    """TASK-099: WARN_MIXED_AND_OR's `reading` (the text at its code-point span, as read) is a field, sent on
    /parse and /search alike, so a client never parses the message; every other diagnostic sends it null."""
    q = "𝔸I trust or model OR calibration"  # an astral character, and a lowercase `or` warning with no reading
    body = client.post("/api/v1/parse", json={"q": q}).json()
    by_code = {w["code"]: w for w in body["warnings"]}
    assert by_code["WARN_MIXED_AND_OR"]["span"] == [0, 32]
    assert by_code["WARN_MIXED_AND_OR"]["reading"] == "(𝔸I trust or model) OR calibration"
    assert by_code["WARN_LOWERCASE_OPERATOR"]["reading"] is None
    searched = client.get("/api/v1/search", params={"q": q}).json()["query"]["warnings"]
    assert searched == body["warnings"]


def test_mixed_levels_past_the_per_code_cap_are_a_200_with_a_readingless_summary(client: TestClient) -> None:
    """TASK-099 review: 22 mixed levels give 20 warnings with readings, then "… and 2 more like these." whose
    `reading` is null. That summary once failed the Diagnostic validator, a 500 on /parse and /search."""
    q = " ".join(f"(a{i} b{i} OR c{i})" for i in range(22))
    r = client.post("/api/v1/parse", json={"q": q})
    assert r.status_code == 200, r.text
    mixed = [w for w in r.json()["warnings"] if w["code"] == "WARN_MIXED_AND_OR"]
    assert len(mixed) == 21 and all(w["reading"] for w in mixed[:20])
    assert (mixed[-1]["message"], mixed[-1]["reading"]) == ("… and 2 more like these.", None)
    s = client.get("/api/v1/search", params={"q": q})
    assert s.status_code == 200, s.text
    assert s.json()["query"]["warnings"] == r.json()["warnings"]


def test_parse_errors_are_values_with_code_point_spans(client: TestClient) -> None:
    body = client.post("/api/v1/parse", json={"q": "𝔸I (trust"}).json()
    assert [(e["code"], e["span"], e["reading"]) for e in body["errors"]] == [
        ("PARSE_UNBALANCED_PAREN", [3, 4], None)
    ]
    assert body["canonical"] is None and body["effective_ast"] is None and body["mode"] == "native"


def test_parse_reports_an_over_long_query_as_a_value_without_parsing_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/parse reports a parse (spec 04 §Conventions): PARSE_TOO_LONG is a 200 whose `errors` hold it, and
    the cap still comes before any lexing."""
    from openproceedings.query import parser

    def refuse(q: str) -> Any:
        raise AssertionError(f"lexed a query of {len(q)} characters")

    monkeypatch.setattr(parser, "lex", refuse)
    q = "a " * MAX_QUERY_LENGTH
    r = client.post("/api/v1/parse", json={"q": q})
    assert r.status_code == 200, r.text
    assert [(e["code"], e["span"]) for e in r.json()["errors"]] == [
        ("PARSE_TOO_LONG", [MAX_QUERY_LENGTH, len(q)])
    ]
    assert r.json()["canonical"] is None


@pytest.mark.parametrize(
    "body",
    [{}, {"q": 3}, {"q": "trust", "mode": "wos"}, {"q": "trust", "extra": 1}],
)
def test_parse_refuses_a_malformed_body_as_api_bad_param(client: TestClient, body: dict[str, Any]) -> None:
    error(client.post("/api/v1/parse", json=body), 422, "API_BAD_PARAM")


def test_parse_is_post_only(client: TestClient) -> None:
    r = client.get("/api/v1/parse", params={"q": "trust"})
    error(r, 405, "API_METHOD_NOT_ALLOWED")
    assert r.headers["allow"] == "POST"


# --- /papers/{id} -------------------------------------------------------------------------------------------
def test_a_paper_is_its_full_snapshot_record(client: TestClient, store: Store) -> None:
    hit = client.get("/api/v1/search", params={"q": "trust", "limit": 1}).json()["hits"][0]
    r = client.get(f"/api/v1/papers/{hit['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == VERSIONS | {
        "paper",
        "matched",
        "highlights",
        "abstract_withheld",
        "twins",
        "abstract_note",
    }
    assert body["abstract_withheld"] is False  # TASK-136: nothing is listed here
    assert body["twins"] == []  # TASK-162: the fixture holds no twin claims
    assert body["abstract_note"] is None  # TASK-210: the fixture holds no submission-time abstract
    versions_of(body, store)
    snapshot = load_records(store.indexes.parent / "snapshots" / "big")
    assert body["paper"] == snapshot[hit["id"]].model_dump(mode="json")
    assert body["paper"]["provenance"] and body["paper"]["content_hash"]
    assert body["paper"]["title"] == hit["title"]  # the record the search showed
    # TASK-112: the conference's full name for the paper page, derived per venue-year, never stored
    paper = body["paper"]
    assert paper["venue_name"] == venue_name(paper["venue"], paper["year"])


def test_every_paper_of_an_index_is_served(store: Store, data_dir: Path) -> None:
    from tests.contract.conftest import point_current

    point_current(data_dir, store.small)
    manifest = json.loads((data_dir / "indexes" / store.small / "manifest.json").read_text())
    records = load_records(data_dir / "snapshots" / manifest["snapshot"])
    assert len(records) == 300
    with TestClient(make_app(data_dir)) as c:
        for rid, record in records.items():
            body = c.get(f"/api/v1/papers/{rid}").json()
            assert body["index_version"] == store.small
            assert body["paper"] == record.model_dump(mode="json")


@pytest.mark.parametrize(
    "rid", ["op:iclr:2024:nope", f"op:icml:2023:{SECRET}", "op:neurips:1999:" + "x" * 5000]
)
def test_an_unknown_paper_is_404_api_paper_not_found(client: TestClient, rid: str) -> None:
    e = error(client.get(f"/api/v1/papers/{rid}"), 404, "API_PAPER_NOT_FOUND")
    assert rid not in e["message"]


def only_snapshots(store: Store, tmp_path: Path, snapshots: dict[str, str]) -> Path:
    """A data directory with both indexes and the given snapshots (published name → the store's name)."""
    data = tmp_path / "data"
    shutil.copytree(store.indexes, data / "indexes", symlinks=True)
    for name, source in snapshots.items():
        shutil.copytree(store.indexes.parent / "snapshots" / source, data / "snapshots" / name)
    return data


@pytest.mark.parametrize(
    "snapshots",
    [{}, {"big": "small"}],  # missing; a different snapshot under the index's snapshot name
    ids=["missing", "different"],
)
def test_an_index_without_its_snapshot_is_not_loaded(
    store: Store, tmp_path: Path, logs: Logs, snapshots: dict[str, str]
) -> None:
    """The snapshot is verified at load, beside the index (task-035 review): a bad deploy is 503 at
    startup, one ERROR line, never a per-request re-hash or a record without provenance."""
    with TestClient(make_app(only_snapshots(store, tmp_path, snapshots))) as c:
        assert c.get("/api/v1/healthz").json()["index_loaded"] is False
        error(c.get("/api/v1/papers/op:iclr:2024:Fx0001"), 503, "API_INDEX_NOT_LOADED")
        error(c.get("/api/v1/search", params={"q": "trust"}), 503, "API_INDEX_NOT_LOADED")
    (failed,) = [line for line in logs() if line["event"] == "index_load_failed"]
    assert failed["level"] == "ERROR" and failed["error"] == "SnapshotError"


def test_a_swap_to_an_index_without_its_snapshot_keeps_serving_the_old_one(
    store: Store, tmp_path: Path, logs: Logs
) -> None:
    from tests.contract.conftest import point_current

    data = only_snapshots(store, tmp_path, {"big": "big"})  # the small index's snapshot is missing
    app = make_app(data)
    with TestClient(app) as c:
        rid = c.get("/api/v1/search", params={"q": "trust", "limit": 1}).json()["hits"][0]["id"]
        point_current(data, store.small)
        assert app.state.index.load() is False
        assert c.get("/api/v1/healthz").json()["index_version"] == store.big
        assert c.get(f"/api/v1/papers/{rid}").json()["paper"]["id"] == rid
    assert [line["error"] for line in logs() if line["event"] == "index_load_failed"] == ["SnapshotError"]


def test_a_snapshot_that_vanishes_after_load_is_a_500(store: Store, tmp_path: Path, logs: Logs) -> None:
    import os

    data = only_snapshots(store, tmp_path, {"big": "big"})
    with TestClient(make_app(data)) as c:
        rid = c.get("/api/v1/search", params={"q": "trust", "limit": 1}).json()["hits"][0]["id"]
        snap = data / "snapshots" / "big"
        os.chmod(snap, 0o755)
        (snap / "records.jsonl").rename(snap / "gone.jsonl")
        e = error(c.get(f"/api/v1/papers/{rid}"), 500, "API_INTERNAL")
    assert "snapshot" not in e["message"]  # the client learns only the request id
    (failed,) = [line for line in logs() if line["event"] == "request_failed"]
    assert failed["level"] == "ERROR"
    assert (failed["cause"], failed["cause_reason"]) == ("FileNotFoundError", "ENOENT")  # why, never a path


def test_the_paper_line_logs_the_template_not_the_id(client: TestClient, logs: Logs) -> None:
    client.get(f"/api/v1/papers/op:iclr:2024:{SECRET}")
    client.get(f"/api/v1/papers/{SECRET}")  # malformed: a 422 whose message names the pattern, not the id
    lines = [entry for entry in logs() if entry["event"] == "request"]
    assert [(line["route"], line["status"]) for line in lines] == [
        ("/api/v1/papers/{id}", 404),
        ("/api/v1/papers/{id}", 422),
    ]
    raw = logs.raw.getvalue()  # type: ignore[attr-defined]
    assert SECRET not in raw


def test_the_parse_line_holds_no_query_text(client: TestClient, logs: Logs) -> None:
    client.post("/api/v1/parse", json={"q": f"trust {SECRET}"})
    client.post("/api/v1/parse", json={"q": f"({SECRET}"})
    lines = [entry for entry in logs() if entry["event"] == "request"]
    assert [(line["route"], line["status"]) for line in lines] == [("/api/v1/parse", 200)] * 2
    assert lines[0]["canonical_hash"] == parse(f"trust {SECRET}").canonical_hash
    assert lines[1]["error_codes"] == ["PARSE_UNBALANCED_PAREN"]
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]


# --- /meta ------------------------------------------------------------------------------------------------
def test_meta_lists_the_versions_and_vocabularies(client: TestClient, store: Store) -> None:
    r = client.get("/api/v1/meta")
    assert r.status_code == 200, r.text
    body = r.json()
    versions_of(body, store)
    assert body["index_versions"] == sorted([store.big, store.small])
    assert body["text_fields"] == ["title", "abstract"]
    assert body["filter_fields"] == list(FILTER_FIELDS)
    assert body["values"] == {"venue": list(VENUES.values()), "track": list(TRACKS), "status": list(STATUSES)}


def test_every_meta_value_parses_as_a_filter(client: TestClient) -> None:
    values = client.get("/api/v1/meta").json()["values"]
    for field, vs in values.items():
        for v in vs:
            assert not parse(f"trust {field}:{v}").errors, (field, v)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/parse", {"q": "trust"}),
        ("GET", "/api/v1/meta", None),
        ("GET", "/api/v1/papers/x", None),
    ],
)
def test_every_route_answers_503_before_an_index_loads(
    tmp_path: Path, method: str, path: str, body: dict[str, str] | None
) -> None:
    (tmp_path / "indexes").mkdir()
    with TestClient(make_app(tmp_path)) as c:
        error(c.request(method, path, json=body), 503, "API_INDEX_NOT_LOADED")


def test_the_openapi_document_describes_the_routes_and_their_models(client: TestClient) -> None:
    """(The committed snapshot is pinned by test_openapi_snapshot.py.)"""
    doc = client.get("/api/v1/openapi.json").json()
    paths = {"/api/v1/parse", "/api/v1/search", "/api/v1/papers/{id}", "/api/v1/meta", "/api/v1/healthz"}
    assert paths <= set(doc["paths"])
    schemas = doc["components"]["schemas"]
    for name in ("SearchResponse", "ParseResponse", "PaperResponse", "MetaResponse"):
        assert set(schemas[name]["required"]) >= VERSIONS
    assert "Diagnostic" in schemas
    limit = next(p for p in doc["paths"]["/api/v1/search"]["get"]["parameters"] if p["name"] == "limit")
    assert limit["schema"]["maximum"] == 200


def test_a_malformed_paper_id_is_a_422_like_a_malformed_record_id_without_asking_the_index(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One rule for both path ids (M3a review): a malformed one is 422 `API_BAD_PARAM` (the path's
    `pattern`), an unknown well-formed one 404; neither message repeats the id."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]

    def refuse(ids: list[str]) -> Any:
        raise AssertionError("the index was asked about a malformed id")

    monkeypatch.setattr(engine, "display", refuse)
    for rid in ("nope", "op:iclr:24:x", "op:ACL:2024:x", "x" * 5000, SECRET, "op:iclr:2024:Fx0001 x"):
        e = error(client.get(f"/api/v1/papers/{rid}"), 422, "API_BAD_PARAM")
        assert rid not in e["message"]
    # a venue this code doesn't know is well-formed (venue is an open enum, decision-009): not found
    error(client.get("/api/v1/papers/op:acl:2024:x"), 404, "API_PAPER_NOT_FOUND")
    for rid in ("nope", "short", "x" * 13):
        e = error(client.get(f"/api/v1/records/{rid}"), 422, "API_BAD_PARAM")
        e = error(client.get(f"/api/v1/records/{rid}/diff"), 422, "API_BAD_PARAM")
        assert rid not in e["message"]


def test_the_path_patterns_admit_every_id_the_code_makes(client: TestClient) -> None:
    """The paper `pattern` admits every id the code makes (a superset of `is_paper_id` on real ids, any venue
    included: an open enum); the record one is exactly `records.RECORD_ID`."""
    import re

    from openproceedings.api.models import PAPER_ID, RECORD_ID
    from openproceedings.ingest.record import is_paper_id
    from openproceedings.records import RECORD_ID as RECORD_ID_RE
    from openproceedings.records import valid_record_id

    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    made = [*engine.ids, "op:icml:2023:pmlr-v202-x_y", "op:neurips:2019:nips-" + "0" * 32, "op:acl:2024:x"]
    for text in made:
        assert re.fullmatch(PAPER_ID, text), text
    for text in engine.ids:
        assert is_paper_id(text), text
    for text in ("nope", "op:iclr:24:x", "op:icml:2023:Fx0001 x", "op:ICLR:2024:x", "op:iclr:2024:"):
        assert not re.fullmatch(PAPER_ID, text), text
    assert f"^{RECORD_ID_RE.pattern}$" == RECORD_ID
    for text in ("AAAAAAAAAAAA", "a-_b" * 3, "short", "x" * 13):
        assert bool(re.fullmatch(RECORD_ID, text)) == valid_record_id(text), text


def test_meta_lists_the_index_the_request_read(client: TestClient, store: Store) -> None:
    """`available` takes the request's engine (read once), never the state's reference a second time."""
    from types import SimpleNamespace

    state = client.app.state.index  # type: ignore[attr-defined]
    listed = state.available(SimpleNamespace(index_version="ffffffffffff"))
    assert listed == sorted([store.big, store.small, "ffffffffffff"])


def test_openapi_operation_ids_are_unique(client: TestClient) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # FastAPI warns "Duplicate Operation ID" while building the schema
        client.app.openapi_schema = None  # type: ignore[attr-defined]
        doc = client.app.openapi()  # type: ignore[attr-defined]
    ids = [op["operationId"] for path in doc["paths"].values() for op in path.values()]
    assert len(ids) == len(set(ids)), ids
    assert "head" not in doc["paths"]["/api/v1/healthz"]  # HEAD is served, not documented
