"""The editor's highlighter reads tokens exactly as the server's lexer does (TASK-041; codemirror-lezer skill).

Two files under `frontend/src/editor/lang/` are generated from `query/lexer.py`:
- `lexer-tables.json`: the lexer's character classes (quotes and their closers, the NFKC look-alikes of `( ) | : - * $`,
  the field names, Python's `str.isspace` set and the non-`Nd` characters `str.isdigit` accepts), which
  `frontend/src/editor/lang/lex.ts` imports instead of restating, so the two sides cannot drift;
- `lexer-golden.json`: every lexer and parser golden input, every error and warning input, the Trust-Evals strings and
  some probes, each with the lexemes `lex()` returns as `[kind, start, end]` in code points. The frontend's
  `grammar.test.ts` runs the Lezer parser over each `q` and requires the same token classes at the same spans.

This test fails when either file is stale. Regenerate it with
`(cd backend && uv run python -m tests.contract.test_frontend_lexer_golden --write)` and commit it.
"""

from __future__ import annotations

import json
import random
import sys
import unicodedata
from pathlib import Path
from typing import Any

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query import lexer
from openproceedings.query.lexer import Kind, lex
from openproceedings.query.normalize import ACCENT_LETTERS, ACCENT_SYMBOLS

from tests.unit import test_lexer, test_parser

ROOT = Path(__file__).resolve().parents[3]
LANG = ROOT / "frontend" / "src" / "editor" / "lang"
GOLDEN = LANG / "lexer-golden.json"
TABLES = LANG / "lexer-tables.json"
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "queries"

# Inputs no backend list has yet, aimed at the highlighter's harder paths (math, escapes, look-alikes, astral).
PROBES = [
    "trust* NEAR/5 calibrat*",
    '"large language model$" AND (benchmark OR leaderboard) year:2023..2026',
    "𝐱 trust* 😀 model$ year:2020..2026",
    "$f(x)$ OR $$a|b$$ OR \\(x)\\) OR $5 US$5 model$ $x$*",
    "a$b$ c $ x$ $x $ $x$y",
    '"unterminated phrase (with) OR stuff',
    'a"b c" "d"e title:"x"',
    "author:smith intitle:x Title:X TRACK:main",
    "NEAR/101 NEAR/x NEAR/0003 NEAR NEAR/3",
    "trust -bias - x --y (-a) a|-b title:-x",
    "ａ ＯＲ ｂ （c） ｜ d：e －f ＊ ＂g＂",
    'G\\"odel na\\"{\\i}ve Erd\\H{o}s \\alpha{}-x bench\\-mark',
    "model(s) (a)b «x» »y« 「z」 『w』 〝v〞 ″u″",
    "a b c　d e\x1cf",
    "2020..2026 2020.. ..2026 20x",
    "trust\\ calibration \\",
]


# Random strings over the characters the lexer treats specially (a fixed seed, so the file is stable): the
# hand-written inputs can't reach every interleaving of quotes, math, escapes and parentheses.
_ALPHABET = [
    *'ab1 ()|:-*$"\\«»「」“”（）｜：－＊＄＂',
    "AND",
    "OR",
    "NOT",
    "NEAR/3",
    "title:",
    "x:",
    "20..21",
    "𝐱",
]


def _random_queries(n: int = 400) -> list[str]:
    rng = random.Random(41)
    return ["".join(rng.choice(_ALPHABET) for _ in range(rng.randint(1, 14))) for _ in range(n)]


def _kind(q: str, x: lexer.Lexeme) -> str:
    if x.kind is Kind.WORD:
        return "WILDCARD" if x.wildcard else "WORD"
    if x.kind is Kind.FIELD:
        return "FIELD" if x.field in lexer.FIELDS else "UNKNOWN_FIELD"
    if x.kind is Kind.OR and x.text in lexer.PIPES:
        return "PIPE"
    if x.kind is Kind.NOT and x.text in lexer.MINUSES:
        return "MINUS"
    return x.kind.value


