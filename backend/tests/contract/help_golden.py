"""The data behind `/help/syntax` (TASK-045; spec 05 §Pages, design `2026-09-27-coverage-and-syntax-help.md`):
generated from the parser, the token golden table and spec 02, never written by hand.

`build()` returns what `frontend/src/help/syntax-golden.json` must hold, and
`test_frontend_help_golden.py` fails while the committed file differs, so a changed message, rule, limit or
golden row turns a test red until the file is regenerated:

    PYTHONPATH=backend uv run python -m tests.contract.help_golden

What is written by hand here is only the choice of examples (their inputs, modes and fixes); everything
they say (each diagnostic's message and code, the tokens, the canonical forms, the limits, the
vocabularies, the default filters and spec 02's consequences table) is computed or read from its source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openproceedings.api.config import ApiConfig
from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.engine.protocol import MAX_EXPANSIONS, EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import MAX_YEAR, MIN_YEAR, Wildcard
from openproceedings.query.clauses import MAX_YEAR_RANGES
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.lexer import MAX_NEAR, MIN_STEM
from openproceedings.query.normalize import normalize
from openproceedings.query.parser import MAX_DEPTH, MAX_QUERY_LENGTH, Mode, parse
from openproceedings.vocab import STATUSES, TEXT_FIELDS, TRACKS, VENUES

from tests.golden.test_tokens import GOLDEN as TOKEN_GOLDEN

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "src" / "help" / "syntax-golden.json"
SPEC_02 = REPO / "docs" / "specs" / "02-query-language.md"

# The rows of the token golden table the Matching section shows (each must be a row of `test_tokens.GOLDEN`)
TOKEN_ROWS = (
    "Benchmarking LLMs",
    "LLM-as-a-judge",
    "Vision–Language",
    "naïve Bayes",
    "GPT-4o",
    "model's",
    "$\\epsilon$-DP",
    "\\textit{TrustLLM}",
    "ﬁne-tuning",
    "Straße",
    "trust in AI",
    "Llama 3.1 70B",
)

# Examples per section: (query, mode). Each parses without errors in its mode.
SECTIONS: dict[str, tuple[tuple[str, Mode], ...]] = {
    "matching": (("benchmark", "native"), ("benchmark$", "native"), ("LLM*", "native")),
    "phrases": (('"trust in AI"', "native"), ('"large language model$"', "native")),
    "operators": (
        ("trust AND reliance", "native"),
        ("trust reliance", "native"),
        ("trust OR reliance", "native"),
        ("trust NOT distrust", "native"),
        ("trust -distrust", "native"),
        ("(trust OR reliance) AND (LLM OR agent*)", "native"),
    ),
    "wildcards": (
        ("bench*", "native"),
        ("model$", "native"),
        ('"generative AI$"', "native"),
        ("gpt-4*", "native"),
    ),
    "near": (("trust NEAR/3 calibration", "native"), ('"language model" NEAR/5 judge*', "native")),
    "fields": (
        ("title:benchmark", "native"),
        ('abstract:"human evaluation"', "native"),
        ("title:(trust OR reliance)", "native"),
    ),
    "filters": (
        ("trust venue:ICLR", "native"),
        ("trust year:2020..2024", "native"),
        ("trust year:(2020 OR 2024..2026)", "native"),
        ("trust track:(main OR workshop)", "native"),
        ("trust status:(accepted OR withdrawn)", "native"),
        ("trust NOT venue:ICML", "native"),
    ),
    "defaults": (
        ("trust", "native"),
        ("trust track:workshop", "native"),
        ("trust status:rejected", "native"),
    ),
    "scholar": (
        ('source:PMLR "large language model"', "scholar"),
        ("(large language model$ | LLM) trust", "scholar"),
        ("trust", "scholar"),
    ),
}

# Messages (A–Z): one or more per reader-facing code: (code, example, mode, fix or None, display or None).
# `display` stands in for an example too long to show; such an example gets no search link.
DEEP = "(" * (MAX_DEPTH + 1) + "trust" + ")" * (MAX_DEPTH + 1)
LONG = "x" * (MAX_QUERY_LENGTH + 1)
MESSAGES: tuple[tuple[DiagnosticCode, str, Mode, str | None, str | None], ...] = (
    (DiagnosticCode.PARSE_UNBALANCED_PAREN, "(trust OR reliance", "native", "(trust OR reliance)", None),
    (DiagnosticCode.PARSE_EMPTY_GROUP, "trust ()", "native", "trust", None),
    (DiagnosticCode.PARSE_ALL_NEGATIVE, "NOT workshop", "native", "trust NOT workshop", None),
    (DiagnosticCode.PARSE_UNTERMINATED_PHRASE, '"large language', "native", '"large language"', None),
    (DiagnosticCode.PARSE_BAD_NEAR, "trust NEAR/x model", "native", "trust NEAR/3 model", None),
    (DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX, "tr*st", "native", "trust", None),
    (DiagnosticCode.PARSE_EXPECTED_TERM, "trust OR", "native", "trust OR reliance", None),
    (DiagnosticCode.PARSE_EMPTY_TERM, "trust ~ bias", "native", "trust -bias", None),
    (
        DiagnosticCode.PARSE_NESTED_FIELD,
        "title:(abstract:trust)",
        "native",
        "title:trust abstract:trust",
        None,
    ),
    (DiagnosticCode.PARSE_TOO_DEEP, DEEP, "native", "trust", f"{MAX_DEPTH + 1} nested ( … ) around trust"),
    (DiagnosticCode.PARSE_WILDCARD_DETACHED, "abcd.*", "native", "abcd*", None),
    (DiagnosticCode.PARSE_AMBIGUOUS_MINUS, "trust -", "native", "trust -bias", None),
    (DiagnosticCode.PARSE_STRAY_COLON, "trust : model", "native", "title:trust", None),
    (DiagnosticCode.PARSE_AMBIGUOUS_QUOTE, 'trust "in "AI"', "native", '"trust in AI"', None),
    (DiagnosticCode.PARSE_PAREN_TOUCHES_WORD, "model(s)", "native", "model$", None),
    (DiagnosticCode.PARSE_TOO_LONG, LONG, "native", None, f"x repeated {MAX_QUERY_LENGTH + 1:,} times"),
    (DiagnosticCode.WILDCARD_STEM_TOO_SHORT, "be*", "native", "bench*", None),
    (DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS, "tru*", "native", "trustworth*", None),
    (DiagnosticCode.FIELD_UNKNOWN, "author:smith", "native", '"author smith"', None),
    (DiagnosticCode.FIELD_UNKNOWN_VALUE, "trust track:poster", "native", "trust track:main", None),
    (DiagnosticCode.FIELD_UNKNOWN_VALUE, "trust year:20x", "native", "trust year:2020..2026", None),
    (DiagnosticCode.FIELD_RANGE_INVERTED, "trust year:2026..2020", "native", "trust year:2020..2026", None),
    (
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        "trust venue:(ICLR AND ICML)",
        "native",
        "trust venue:(ICLR OR ICML)",
        None,
    ),
    (DiagnosticCode.FIELD_COMPAT_ONLY, "trust source:PMLR", "native", "trust venue:ICML", None),
    (DiagnosticCode.WARN_LOWERCASE_OPERATOR, "trust or reliance", "native", "trust OR reliance", None),
    (DiagnosticCode.WARN_MIXED_AND_OR, "trust AND LLM OR agent", "native", "trust AND (LLM OR agent)", None),
    (
        DiagnosticCode.WARN_NESTED_FILTER,
        "(track:workshop AND trust) OR reliance",
        "native",
        "(trust OR reliance) track:workshop",
        None,
    ),
    (DiagnosticCode.WARN_FILTER_SCOPE, "source:ICLR OR PMLR", "scholar", "source:(ICLR OR PMLR)", None),
    (DiagnosticCode.WARN_LOOKALIKE_OPERATOR, "trust −bias", "native", "trust -bias", None),
    (DiagnosticCode.WARN_LOOKALIKE_OPERATOR, "trust ‘AI’", "native", 'trust "AI"', None),
    (DiagnosticCode.WARN_SYMBOLS_DROPPED, "C++", "native", None, None),
    (DiagnosticCode.WARN_SOURCE_PARTIAL, "trust source:PMLR", "scholar", "trust venue:ICML", None),
    (DiagnosticCode.WARN_CJK_RUN, "大语言模型", "native", "大语言模型*", None),
    (DiagnosticCode.WARN_SPELLED_GREEK, "alpha test", "native", "(alpha OR α) test", None),
    (DiagnosticCode.COMPAT_SOURCE_ALIAS, "trust source:PMLR", "scholar", None, None),
    (DiagnosticCode.COMPAT_POP_DOLLAR, "model$", "scholar", None, None),
    (DiagnosticCode.COMPAT_POP_PHRASE, "(large language model | LLM)", "scholar", None, None),
    (DiagnosticCode.COMPAT_NO_STEMMING, "trust", "scholar", "trust$", None),
)
# said beside a message whose text depends on the index it ran on
NOTES = {
    DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS: (
        "The count in the message is the index's own; this one comes from a small example index."
    ),
}
# the two API codes a reader meets as a refused query: explained together, in the slow-clauses section
SLOW_CLAUSES = (DiagnosticCode.API_TOO_MANY_VERIFIED_CLAUSES, DiagnosticCode.API_QUERY_TOO_COSTLY)
READER_PREFIXES = ("PARSE_", "FIELD_", "WILDCARD_", "WARN_", "COMPAT_")


def reader_facing() -> set[str]:
    """Every code a reader can meet in the UI: the query diagnostics and the two slow-clause refusals."""
    return {c.value for c in DiagnosticCode if c.startswith(READER_PREFIXES)} | {
        c.value for c in SLOW_CLAUSES
    }


class _Doc:
    """A record for the reference engine (its `Searchable` shape)."""

    def __init__(self, i: int, title: str) -> None:
        self.id, self.title, self.abstract = f"d{i}", title, None
        self.venue, self.year, self.track, self.status = "ICLR", 2024, "main", "accepted"


def _too_many(example: str) -> Diagnostic:
    """The engine's message for a stem with more than MAX_EXPANSIONS words, over a corpus of MAX_EXPANSIONS + 1
    words that start with the stem (the count in a real message is the index's own)."""
    result = parse(example)
    assert result.ast is not None and isinstance(result.ast, Wildcard), example
    stem = result.ast.stem
    words = [stem + "".join(chr(97 + (i // 26**k) % 26) for k in range(2)) for i in range(MAX_EXPANSIONS + 1)]
    engine = ReferenceEngine([_Doc(i, w) for i, w in enumerate(words)])
    try:
        engine.expand(result.ast)
    except EngineInputError as e:  # the registry code and message the API's 422 carries
        return Diagnostic(code=e.code, message=e.message)
    raise AssertionError(f"{example} expanded within the cap")


def _diagnostic(code: DiagnosticCode, example: str, mode: Mode) -> Diagnostic:
    if code is DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS:
        return _too_many(example)
    result = parse(example, mode)
    found = [d for d in (*result.errors, *result.warnings, *result.translations) if d.code is code]
    assert found, (
        f"{example!r} ({mode}) gives no {code}: {[d.code for d in (*result.errors, *result.warnings)]}"
    )
    return found[0]


def _kind(code: DiagnosticCode) -> str:
    if code.startswith("WARN_"):
        return "warning"
    if code.startswith("COMPAT_"):
        return "translation"
    return "error"


def consequences() -> list[dict[str, str]]:
    """Spec 02 §Token semantics' consequences table (query | matches | does not match), read from the spec."""
    section = SPEC_02.read_text(encoding="utf-8").split("Consequences, which are also golden tests:", 1)[1]
    rows = []
    for line in section.split("\n## ", 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith("`"):
            rows.append({"query": cells[0].strip("`"), "matches": cells[1], "not": cells[2]})
    assert rows, "spec 02's consequences table was not found"
    return rows


def _example(q: str, mode: Mode) -> dict[str, Any]:
    result = parse(q, mode)
    assert not result.errors, f"{q!r} ({mode}): {[e.code for e in result.errors]}"
    return {"q": q, "mode": mode, "canonical": result.canonical}


def build() -> dict[str, Any]:
    golden = dict(TOKEN_GOLDEN)
    tokens = []
    for text in TOKEN_ROWS:
        assert text in golden and normalize(text) == golden[text], text
        tokens.append({"input": text, "tokens": golden[text]})
    messages = []
    for code, example, mode, fix, display in MESSAGES:
        d = _diagnostic(code, example, mode)
        if fix is not None:
            fixed = parse(fix, mode)
            assert not fixed.errors and code not in {w.code for w in fixed.warnings}, (code, fix)
        messages.append(
            {
                "code": code.value,
                "kind": _kind(code),
                "mode": mode,
                "example": example if display is None else None,
                "display": display,
                "message": d.message,
                "fix": fix,
                "note": NOTES.get(code),
            }
        )
    messages.sort(key=lambda m: m["code"])  # A–Z; a code's examples keep their order (a stable sort)
    config = ApiConfig.model_fields
    return {
        "_comment": (
            "Generated by backend/tests/contract/help_golden.py (PYTHONPATH=backend uv run python -m "
            "tests.contract.help_golden); never edit by hand. test_frontend_help_golden.py fails while it differs "
            "from what the parser, the token goldens and spec 02 say. Read by frontend/src/app/help/syntax."
        ),
        "constants": {
            "min_wildcard_stem": MIN_STEM,
            "max_expansions": MAX_EXPANSIONS,
            "max_near": MAX_NEAR,
            "min_year": MIN_YEAR,
            "max_year": MAX_YEAR,
            "max_year_ranges": MAX_YEAR_RANGES,
            "max_query_length": MAX_QUERY_LENGTH,
            "max_query_depth": MAX_DEPTH,
            "max_verified_clauses": config["max_verified_clauses"].default,
            "max_verification_candidates": config["max_verification_candidates"].default,
        },
        "text_fields": list(TEXT_FIELDS),
        "values": {"venue": list(VENUES.values()), "track": list(TRACKS), "status": list(STATUSES)},
        "defaults": [
            {"field": field, "values": list(values), "canonical": _clause(field, values)}
            for field, values in DEFAULT_CLAUSES.items()
        ],
        "tokens": tokens,
        "consequences": consequences(),
        "sections": {
            name: [_example(q, mode) for q, mode in examples] for name, examples in SECTIONS.items()
        },
        "messages": messages,
        "slow_clauses": [c.value for c in SLOW_CLAUSES],
    }


def _clause(field: str, values: tuple[str, ...]) -> str:
    """The default clause as the canonical form writes it: the top-level `AND` conjunct of a bare query's
    canonical string that names `field`."""
    canonical = parse("x").canonical
    assert canonical is not None and canonical.startswith("(") and canonical.endswith(")")
    parts, depth, begin = [], 0, 0
    inner = canonical[1:-1]
    for i, ch in enumerate(inner):
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and inner.startswith(" AND ", i):
            parts.append(inner[begin:i])
            begin = i + len(" AND ")
    parts.append(inner[begin:])
    [clause] = [p for p in parts if p.startswith(f"{field}:")]
    assert all(v in clause for v in values), clause
    return clause


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    sys.stdout.write(f"wrote {OUT.relative_to(REPO)}\n")
