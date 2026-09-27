"""A position check's cost per candidate doesn't grow with the clause's width or its expansions (M3a review
gate round 4): each clause's allowed-token sets are built once per compile, not per candidate document, so a
300-item wildcard phrase costs what a 2-item one does, and the candidate count (what the API bounds,
`max_verification_candidates`) stays the measure of the work. Same ids as before and as ReferenceEngine."""

from __future__ import annotations

from pathlib import Path

import pytest
from openproceedings.engine.compile import Compiler, verified_clauses
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse

from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper
from tests.unit.engine.test_exclusions import tantivy_of

RECORDS = list(records())
BACK = {as_paper(r).id: r.id for r in RECORDS}
REFERENCE = ReferenceEngine(RECORDS)
STEM = "tru*"  # 5k fixture: a few dozen expansions, thousands of candidates


def wide(width: int, stem: str = STEM) -> str:
    return '"' + " ".join([stem] * width) + '"'


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cost")
    tantivy_of(RECORDS, root)
    (path,) = (p for p in (root / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    return path


@pytest.mark.parametrize("width", [2, 50, 300])
def test_a_clause_builds_its_token_sets_once_not_per_candidate(
    built: Path, width: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = TantivyEngine(built)
    ast = parse(wide(width)).effective_ast
    assert ast is not None
    candidates = sum(n for _c, _f, n in engine.candidates(ast))
    assert candidates > 1_000
    built_sets = 0
    make = Compiler.allowed

    def counting(self: Compiler, i: object) -> frozenset[str]:
        nonlocal built_sets
        before = len(self._allowed)
        out = make(self, i)  # type: ignore[arg-type]
        built_sets += len(self._allowed) - before  # a set built, not a cached one read
        return out

    monkeypatch.setattr(Compiler, "allowed", counting)
    engine.compile(ast)
    assert (
        built_sets <= 2
    )  # one per distinct item (here `tru*`) per compile, whatever the width or candidates


def test_the_calls_per_clause_do_not_scale_with_candidates(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before round 4 `allowed` ran width × candidates times (a 50-item phrase over thousands of candidates:
    hundreds of thousands of set builds); now its calls are bounded by the clause, not the documents."""
    engine = TantivyEngine(built)
    ast = parse(wide(50)).effective_ast
    assert ast is not None
    calls = 0
    make = Compiler.allowed

    def counting(self: Compiler, i: object) -> frozenset[str]:
        nonlocal calls
        calls += 1
        return make(self, i)  # type: ignore[arg-type]

    monkeypatch.setattr(Compiler, "allowed", counting)
    engine.compile(ast)
    assert calls <= 50 * 4 * 2  # distinct, candidates and parts, per field: never per document


@pytest.mark.parametrize(
    "q",
    [wide(2), wide(7), wide(40), '"trust tru* model*"', f"{wide(3)} NEAR/4 model*", '"tru* calibrat*" NEAR/2 trust',
     "trust NEAR/3 trust", '"a tru* a"'],
)  # fmt: skip
def test_wide_and_mixed_clauses_match_the_reference(built: Path, q: str) -> None:
    ast = parse(q).effective_ast
    assert ast is not None and verified_clauses(ast)
    got = {BACK[i] for i in TantivyEngine(built).match_ids(ast)}  # index ids -> the fixture's own
    assert got == set(REFERENCE.match_ids(ast))
