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
  alone): the lexer's own conditions (`_Lexer.check_stem`, restated in `exact.takes_dollar`);
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
its canonical form, being over the length cap. `test_wordforms.py` holds them to that (a generated query whose
candidates are refused for any other reason fails it; that is how the operator-word rule was found) and checks
every subset of the edits a reader can tick, not only all of them.

Not part of `parse` (as `clauses.filter_clauses` is not): the edited string is work `/search` and replay do
not need. `POST /parse` serves it as `word_forms`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from openproceedings.query.ast import And, Leaf, Near, Node, Not, Or, Phrase, Term, Wildcard, structure
from openproceedings.query.compat import group_phrases
from openproceedings.query.exact import dollar_places
from openproceedings.query.lexer import lex
from openproceedings.query.parser import ParseResult, parse


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


def _candidates(q: str, ast: Node, result: ParseResult) -> list[tuple[WordForm, int]]:
    """Each edit the rules allow (`exact.dollar_places`), in order, with the end of the leaf it rewrites: not
    yet read back."""
    tokenizer = result.tokenizer_version
    lexemes, _, _ = group_phrases(q, lex(q, tokenizer).lexemes, tokenizer)
    places = dollar_places(q, ast, lexemes, tokenizer)
    return [
        (
            WordForm(
                term=place.term,
                at=place.at,
                insert="$ " if i + 1 < len(places) and places[i + 1].run == place.run else "$",
            ),
            place.leaf_end,
        )
        for i, place in enumerate(places)
    ]


def word_forms(q: str, result: ParseResult) -> list[WordForm] | None:
    """Each place a `$` can be added to a term the no-stemming notice names, in order. None exactly when
    `result` has errors; empty outside Scholar mode (no notice), and when the edits can't be made."""
    ast = result.ast
    if ast is None:
        return None
    if result.mode != "scholar":
        return []
    candidates = _candidates(q, ast, result)
    forms = [form for form, _ in candidates]
    if not forms:
        return []
    edited = parse(apply(q, forms), result.mode, result.tokenizer_version)
    expected = _with_dollar(ast, frozenset(end for _, end in candidates))
    if edited.ast is None or structure(edited.ast) != structure(expected):
        return []
    return forms
