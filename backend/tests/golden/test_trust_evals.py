"""Canonical snapshots of every Trust-Evals protocol string in Scholar mode (task-005 AC2, task-015 AC1).

A change to any snapshot changes that string's canonical_hash in every saved search record: it needs a
decision record (scholar-syntax-compat skill). Regenerate only deliberately, then review the diff. Each string
parses to the same canonical string under every served tokenizer, and its canonical_hash is pinned per tokenizer
(the version is hashed with it, decision-003).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings.query.normalize import SERVED_TOKENIZERS
from openproceedings.query.parser import parse

HERE = Path(__file__).parent
LINES = (HERE.parent / "fixtures" / "queries" / "trust-evals.txt").read_text().split("\n")
STRINGS = {LINES[i][3:]: LINES[i + 1] for i in range(len(LINES) - 1) if LINES[i].startswith("## ")}
SNAPSHOT = json.loads((HERE / "trust_evals_canonical.json").read_text())


def test_every_string_has_a_snapshot() -> None:
    assert SNAPSHOT.keys() == STRINGS.keys()


@pytest.mark.parametrize("version", list(SERVED_TOKENIZERS))
@pytest.mark.parametrize("name", list(STRINGS))
def test_snapshot(name: str, version: str) -> None:
    result = parse(STRINGS[name], "scholar", version)
    assert result.errors == []
    got = {
        "canonical": result.canonical,
        "canonical_hash": result.canonical_hash,
        "identification_query": result.identification_query,
    }
    assert got == {**SNAPSHOT[name], "canonical_hash": SNAPSHOT[name]["canonical_hash"][version]}
