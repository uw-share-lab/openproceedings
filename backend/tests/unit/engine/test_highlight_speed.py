"""Task-073's faster highlights change no span (spec 03 §Highlights; exactness-guardian standard).

Two differentials, each against a frozen copy of the code as it was before (`tests/unit/tokenize_before.py`,
`tests/unit/engine/highlight_before.py`):
- `tokenize` (its ASCII-text path and its per-character ASCII branch) gives exactly the old tokens, text,
  span and `op`, on arbitrary, adversarial and LaTeX-heavy text and on every fixture text;
- `Highlighter` (one per query, token maps per field) gives exactly the old spans, for every golden query on
  every record it matches, every Trust-Evals protocol string on the 5k corpus, and generated trees, and
  refuses a non-hit the same way.
Then exact spans for NEAR, phrases and wildcards through each path of the new occurrence lookup.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from openproceedings.engine import highlight
from openproceedings.engine.highlight import Highlighter, highlights
from openproceedings.engine.protocol import EngineInputError, EngineInternalError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query import normalize
from openproceedings.query.ast import Node
from openproceedings.query.normalize import Token, tokenize
from openproceedings.query.parser import parse

from tests.corpus import Rec, fixture_records
from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_trust_evals import STRINGS
from tests.strategies import asts, engine_asts
from tests.unit.engine import highlight_before
from tests.unit.test_normalize import TRICKY_ALPHABET
from tests.unit.tokenize_before import tokenize as tokenize_before

RECORDS = fixture_records()
REFERENCE = ReferenceEngine(RECORDS)
SYNTHETIC = list(records())
SYNTHETIC_REFERENCE = ReferenceEngine(SYNTHETIC)
GOLDEN = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "corpus" / "reference-200-queries.json").read_text()
)


def full(tokens: list[Token]) -> list[tuple[str, int, int, bool]]:
    """Everything a token carries."""
    return [(t.text, t.start, t.end, t.op) for t in tokens]


# --- tokenize ----------------------------------------------------------------------------------------------

# LaTeX-ish text: pieces of markup, command names and math, glued from an alphabet of fragments
LATEXISH = st.lists(
    st.sampled_from([*TRICKY_ALPHABET, *"\\$^_{}()[]xX", "alpha", "le", "not", "in", "\u0338", "×", "½"]),
    max_size=30,
).map("".join)
ASCII = st.text(alphabet=st.characters(max_codepoint=0x7F), max_size=80)


@given(st.one_of(st.text(max_size=80), ASCII, LATEXISH))
@example("Trust in AI: GPT-4o, 5 models.")  # the whole-text ASCII path
@example("na\u00efve e\u0301 5\u00d73")  # non-ASCII: the loop, its ASCII branch around the rest
@example("a\u0301b")  # an ASCII letter with a mark after it leaves the branch
@example('$x^2$ G\\"odel \\alpha \\emph{x} \\-')  # ASCII, but LaTeX: never the whole-text path
@example("x\u00bd\u0338y =\u0345\u0338")  # combining-slash clusters (task-075)
@example("\\\"{O}del \\'etude \\-x $^2x$")  # markup that opens a word: its span starts there (task-074)
def test_tokenize_gives_exactly_the_old_tokens(text: str) -> None:
    assert full(tokenize(text)) == full(tokenize_before(text))


def test_tokenize_gives_exactly_the_old_tokens_on_every_fixture_text() -> None:
    texts = [t for r in [*RECORDS, *SYNTHETIC] for t in (r.title, r.abstract or "")]
    assert [full(tokenize(t)) for t in texts] == [full(tokenize_before(t)) for t in texts]


def test_only_plain_ascii_takes_the_whole_text_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    each_char = normalize._tokenize_each_char
    monkeypatch.setattr(normalize, "_tokenize_each_char", lambda t: calls.append(t) or each_char(t))
    for text in ("plain ASCII, 42 words.", ""):
        tokenize(text)
    assert calls == []
    for text in ("$x$ y", "a \\emph{b}", "na\u00efve", "a\u0301"):
        tokenize(text)
    assert calls == ["$x$ y", "a \\emph{b}", "na\u00efve", "a\u0301"]


# --- highlights --------------------------------------------------------------------------------------------


def same_spans(ast: Node, engine: ReferenceEngine, recs: list[Rec], limit: int | None = None) -> int:
    """Old and new spans agree on every record `ast` matches (the first `limit` by id, if given), and both
    refuse one it doesn't; returns how many hits were compared."""
    try:
        expansions = engine.expansions(ast)
    except EngineInputError:  # a wildcard over the cap: refused before any engine runs, so never a hit
        return 0
    matched = engine.match_ids(ast)
    lit = Highlighter(ast, expansions)
    hits = sorted((r for r in recs if r.id in matched), key=lambda r: r.id)[:limit]
    for r in hits:
        assert lit(r) == highlight_before.highlights(ast, r, expansions), r.id  # type: ignore[arg-type]
    miss = next((r for r in recs if r.id not in matched), None)
    if miss is not None:
        with pytest.raises(EngineInternalError):
            lit(miss)  # type: ignore[arg-type]
        with pytest.raises(EngineInternalError):
            highlight_before.highlights(ast, miss, expansions)  # type: ignore[arg-type]
    return len(hits)


@pytest.mark.parametrize("case", GOLDEN, ids=[c["q"] for c in GOLDEN])
def test_every_golden_query_lights_the_same_spans(case: dict[str, object]) -> None:
    ast = parse(str(case["q"])).ast
    assert ast is not None
    same_spans(ast, REFERENCE, RECORDS)


