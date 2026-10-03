"""`POST /api/v1/parse` reports each filter field's top-level clause as `filters` (TASK-078; spec 04 §Endpoints,
spec 02 §Filter clauses; decision-011). The same goldens drive the frontend reducer's test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.query.ast import FILTER_FIELDS

GOLDEN: list[dict[str, Any]] = json.loads(
    (
        Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "filter-clause-golden.json"
    ).read_text(encoding="utf-8")
)["cases"]


def _q(case: dict[str, Any]) -> str:
    return case["q"] if "q" in case else "".join(part * times for part, times in case["q_parts"])


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_parse_serves_the_golden_filters(client: TestClient, case: dict[str, Any]) -> None:
    r = client.post("/api/v1/parse", json={"q": _q(case), "mode": case["mode"]})
    assert r.status_code == 200, r.text
    filters = r.json()["filters"]
    assert list(filters) == list(FILTER_FIELDS)
    assert {f: filters[f] for f in case["filters"]} == case["filters"]


@pytest.mark.parametrize("q", ["(trust", "", "x" * 2001], ids=["unbalanced", "empty", "too-long"])
def test_filters_are_null_when_the_query_has_errors(client: TestClient, q: str) -> None:
    body = client.post("/api/v1/parse", json={"q": q}).json()
    assert body["errors"] and body["filters"] is None


def test_every_clause_sends_every_key(client: TestClient) -> None:
    """Required-fields convention (spec 04 §Conventions): a null span, values and reason are sent, not omitted."""
    filters = client.post("/api/v1/parse", json={"q": "track:main track:main"}).json()["filters"]
    common = {"field", "negated", "span", "toggleable", "reason", "blocking_spans"}
    assert set(filters["track"]) == common | {"values"} and filters["track"]["span"] is None
    assert set(filters["year"]) == common | {"ranges"}


YEAR_GOLDEN: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "year-clause-golden.json").read_text(
        encoding="utf-8"
    )
)["cases"]


@pytest.mark.parametrize("case", YEAR_GOLDEN, ids=[c["name"] for c in YEAR_GOLDEN])
def test_parse_serves_the_golden_year_clause(client: TestClient, case: dict[str, Any]) -> None:
    """The year report the reducer's year actions start from (TASK-092; `year-clause-golden.json`)."""
    r = client.post("/api/v1/parse", json={"q": _q(case), "mode": case["mode"]})
    assert r.status_code == 200, r.text
    assert r.json()["filters"]["year"] == case["year"]
