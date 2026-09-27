"""The /api/v1 shapes as they freeze at the first release (M3a review-gate, spec 04 §Conventions): what the
OpenAPI document promises (every sent field required, one timestamp form, open enums marked, the error code
enum, the headers), and that the routes keep it (unknown or repeated parameters refused, no trailing-slash
redirect)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.app import EXPOSED_HEADERS
from openproceedings.api.openapi import OPEN_NOTE, openapi_document, unclassified_enums
from openproceedings.diagnostics import DiagnosticCode, http_status

from tests.contract.conftest import Store, make_app

DOC = openapi_document()
SCHEMAS: dict[str, Any] = DOC["components"]["schemas"]
REQUESTS = {"ParseRequest", "RecordRequest"}  # request bodies: a default there is an optional key
Z_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z")


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code, body
    return dict(body["error"])


# --- 1. every field a response always sends is required ----------------------------------------------------
@pytest.mark.parametrize("name", sorted(set(SCHEMAS) - REQUESTS - {"ErrorBody", "ErrorEnvelope"}))
def test_every_response_field_is_required(name: str) -> None:
    """A defaulted field is sent all the same (null included), so a client may rely on it: the schema says
    required (`json_schema_serialization_defaults_required`), for Urls, PaperRecord, Diagnostic and the AST
    nodes too."""
    schema = SCHEMAS[name]
    if "properties" in schema:
        assert set(schema.get("required", [])) == set(schema["properties"]), name


def test_a_hit_and_a_paper_record_agree_on_their_shared_fields() -> None:
    hit, paper = SCHEMAS["Hit"], SCHEMAS["PaperRecord"]
    shared = set(hit["properties"]) & set(paper["properties"])
    assert {"presentation", "urls", "abstract", "venue"} <= shared
    for field in shared:

        def shape(schema: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in schema.items() if k not in ("title", "default")}  # always sent anyway

        assert shape(hit["properties"][field]) == shape(paper["properties"][field]), field
    assert shared <= set(hit["required"]) and shared <= set(paper["required"])


def test_only_the_error_bodys_diagnostics_is_optional_and_never_null() -> None:
    body = SCHEMAS["ErrorBody"]
    assert set(body["properties"]) - set(body["required"]) == {"diagnostics"}
    assert body["properties"]["diagnostics"]["type"] == "array"  # absent, never null
    assert "anyOf" not in body["properties"]["diagnostics"]


# --- 2. counts are *_total ------------------------------------------------------------------------------------
def test_replay_and_diff_name_their_counts_alike() -> None:
    replay, diff = set(SCHEMAS["ReplayInfo"]["properties"]), set(SCHEMAS["RecordDiff"]["properties"])
    assert {"added_total", "removed_total"} <= replay & diff
    assert not {"added", "removed"} & replay  # in the diff, `added`/`removed` are the id lists


# --- 4. one timestamp form ------------------------------------------------------------------------------------
def test_every_timestamp_is_a_typed_date_time() -> None:
    assert SCHEMAS["SearchRecord"]["properties"]["searched_at"]["format"] == "date-time"
    assert SCHEMAS["SnapshotInfo"]["properties"]["built_at"]["format"] == "date-time"
    assert SCHEMAS["SnapshotInfo"]["properties"]["crawl_date"]["format"] == "date"
    assert SCHEMAS["Claim"]["properties"]["fetched_at"]["format"] == "date-time"
    for end in ("from", "to"):
        assert SCHEMAS["CrawlWindow"]["properties"][end]["format"] == "date-time"
    assert "crawl_from" not in SCHEMAS["SnapshotInfo"]["properties"]


def test_every_timestamp_sent_is_utc_with_z(data_dir: Path) -> None:
    with TestClient(make_app(data_dir)) as c:
        record_id = c.post("/api/v1/records", json={"q": "trust"}).json()["record_id"]
        record = c.get(f"/api/v1/records/{record_id}").json()["record"]
        snapshot = c.get("/api/v1/coverage").json()["snapshot"]
        hit = c.get("/api/v1/search", params={"q": "trust", "limit": 1}).json()["hits"][0]
        paper = c.get(f"/api/v1/papers/{hit['id']}").json()["paper"]
    sent = [
        record["searched_at"],
        snapshot["built_at"],
        *(
            t
            for w in [*record["crawl_dates"].values(), *snapshot["crawl_dates"].values()]
            for t in w.values()
        ),
        *(claim["fetched_at"] for claim in paper["provenance"]),
    ]
    assert paper["provenance"] and all(Z_TIME.fullmatch(t) for t in sent), sent


# --- 6. unknown or repeated query parameters ------------------------------------------------------------------
@pytest.mark.parametrize(
    "params",
    [
        [("q", "trust"), ("limt", "5")],  # a typo: never answered as if `limit` were the default
        [("q", "trust"), ("index_version", "0123456789ab")],  # /export's, not /search's
        [("q", "a"), ("q", "b")],  # which one ran?
        [("q", "trust"), ("limit", "5"), ("limit", "6")],
    ],
)
def test_search_refuses_an_unknown_or_repeated_parameter(
    client: TestClient, params: list[tuple[str, str]]
) -> None:
    e = error(client.get("/api/v1/search", params=params), 422, "API_BAD_PARAM")
    assert "trust" not in e["message"] or ("q", "trust") not in params  # names the key, never a value


def route_urls(record_id: str, paper_id: str) -> Iterator[tuple[str, str, dict[str, Any] | None]]:
    yield "GET", "/api/v1/search?q=trust", None
    yield "POST", "/api/v1/parse", {"q": "trust"}
    yield "GET", f"/api/v1/papers/{paper_id}", None
    yield "GET", "/api/v1/export?q=trust&format=ris", None
    yield "POST", "/api/v1/records", {"q": "trust"}
    yield "GET", f"/api/v1/records/{record_id}", None
    yield "GET", f"/api/v1/records/{record_id}/diff", None
    yield "GET", "/api/v1/coverage", None
    yield "GET", "/api/v1/meta", None
    yield "GET", "/api/v1/healthz", None


def test_every_route_refuses_a_parameter_it_doesnt_take(data_dir: Path) -> None:
    with TestClient(make_app(data_dir)) as c:
        record_id = c.post("/api/v1/records", json={"q": "trust"}).json()["record_id"]
        paper_id = c.get("/api/v1/search", params={"q": "trust", "limit": 1}).json()["hits"][0]["id"]
        routes = list(route_urls(record_id, paper_id))
        templates = {
            path.split("?")[0].replace(record_id, "{id}").replace(paper_id, "{id}") for _m, path, _b in routes
        }
        assert templates == set(DOC["paths"])  # every route of the contract
        for method, path, body in routes:
            assert c.request(method, path, json=body).status_code in (200, 201), path
            joined = f"{path}{'&' if '?' in path else '?'}bogus=1"
            e = error(c.request(method, joined, json=body), 422, "API_BAD_PARAM")
            assert "`bogus`" in e["message"], path


# --- 7. no trailing-slash redirect ----------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/api/v1/search/?q=trust", "/api/v1/meta/", "/api/v1/healthz/"])
def test_a_trailing_slash_is_a_404_envelope_never_a_redirect(client: TestClient, path: str) -> None:
    r = client.get(path, follow_redirects=False)
    error(r, 404, "API_NOT_FOUND")
    assert "location" not in r.headers


# --- 8. open enums ----------------------------------------------------------------------------------------------
def test_every_enum_is_declared_open_or_closed() -> None:
    """A new enum in the document must be classified in `api/openapi.py` (spec 04 §Conventions)."""
    assert unclassified_enums(DOC) == []


def test_open_enums_say_so_and_closed_ones_dont() -> None:
    assert OPEN_NOTE in SCHEMAS["ErrorCode"]["description"]
    assert OPEN_NOTE in SCHEMAS["DiagnosticCode"]["description"]
    assert OPEN_NOTE in SCHEMAS["Hit"]["properties"]["venue"]["description"]
    assert OPEN_NOTE in SCHEMAS["ChangedInput"]["properties"]["input"]["description"]
    assert OPEN_NOTE not in str(SCHEMAS["ReplayInfo"]["properties"]["status"])  # closed: three statuses


# --- 9. the error code enum -----------------------------------------------------------------------------------
def test_the_error_code_schema_is_exactly_the_registrys_http_codes() -> None:
    assert set(SCHEMAS["ErrorCode"]["enum"]) == {
        c.value for c in DiagnosticCode if http_status(c) is not None
    }
    assert "API_REPLAY_MISMATCH" not in SCHEMAS["ErrorCode"]["enum"]  # a log code only
    assert not any(c.startswith(("WARN_", "COMPAT_")) for c in SCHEMAS["ErrorCode"]["enum"])
    assert SCHEMAS["ErrorBody"]["properties"]["code"] == {"$ref": "#/components/schemas/ErrorCode"}


# --- 10. headers ---------------------------------------------------------------------------------------------------
QUERY_ROUTES = [
    ("/api/v1/search", "get"),
    ("/api/v1/export", "get"),
    ("/api/v1/records", "post"),
    ("/api/v1/records/{id}", "get"),
    ("/api/v1/records/{id}/diff", "get"),
]


def test_the_status_specific_headers_are_in_the_contract() -> None:
    search = DOC["paths"]["/api/v1/search"]["get"]["responses"]
    assert "Retry-After" in search["429"]["headers"] and "Allow" in search["405"]["headers"]
    # every route that runs a query can be 503 API_BUSY, which sends Retry-After (M3a round 2)
    for path, method in QUERY_ROUTES:
        busy = DOC["paths"][path][method]["responses"]["503"]
        assert "Retry-After" in busy["headers"] and "API_BUSY" in busy["description"], path
    # the 429 names every bucket that can refuse
    for source in ("token bucket", "network", "position-verified", "save ceiling"):
        assert source in search["429"]["description"], source
    assert "429" not in DOC["paths"]["/api/v1/healthz"]["get"]["responses"]  # never rate-limited
    created = DOC["paths"]["/api/v1/records"]["post"]["responses"]["201"]
    assert "Location" in created["headers"]


def test_cors_exposes_every_header_a_client_reads(store: Store) -> None:
    assert {"Content-Disposition", "Location", "X-Total", "Retry-After"} <= set(EXPOSED_HEADERS)
    app = make_app(store.indexes.parent, cors_origins=("https://openproceedings.example",))
    with TestClient(app) as c:
        r = c.get("/api/v1/healthz", headers={"Origin": "https://openproceedings.example"})
    assert "Content-Disposition" in r.headers["access-control-expose-headers"]


# --- nits ------------------------------------------------------------------------------------------------------------
def test_operation_ids_are_verb_noun() -> None:
    ids = {op["operationId"] for item in DOC["paths"].values() for op in item.values()}
    assert ids == {
        "search", "parse_query", "export", "get_paper", "get_coverage", "get_meta", "get_healthz",
        "create_record", "get_record", "get_record_diff",
    }  # fmt: skip


def test_info_version_is_the_api_version() -> None:
    assert DOC["info"]["version"] == "v1"


def test_one_schema_for_the_exclusion_accounting() -> None:
    assert "RecordExcluded" not in SCHEMAS
    assert SCHEMAS["SearchRecord"]["properties"]["excluded"] == {"$ref": "#/components/schemas/Excluded"}
    assert SCHEMAS["SearchResponse"]["properties"]["excluded"] == {"$ref": "#/components/schemas/Excluded"}


def test_a_records_mode_is_the_mode_enum() -> None:
    assert SCHEMAS["SearchRecord"]["properties"]["mode"]["enum"] == ["native", "scholar"]


def test_every_query_parameter_is_described_and_q_names_its_cap() -> None:
    for path, item in DOC["paths"].items():
        for op in item.values():
            for p in op.get("parameters", []):
                assert p.get("description"), (path, p["name"])
    q = next(p for p in DOC["paths"]["/api/v1/search"]["get"]["parameters"] if p["name"] == "q")
    assert "2,000" in q["description"] and "PARSE_TOO_LONG" in q["description"]
    assert "2,000" in SCHEMAS["ParseRequest"]["properties"]["q"]["description"]


def test_response_objects_are_open_to_new_keys_and_request_bodies_are_closed() -> None:
    """Adding a response field is non-breaking (spec 04 §Conventions: clients ignore unknown keys), so no
    response schema says `additionalProperties: false`; a request body does (the server refuses an unknown
    key)."""

    def closed(node: Any) -> bool:
        if isinstance(node, dict):
            return node.get("additionalProperties") is False or any(closed(v) for v in node.values())
        if isinstance(node, list):
            return any(closed(v) for v in node)
        return False

    assert [name for name in SCHEMAS if name not in REQUESTS and closed(SCHEMAS[name])] == []
    for name in REQUESTS:
        assert SCHEMAS[name]["additionalProperties"] is False, name


def test_integer_bounds_are_integers() -> None:
    year = SCHEMAS["PaperRecord"]["properties"]["year"]
    assert year["minimum"] == 1000 and isinstance(year["minimum"], int)
    assert "1000.0" not in json.dumps(DOC)


def test_the_diff_pages_count_entries_not_hits() -> None:
    params = {p["name"]: p for p in DOC["paths"]["/api/v1/records/{id}/diff"]["get"]["parameters"]}
    for name in ("offset", "limit"):
        assert "Entries" in params[name]["description"] and "Hits" not in params[name]["description"]


def test_crawl_dates_kind_says_it_is_an_open_set() -> None:
    assert OPEN_NOTE in SCHEMAS["SearchRecord"]["properties"]["crawl_dates_kind"]["description"]


def test_path_ids_carry_their_pattern() -> None:
    for path in ("/api/v1/papers/{id}", "/api/v1/records/{id}", "/api/v1/records/{id}/diff"):
        (param,) = [p for p in DOC["paths"][path]["get"]["parameters"] if p["in"] == "path"]
        assert param["schema"]["pattern"], path
