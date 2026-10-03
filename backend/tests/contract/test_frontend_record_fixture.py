"""The record page's, save panel's, export menu's and methods text's test fixture is this API's own answer
(TASK-044): a changed response model or count turns this red until `record-fixture.json` is regenerated
(`record_fixture.py` says how), so the frontend's tests can't pass against a shape or a number the API no
longer serves."""

from __future__ import annotations

import json

from tests.contract.record_fixture import OUT, RECORDS, SEARCHES, render, response


def test_the_committed_fixture_is_what_the_api_answers() -> None:
    # compared as JSON: prettier (make fmt) may lay the file out differently
    assert json.loads(OUT.read_text(encoding="utf-8")) == json.loads(render(response())), (
        "frontend/src/components/record/record-fixture.json is stale: run "
        "`PYTHONPATH=backend uv run python -m tests.contract.record_fixture` and commit it"
    )


def test_the_fixture_exercises_every_methods_text_branch() -> None:
    """Each record is the case its name says, so a change in the API that removes a branch is caught here, not
    by a frontend test that silently stops covering it."""
    body = json.loads(OUT.read_text(encoding="utf-8"))
    assert set(body["records"]) == set(RECORDS) and set(body["searches"]) == set(SEARCHES)
    recs = {name: e["stored"]["record"] for name, e in body["records"].items()}
    assert all(e["replayed"]["replay"]["status"] == "reproduced" for e in body["records"].values())
    assert all(e["stored"]["replay"] is None for e in body["records"].values())
    assert recs["defaults_only"]["identification_query"] == ""
    codes = [d["code"] for d in body["records"]["all_negative"]["parse_identification"]["errors"]]
    assert codes == ["PARSE_ALL_NEGATIVE"]
    assert (
        body["records"]["limits"]["parse_canonical"]["filters"]["year"]["span"][0]
        < (body["records"]["limits"]["parse_canonical"]["filters"]["year"]["span"][1])
    )  # the reader's year limit is a clause of its own
    assert body["records"]["one_default"]["parse_canonical"]["defaults"] == ["status"]
    assert {t["code"] for t in recs["scholar"]["translations"]} >= {"COMPAT_SOURCE_ALIAS"}
    assert all(r["excluded"]["total"] > 0 and r["unclassified_total"] > 0 for r in recs.values())
    searches = body["searches"]
    assert searches["statuses"]["parse"]["filters"]["status"]["values"] == [
        "accepted",
        "rejected",
        "withdrawn",
    ]
    assert searches["negated_status"]["parse"]["filters"]["status"]["negated"] is True
    assert "track" not in searches["workshop"]["parse"]["defaults"]
