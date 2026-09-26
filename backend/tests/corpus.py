"""The test record shape and the 200-record fixture, shared by the oracle's tests and the properties."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "corpus" / "reference-200.jsonl"


@dataclass(frozen=True)
class Rec:
    """A `Searchable` record (engine/protocol.py) with defaults for the fields a test doesn't care about."""

    id: str
    title: str
    abstract: str | None
    venue: str = "ICLR"
    year: int = 2024
    track: str = "main"
    status: str = "accepted"


def fixture_records() -> list[Rec]:
    return [Rec(**json.loads(line)) for line in FIXTURE.read_text().splitlines()]
