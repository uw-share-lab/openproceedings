"""The `GET /coverage` response the `/coverage` page's tests render (TASK-045): a real answer of this API over a
small, varied slice of the synthetic 5k fixture (every 131st record: 39 records, 18 venue-years), so the
page is tested against the contract as served, never a hand-written body.

`test_frontend_coverage_fixture.py` fails while `frontend/src/components/coverage/coverage-fixture.json`
differs from what the API answers now. Regenerate with:

    PYTHONPATH=backend uv run python -m tests.contract.coverage_fixture
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.contract.conftest import build, make_app
from tests.fixtures.corpus.synthetic_5k import records

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "src" / "components" / "coverage" / "coverage-fixture.json"
STRIDE = 131


def response() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        version = build(list(records())[::STRIDE], root / "snapshots", "slice", root / "indexes")
        (root / "indexes" / "current").symlink_to(version)
        with TestClient(make_app(root)) as client:
            r = client.get("/api/v1/coverage")
            assert r.status_code == 200, r.text
            body: dict[str, Any] = r.json()
            return body


def render(body: dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(response()), encoding="utf-8")
    sys.stdout.write(f"wrote {OUT.relative_to(REPO)}\n")
