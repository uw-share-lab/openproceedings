"""`POST /api/v1/parse` on a query that fits the cap but whose canonical form does not (decision-008).

The input is admitted (1,799 code points), parsed, and refused after canonicalising: a 200 whose `errors`
hold one `PARSE_TOO_LONG` spanning the whole input, with no canonical string, in both modes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("mode", ["native", "scholar"])
def test_parse_reports_a_canonical_form_over_the_cap(client: TestClient, mode: str) -> None:
    q = " ".join(f"w{i:04d}" for i in range(300))
    r = client.post("/api/v1/parse", json={"q": q, "mode": mode})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["code"] for e in body["errors"]] == ["PARSE_TOO_LONG"]
    assert body["errors"][0]["span"] == [0, len(q)]
    assert body["canonical"] is None
