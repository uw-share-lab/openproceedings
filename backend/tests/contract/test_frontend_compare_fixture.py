"""The comparison panel's test fixture is this API's own answer (TASK-177): a changed response model, count or
message turns this red until `compare-fixture.json` is regenerated (`compare_fixture.py` says how), so the
panel's tests can't pass against a shape the API no longer serves."""

from __future__ import annotations

import json

from tests.contract.compare_fixture import OUT, answers, render


def test_the_committed_fixture_is_what_post_compare_answers() -> None:
    # compared as JSON: prettier (make fmt) may lay the file out differently
    assert json.loads(OUT.read_text(encoding="utf-8")) == json.loads(render(answers())), (
        "frontend/src/components/compare/compare-fixture.json is stale: run "
        "`PYTHONPATH=backend uv run python -m tests.contract.compare_fixture` and commit it"
    )


def test_the_fixture_exercises_the_panel() -> None:
    """What the panel must draw is in it: every list non-empty, a repeat, several reasons, a RIS-only record,
    a record that needs a person, the caps, a refusal's envelope, and a paper the query's own limit leaves
    out."""
    body = json.loads(OUT.read_text(encoding="utf-8"))
    r = body["response"]
    for name in ("kept", "dropped", "not_in_index", "added", "not_compared"):
        assert r[f"{name}_total"] == len(r[name]) > 0, name
    assert (
        r["duplicates_total"] > 0 and r["total"] == body["search_total"] == r["kept_total"] + r["added_total"]
    )
    assert len(r["reason_totals"]["dropped"]) >= 2
    assert any(row["independent"] is False for name in ("kept", "dropped", "added") for row in r[name])
    assert any(not row["settled"] for row in r["not_in_index"])
    assert body["limits"]["compare"]["max_records"] > 0
    assert body["invalid"]["error"]["code"] == "API_RIS_INVALID"
    assert body["limited"]["response"]["reason_totals"]["dropped"]["query_limit"] > 0
    assert body["limited"]["response"]["reason_totals"]["not_in_index"]["query_limit"] > 0
