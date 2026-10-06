"""Where `$` can be added to the terms the no-stemming notice names (TASK-175; spec 02 §Word forms).

`query.wordforms.word_forms` reports the edits the UI's "Add `$`" action makes. The table pins what is offered
and what is left alone (a phrase's inner words, filter and `source:` values, terms with a wildcard, stems too
short, symbols after the word, LaTeX in the run); the properties check that every offered edit, alone and all
together, parses to the same query with exactly those terms made `$` wildcards.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from itertools import combinations, pairwise, product
from pathlib import Path
from typing import Any

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode, verbatim
from openproceedings.query import wordforms
from openproceedings.query.ast import Phrase, Term, Wildcard, structure
from openproceedings.query.exact import exact_leaves, exact_name
from openproceedings.query.lexer import OPERATOR_WORDS
from openproceedings.query.parser import MAX_QUERY_LENGTH, ParseResult, parse
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
    ("lowercase operator word", "trust and model", "trust$ and model$"),
    ("lowercase operator word ending a Scholar | item", "x | trust and", "x | trust$ and"),
    ("lowercase not after a Scholar | item", "trust | model not", "trust$ | model$ not"),
    ("lowercase operator word inside a | item", "a | trust and model", "a | trust$ and model$"),
    (
        "operator words in any case or width, and near/n",
        "trust And model ｏｒ agent near/3 judge",
        "trust$ And model$ ｏｒ agent$ near/3 judge$",
    ),
    ("an operator word ends a quoted phrase", '"supply and" "to be or not"', '"supply and$" "to be or not$"'),
    ("near alone is a word", "trust near model", "trust$ near$ model$"),
    ("zero-width space after the word", "trust\u200b model", "trust\u200b$ model$"),
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


# (name, query, each named term not offered, with its reason, in the notice's order)
SKIPPED: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("stem under 3 letters or digits", 'AI "a b" trust', [("ai", "too_short"), ("a b", "too_short")]),
    ("a symbol where the $ would go", 'C++ trust? "what is trust?"', [("c", "symbol"), ("trust", "symbol"),
     ("what is trust", "symbol")]),
    ("another $ or a backslash in the run", 'US$5 $f(x)$-DP (model$|LLM) G\\"odel',
     [("us 5", "dollar_nearby"), ("f x dp", "dollar_nearby"), ("llm", "dollar_nearby"),
      ("godel", "dollar_nearby")]),
    ("a lowercase operator word", "trust and model not", [("and", "operator_word"), ("not", "operator_word")]),
    ("every term offered", "trust model", []),
    ("a term offered in one place is not skipped", "AI trust (US$5 OR trust)", [("ai", "too_short"),
     ("us 5", "dollar_nearby")]),
]  # fmt: skip


@pytest.mark.parametrize(("q", "skipped"), [c[1:] for c in SKIPPED], ids=[c[0] for c in SKIPPED])
def test_each_named_term_left_as_typed_says_why(q: str, skipped: list[tuple[str, str]]) -> None:
    report = wordforms.report(q, scholar(q))
    assert report is not None
    assert [(s.term, s.reason) for s in report.skipped] == skipped
    assert report.forms == forms_of(q)


def test_no_report_with_errors_and_an_empty_one_outside_scholar_mode() -> None:
    assert wordforms.report("(trust", parse("(trust", "scholar")) is None
    assert wordforms.report("AI trust", parse("AI trust")) == wordforms.Report(forms=[], skipped=[])


def term_subsets(forms: list[WordForm]) -> list[list[WordForm]]:
    """What a reader can tick: whole terms, each in every place it is written. Every subset when there are at
    most 6 terms, else each term alone, all but one, and all."""
    terms = list(dict.fromkeys(f.term for f in forms))
    if len(terms) <= MAX_SUBSET_FORMS:
        picks = [set(c) for r in range(1, len(terms) + 1) for c in combinations(terms, r)]
    else:
        picks = [{t} for t in terms] + [set(terms) - {t} for t in terms] + [set(terms)]
    return [[f for f in forms if f.term in pick] for pick in picks]


def check_fits(q: str, *, exact: bool = True) -> wordforms.Report:
    """Near the cap: every subset of the offered terms a reader can tick parses (under the cap, raw and
    canonical), and, when `exact` (no term's `$` shortens the canonical form here), each term named as too
    long would put the query, or its canonical form, over the cap if added to all the offered ones."""
    result = scholar(q)
    report = wordforms.report(q, result)
    assert report is not None
    for chosen in term_subsets(report.forms):
        assert parse(apply(q, chosen), "scholar").errors == [], [f.term for f in chosen]
    assert result.ast is not None
    allowed = [form for form, _ in wordforms._candidates(q, result.ast, result)]
    for skipped in (s for s in report.skipped if s.reason == "too_long" and exact):
        more = [*report.forms, *(f for f in allowed if f.term == skipped.term)]
        assert [e.code for e in parse(apply(q, more), "scholar").errors] == [DiagnosticCode.PARSE_TOO_LONG]
    return report


def canonical_at(head: str, tail: str, length: int) -> str:
    """`head (aa OR ab OR … OR a OR b …) tail` whose canonical form is exactly `length` code points: the padding's
    words have under 3 letters, so none takes a `$`, and each is its own term."""
    pairs = [x + y for x in "abcdefghijklmnopqrstuvwxyz" for y in "abcdefghijklmnopqrstuvwxyz"]
    base = len(parse(f"{head} (aa) {tail}", "scholar").canonical or "")
    for n in range(max(1, (length - base) // 6 - 2), len(pairs)):
        for singles in range(6):  # " OR aa" is 6 code points and " OR a" 5, so every length is reached
            q = f"{head} ({' OR '.join(pairs[:n] + list('vwxyz'[:singles]))}) {tail}"
            result = parse(q, "scholar")
            if not result.errors and len(result.canonical or "") == length:
                return q
    raise AssertionError(f"no padding gives a canonical form of {length}")


def test_one_terms_savings_never_pay_for_another() -> None:
    """`trust$` dedupes `trust OR trust$` (7 code points shorter), and `"and"` loses its quotes (1 shorter): with
    every `$` the query would fit, but a reader may tick any subset, and the ones without those terms must fit
    too. So each term is budgeted at one code point per place from the query as typed (review of TASK-192)."""
    q = canonical_at("(trust OR trust$)", "zebra wolf lynx moose otter", MAX_QUERY_LENGTH - 2)
    assert parse(apply(q, forms_of_all(q)), "scholar").errors == []  # every `$` at once would fit
    report = check_fits(q, exact=False)
    assert [f.term for f in report.forms] == ["trust", "zebra"]
    too_long = [s.term for s in report.skipped if s.reason == "too_long"]
    assert too_long == ["wolf", "lynx", "moose", "otter"]

    q = canonical_at('"and"', "zebra", MAX_QUERY_LENGTH)
    assert parse(apply(q, forms_of_all(q)), "scholar").errors == []  # `and$` pays for `zebra$`
    report = check_fits(q, exact=False)
    assert report.forms == []
    assert [s.term for s in report.skipped if s.reason == "too_long"] == ["and", "zebra"]


def forms_of_all(q: str) -> list[WordForm]:
    """Every edit the rules allow, before any budget."""
    result = scholar(q)
    assert result.ast is not None
    return [form for form, _ in wordforms._candidates(q, result.ast, result)]


def test_near_the_cap_the_terms_that_fit_are_offered_and_the_rest_named() -> None:
    """The query is under the cap, but its canonical form has room for 30 more characters: the first 30 terms
    in the order they are written get their `$`, and every later one is named as too long."""
    words = [f"term{i:03d}" for i in range(300)]
    q = " OR ".join(words)
    while parse(q, "scholar").errors or len(scholar(q).canonical or "") > MAX_QUERY_LENGTH - 30:
        words.pop()
        q = " OR ".join(words)
    room = MAX_QUERY_LENGTH - len(scholar(q).canonical or "")
    report = check_fits(q)
    assert [f.term for f in report.forms] == words[:room]
    assert [(s.term, s.reason) for s in report.skipped] == [(w, "too_long") for w in words[room:]]


def padded(tail: str, spare: int) -> str:
    """`abc OR abc OR … tail`, padded with spaces to `spare` code points under the cap. `abc` is written in
    hundreds of places, so it never fits: the canonical form, which dedupes it, stays short, and the raw cap
    is the one that binds."""
    head = " OR ".join(["abc"] * ((MAX_QUERY_LENGTH - spare - len(tail)) // 7))
    q = head + " " * (MAX_QUERY_LENGTH - spare - len(tail) - len(head)) + tail
    assert len(q) == MAX_QUERY_LENGTH - spare and len(scholar(q).canonical or "") < MAX_QUERY_LENGTH // 2
    return q


def test_near_the_cap_a_term_written_in_many_places_is_skipped_whole_and_a_later_one_offered() -> None:
    """`abc` has no room for its `$` in every place, so it is named as too long; the terms after it still fit,
    one character each, and are offered until the room runs out."""
    report = check_fits(padded(" OR model OR agent OR judge", 2))
    assert [f.term for f in report.forms] == ["model", "agent"]
    assert [(s.term, s.reason) for s in report.skipped] == [("abc", "too_long"), ("judge", "too_long")]


def test_near_the_cap_the_spaced_insert_of_a_skipped_neighbour_is_not_counted() -> None:
    """`(model|LLM)` takes `$ ` and `$` when both are offered; with room for two characters, `model$` (a bare
    `$`, since `LLM` is not offered) and `trust$` fit, and `LLM` does not."""
    report = check_fits(padded(" OR (model|LLM) OR trust", 2))
    assert [(f.term, f.insert) for f in report.forms] == [("model", "$"), ("trust", "$")]
    assert [(s.term, s.reason) for s in report.skipped] == [("abc", "too_long"), ("llm", "too_long")]


def test_every_term_offered_is_one_the_notice_names() -> None:
    q = TRUST_EVALS["main-2-pop"]
    result = scholar(q)
    [note] = [t for t in result.translations if t.code is DiagnosticCode.COMPAT_NO_STEMMING]
    named = {exact_name(leaf) for leaf in exact_leaves(result.ast)}  # type: ignore[arg-type]
    assert {f.term for f in forms_of(q)} == named  # every one of this string's exact terms takes a `$`
    assert all(f"`{t}`" in note.message for t in list(dict.fromkeys(f.term for f in forms_of(q)))[:8])


def test_a_lowercase_operator_keeps_its_warning_and_its_reading() -> None:
    """`and$` would no longer be warned about, and in Scholar mode would join a phrase: it is never offered."""
    q = "trust and model"
    assert [f.term for f in forms_of(q)] == ["trust", "model"]
    edited = scholar(apply(q, forms_of(q)))
    assert [
        (w.code, w.span) for w in edited.warnings if w.code is DiagnosticCode.WARN_LOWERCASE_OPERATOR
    ] == [(DiagnosticCode.WARN_LOWERCASE_OPERATOR, (7, 10))]
    assert [w.code for w in scholar(q).warnings] == [w.code for w in edited.warnings]
    # the three strings the read-back used to refuse whole (no parse error, nothing offered)
    assert apply("trust | LLM and", forms_of("trust | LLM and")) == "trust$ | LLM$ and"
    assert apply("trust | model not", forms_of("trust | model not")) == "trust$ | model$ not"
    assert apply("a | trust and model", forms_of("a | trust and model")) == "a | trust$ and model$"


def check_example(example: str, term: str) -> None:
    """The notice's example reads, in both modes, as `term` made a `$` wildcard (a phrase's last word): the
    very thing "Add `$`" writes for it, not merely something that parses."""
    for mode in ("native", "scholar"):
        alone = parse(example, mode)  # type: ignore[arg-type]
        assert alone.errors == [] and alone.ast is not None, (example, mode, alone.errors)
        items = alone.ast.items if isinstance(alone.ast, Phrase) else (alone.ast,)
        last = items[-1]
        assert isinstance(last, Wildcard) and last.op == "$", (example, mode)
        assert all(isinstance(i, Term) for i in items[:-1])
        assert " ".join([*(i.token for i in items[:-1] if isinstance(i, Term)), last.stem]) == term


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


MAX_SUBSET_FORMS = 6  # every combination of up to this many forms: at most 57 parses on top of the singles


def check_edits(q: str) -> list[WordForm]:
    """Every subset of the offered edits (each alone, all together, and every combination of the first
    `MAX_SUBSET_FORMS`: what ticking terms can apply) parses to `q`'s tree with exactly those exact terms
    made `$` wildcards: nothing else in the query is read differently."""
    before = scholar(q)
    assert before.ast is not None
    forms = word_forms(q, before)
    assert forms is not None
    tree = structure(before.ast)
    names = Counter(exact_name(leaf) for leaf in exact_leaves(before.ast))
    assert [f.at for f in forms] == sorted({f.at for f in forms})  # in order, one per place
    few = forms[:MAX_SUBSET_FORMS]
    subsets = [list(c) for r in range(2, len(few) + 1) for c in combinations(few, r)]
    for chosen in [*([f] for f in forms), *subsets, forms]:
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
     "model$", 'G\\"odel', "a\\$b", "＄y＄", "𝒜𝒜𝒜", "and", "or", "not", "And",
     "near/3", "2024", "naïve", "大语言模型", "x×y", "~"]
)  # fmt: skip
_PHRASES = st.lists(st.one_of(_WORDS, st.sampled_from(["and", "or", "not"])), min_size=1, max_size=3).map(
    lambda ws: '"' + " ".join(ws) + '"'
)
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
@example("trust | LLM and")  # `and$` joined `LLM$` in a phrase, so the read-back refused every edit
@example("trust | model not")
@example("a | trust and model")
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
    # the notice's example (TASK-181) is the first of them, written so that it parses alone, or there is none
    [note] = [t for t in result.translations if t.code is DiagnosticCode.COMPAT_NO_STEMMING] or [None]
    example = None if note is None else re.search(r"\(e\.g\. `([^`]*)`\)\.$", note.message)
    quotable = [
        f.term
        for f in allowed
        if verbatim(f.term) and len(f.term) + 1 + 2 * (" " in f.term or f.term in OPERATOR_WORDS) <= 40
    ]  # a message quotes at most 40 characters, and only text it need not escape
    if example is not None:
        event("the notice has an example")
        check_example(example.group(1), quotable[0])
    elif note is not None:
        assert quotable == []
    report = wordforms.report(q, result)
    assert report is not None and report.forms == forms
    if forms != allowed:
        event("over the length budget once edited")
        assert {f.term for f in allowed} - {f.term for f in forms} <= {
            s.term for s in report.skipped if s.reason == "too_long"
        }
    # every term the notice names is offered or named as left as typed, once, with a reason
    named_terms = list(dict.fromkeys(exact_name(leaf) for leaf in exact_leaves(result.ast)))
    offered = list(dict.fromkeys(f.term for f in forms))
    skipped = [s.term for s in report.skipped]
    assert sorted(offered + skipped) == sorted(named_terms)
    assert skipped == [t for t in named_terms if t in set(skipped)]  # in the notice's order
    assert "unconfirmed" not in {s.reason for s in report.skipped}  # the rules name every refusal
    named = len(exact_leaves(result.ast))  # type: ignore[arg-type]
    event(
        "every named term offered" if len(forms) == named else "none offered" if not forms else "some offered"
    )
    event(f"spaced inserts: {min(sum(f.insert == '$ ' for f in forms), 2)}")


def test_a_term_refused_in_another_place_is_budgeted_by_its_own_change() -> None:
    """`trust? OR trust` is deduped to `trust`; `trust$` in the one place that takes it makes the two differ, so
    the canonical form grows by more than one: that term's change is rendered and budgeted, so near the cap it
    is named as too long while `zebra`, one code point, still fits."""
    q = canonical_at("(trust? OR trust)", "zebra", MAX_QUERY_LENGTH - 2)
    report = check_fits(q, exact=False)
    assert [f.term for f in report.forms] == ["zebra"]
    assert [s.term for s in report.skipped if s.reason == "too_long"] == ["trust"]
    trust = [f for f in forms_of_all(q) if f.term == "trust"]
    assert [e.code for e in parse(apply(q, trust), "scholar").errors] == [DiagnosticCode.PARSE_TOO_LONG]
    small = "trust? OR trust"  # what one place's `$` does to the canonical form: more than one code point
    assert (
        len(scholar(apply(small, forms_of(small))).canonical or "") > len(scholar(small).canonical or "") + 1
    )


def hostile_near_cap() -> dict[str, str]:
    """Near-cap queries that make the most budget work: many distinct terms, one term in many places, and
    many terms the rules refuse in another place (each would need its own canonical rendering)."""
    words = ["".join(p) for p in product("abcdefghijklmnopqrstuvwxyz", repeat=3)]

    def fill(units: list[str], sep: str) -> str:
        out: list[str] = []
        for unit in units:
            if len(sep.join([*out, unit])) > MAX_QUERY_LENGTH:
                break
            out.append(unit)
        q = sep.join(out)
        while parse(q, "scholar").errors:  # its canonical form over the cap: drop units until it is not
            out.pop()
            q = sep.join(out)
        return q

    return {
        "distinct terms": fill(words, " OR "),
        "tight runs": fill(["(" + "|".join(words[i : i + 20]) + ")" for i in range(0, 4000, 20)], " "),
        "one term in many places": fill(["abc?", "abc"] * 500, " OR "),
        "refused elsewhere, grouped": fill([f"({w}? OR {w})" for w in words], " "),
        "refused elsewhere, in runs": fill([f"{w}?|{w}" for w in words], "|"),
        "refused in different copies": fill(
            [f"(({a} AND {b}) OR ({a}$ AND {b}?) OR ({a}? AND {b}))" for a, b in pairwise(words)],
            " ",
        ),
    }


@pytest.mark.parametrize("name", list(hostile_near_cap()))
def test_word_forms_near_the_cap_stay_cheap(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`POST /parse` is public and runs this as you type: the budget renders the canonical form at most
    twice however many terms the rules refuse elsewhere (review of TASK-192: one rendering
    per such term took 0.9 s), and every subset a reader can tick still fits."""
    q = hostile_near_cap()[name]
    result = scholar(q)
    renders = 0
    real = wordforms.render

    def counted(n: Any) -> str:
        nonlocal renders
        renders += 1
        return real(n)

    monkeypatch.setattr(wordforms, "render", counted)
    assert wordforms.report(q, result) is not None
    assert renders <= 2  # the query undeduped, and one term's own change: never a second term's
    monkeypatch.undo()
    # the rendering count above is the guarantee; this ceiling is only a backstop against a far worse cost than
    # the old one rendering per term (0.9 s on a laptop, now about 30 ms), never against a slow CI runner
    best = min(_timed(lambda: wordforms.report(q, result)) for _ in range(3))
    assert best < 2.0, f"{name}: {best * 1000:.0f} ms"
    check_fits(q, exact=False)


