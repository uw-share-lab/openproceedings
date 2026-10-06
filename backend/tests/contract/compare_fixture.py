"""The `POST /compare` answers the web app's comparison panel is tested against (TASK-177): this API's own
response for a file with every list in it (`test_compare.the_file`, over that module's corpus), its `/meta`
limits, one refusal, and the same file against the query with a year limit of its own (`limited`: a
`query_limit` row, TASK-185), so the panel is tested against the contract as served, never a hand-written body.

`test_frontend_compare_fixture.py` fails while `frontend/src/components/compare/compare-fixture.json` differs
from what the API answers now. Regenerate with:

    PYTHONPATH=backend uv run python -m tests.contract.compare_fixture
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient
from openproceedings.api import compare as route

from tests.contract.conftest import attributed, build, make_app
from tests.contract.test_compare import BY_ID, COMPARE, DATE, KEPT, NO_COOLDOWN, RIS, TWIN, Q, the_file
from tests.fixtures.corpus.synthetic_5k import records

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "src" / "components" / "compare" / "compare-fixture.json"


def answers() -> dict[str, Any]:
    corpus = [*list(records())[:800], list(records())[TWIN]]
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(route, "utc_date", lambda: DATE):
        root = Path(tmp)
        version = build(corpus, root / "snapshots", "compared", root / "indexes", paper=attributed)
        (root / "indexes" / "current").symlink_to(version)
        with TestClient(make_app(root, compare_enabled=True, rate_limit=NO_COOLDOWN)) as client:
            file = the_file()
            r = client.post(COMPARE, params={"q": Q}, content=file.encode("utf-8"), headers=RIS)
            assert r.status_code == 200, r.text
            refused = client.post(COMPARE, params={"q": Q}, content=b"\xff\xfe", headers=RIS)
            assert refused.status_code == 422, refused.text
            search = client.get("/api/v1/search", params={"q": Q, "limit": 0})
            # the same file against the query with a limit of its own, which leaves a kept paper out (TASK-185)
            limited_q = f"{Q} AND NOT year:{BY_ID[KEPT[0]].year}"
            limited = client.post(COMPARE, params={"q": limited_q}, content=file.encode("utf-8"), headers=RIS)
            assert limited.status_code == 200, limited.text
            return {
                "q": Q,
                "mode": "native",
                "file": file,
                "limits": client.get("/api/v1/meta").json()["limits"],
                "search_total": search.json()["total"],
                "response": r.json(),
                "invalid": refused.json(),
                "limited": {"q": limited_q, "response": limited.json()},
            }


def render(body: dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(answers()), encoding="utf-8")
    sys.stdout.write(f"wrote {OUT.relative_to(REPO)}\n")