def tokens(q: str) -> list[list[Any]]:
    """The lexemes as `[kind, start, end]`, plus `BAD_NEAR` where the lexer dropped a malformed `NEAR/…`
    (it emits no lexeme there, only PARSE_BAD_NEAR), so every non-space character is covered."""
    result = lex(q)
    out: list[list[Any]] = [[_kind(q, x), x.start, x.end] for x in result.lexemes]
    covered = {(x.start, x.end) for x in result.lexemes}
    for e in result.errors:
        if e.code is DiagnosticCode.PARSE_BAD_NEAR and e.span is not None and e.span not in covered:
            out.append(["BAD_NEAR", *e.span])
    return sorted(out, key=lambda t: (t[1], t[2]))


def _queries() -> list[str]:
    lines = (FIXTURES / "trust-evals.txt").read_text(encoding="utf-8").split("\n")
    trust = [line for line in lines if line.strip() and not line.startswith(("#", "## "))]
    found = [
        *(q for q, _ in test_lexer.GOLDEN),
        *(q for q, *_ in test_lexer.ERRORS),
        *(q for q, *_ in test_lexer.WARNINGS),
        *(q for q, _ in test_parser.GOLDEN),
        *(q for q, *_ in test_parser.ERRORS),
        *trust,
        *PROBES,
        *_random_queries(),
    ]
    seen: set[str] = set()
    return [q for q in found if not (q in seen or seen.add(q))]


def _chars(pred: Any) -> str:
    return "".join(chr(c) for c in range(sys.maxunicode + 1) if pred(chr(c)))


GENERATED = (
    "by (cd backend && uv run python -m tests.contract.test_frontend_lexer_golden --write); do not edit"
)


def build_tables() -> dict[str, Any]:
    return {
        "_generated": GENERATED,
        "quotes": "".join(sorted(lexer.QUOTES)),
        "closers": {k: "".join(sorted(v)) for k, v in sorted(lexer.CLOSERS.items())},
        "lparens": "".join(sorted(lexer.LPARENS)),
        "rparens": "".join(sorted(lexer.RPARENS)),
        "pipes": "".join(sorted(lexer.PIPES)),
        "colons": "".join(sorted(lexer.COLONS)),
        "minuses": "".join(sorted(lexer.MINUSES)),
        "stars": "".join(sorted(lexer.STARS)),
        "dollars": "".join(sorted(lexer.DOLLARS)),
        "fields": list(lexer.FIELDS),
        "max_near": lexer.MAX_NEAR,
        "accent_symbols": "".join(sorted(ACCENT_SYMBOLS)),
        "accent_letters": "".join(sorted(ACCENT_LETTERS)),
        "space": _chars(str.isspace),
        "digit_not_nd": _chars(lambda c: c.isdigit() and unicodedata.category(c) != "Nd"),
    }


def build_golden() -> dict[str, Any]:
    return {"_generated": GENERATED, "cases": [{"q": q, "tokens": tokens(q)} for q in _queries()]}


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def test_the_frontend_lexer_files_are_current() -> None:
    for path, data in ((TABLES, build_tables()), (GOLDEN, build_golden())):
        assert path.read_text(encoding="utf-8") == render(data), (
            f"{path.relative_to(ROOT)} is stale: run "
            "`(cd backend && uv run python -m tests.contract.test_frontend_lexer_golden --write)` and commit it"
        )


def test_every_case_covers_each_non_space_character() -> None:
    """No gap the highlighter would have to guess about: tokens never overlap, and every non-space character
    is in one (a space may be inside a phrase or LaTeX math)."""
    for case in build_golden()["cases"]:
        q = case["q"]
        seen = [0] * len(q)
        for _, start, end in case["tokens"]:
            for k in range(start, end):
                seen[k] += 1
        assert all(n <= 1 for n in seen), q
        assert all(n == 1 for n, c in zip(seen, q, strict=True) if not c.isspace()), q


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        sys.exit("usage: test_frontend_lexer_golden.py --write")
    for path, data in ((TABLES, build_tables()), (GOLDEN, build_golden())):
        path.write_text(render(data), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