@pytest.mark.parametrize("name", list(STRINGS))
def test_every_trust_evals_string_lights_the_same_spans_on_the_5k_corpus(name: str) -> None:
    ast = parse(STRINGS[name], "scholar").effective_ast
    assert ast is not None
    same_spans(ast, SYNTHETIC_REFERENCE, SYNTHETIC)


# capped at 10,000 (the nightly profile's 50,000 would take over an hour here, ~80 ms an example)
@settings(deadline=None, max_examples=min(settings().max_examples, 10_000))
@given(asts())
def test_generated_trees_light_the_same_spans_on_every_fixture_record(ast: Node) -> None:
    same_spans(ast, REFERENCE, RECORDS)


# the old highlighter tokenizes each hit with the old tokenizer: slow on thousands of hits, so the first 20;
# and a tenth of the profile's examples, at most 500 (20 per PR, 200 in nightly suite-ci, 500 at 50k): each one runs the oracle over
# 5k records, up to ~1 s an example
@settings(deadline=None, max_examples=min(max(10, settings().max_examples // 10), 500))
@given(engine_asts(vocab()))
def test_generated_trees_light_the_same_spans_on_the_5k_corpus(ast: Node) -> None:
    same_spans(ast, SYNTHETIC_REFERENCE, SYNTHETIC, limit=20)


# --- exact spans through each path of the occurrence lookup -------------------------------------------------


def lit(q: str, title: str, abstract: str | None = None) -> dict[str, list[str]]:
    r = Rec("fx:001", title, abstract)  # type: ignore[call-arg]
    ast = parse(q).ast
    assert ast is not None
    spans = highlights(ast, r, ReferenceEngine([r]).expansions(ast))  # type: ignore[arg-type]
    assert spans == highlight_before.highlights(ast, r, ReferenceEngine([r]).expansions(ast))  # type: ignore[arg-type]
    return {f: [(getattr(r, f) or "")[s:e] for s, e in v] for f, v in spans.items()}


def test_a_phrase_that_ends_the_field_and_one_cut_off_by_it() -> None:
    got = lit('"language model"', "t", "a language model; the last word is language")
    assert got["abstract"] == ["language model"]  # the trailing `language` has no room for `model`


def test_a_phrase_led_by_a_wildcard_lights_each_occurrence() -> None:
    # the wildcard's expansion (trust, trusted, trusting) is looked up in the field's token map
    got = lit('"trust* in" ai', "t", "trusting in ai, trusted in AI, trust in me, in ai")
    assert got["abstract"] == [
        "trusting in",
        "ai",
        "trusted in",
        "AI",
        "trust in",
        "ai",
    ]  # `in me` isn't `ai`


def test_a_wildcard_wider_than_the_field_scans_the_field_instead() -> None:
    # more expansions (from the other field) than the abstract has distinct tokens: the other branch
    title = " ".join(f"model{i}" for i in range(30))
    got = lit('"model* x"', title + " x", "model3 x, model9 y")
    assert got["abstract"] == ["model3 x"]
    assert got["title"] == ["model29 x"]


def test_near_through_the_token_map_in_either_order_and_with_a_phrase() -> None:
    abstract = "ai x trust. y y y y y trust in ai z trust"
    got = lit("trust NEAR/1 ai", "t", abstract)
    # `ai x trust` and `trust in ai z trust`: one token between each pair, in either order
    assert got["abstract"] == ["ai", "trust", "trust", "ai", "trust"]
    got = lit('"trust in" NEAR/0 ai', "t", abstract)
    assert got["abstract"] == ["trust in", "ai"]
    got = lit("tru* NEAR/0 x", "t", abstract)
    assert got["abstract"] == ["x", "trust"]  # only the first `trust` is next to an `x`


def test_highlights_over_text_the_ascii_path_and_the_loop_both_tokenize() -> None:
    # the title is plain ASCII (the whole-text path); the abstract has a diacritic and math (the loop)
    got = lit(
        'naive OR "5 times" OR trust*', "Trusted naive models", "A na\u00efve 5\u00d73 trusting $\\alpha$"
    )
    assert got == {"title": ["Trusted", "naive"], "abstract": ["na\u00efve", "5\u00d7", "trusting"]}


def test_a_field_no_leaf_reads_is_never_tokenized(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(highlight, "tokenize", lambda t: seen.append(t) or tokenize(t))
    r = Rec("fx:001", "trust in ai", "an abstract no leaf reads")  # type: ignore[call-arg]
    ast = parse("title:trust").ast
    assert ast is not None
    assert Highlighter(ast, {})(r) == {"title": [(0, 5)], "abstract": []}  # type: ignore[arg-type]
    assert seen == ["trust in ai"]


def test_a_highlighter_does_its_query_work_once_for_every_hit() -> None:
    ast = parse('trust* OR ("large language" NEAR/3 model*) OR (ai NOT survey)').ast
    assert ast is not None
    lit = Highlighter(ast, REFERENCE.expansions(ast))
    before = dict(lit.allowed)
    assert len(before) == 5  # trust*, the phrase, model*, ai and survey (a NOT's child is evaluated too)
    for r in RECORDS:
        if r.id in REFERENCE.match_ids(ast):
            lit(r)  # type: ignore[arg-type]
    assert lit.allowed == before  # never written to after construction