def _timed(f: Any) -> float:
    start = time.perf_counter()
    f()
    return time.perf_counter() - start


def test_terms_refused_elsewhere_share_one_bound_away_from_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Away from the cap, what deduping saved bounds every term refused elsewhere at once: all three are offered
    with one rendering (the query undeduped), not one per term; near the cap the per-term renderings decide."""
    q = "(trust? OR trust) (model? OR model) (agent? OR agent)"
    renders = 0
    real = wordforms.render

    def counted(n: Any) -> str:
        nonlocal renders
        renders += 1
        return real(n)

    monkeypatch.setattr(wordforms, "render", counted)
    report = check_fits(q, exact=False)
    assert [f.term for f in report.forms] == ["trust", "model", "agent"]
    assert renders == 1


# two terms each refused in a different copy of a deduped subtree: alone, each leaves two copies equal; ticked
# together they split it into three, more than both their own changes (review round 2 of TASK-192)
SPLIT = "((trust AND model) OR (trust$ AND model?) OR (trust? AND model))"
SAVERS = "(zebrazebrazebra OR zebrazebrazebra$) (otterotterotter OR otterotterotter$)"


def test_two_terms_refused_in_different_copies_are_not_both_budgeted_by_their_own_change() -> None:
    """Rendered alone, `trust$` and `model$` each cost little; ticked together they cost far more. Only one
    term is budgeted by its own rendering, so near the cap the second is named as too long, unless what
    deduping saved fits and covers both, rather than offered with a pair that would not fit."""
    alone = {t: len(scholar(apply(SPLIT, [f for f in forms_of_all(SPLIT) if f.term == t])).canonical or "")
             for t in ("trust", "model")}  # fmt: skip
    both = len(scholar(apply(SPLIT, forms_of_all(SPLIT))).canonical or "")
    base = len(scholar(SPLIT).canonical or "")
    assert both - base > sum(n - base for n in alone.values()) + 2  # not additive
    checked = 0
    for spare in range(4, 40):  # where both would have been offered (17 of these, before the fix)
        try:
            q = canonical_at(f"{SPLIT} {SAVERS}", "", MAX_QUERY_LENGTH - spare)
        except AssertionError:  # a length the padding can't reach
            continue
        check_fits(q, exact=False)  # every tickable subset, `trust` and `model` alone among them, fits
        checked += 1
    assert checked >= 10


def test_a_rendered_terms_saving_pays_for_no_other_term() -> None:
    """`trust` is refused in one place (`trust?`) and dedupes away in another (`trust OR trust$`): its own
    change is negative, and is counted as nothing, so the terms after it get no room it would free. (`xy OR
    xy` deduping saves more than the room left, so `trust` is budgeted by its own rendering.)"""
    head = "(trust OR trust$) (trust? AND judge) (xy OR xy)"
    report = check_fits(canonical_at(head, "zebra wolf lynx moose otter", MAX_QUERY_LENGTH - 3), exact=False)
    assert [f.term for f in report.forms] == ["trust", "judge", "zebra"]
