"""Where a `$` can be added to the terms the Scholar-mode no-stemming notice names (TASK-175; spec 02 §Word
forms; spec 05 §Components 1).

Google Scholar stems words and openproceedings never does (guarantee 1), so a Scholar string run unchanged
identifies fewer records, and `COMPAT_NO_STEMMING` names the terms matched exactly. The UI offers to write the
notice's own suggestion, `$`, into the query text: an edit of `q` the reader triggers and sees (guarantees 3
and 6), never a change to how a query is matched. The UI must not re-parse the query to find the terms, so the
server reports each place a `$` can go: `at`, a code-point offset in `q`, and `insert`, the text to put there.

A term is offered when the notice names it (`exact.exact_leaves`: a word or phrase with no wildcard, in a
NEAR or under a NOT too) and `$` would be a valid wildcard on it as written:
- a phrase takes the `$` on its **last word** only (`"large language model"` → `"large language model$"`, as
  the review's own strings write it); its inner words are left alone, and a phrase that already holds a
  wildcard is not named by the notice;
- the stem keeps at least `MIN_STEM` letters or digits, counting a phrase's earlier words (`AI` is left
  alone, `"generative AI"` is offered), and the `$` would directly follow a letter or digit (`C++` is left
  alone): the lexer's own conditions (`_Lexer.check_stem`, restated in `exact.stem_refusal`);
- the unspaced run the word sits in (up to whitespace or a quote: where the lexer looks for LaTeX math) holds
  no `$` or backslash already, since a second `$` in a run would close math (`US$5`, `(model$|LLM)`);
- a lowercase operator word (`and`, `or`, `not`, `near/3`) is left alone: the lexer's "did you mean AND?"
  warning and Scholar mode's phrase grouping both go by the word's text, so `and$` would lose the warning and
  could join the words around it into a phrase (`trust | LLM and` → `trust$ | "LLM$ and$"`). Inside a quoted
  phrase it is an ordinary last word (`"supply and"`);
- filter and `source:` values are never offered: they are not terms, and take no wildcards.

The rules themselves are `exact.dollar_places`, below both this module and `parser.py`, so the notice's own
example ("e.g. `trust$`") is always a term offered here (TASK-181).

Two offered words in one unspaced run (`(model|LLM)`) would read as math once both had a `$`
(`(model$|LLM$)`), so every one but the last gets `insert` `"$ "`, the `$` and a space: `(model$ |LLM$)`.
Whitespace there changes nothing else, and with it any subset of the edits is sound, not only all of them.

The answer is then checked by making every edit at once and parsing the result with the parser itself, in the
query's mode: it must parse, and its tree must be the original with exactly those leaves made `$` wildcards.
If it is not, nothing is offered, so an offered edit is always one the server has read back. The rules above
are meant to allow only what the read-back accepts, with one exception they can't see: the edited query, or
its canonical form, being over the length cap; then the terms that fit are offered, and read back. `test_wordforms.py` holds them to that (a generated query whose
candidates are refused for any other reason fails it; that is how the operator-word rule was found) and checks
every subset of the edits a reader can tick, not only all of them.

Near the cap, the terms whose `$` fit are offered and the rest are named with the reason `too_long` (TASK-192;
`_fit` says how they are counted). Every other term the notice names but no place is offered for is named
with the rule that refuses it (`exact.dollar_verdicts`), so the UI can say which terms were left as typed
and why without reading a message.

Not part of `parse` (as `clauses.filter_clauses` is not): the edited string is work `/search` and replay do
not need. `POST /parse` serves `report` as `word_forms` and `word_forms_skipped`.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.ast import And, Leaf, Near, Node, Not, Or, Phrase, Term, Wildcard, structure
from openproceedings.query.compat import group_phrases
from openproceedings.query.exact import Place, SkipReason, dollar_verdicts, exact_leaves, exact_name
from openproceedings.query.lexer import lex
from openproceedings.query.parser import MAX_QUERY_LENGTH, ParseResult, parse


class WordForm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    term: str = Field(
        description="The term as the `COMPAT_NO_STEMMING` notice names it: its normalised tokens, a phrase's "
        "joined by spaces. One term written in several places has one entry per place."
    )
    at: int = Field(
        ge=0,
        description="The code-point offset in `q` to insert at: the end of the word, or of a phrase's last word, "
        "as the lexer ends it, so after any invisible character that joins the word (a zero-width space).",
    )
    insert: str = Field(
        pattern=r"^\$ ?$",
        description="The text to insert at `at`, as it is: `$`, or `$` and a space where another offered word "
        "follows in the same unspaced run (`(model|LLM)`), so that the two `$` are not read as LaTeX math.",
    )


class SkippedTerm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    term: str = Field(
        description="The term as the `COMPAT_NO_STEMMING` notice names it, as in `WordForm.term`."
    )
    reason: SkipReason = Field(
        description="Why it gets no `$` (spec 02 §Word forms): `too_short`, a stem under 3 letters or digits "
        "(`AI`); `symbol`, the `$` would not directly follow a letter or digit (`C++`); `dollar_nearby`, its "
        "unspaced run already holds a `$` or a backslash, so a second `$` would close LaTeX math (`US$5`); "
        "`operator_word`, a lowercase `and`, `or`, `not` or `near/n`, read by its text; `too_long`, its `$` "
        "would put the query, or its canonical form, over the 2,000-code-point cap with the offered ones; "
        "`unconfirmed`, the server could not read the edit back."
    )


def _leaf_with_dollar(n: Leaf, ends: frozenset[int]) -> Leaf:
    if n.span[1] not in ends:
        return n
    if isinstance(n, Term):
        return Wildcard(span=n.span, stem=n.token, op="$", field=n.field)
    last = n.items[-1] if isinstance(n, Phrase) else None
    if not isinstance(n, Phrase) or not isinstance(last, Term):
        return n
    items = (*n.items[:-1], Wildcard(span=last.span, stem=last.token, op="$"))
    return Phrase(span=n.span, items=items, field=n.field)


def _with_dollar(n: Node, ends: frozenset[int]) -> Node:
    """`n` with each exact leaf that ends at one of `ends` made a `$` wildcard (a phrase's last word)."""
    if isinstance(n, Term | Phrase):
        return _leaf_with_dollar(n, ends)
    if isinstance(n, Near):
        left, right = _leaf_with_dollar(n.left, ends), _leaf_with_dollar(n.right, ends)
        return Near(span=n.span, left=left, right=right, distance=n.distance)
    if isinstance(n, Not):
        return Not(span=n.span, child=_with_dollar(n.child, ends))
    if isinstance(n, And | Or):
        return type(n)(span=n.span, children=tuple(_with_dollar(c, ends) for c in n.children))
    return n


def apply(q: str, forms: list[WordForm]) -> str:
    """`q` with every one of `forms` inserted: the edit the UI makes, in code points."""
    out, last = [], 0
    for f in sorted(forms, key=lambda f: f.at):
        out += [q[last : f.at], f.insert]
        last = f.at
    return "".join([*out, q[last:]])


def _spaced(places: list[Place]) -> list[bool]:
    """For `places` (in order of `at`), whether each takes `$ `: every one but the last of an unspaced run."""
    return [i + 1 < len(places) and places[i + 1].run == place.run for i, place in enumerate(places)]


def _forms(places: list[Place]) -> list[WordForm]:
    """The edits for `places` (in order of `at`)."""
    return [
        WordForm(term=place.term, at=place.at, insert="$ " if spaced else "$")
        for place, spaced in zip(places, _spaced(places), strict=True)
    ]


def _candidates(q: str, ast: Node, result: ParseResult) -> list[tuple[WordForm, int]]:
    """Each edit the rules allow (`exact.dollar_verdicts`), in order, with the end of the leaf it rewrites: not
    yet read back."""
    places = _verdicts(q, ast, result)[0]
    return list(zip(_forms(places), (place.leaf_end for place in places), strict=True))


def _verdicts(q: str, ast: Node, result: ParseResult) -> tuple[list[Place], list[tuple[str, SkipReason]]]:
    tokenizer = result.tokenizer_version
    lexemes, _, _ = group_phrases(q, lex(q, tokenizer).lexemes, tokenizer)
    places, refusals = dollar_verdicts(q, ast, lexemes, tokenizer)
    return places, [(r.term, r.reason) for r in refusals]


def _read_back(q: str, result: ParseResult, places: list[Place]) -> tuple[ParseResult, bool]:
    """`q` with `places`' edits made, parsed, and whether its tree is the original with exactly those leaves
    made `$` wildcards."""
    assert result.ast is not None
    edited = parse(apply(q, _forms(places)), result.mode, result.tokenizer_version)
    expected = _with_dollar(result.ast, frozenset(place.leaf_end for place in places))
    return edited, edited.ast is not None and structure(edited.ast) == structure(expected)


MAX_FIT_ROUNDS = 3  # read-backs while fitting terms under the cap; each after the first only adds terms


def _fit(q: str, result: ParseResult, by_term: dict[str, list[Place]]) -> list[Place] | None:
    """Near the cap: the places of the terms whose `$` fit, each term in every place it is written or in none,
    taken in the order the terms are first written; None if a read-back refuses them for another reason.

    The raw length of an edit is exact (`len(q)` plus its inserts, which are recounted for each choice: a word's
    `$ ` is a bare `$` while its neighbour is not chosen). The canonical form is not re-rendered for each term,
    which would cost as much as a parse: a `$` adds at most one code point to it per place (a term that was
    quoted there, `"and"`, or that dedupes with a sibling, adds less), so each round counts one per place
    from the canonical length the last read-back measured, and the next round tries the terms left over
    against that measured length."""
    assert result.canonical is not None
    chosen: list[Place] = []
    canonical = len(result.canonical)
    left = dict(by_term)
    for _ in range(MAX_FIT_ROUNDS):
        added = 0
        for term, places in list(left.items()):
            trial = sorted([*chosen, *places], key=lambda place: place.at)
            raw = len(q) + len(trial) + sum(_spaced(trial))
            if raw <= MAX_QUERY_LENGTH and canonical + added + len(places) <= MAX_QUERY_LENGTH:
                chosen, added = trial, added + len(places)
                del left[term]
        if not added:
            break
        edited, ok = _read_back(q, result, chosen)
        if not ok or edited.canonical is None:
            return None
        canonical = len(edited.canonical)
    return chosen


class Report(NamedTuple):
    """`POST /parse`'s `word_forms` and `word_forms_skipped` for one query."""

    forms: list[WordForm]  # each place a `$` can go, in order of `at`
    skipped: list[SkippedTerm]  # each named term with no place offered, in the notice's order, with why


def report(q: str, result: ParseResult) -> Report | None:
    """Where a `$` can be added to the terms the no-stemming notice names, and why each other named term gets
    none. None exactly when `result` has errors; empty outside Scholar mode (no notice).

    Every edit at once is read back first. When that passes the cap, the terms that fit are offered (`_fit`)
    and the rest are `too_long`; when the read-back refuses the edits for another reason, which the rules are
    meant to make impossible, none is offered and each is `unconfirmed`."""
    ast = result.ast
    if ast is None:
        return None
    if result.mode != "scholar":
        return Report(forms=[], skipped=[])
    places, refusals = _verdicts(q, ast, result)
    by_term: dict[str, list[Place]] = {}
    for place in places:
        by_term.setdefault(place.term, []).append(place)
    why: dict[str, SkipReason] = {}
    chosen: list[Place] | None = places
    edited, ok = _read_back(q, result, places) if places else (result, True)
    if not ok:
        over = [e.code for e in edited.errors] == [DiagnosticCode.PARSE_TOO_LONG]
        chosen = _fit(q, result, by_term) if over else None
        reason: SkipReason = "unconfirmed" if chosen is None else "too_long"
        offered = {place.term for place in chosen or []}
        why = {term: reason for term in by_term if term not in offered}
    for term, reason in refusals:
        if term not in by_term:  # a term offered in one place is not named as skipped for another
            why.setdefault(term, reason)
    named = dict.fromkeys(exact_name(leaf) for leaf in exact_leaves(ast))
    return Report(
        forms=_forms(chosen or []),
        skipped=[SkippedTerm(term=term, reason=why[term]) for term in named if term in why],
    )


def word_forms(q: str, result: ParseResult) -> list[WordForm] | None:
    """Each place a `$` can be added to a term the no-stemming notice names, in order (`report`). None exactly
    when `result` has errors; empty outside Scholar mode (no notice), and when no term can take one."""
    found = report(q, result)
    return None if found is None else found.forms
