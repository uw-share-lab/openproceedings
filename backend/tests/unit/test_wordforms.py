"""Where `$` can be added to the terms the no-stemming notice names (TASK-175; spec 02 §Word forms).

`query.wordforms.word_forms` reports the edits the UI's "Add `$`" action makes. The table pins what is offered
and what is left alone (a phrase's inner words, filter and `source:` values, terms with a wildcard, stems too
short, symbols after the word, LaTeX in the run); the properties check that every offered edit, alone and all
together, parses to the same query with exactly those terms made `$` wildcards.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from hypothesis import event, given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query import wordforms
from openproceedings.query.ast import structure
from openproceedings.query.parser import MAX_QUERY_LENGTH, ParseResult, exact_leaves, exact_name, parse
from openproceedings.query.wordforms import WordForm, apply, word_forms

from tests.strategies import queries

ROOT = Path(__file__).resolve().parents[3]
LINES = (ROOT / "backend" / "tests" / "fixtures" / "queries" / "trust-evals.txt").read_text().split("\n")
TRUST_EVALS = {LINES[i][3:]: LINES[i + 1] for i in range(len(LINES) - 1) if LINES[i].startswith("## ")}

# (name, query, the query with every offered `$` added)
CASES: list[tuple[str, str, str]] = [
    ("word", "trust", "trust$"),
    ("case is kept as typed", "LLM benchmark", "LLM$ benchmark$"),
    ("phrase: last word only", '"large language model" trust', '"large language model$" trust$'),
    ("phrase: inner words are left alone", '"model evaluation framework"', '"model evaluation framework$"'),
    ("phrase with a space before its closing quote", '"trust in AI "', '"trust in AI$ "'),
    ("phrase of one word", '"trust"', '"trust$"'),
    ("Scholar `|` item read as a phrase", "(large language model | LLM)", "(large language model$ | LLM$)"),
    ("hyphenated word is a phrase", "vision-language gpt-4", "vision-language$ gpt-4$"),
    (
        "phrase holding a wildcard is not named",
        '"large$ language model" "x model$ yy"',
        '"large$ language model" "x model$ yy"',
    ),
    ("term with $ already", "model$ trust", "model$ trust$"),
    ("term with * already", "bench* trust", "bench* trust$"),
    (
        "filter values",
        "trust year:2020..2024 venue:ICLR track:(main OR workshop) status:accepted",
        "trust$ year:2020..2024 venue:ICLR track:(main OR workshop) status:accepted",
    ),
    (
        "source: values",
        'trust source:ICLR source:"international conference on machine learning"',
        'trust$ source:ICLR source:"international conference on machine learning"',
    ),
    ("source: group", "trust (source:ICLR OR source:PMLR)", "trust$ (source:ICLR OR source:PMLR)"),
    ("bare value beside a filter is a term", "year:2023 OR 2024", "year:2023 OR 2024$"),
    ("stem under 3 letters or digits", "AI ML trust", "AI ML trust$"),
    ("a phrase's earlier words count toward the stem", '"generative AI" "a b"', '"generative AI$" "a b"'),
    ("symbols after the word", "C++ trust? .NET", "C++ trust? .NET$"),
    ("phrase ending in symbols", '"what is trust?" "trust in AI ?"', '"what is trust?" "trust in AI ?"'),
    ("currency $ in the word", "US$5 trust", "US$5 trust$"),
    ("LaTeX math in the word", "$f(x)$-DP trust", "$f(x)$-DP trust$"),
    ("a backslash in the word", 'G\\"odel trust', 'G\\"odel trust$'),
    ("full-width $ in the run", "(model＄|LLM) trust", "(model＄|LLM) trust$"),
    ("a wildcard earlier in the unspaced run", "(model$|LLM)", "(model$|LLM)"),
    ("a star earlier in the unspaced run", "(bench*|LLM)", "(bench*|LLM$)"),
    ("two words in one unspaced run", "(model|LLM)", "(model$ |LLM$)"),
    ("three words in one unspaced run", "(model|LLM|agent) trust", "(model$ |LLM$ |agent$) trust$"),
    ("a quote ends the run", '"trust"|("abc")(model)', '"trust$"|("abc$")(model$)'),
    ("field prefix", 'title:trust abstract:"human evaluation"', 'title:trust$ abstract:"human evaluation$"'),
    ("field group", "title:(trust OR reliance)", "title:(trust$ OR reliance$)"),
    ("group of one", '(model) (("trust in AI")) title:(LLM)', '(model$) (("trust in AI$")) title:(LLM$)'),
    ("NOT and -", "trust NOT bias -harm", "trust$ NOT bias$ -harm$"),
    ("NEAR operands", 'trust NEAR/3 "language model"', 'trust$ NEAR/3 "language model$"'),
    ("each place a term is written", "trust OR (trust AND model)", "trust$ OR (trust$ AND model$)"),
    ("lowercase operator word", "trust and model", "trust$ and$ model$"),
    ("astral letters before the term", "𝒜𝒜𝒜 model", "𝒜𝒜𝒜$ model$"),
    ("CJK run", "大语言模型", "大语言模型$"),
]


def scholar(q: str) -> ParseResult:
    result = parse(q, "scholar")
    assert result.errors == [], result.errors
    return result


def forms_of(q: str) -> list[WordForm]:
    forms = word_forms(q, scholar(q))
    assert forms is not None
    return forms


@pytest.mark.parametrize(("q", "rewritten"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_dollar_goes_only_where_it_is_a_valid_wildcard_on_a_named_term(q: str, rewritten: str) -> None:
    assert apply(q, forms_of(q)) == rewritten


def test_forms_carry_the_notices_name_and_a_code_point_offset() -> None:
    q = '𝒜𝒜𝒜 "Large Language Model" (model|LLM)'
    assert [f.model_dump() for f in forms_of(q)] == [
        {"term": "aaa", "at": 3, "insert": "$"},  # code points: each 𝒜 is one, and two UTF-16 units
        {"term": "large language model", "at": 25, "insert": "$"},  # inside the closing quote
        {"term": "model", "at": 33, "insert": "$ "},  # another offered word follows in its unspaced run
        {"term": "llm", "at": 37, "insert": "$"},
    ]


def test_none_with_errors_and_empty_outside_scholar_mode() -> None:
    assert word_forms("(trust", parse("(trust", "scholar")) is None
    assert word_forms("trust", parse("trust")) == []  # native mode has no notice: the rule is the spec
    assert forms_of("bench* model$ year:2024") == []  # nothing the notice names


def test_nothing_is_offered_when_the_edited_query_would_be_too_long() -> None:
    """The check is all the edits at once, so near the cap none is offered rather than some that fit."""
    q = " ".join(["abc"] * (MAX_QUERY_LENGTH // 4))
    assert len(q) <= MAX_QUERY_LENGTH < len(q) + q.count("abc")
    result = scholar(q)
    assert result.ast is not None and len(wordforms._candidates(q, result.ast, result)) == q.count("abc")
    assert forms_of(q) == []
    room = " ".join(["abc"] * 300)
    assert len(forms_of(room)) == 300


def test_every_term_offered_is_one_the_notice_names() -> None:
    q = TRUST_EVALS["main-2-pop"]
    result = scholar(q)
    [note] = [t for t in result.translations if t.code is DiagnosticCode.COMPAT_NO_STEMMING]
    named = {exact_name(leaf) for leaf in exact_leaves(result.ast)}  # type: ignore[arg-type]
    assert {f.term for f in forms_of(q)} == named  # every one of this string's exact terms takes a `$`
    assert all(f"`{t}`" in note.message for t in list(dict.fromkeys(f.term for f in forms_of(q)))[:8])


def _plain(n: Any) -> Any:
    """A tree's structure with every `$` wildcard put back as the term it was."""
    if isinstance(n, dict):
        if n.get("kind") == "wildcard" and n["op"] == "$":
            return {"kind": "term", "token": n["stem"], "field": n["field"]}
        return {k: _plain(v) for k, v in n.items()}
    return [_plain(v) for v in n] if isinstance(n, list | tuple) else n


