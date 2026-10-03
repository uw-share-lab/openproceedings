"""TantivyEngine on the 200-record fixture: the 44 golden queries (expected sets computed by an independent
evaluator) and combinations of them against ReferenceEngine (ast-compilation skill: every table row through
both engines). The full differential suite over generated ASTs is task-028."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings.engine.index import build_index
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.snapshot import render
from openproceedings.query.parser import parse

from tests.corpus import Rec, fixture_records

CORPUS = Path(__file__).parents[1] / "fixtures" / "corpus"
GOLDEN = json.loads((CORPUS / "reference-200-queries.json").read_text())
RECORDS = fixture_records()
BUILT = datetime(2026, 9, 26, tzinfo=UTC)


def as_paper(r: Rec) -> PaperRecord:
    """A fixture record as a snapshot record (the fixture's ids aren't record ids: `Fx` + its number)."""
    claim = Claim(field="title", value=r.title, source="ris", fetched_at=BUILT)
    return PaperRecord.build(
        id=f"op:{r.venue.lower()}:{r.year}:Fx{r.id.rsplit(':', 1)[1]}", title=r.title, abstract=r.abstract,
        authors=(), venue=r.venue, year=r.year, track=r.track, status=r.status, provenance=(claim,),
    )  # fmt: skip


BACK = {as_paper(r).id: r.id for r in RECORDS}


@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> TantivyEngine:
    root = tmp_path_factory.mktemp("tantivy200")
    snap = root / "snap"
    snap.mkdir()
    papers = tuple(sorted((as_paper(r) for r in RECORDS), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    return TantivyEngine(build_index(snap, root / "indexes", BUILT).path)


def ids(engine: TantivyEngine, q: str) -> list[str]:
    result = parse(q)
    assert result.ast is not None, result.errors
    return sorted(BACK[i] for i in engine.match_ids(result.ast))


@pytest.mark.parametrize("case", GOLDEN, ids=[c["q"] for c in GOLDEN])
def test_golden(engine: TantivyEngine, case: dict[str, object]) -> None:
    assert ids(engine, str(case["q"])) == case["expected"]


REFERENCE = ReferenceEngine(RECORDS)


def combined(parts: list[str], op: str) -> str:
    return op.join(f"({p})" for p in parts) if op != " NEAR/2 " else op.join(parts)


@settings(max_examples=150)
@given(
    st.tuples(
        st.lists(st.sampled_from([c["q"] for c in GOLDEN]), min_size=1, max_size=3),
        st.sampled_from([" ", " OR ", " AND NOT ", " NEAR/2 "]),
    ).filter(
        lambda t: parse(combined(*t)).ast is not None
    )  # only strings that parse, chosen while generating
)
def test_combinations_agree_with_the_oracle(engine: TantivyEngine, case: tuple[list[str], str]) -> None:
    result = parse(combined(*case))
    assert result.ast is not None
    assert sorted(BACK[i] for i in engine.match_ids(result.ast)) == sorted(REFERENCE.match_ids(result.ast))
