"""A search saved at the 2,000-code-point cap replays as `reproduced` (M3a review gate, decision-008).

Replay re-parses the record's canonical string (`records.py`), which the parser caps like any query. Before
decision-008 a query that fit the cap could canonicalise past it (the defaults, ` AND ` for juxtaposition,
parentheses), so it was saved but replayed as `mismatch`. Now such a query is refused up front, and one
whose canonical string sits exactly at the cap saves and reproduces.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings.query.parser import MAX_QUERY_LENGTH, parse
from openproceedings.records import RECORDS_DIR

from tests.contract.conftest import make_app

HEAD, TAIL = "((trust OR ", ") AND track:main AND status:accepted)"


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    with TestClient(make_app(data_dir)) as c:
        yield c


def test_a_search_saved_at_the_cap_is_reproduced(client: TestClient) -> None:
    q = HEAD + "t" * (MAX_QUERY_LENGTH - len(HEAD) - len(TAIL)) + TAIL  # canonical form, 2,000 code points
    parsed = parse(q)
    assert len(q) == MAX_QUERY_LENGTH and parsed.errors == [] and parsed.canonical == q
    r = client.post("/api/v1/records", json={"q": q})
    assert r.status_code == 201, r.text
    body = client.get(f"/api/v1/records/{r.json()['record_id']}").json()
    assert body["record"]["canonical"] == q and body["record"]["total"] > 0
    assert body["replay"]["status"] == "reproduced", body["replay"]


def test_a_query_whose_canonical_form_would_pass_the_cap_is_refused_and_not_saved(
    client: TestClient, data_dir: Path
) -> None:
    q = " ".join(f"w{i:04d}" for i in range(300))  # 1,799 code points; canonical over 3,000
    r = client.post("/api/v1/records", json={"q": q})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "PARSE_TOO_LONG"
    assert not (data_dir / RECORDS_DIR).exists()