def _dollars(n: Any) -> int:
    if isinstance(n, dict):
        return (n.get("kind") == "wildcard" and n["op"] == "$") + sum(_dollars(v) for v in n.values())
    return sum(_dollars(v) for v in n) if isinstance(n, list | tuple) else 0


def check_edits(q: str) -> list[WordForm]:
    """Every offered edit, alone and all together, parses to `q`'s tree with exactly those exact terms made
    `$` wildcards: nothing else in the query is read differently."""
    before = scholar(q)
    assert before.ast is not None
    forms = word_forms(q, before)
    assert forms is not None
    tree = structure(before.ast)
    names = Counter(exact_name(leaf) for leaf in exact_leaves(before.ast))
    assert [f.at for f in forms] == sorted({f.at for f in forms})  # in order, one per place
    for chosen in [*([f] for f in forms), forms]:
        after = parse(apply(q, chosen), "scholar")
        assert after.errors == [], (q, chosen, after.errors)
        assert after.ast is not None
        edited = structure(after.ast)
        assert _plain(edited) == _plain(tree), (q, chosen)
        assert _dollars(edited) == _dollars(tree) + len(chosen), (q, chosen)
        left = Counter(exact_name(leaf) for leaf in exact_leaves(after.ast))
        assert left == names - Counter(f.term for f in chosen), (q, chosen)
    return forms


