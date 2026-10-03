"""The API answers the record page, the save panel, the export menu and the methods text are tested against
(TASK-044): real answers of this API over a slice of the synthetic 5k fixture (every 7th record), so every
count the frontend's tests expect comes from the API, never a hand-typed number.

For each query in `RECORDS`: the `POST /records` 201 body, `GET /records/{id}?replay=false` (the stored record)
and `GET /records/{id}` (with its replay), and `POST /parse` of the record's `canonical` and of its
`identification_query` (the methods text reads the default and limit clauses from the first and the
all-negative case from the second). For each query in `SEARCHES`: `GET /search` and `POST /parse` of it (the
export menu's status and track warnings). A record id is random and `searched_at` is the clock, so both are
replaced with fixed values (`FIXED_IDS`, `FIXED_SEARCHED_AT`) everywhere they appear.

`test_frontend_record_fixture.py` fails while `frontend/src/components/record/record-fixture.json` differs
from what the API answers now. Regenerate with:

    PYTHONPATH=backend uv run python -m tests.contract.record_fixture
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
OUT = REPO / "frontend" / "src" / "components" / "record" / "record-fixture.json"
STRIDE = 7
FIXED_SEARCHED_AT = "2026-09-25T14:03:11Z"

# name → (q, mode): each exercises one branch of the methods text (spec 05 §Components 8)
RECORDS: dict[str, tuple[str, str]] = {
    "limits": ("trust* AND year:2020..2026", "native"),  # a user limit; both defaults applied
    "defaults_only": ("status:accepted", "native"),  # identification_query "" → "all indexed records"
    "all_negative": ("status:accepted NOT trust", "native"),  # identification_query is all-negative
    "one_default": ("trust AND track:(main OR workshop)", "native"),  # track is the reader's; status default
    "scholar": ('source:ICLR "large language" | trust', "scholar"),  # translations recorded
}
FIXED_IDS = {name: f"Rec{i:09d}" for i, name in enumerate(RECORDS)}  # 12 chars, a record id's shape

# name → (q, mode): the export menu's warnings
SEARCHES: dict[str, tuple[str, str]] = {
    "accepted": ("trust*", "native"),  # the default status filter: no warning
    "statuses": ("trust* AND status:(accepted OR rejected OR withdrawn)", "native"),  # status warning, counts
    "negated_status": ("trust* NOT status:rejected", "native"),  # status warning without counts
    "workshop": ("trust* AND track:(main OR workshop)", "native"),  # track warning
}


def _parse(client: TestClient, q: str, mode: str = "native") -> dict[str, Any]:
    r = client.post("/api/v1/parse", json={"q": q, "mode": mode})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _fixed(body: Any, record_id: str, fixed_id: str, searched_at: str) -> Any:
    text = json.dumps(body, ensure_ascii=False)
    return json.loads(text.replace(record_id, fixed_id).replace(searched_at, FIXED_SEARCHED_AT))


def response() -> dict[str, Any]:
    out: dict[str, Any] = {"records": {}, "searches": {}}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        version = build(list(records())[::STRIDE], root / "snapshots", "slice", root / "indexes")
        (root / "indexes" / "current").symlink_to(version)
        with TestClient(make_app(root)) as client:
            for name, (q, mode) in RECORDS.items():
                created = client.post("/api/v1/records", json={"q": q, "mode": mode})
                assert created.status_code == 201, created.text
                record_id = created.json()["record_id"]
                stored = client.get(f"/api/v1/records/{record_id}", params={"replay": "false"})
                replayed = client.get(f"/api/v1/records/{record_id}")
                assert stored.status_code == replayed.status_code == 200, (stored.text, replayed.text)
                record = stored.json()["record"]
                entry = {
                    "q": q,
                    "mode": mode,
                    "created": created.json(),
                    "stored": stored.json(),
                    "replayed": replayed.json(),
                    "parse_canonical": _parse(client, record["canonical"]),
                    "parse_identification": _parse(client, record["identification_query"]),
                }
                out["records"][name] = _fixed(entry, record_id, FIXED_IDS[name], record["searched_at"])
            for name, (q, mode) in SEARCHES.items():
                search = client.get("/api/v1/search", params={"q": q, "mode": mode, "limit": 1})
                assert search.status_code == 200, search.text
                out["searches"][name] = {
                    "q": q,
                    "mode": mode,
                    "search": search.json(),
                    "parse": _parse(client, q, mode),
                }
    return out


def render(body: dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(response()), encoding="utf-8")
    sys.stdout.write(f"wrote {OUT.relative_to(REPO)}\n")
