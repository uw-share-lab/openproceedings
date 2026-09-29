"""The concept-group builder never writes a query the server reads differently (TASK-043; spec 05 §Components 3).

The builder (`frontend/src/builder/`) walks the server's `ast` of a query (it never parses text) and writes a
query string back. Two files hold the evidence, one owned by each side:

- `builder-read-golden.json` is generated **here**: queries (the Trust-Evals strings, hand cases for every
  row of the design's fit table, and seeded random queries, in both modes), each with the server's `ast`
  and this module's reference reading of it (`read`): the groups, the Exclude row and the limits as
  code-point spans, or the first construct that doesn't fit. The frontend's reader must give the same
  reading (`read.test.ts`), so the fit rule has two implementations that are checked against each other.
- `builder-write-golden.json` is generated **by the frontend** (`write.test.ts`, `UPDATE_BUILDER_GOLDEN=1`):
  what the builder writes for each fitting read case without an edit, and for seeded random edits (awkward
  term text, pasted lists, scopes, reordering, removal, an Exclude row). This module checks each string
  with the real parser: an unedited rewrite has the original's `canonical`, and an edited one means exactly
  what its chips say (every group is the OR of its chips, each read alone; the Exclude row; the limits
  verbatim), with no error or warning that the chips don't raise on their own.

Regenerate the read golden with
`(cd backend && uv run python -m tests.contract.test_frontend_builder_golden --write)`, then the write golden
with `UPDATE_BUILDER_GOLDEN=1 npm test --workspace frontend -- builder`, and commit both.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest
from openproceedings.query.ast import And, Filter, Near, Node, Not, Or, Phrase, Term, Wildcard, structure
from openproceedings.query.parser import Mode, parse

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "frontend" / "src" / "builder"
READ_GOLDEN = BUILDER / "builder-read-golden.json"
WRITE_GOLDEN = BUILDER / "builder-write-golden.json"
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "queries"
MODES: tuple[Mode, ...] = ("native", "scholar")

LEAVES = (Term, Wildcard, Phrase)

# The design's kinds (copy deck BD-7), plus two the table implies but doesn't word.
PROXIMITY = "proximity"
AND_IN_OR = "AND inside OR"
LIMIT_IN_OR = "a limit inside OR"
NOT_OF_COMBINATION = "NOT of a combination"
NOT_IN_OR = "NOT inside OR"
SECOND_NOT = "a second NOT"


class Blocked(Exception):
    def __init__(self, kind: str, span: tuple[int, int]) -> None:
        super().__init__(kind)
        self.kind, self.span = kind, span


def _flat(node: Node, kind: type[And] | type[Or]) -> list[Node]:
    """The children of nested same-kind nodes, in source order (`(a OR b) OR c` is one list)."""
    if isinstance(node, kind):
        return [leaf for child in node.children for leaf in _flat(child, kind)]
    return [node]


def _only_filters(node: Node) -> bool:
    return isinstance(node, Filter) or (isinstance(node, Or) and all(_only_filters(c) for c in node.children))


def _group(node: Node) -> list[Node]:
    """The leaves of a group (a leaf, or an OR of leaves), or the construct that blocks it."""
    items = _flat(node, Or)
    for item in items:
        if isinstance(item, LEAVES):
            continue
        if isinstance(item, Near):
            raise Blocked(PROXIMITY, item.span)
        # what's left after flattening: an And, a Filter or a Not; the group's own span names it
        raise Blocked({And: AND_IN_OR, Filter: LIMIT_IN_OR, Not: NOT_IN_OR}[type(item)], node.span)
    return items


def read(ast: Node) -> dict[str, Any]:
    """The reference reading (docs/design/2026-09-27-concept-group-builder.md §The shape the builder edits):
    groups, one optional Exclude row (and how many groups precede it), and the limits, each as spans."""
    groups: list[list[Node]] = []
    exclude: list[Node] | None = None
    exclude_at = 0
    limits: list[Node] = []
    for child in _flat(ast, And):
        if _only_filters(child) or (isinstance(child, Not) and _only_filters(child.child)):
            limits.append(child)
        elif isinstance(child, Not):
            inner = child.child
            if exclude is not None:
                raise Blocked(SECOND_NOT, child.span)
            if isinstance(inner, Near):
                raise Blocked(PROXIMITY, inner.span)
            if isinstance(inner, And | Not):
                raise Blocked(NOT_OF_COMBINATION, child.span)
            exclude, exclude_at = _group(inner), len(groups)
        elif isinstance(child, Near):
            raise Blocked(PROXIMITY, child.span)
        else:
            groups.append(_group(child))
    spans = lambda nodes: [list(n.span) for n in nodes]  # noqa: E731
    return {
        "groups": [spans(g) for g in groups],
        "exclude": None if exclude is None else spans(exclude),
        "exclude_at": exclude_at if exclude is not None else len(groups),
        "limits": spans(limits),
    }


def reading(ast: Node | None) -> dict[str, Any] | None:
    if ast is None:
        return None
    try:
        return read(ast)
    except Blocked as b:
        return {"blocker": {"kind": b.kind, "span": list(b.span)}}


# ---------------------------------------------------------------------------------------------------------
# The read golden's inputs

HAND = [
    # fits
    '("foundation model" OR LLM) AND (trustworth* OR trust) AND benchmark AND venue:ICLR',
    "trust",
    "a OR b",
    "(a OR b) OR c",
    "(a AND b) AND c",
    "a (b c)",
    "title:(a OR b) c",
    "title:(a OR abstract:b)",
    'Title:LLM OR abstract: "trust calibration"',
    "trust -bias",
    "trust NOT (bias OR fairness) benchmark",
    "NOT (bias OR fairness) trust",
    "-bias trust",
    "trust venue:ICLR year:2020..2026 NOT track:workshop",
    "venue:ICLR trust (venue:ICML OR venue:NeurIPS)",
    "venue:ICLR OR venue:ICML",
    "trust AND (venue:ICLR OR (venue:ICML OR year:2024))",
    "gpt-4* OR model$ OR “curly phrase” OR «guillemets»",
    'G\\"odel OR $f(x)$-DP OR 𝐱 OR ＬＬＭ',
    "(((trust)))",
    "trust | reliance",
    "a AND b AND NOT c",
    '"and" OR "or"',
    "trust AND (bias OR (fairness OR equity))",
    # what the builder's own UI tests write (concept-builder.test.tsx answers /parse from this file)
    '("foundation model" OR LLM) AND (trustworth* OR trust) AND (benchmark OR leaderboard) AND venue:ICLR',
    "(trust OR reliance) AND benchmark",
    "(trust OR reliance)",
    "trust AND benchmark",
    "benchmark AND (trust OR reliance)",
    "(bias OR fairness OR equity)",
    '"foundation model"',
    "title:trust",
    "trust AND NOT bias",
    '(  "foundation model"   OR LLM )  trustworth*   venue:iclr',
    # doesn't fit
    "trust NEAR/5 calibrat*",
    "(trust NEAR/5 calibrat*) OR reliance",
    "(a AND b) OR c",
    "a OR b AND c",
    "track:workshop OR x",
    "trust (venue:ICLR OR bias)",
    "NOT (a AND b) c",
    "trust NOT a NOT b",
    "trust -a -b",
    "trust (bias OR NOT fairness)",
    "trust AND (a OR -b)",
    "trust NOT (x NEAR/2 y)",
    "trust NOT NOT bias",
    "title:(a AND b) OR c",
    # errors (the builder reads nothing)
    "trust OR",
    "(trust",
    "be*",
]

SCHOLAR_HAND = [
    "(large language model$ | LLM) source:ICLR",
    'trust (source:"ICLR" OR source:PMLR)',
    "(AI agent$ | text-to-image model$) (trust | trustworthy AI$)",
]

_WORDS = ["trust", "LLM", "Benchmark", "reliance", "bias", "fairness", "AI", "evaluation", "model", "2024"]
_WILDCARDS = ["trustworth*", "calibrat*", "model$", "benchmark*", "gpt-4*"]
_PHRASES = ['"foundation model"', '"large language model$"', '"trust in AI"', "“vision language”", '"x"']
_ODD = ["C++", ".NET", 'G\\"odel', "$x$", "𝐱", "ＬＬＭ", "vision-language", "human-AI", "o'brien", "é"]
_LIMITS = [
    "venue:ICLR",
    "venue:(ICML OR NeurIPS)",
    "year:2020..2026",
    "year:2023",
    "track:(main OR workshop)",
    "NOT track:workshop",
    "-status:rejected",
    "status:accepted",
    "(venue:ICLR OR venue:ICML)",
]
_SCHOLAR_WORDS = ["large language model$", "AI agent$", "trustworthy AI$"]
_SCHOLAR_LIMITS = ["source:ICLR", "(source:ICML OR source:NeurIPS)", 'source:"ICLR"', "source:PMLR"]
_BLOCKERS = ["trust NEAR/3 bias", "(a AND b) OR c", "track:main OR x", "NOT (a AND b)", "(a OR NOT b)"]


def _leaf(rng: random.Random, scholar: bool) -> str:
    pool = [_WORDS, _WORDS, _WILDCARDS, _PHRASES, _ODD]
    leaf = rng.choice(rng.choice(pool))
    if rng.random() < 0.15:
        leaf = rng.choice(["title:", "abstract:", "Title:", "title: "]) + leaf
    return leaf


def _group_text(rng: random.Random, scholar: bool) -> str:
    n = rng.choice([1, 1, 2, 3, 4])
    if scholar and n > 1 and rng.random() < 0.4:
        items = [rng.choice(_SCHOLAR_WORDS + _WORDS) for _ in range(n)]
        return "(" + " | ".join(items) + ")"
    items = [_leaf(rng, scholar) for _ in range(n)]
    if n == 1:
        return items[0]
    sep = rng.choice([" OR ", " OR ", " | "])
    if n >= 3 and rng.random() < 0.2:
        return f"(({items[0]}{sep}{items[1]}){sep}{sep.join(items[2:])})"
    if rng.random() < 0.15:
        field = rng.choice(["title", "abstract"])
        plain = [i.split(":", 1)[-1].strip() for i in items]
        return f"{field}:({sep.join(plain)})"
    return "(" + sep.join(items) + ")"


def _random_query(rng: random.Random, mode: Mode) -> str:
    scholar = mode == "scholar"
    parts = [_group_text(rng, scholar) for _ in range(rng.randint(1, 4))]
    if rng.random() < 0.3:
        exclusion = _group_text(rng, scholar)
        neg = "-" + exclusion if not exclusion.startswith("(") and rng.random() < 0.5 else "NOT " + exclusion
        parts.insert(rng.randint(1, len(parts)), neg)
    for _ in range(rng.choice([0, 0, 1, 2])):
        limit = rng.choice(_SCHOLAR_LIMITS + _LIMITS if scholar else _LIMITS)
        parts.insert(rng.randint(0, len(parts)), limit)
    if rng.random() < 0.12:
        parts.insert(rng.randint(0, len(parts)), rng.choice(_BLOCKERS))
    joined = parts[0]
    for part in parts[1:]:
        joined += rng.choice([" AND ", " AND ", " "]) + part
    if len(parts) >= 3 and rng.random() < 0.1:
        joined = f"({parts[0]} AND {parts[1]}) AND " + " AND ".join(parts[2:])
    return joined


def _random_queries(mode: Mode, n: int) -> list[str]:
    rng = random.Random(f"builder-{mode}-43")
    out: list[str] = []
    while len(out) < n:
        q = _random_query(rng, mode)
        if parse(q, mode).errors == [] and q not in out:
            out.append(q)
    return out


def _trust_evals() -> list[str]:
    lines = (FIXTURES / "trust-evals.txt").read_text(encoding="utf-8").split("\n")
    return [line for line in lines if line.strip() and not line.startswith(("#", "## "))]


def _inputs() -> list[tuple[str, Mode]]:
    found: list[tuple[str, Mode]] = []
    for mode in MODES:
        found += [(q, mode) for q in (*_trust_evals(), *HAND)]
        found += [(q, mode) for q in _random_queries(mode, 120)]
    found += [(q, "scholar") for q in SCHOLAR_HAND]
    seen: set[tuple[str, Mode]] = set()
    return [c for c in found if not (c in seen or seen.add(c))]


GENERATED = (
    "by (cd backend && uv run python -m tests.contract.test_frontend_builder_golden --write); do not edit"
)


def build_read_golden() -> dict[str, Any]:
    cases = []
    for q, mode in _inputs():
        result = parse(q, mode)
        ast = None if result.ast is None else result.ast.model_dump(mode="json")
        cases.append(
            {
                "q": q,
                "mode": mode,
                "errors": [e.code.value for e in result.errors],
                "ast": ast,
                "read": reading(result.ast),
            }
        )
    return {"_generated": GENERATED, "cases": cases}


def render(data: dict[str, Any]) -> str:
    """One case per line: the file is large, and a line per case keeps a regenerated diff readable."""
    cases = ",\n".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in data["cases"])
    return f'{{"_generated": {json.dumps(data["_generated"])},\n"cases": [\n{cases}\n]}}\n'


def test_the_read_golden_is_current() -> None:
    assert READ_GOLDEN.read_text(encoding="utf-8") == render(build_read_golden()), (
        f"{READ_GOLDEN.relative_to(ROOT)} is stale: run "
        "`(cd backend && uv run python -m tests.contract.test_frontend_builder_golden --write)`, then "
        "`UPDATE_BUILDER_GOLDEN=1 npm test --workspace frontend -- builder`, and commit both"
    )


def test_the_read_golden_covers_every_outcome() -> None:
    """Each fit-table row and each blocker kind is exercised, and most random cases fit (else the random
    part tests only the read-only path)."""
    cases = build_read_golden()["cases"]
    kinds = {c["read"]["blocker"]["kind"] for c in cases if c["read"] and "blocker" in c["read"]}
    assert kinds == {PROXIMITY, AND_IN_OR, LIMIT_IN_OR, NOT_OF_COMBINATION, NOT_IN_OR, SECOND_NOT}
    fits = [c for c in cases if c["read"] and "groups" in c["read"]]
    assert len(fits) > 250
    assert any(c["read"]["exclude"] is not None for c in fits)
    assert any(c["read"]["exclude_at"] < len(c["read"]["groups"]) for c in fits)
    assert any(c["read"]["limits"] for c in fits)
    assert any(c["read"] is None for c in cases)
    main7 = [c for c in fits if c["mode"] == "scholar" and c["q"] in _trust_evals()]
    assert main7, "the Trust-Evals strings fit in Scholar mode"


# ---------------------------------------------------------------------------------------------------------
# The write golden: what the frontend builder writes, checked with the real parser

WRITE: list[dict[str, Any]] = (
    json.loads(WRITE_GOLDEN.read_text(encoding="utf-8"))["cases"] if WRITE_GOLDEN.exists() else []
)


def _id(case: dict[str, Any]) -> str:
    return f"{case['mode']}:{case['written']!r}"


def test_the_write_golden_has_both_kinds() -> None:
    assert sum(1 for c in WRITE if "from" in c) > 250
    assert sum(1 for c in WRITE if "chips" in c) > 250


@pytest.mark.parametrize("case", [c for c in WRITE if "from" in c], ids=_id)
def test_an_unedited_rewrite_keeps_the_canonical_query(case: dict[str, Any]) -> None:
    """Builder → q' without an edit: `canonical(q') == canonical(q)` (design §The shape; TASK-043 AC#1)."""
    original = parse(case["from"], case["mode"])
    rewritten = parse(case["written"], case["mode"])
    assert original.errors == [] and rewritten.errors == [], [e.code for e in rewritten.errors]
    assert rewritten.canonical == original.canonical
    assert "WARN_MIXED_AND_OR" not in [w.code.value for w in rewritten.warnings]


@pytest.mark.parametrize("case", [c for c in WRITE if "chips" in c], ids=_id)
def test_an_edited_query_means_what_its_chips_say(case: dict[str, Any]) -> None:
    """Every chip, read on its own, is one leaf; the written query is the AND of the groups, each the OR of
    its chips' leaves, the Exclude row where the builder put it, and the limits as written. A chip the
    server refuses on its own makes the whole query refused (never read another way), and the query raises
    no warning its chips and limits don't raise on their own."""
    mode: Mode = case["mode"]
    chips: list[list[str]] = case["chips"]
    exclude: list[str] | None = case["exclude"]
    limits: list[str] = case["limits"]
    written = parse(case["written"], mode)
    # a limit alone may be all-negative (`NOT track:workshop`), so it is read next to a plain word
    alone = [parse(t, mode) for t in [*(c for g in chips for c in g), *(exclude or [])]]
    alone += [parse(f"x AND {limit}", mode) for limit in limits]
    if any(a.errors for a in alone):
        assert written.errors, "a chip the server refuses alone was accepted in context"
        return
    if not chips and [e.code.value for e in written.errors] == ["PARSE_ALL_NEGATIVE"]:
        return  # every group emptied, nothing positive left: the server's all-negative error, as in Text
    assert written.errors == [], [(e.code, e.span) for e in written.errors]
    assert written.ast is not None
    got = read(written.ast)

    def leaf(text: str) -> Any:
        ast = parse(text, mode).ast
        assert isinstance(ast, LEAVES), f"chip {text!r} is not one term: {ast}"
        return structure(ast)

    def at(span: list[int]) -> Node:
        found = [n for n in _nodes(written.ast) if list(n.span) == span and isinstance(n, LEAVES)]
        assert found, span
        return found[0]

    assert [[structure(at(s)) for s in g] for g in got["groups"]] == [[leaf(c) for c in g] for g in chips]
    if exclude is None:
        assert got["exclude"] is None
    else:
        assert got["exclude"] is not None
        assert [structure(at(s)) for s in got["exclude"]] == [leaf(c) for c in exclude]
        assert got["exclude_at"] == case["exclude_at"]
    assert [case["written"][s:e] for s, e in got["limits"]] == limits  # str indices are code points
    allowed = {w.code for a in alone for w in a.warnings}
    assert {w.code for w in written.warnings} <= allowed, [w.code for w in written.warnings]


def _nodes(n: Node) -> list[Node]:
    out: list[Node] = [n]
    if isinstance(n, And | Or):
        for c in n.children:
            out += _nodes(c)
    elif isinstance(n, Not):
        out += _nodes(n.child)
    return out


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        sys.exit("usage: test_frontend_builder_golden.py --write")
    READ_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    READ_GOLDEN.write_text(render(build_read_golden()), encoding="utf-8")
    print(f"wrote {READ_GOLDEN.relative_to(ROOT)}")
