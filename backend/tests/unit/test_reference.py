"""ReferenceEngine: one row per evaluation rule of the reference-oracle skill (task-016)."""

from __future__ import annotations

import ast as pyast
from dataclasses import dataclass
from pathlib import Path

import pytest
from openproceedings.diagnostics import OpenProceedingsError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import Not, Or, Term, Wildcard
from openproceedings.query.parser import parse


@dataclass(frozen=True)
class Rec:
    id: str
    title: str
    abstract: str | None
    venue: str = "ICLR"
    year: int = 2024
    track: str = "main"
    status: str = "accepted"


CORPUS = [
    Rec("a", "Trust calibration in LLMs", "We benchmark trust and reliance."),
    Rec(
        "b",
        "A benchmark for trustworthy models",
        "Benchmarking vision-language models.",
        venue="NeurIPS",
        year=2023,
    ),
    Rec("c", "Calibration", "Trust in AI is studied; human trust matters.", track="workshop"),
    Rec("d", "Model selection", None, status="rejected", year=2021),
    Rec("e", "Trust", "The model and the models of trust in AI", venue="ICML", track="datasets_benchmarks"),
    Rec(
        "f", "Naïve Bayes for GPT-4o", "A $\\epsilon$-DP study of trust calibration.", venue="ICML", year=2022
    ),
]
ENGINE = ReferenceEngine(CORPUS)


def ids(q: str) -> list[str]:
    result = parse(q)
    assert result.ast is not None, result.errors
    return sorted(ENGINE.match_ids(result.ast))


ROWS = [
    # Term: exact token, either field unless fielded; no stemming
    ("trust", ["a", "c", "e", "f"]),
    ("benchmark", ["a", "b"]),
    ("benchmarking", ["b"]),
    ("llm", []),  # LLMs is not LLM
    ("title:trust", ["a", "e"]),
    ("abstract:calibration", ["f"]),
    ("naive", ["f"]),
    ("epsilon", ["f"]),
    # Wildcards over the snapshot vocabulary
    ("benchmark*", ["a", "b"]),
    ("model$", ["b", "d", "e"]),  # model, models
    ("llm$", ["a"]),
    ("trustworth*", ["b"]),
    # Phrases: consecutive, within one field
    ('"trust calibration"', ["a", "f"]),
    ('"human trust"', ["c"]),
    ('"calibration we"', []),  # never across the title/abstract boundary
    ("vision-language", ["b"]),
    ('"trust in ai"', ["c", "e"]),
    ('"the model$ and"', ["e"]),
    ("gpt-4o", ["f"]),
    # NEAR/n: unordered, ≤ n tokens between, one field
    ("trust NEAR/0 calibration", ["a", "f"]),
    ("calibration NEAR/0 trust", ["a", "f"]),
    ("trust NEAR/1 reliance", ["a"]),  # trust and reliance: one token between
    ("trust NEAR/0 reliance", []),
    ("models NEAR/2 ai", []),  # "models of trust in ai": 3 tokens between
    ("models NEAR/3 ai", ["e"]),
    ('"trust in" NEAR/0 ai', ["c", "e"]),
    ("title:(trust NEAR/0 calibration)", ["a"]),
    # Filters
    ("trust venue:ICML", ["e", "f"]),
    ("trust year:2022..2023", ["f"]),
    ("model$ year:2021", ["d"]),
    ("trust track:workshop", ["c"]),
    ("model$ status:rejected", ["d"]),
    # Boolean
    ("trust NOT calibration", ["e"]),  # c has calibration in its title
    ("calibration OR benchmark", ["a", "b", "c", "f"]),
]


@pytest.mark.parametrize(("q", "expected"), ROWS, ids=[q for q, _ in ROWS])
def test_rows(q: str, expected: list[str]) -> None:
    assert ids(q) == expected


def test_not_is_the_complement_in_the_snapshot() -> None:
    """`a OR NOT b` is well defined in the oracle (the parser rejects it as all-negative, but the tree is valid)."""
    tree = Or(
        span=(0, 1),
        children=(Term(span=(0, 1), token="model"), Not(span=(0, 1), child=Term(span=(0, 1), token="trust"))),
    )
    assert sorted(ENGINE.match_ids(tree)) == ["b", "d", "e"]


def test_default_filters_apply_through_the_effective_tree() -> None:
    result = parse("trust")
    assert result.effective_ast is not None
    assert sorted(ENGINE.match_ids(result.effective_ast)) == ["a", "e", "f"]  # c is a workshop paper


def test_expand_is_sorted_and_capped() -> None:
    assert ENGINE.expand(Wildcard(span=(0, 1), stem="model", op="$")) == ["model", "models"]
    many = ReferenceEngine([Rec(str(i), f"term{i:03d}", None) for i in range(201)])
    with pytest.raises(OpenProceedingsError) as err:
        many.expand(Wildcard(span=(0, 1), stem="term", op="*"))
    assert err.value.code == "WILDCARD_TOO_MANY_EXPANSIONS"
    assert len(many.expand(Wildcard(span=(0, 1), stem="term00", op="*"))) == 10


def test_search_is_in_id_order() -> None:
    result = parse("trust")
    assert result.ast is not None
    page = ENGINE.search(result.ast, offset=1, limit=2)
    assert (page.total, page.ids) == (4, ("c", "e"))


def test_facets_drop_only_the_fields_own_top_level_conjuncts() -> None:
    result = parse("trust venue:ICML")
    assert result.ast is not None
    facets = ENGINE.facets(result.ast)
    assert facets["venue"] == {"ICLR": 2, "ICML": 2}  # venue facet ignores venue:ICML
    assert facets["year"] == {"2022": 1, "2024": 1}  # other facets keep it
    nested = parse("(trust venue:ICML) OR benchmark")
    assert nested.ast is not None
    assert ENGINE.facets(nested.ast, ("venue",))["venue"] == {"ICLR": 1, "ICML": 2, "NeurIPS": 1}


def test_api_never_imports_the_oracle() -> None:
    src = Path(__file__).parents[2] / "src" / "openproceedings"
    for path in src.rglob("*.py"):
        if "api" not in path.relative_to(src).parts:
            continue
        tree = pyast.parse(path.read_text())
        names = [n.module or "" for n in pyast.walk(tree) if isinstance(n, pyast.ImportFrom)]
        names += [a.name for n in pyast.walk(tree) if isinstance(n, pyast.Import) for a in n.names]
        assert not any("engine.reference" in n for n in names), path


def test_the_oracle_imports_nothing_it_must_not() -> None:
    tree = pyast.parse((Path(__file__).parents[2] / "src/openproceedings/engine/reference.py").read_text())
    modules = {n.module for n in pyast.walk(tree) if isinstance(n, pyast.ImportFrom)}
    allowed = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "openproceedings.diagnostics",
        "openproceedings.engine.protocol",
        "openproceedings.query.ast",
        "openproceedings.query.normalize",
    }
    assert modules <= allowed, modules - allowed
