"""The `/coverage` page's test fixture is this API's own answer (TASK-045): a changed response model or count
turns this red until `coverage-fixture.json` is regenerated (`coverage_fixture.py` says how), so the page's
tests can't pass against a shape the API no longer serves."""

from __future__ import annotations

import json

from tests.contract.coverage_fixture import OUT, render, response


def test_the_committed_fixture_is_what_get_coverage_answers() -> None:
    # compared as JSON: prettier (make fmt) may lay the file out differently
    assert json.loads(OUT.read_text(encoding="utf-8")) == json.loads(render(response())), (
        "frontend/src/components/coverage/coverage-fixture.json is stale: run "
        "`PYTHONPATH=backend uv run python -m tests.contract.coverage_fixture` and commit it"
    )


def test_the_fixture_exercises_the_page() -> None:
    """What the page must render is in it: several venues and years, unknowns, missing abstracts, statuses
    indexed, and per-source crawl windows."""
    body = json.loads(OUT.read_text(encoding="utf-8"))
    assert len({vy["venue"] for vy in body["venue_years"]}) == 3 and len(body["venue_years"]) > 10
    assert body["totals"]["abstract_missing"] > 0 and body["totals"]["unknown_status"] > 0
    assert all(vy["statuses_indexed"] and vy["tracks"] for vy in body["venue_years"])
    assert set(body["snapshot"]["crawl_dates"]) == {"*", "ris"}
