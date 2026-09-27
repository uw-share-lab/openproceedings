"""`api.export.stored_documents` (a record-pinned export, spec 04 §Exports) against a fake engine: the stored
ids are read a chunk of `STORED_CHUNK` at a time and yielded in order; an id the index doesn't hold ends the
stream short, and `_body`'s count against `X-Total` turns that into a loud failure, never a smaller file."""

from __future__ import annotations

from typing import Any

import pytest
from openproceedings.api import export as route
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.export import Provenance


class FakeEngine:
    """`display(ids)` over a fixed id set, recording each call's ids."""

    def __init__(self, held: set[str]) -> None:
        self.held = held
        self.calls: list[list[str]] = []

    def display(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        self.calls.append(list(ids))
        return {i: {"id": i, "title": "T", "venue": "ICLR", "year": 2024} for i in ids if i in self.held}


def ids(n: int) -> list[str]:
    return [f"op:iclr:2024:{i:06d}" for i in range(n)]


PROVENANCE = Provenance(
    "abc", "0" * 64, "2026-09-27", record_id="Rec0rd_Id-01", searched_at="2026-09-26T00:00:00Z"
)


@pytest.mark.parametrize(
    "n", [route.STORED_CHUNK - 1, route.STORED_CHUNK, route.STORED_CHUNK + 1, 2 * route.STORED_CHUNK + 3]
)
def test_every_stored_id_is_read_in_chunks_and_in_order(n: int) -> None:
    wanted = ids(n)
    engine = FakeEngine(set(wanted))
    got = [d["id"] for d in route.stored_documents(engine, wanted)]  # type: ignore[arg-type]
    assert got == wanted
    assert [len(c) for c in engine.calls] == [
        min(route.STORED_CHUNK, n - s) for s in range(0, n, route.STORED_CHUNK)
    ]
    assert [i for c in engine.calls for i in c] == wanted  # each id asked for once, never re-read


@pytest.mark.parametrize(
    "missing_at", [0, route.STORED_CHUNK - 1, route.STORED_CHUNK, route.STORED_CHUNK + 5]
)
def test_a_missing_id_ends_the_stream_short_and_the_body_fails_loudly(missing_at: int) -> None:
    wanted = ids(route.STORED_CHUNK + 10)
    engine = FakeEngine(set(wanted) - {wanted[missing_at]})
    got = [d["id"] for d in route.stored_documents(engine, wanted)]  # type: ignore[arg-type]
    assert got == wanted[:missing_at]  # stops at the gap: nothing after it is passed off as complete
    body = route._body("jsonl", route.stored_documents(engine, wanted), PROVENANCE, total=len(wanted))  # type: ignore[arg-type]
    with pytest.raises(EngineInternalError, match=f"exported {missing_at} records, but {len(wanted)} match"):
        b"".join(body)


def test_an_empty_record_reads_nothing() -> None:
    engine = FakeEngine(set())
    assert list(route.stored_documents(engine, [])) == [] and engine.calls == []  # type: ignore[arg-type]
