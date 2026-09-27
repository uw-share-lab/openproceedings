"""`GET /api/v1/meta`'s `limits` (TASK-089; spec 04 §Endpoints): the instance's query-length cap and
verification limits, so a client need not hard-code them. The frontend's default for the cap
(`frontend/src/lib/default-limits.json`, used until `/meta` is fetched) must equal what the server serves."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from openproceedings.api.config import ApiConfig
from openproceedings.query.parser import MAX_QUERY_LENGTH

from tests.contract.conftest import Store, make_app

DEFAULT_LIMITS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "default-limits.json"
DEFAULTS = ApiConfig.model_fields


def test_meta_serves_the_parser_cap_and_the_default_verification_limits(client: TestClient) -> None:
    assert client.get("/api/v1/meta").json()["limits"] == {
        "max_query_length": MAX_QUERY_LENGTH,
        "max_verified_clauses": DEFAULTS["max_verified_clauses"].default,
        "max_verification_candidates": DEFAULTS["max_verification_candidates"].default,
    }


def test_meta_serves_this_instances_configured_verification_limits(store: Store) -> None:
    """The values are the served config's, not the defaults: an instance run with other limits says so."""
    app = make_app(store.indexes.parent, max_verified_clauses=3, max_verification_candidates=12_345)
    with TestClient(app) as c:
        limits = c.get("/api/v1/meta").json()["limits"]
    assert (limits["max_verified_clauses"], limits["max_verification_candidates"]) == (3, 12_345)
    assert limits["max_query_length"] == MAX_QUERY_LENGTH  # not configurable (api/config.py)


def test_frontend_default_query_length_is_the_served_cap(client: TestClient) -> None:
    """The reducer's default until `/meta` is fetched (search-state.ts `DEFAULT_LIMITS`) is this file; it
    must equal the cap `/meta` serves, so a hard-coded copy can't drift from the parser."""
    default = json.loads(DEFAULT_LIMITS.read_text(encoding="utf-8"))
    assert default == {"max_query_length": client.get("/api/v1/meta").json()["limits"]["max_query_length"]}


def test_limits_are_required_in_the_meta_schema(client: TestClient) -> None:
    """v1 is released: a new response field is additive only if it is always sent, so required."""
    schemas = client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    assert "limits" in schemas["MetaResponse"]["required"]
    assert sorted(schemas["Limits"]["required"]) == [
        "max_query_length",
        "max_verification_candidates",
        "max_verified_clauses",
    ]
