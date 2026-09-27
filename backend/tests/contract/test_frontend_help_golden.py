"""`/help/syntax` is generated from the parser, the token goldens and spec 02 (TASK-045; spec 05 §Pages).

`frontend/src/help/syntax-golden.json` holds what `help_golden.build()` computes (as JSON: prettier may lay it
out differently): every example's
message is the one the parser produces now, every token row is a row of the golden token table, and every
limit and vocabulary is the code's. Regenerate with `PYTHONPATH=backend uv run python -m
tests.contract.help_golden` when a rule or message changes on purpose.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.contract.help_golden import OUT, build, reader_facing, render

COMMITTED = json.loads(OUT.read_text(encoding="utf-8"))


def test_the_committed_file_is_what_the_parser_says_now() -> None:
    assert json.loads(render()) == COMMITTED, (
        "frontend/src/help/syntax-golden.json is stale: run "
        "`PYTHONPATH=backend uv run python -m tests.contract.help_golden` and commit it"
    )


def test_every_reader_facing_code_has_an_entry() -> None:
    """A code a reader can meet (the query diagnostics and the two slow-clause refusals) is in the Messages
    section, so every diagnostic's Help link lands on its own entry."""
    listed = {m["code"] for m in COMMITTED["messages"]} | set(COMMITTED["slow_clauses"])
    assert listed == reader_facing()


def test_messages_are_a_to_z_with_a_message_and_an_example_or_display() -> None:
    codes = [m["code"] for m in COMMITTED["messages"]]
    assert codes == sorted(codes)
    for m in COMMITTED["messages"]:
        assert m["message"].strip() and (m["example"] is None) != (m["display"] is None), m["code"]


def test_parse_serves_each_examples_message(client: TestClient) -> None:
    """The page quotes what `POST /parse` answers for the example (the wildcard cap needs an index: its
    message comes from the engine, and its count is the index's own)."""
    for m in COMMITTED["messages"]:
        if m["example"] is None or m["code"] == "WILDCARD_TOO_MANY_EXPANSIONS":
            continue
        body = client.post("/api/v1/parse", json={"q": m["example"], "mode": m["mode"]}).json()
        said = [
            (d["code"], d["message"]) for d in (*body["errors"], *body["warnings"], *body["translations"])
        ]
        assert (m["code"], m["message"]) in said, m["code"]


def test_the_limits_are_the_served_defaults(client: TestClient) -> None:
    """The fallback the page shows when `/meta` fails is what an instance with default flags serves."""
    served = client.get("/api/v1/meta").json()["limits"]
    assert {k: COMMITTED["constants"][k] for k in served} == served


def test_build_is_deterministic() -> None:
    assert build() == build()
