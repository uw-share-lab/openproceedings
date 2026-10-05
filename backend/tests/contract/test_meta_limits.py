"""`GET /api/v1/meta`'s `limits` (TASK-089; spec 04 §Endpoints): the instance's query length and depth caps and
verification limits, so a client need not hard-code them. The frontend's defaults for the caps
(`frontend/src/lib/default-limits.json`, used until `/meta` is fetched) must equal what the server serves."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from openproceedings.api.config import ApiConfig
from openproceedings.query.parser import MAX_DEPTH, MAX_QUERY_LENGTH

from tests.contract.conftest import Store, make_app

DEFAULT_LIMITS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "default-limits.json"
DEFAULTS = ApiConfig.model_fields


def test_meta_serves_the_parser_cap_and_the_default_verification_limits(client: TestClient) -> None:
    assert client.get("/api/v1/meta").json()["limits"] == {
        "max_query_length": MAX_QUERY_LENGTH,
        "max_query_depth": MAX_DEPTH,
        "max_verified_clauses": DEFAULTS["max_verified_clauses"].default,
        "max_verification_candidates": DEFAULTS["max_verification_candidates"].default,
        "compare": None,  # comparisons are off by default (TASK-177; test_compare.py has the caps when on)
    }


def test_meta_serves_this_instances_configured_verification_limits(store: Store) -> None:
    """The values are the served config's, not the defaults: an instance run with other limits says so."""
    app = make_app(store.indexes.parent, max_verified_clauses=3, max_verification_candidates=12_345)
    with TestClient(app) as c:
        limits = c.get("/api/v1/meta").json()["limits"]
    assert (limits["max_verified_clauses"], limits["max_verification_candidates"]) == (3, 12_345)
    assert (limits["max_query_length"], limits["max_query_depth"]) == (MAX_QUERY_LENGTH, MAX_DEPTH)  # fixed


def test_frontend_default_caps_are_the_served_caps(client: TestClient) -> None:
    """The reducer's defaults until `/meta` is fetched (search-state.ts `DEFAULT_LIMITS`) are this file; they
    must equal the caps `/meta` serves, so a hard-coded copy can't drift from the parser."""
    default = json.loads(DEFAULT_LIMITS.read_text(encoding="utf-8"))
    served = client.get("/api/v1/meta").json()["limits"]
    assert default == {k: served[k] for k in ("max_query_length", "max_query_depth")}


def test_limits_are_required_in_the_meta_schema(client: TestClient) -> None:
    """v1 is released: a new response field is additive only if it is always sent, so required."""
    schemas = client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    assert "limits" in schemas["MetaResponse"]["required"]
    assert sorted(schemas["Limits"]["required"]) == [
        "compare",
        "max_query_depth",
        "max_query_length",
        "max_verification_candidates",
        "max_verified_clauses",
    ]
