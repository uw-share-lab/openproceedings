"""`POST /api/v1/parse` reports where a `$` can be added as `word_forms`, and the edited query is an ordinary
query: nothing is expanded unless its text says so (TASK-175; spec 02 §Word forms; guarantees 1, 3, 4, 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.query.parser import parse
from openproceedings.query.wordforms import WordForm, apply

GOLDEN: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "word-forms-golden.json").read_text(
        encoding="utf-8"
    )
)["cases"]


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_parse_serves_the_golden_word_forms(client: TestClient, case: dict[str, Any]) -> None:
    r = client.post("/api/v1/parse", json={"q": case["q"], "mode": case["mode"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["word_forms"] == case["word_forms"]
    assert body["word_forms_skipped"] == case["word_forms_skipped"]  # TASK-192
    assert (body["word_forms"] is None) == (body["word_forms_skipped"] is None) == bool(body["errors"])


def _search(client: TestClient, q: str, mode: str) -> dict[str, Any]:
    r = client.get("/api/v1/search", params={"q": q, "mode": mode, "limit": 200})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_only_the_edited_text_expands_and_every_expansion_is_reported(client: TestClient) -> None:
    q = "(model | benchmark) evaluation"
    forms = client.post("/api/v1/parse", json={"q": q, "mode": "scholar"}).json()["word_forms"]
    assert [f["term"] for f in forms] == ["model", "benchmark", "evaluation"]
    as_typed = _search(client, q, "scholar")
    assert (
        as_typed["query"]["expansions"] == {}
    )  # the offer changes nothing: no `$` in the text, no expansion

    edited_q = apply(q, [WordForm(**f) for f in forms])
    assert edited_q == "(model$ | benchmark$) evaluation$"
    edited = _search(client, edited_q, "scholar")
    expansions = edited["query"]["expansions"]
    assert set(expansions) == {
        "model$",
        "benchmark$",
        "evaluation$",
    }  # each added wildcard, as any wildcard is
    for key, terms in expansions.items():
        stem = key[:-1]
        assert stem in terms and "models" in expansions["model$"]
        assert all(
            t == stem or (t.startswith(stem) and len(t) == len(stem) + 1) for t in terms
        )  # zero or one
    assert edited["total"] > as_typed["total"]

    # the saved string alone reproduces the set: the canonical query holds the `$`, and runs natively as written
    canonical = edited["query"]["canonical"]
    assert "model$" in canonical and canonical == parse(edited_q, "scholar").canonical
    replay = _search(client, canonical, "native")
    assert replay["total"] == edited["total"] and replay["query"]["expansions"] == expansions
    assert [h["id"] for h in replay["hits"]] == [h["id"] for h in edited["hits"]]