@pytest.mark.parametrize("q", [c[1] for c in CASES], ids=[c[0] for c in CASES])
def test_each_edit_and_all_of_them_change_only_the_terms_they_name(q: str) -> None:
    check_edits(q)


@pytest.mark.parametrize("name", list(TRUST_EVALS))
def test_the_review_strings_take_their_edits(name: str) -> None:
    assert check_edits(TRUST_EVALS[name])


# words that take a `$`, and ones that must not (short, wildcarded, symbols, LaTeX, escapes, operators' look-alikes)
_WORDS = st.sampled_from(
    ["trust", "LLM", "model", "gpt-4", "AI", "ab", "C++", ".NET", "trust?", "US$5", "$x$", "$f(x)$-DP", "bench*",
     "model$", 'G\\"odel', "a\\$b", "＄y＄", "𝒜𝒜𝒜", "and", "or", "2024", "naïve", "大语言模型", "x×y", "~"]
)  # fmt: skip
_PHRASES = st.lists(_WORDS, min_size=1, max_size=3).map(lambda ws: '"' + " ".join(ws) + '"')
_LEAVES = st.one_of(
    _WORDS,
    _WORDS,
    _PHRASES,
    _WORDS.map(lambda w: f"title:{w}"),
    _WORDS.map(lambda w: f"-{w}"),
    st.sampled_from(["year:2024", "venue:ICLR", "source:PMLR", 'source:"ICML"', "track:(main OR workshop)"]),
)
# tight separators put several words in one unspaced run, where a second `$` would close LaTeX math
_SEPARATORS = st.sampled_from([" ", " ", " | ", "|", "|", " OR ", " AND ", ")(", ")|(", ") (", " NEAR/2 "])


@st.composite
def hostile_queries(draw: st.DrawFn) -> str:
    parts = draw(st.lists(_LEAVES, min_size=1, max_size=6))
    out = parts[0]
    for p in parts[1:]:
        out += draw(_SEPARATORS) + p
    return f"({out})" if draw(st.booleans()) else out


# mostly words that take a `$`, glued together: the runs where an edit needs its space
_TIGHT = st.lists(
    st.sampled_from(
        ["trust", "LLM", "model", "agent", "gpt-4", "AI", "bench*", "model$", "US$5", '"trust in AI"']
    ),
    min_size=2,
    max_size=5,
).flatmap(lambda ws: st.sampled_from(["|", ")|(", ")("]).map(lambda sep: "(" + sep.join(ws) + ")"))


@given(st.one_of(hostile_queries(), _TIGHT, queries()))
def test_offered_edits_are_sound_on_generated_queries(q: str) -> None:
    result = parse(q, "scholar")
    if result.errors:
        event("does not parse")
        assert word_forms(q, result) is None
        return
    forms = check_edits(q)
    assert result.ast is not None
    # the rules alone decide what is offered: the read-back refuses nothing they allow, short of the length cap
    allowed = [form for form, _ in wordforms._candidates(q, result.ast, result)]
    if forms != allowed:
        event("over the length cap once edited")
        assert [e.code for e in parse(apply(q, allowed), "scholar").errors] == [DiagnosticCode.PARSE_TOO_LONG]
    named = len(exact_leaves(result.ast))  # type: ignore[arg-type]
    event(
        "every named term offered" if len(forms) == named else "none offered" if not forms else "some offered"
    )
    event(f"spaced inserts: {min(sum(f.insert == '$ ' for f in forms), 2)}")
