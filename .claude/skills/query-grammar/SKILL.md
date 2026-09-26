---
name: query-grammar
description: The openproceedings query grammar (spec 02) — the EBNF, uppercase-only operators, NOT > AND > OR precedence with the mixed-level warning, the all-negative error, the field list, the AST node set, canonical-form rules with the idempotence property, and canonical_hash. Use when writing or reviewing lexer.py, parser.py, ast.py or canonical.py, when deciding what a query string means, or when a canonical string or hash changes.
---

# Query grammar (spec 02 §Grammar, §Outputs, §Error handling)

## EBNF (authoritative copy is spec 02)
```
query      = or_expr ;
or_expr    = and_expr , { ( "OR" | "|" ) , and_expr } ;
and_expr   = not_expr , { [ "AND" ] , not_expr } ;          (* juxtaposition = AND *)
not_expr   = [ "NOT" | "-" ] , primary ;
primary    = "(" , or_expr , ")" | near | field_term | term ;
near       = operand , "NEAR/" , INT , operand ;
field_term = FIELD , ":" , ( term | "(" , or_expr , ")" | range ) ;
term       = PHRASE | WORD ;                                  (* WORD may contain * or $ *)
range      = INT , ".." , INT ;
FIELD      = "title" | "abstract" | "venue" | "year" | "track" | "status" | "source" ;
```
Code: `backend/src/openproceedings/query/{lexer,parser,ast,canonical}.py`.

## Rules that bite
| Rule | Consequence |
|---|---|
| Operators are **uppercase only** | `and`/`or`/`not` are search terms. Lowercase `or` between terms → warning "did you mean OR?", still searched as a term. |
| Precedence `NOT` > `AND` > `OR` | `a b OR c` is `(a AND b) OR c`. |
| Mixed `AND`/`OR` at one level without parens | Parse by precedence **and** warn. Juxtaposition counts as `AND`, so `trust calibration OR reliance` warns. Scholar strings hit this constantly. |
| All-negative query (`NOT x`, `-x` alone) | Error: nothing to subtract from. |
| `-` is negation only at the start of a primary | `vision-language` is one WORD that normalizes to `vision` `language` (a two-token term, matched at consecutive positions). `-bias` after whitespace/`(` is `NOT bias`. |
| A WORD that normalizes to >1 token | Behaves as a phrase of those tokens in one field (golden: `vision-language` matches "vision language", not "visionlanguage"). |
| Wildcard stem length | `*` and `$` both need a written stem of ≥ 3 characters (`a$` → error). The letters and digits of the whole stem count after normalisation, so `gpt-4*` passes and `a-b*` fails. A `*` elsewhere in a word → `PARSE_WILDCARD_NOT_SUFFIX`; a trailing `$` that closes a `$…$` pair is math, not a wildcard. More than 200 expansions of one wildcard → error suggesting a longer stem. |
| Wildcard inside a phrase | Allowed, expanded per position: `"large language model$"` is a `Phrase` whose last element is a `Wildcard`. |
| A wildcard WORD that normalizes to >1 token | A phrase with the wildcard on its last token: `gpt-4*` ≡ `"gpt 4*"`. |
| A WORD that normalizes to 0 tokens | `PARSE_EMPTY_TERM` with a span (`a ~ b`); a bare `-`/`--` is `PARSE_AMBIGUOUS_MINUS` instead. |
| Phrases and `NEAR/n` | One field only; never across title and abstract. |
| Nothing silently reinterpreted | `a - b`, `"x"-based`, `--x` → `PARSE_AMBIGUOUS_MINUS`; `behavio$r` → `PARSE_WILDCARD_NOT_SUFFIX`; `vision-*` → `PARSE_WILDCARD_DETACHED`; bare `NEAR` → `PARSE_BAD_NEAR`; `year:2023 OR 2024` → `WARN_FILTER_SCOPE`; `C++` → `WARN_SYMBOLS_DROPPED`; NFKC look-alikes (`（`, `－`, `＂`) act as syntax. Spec 02 §Grammar lists them all. |
| Lexing (`lexer.py`) | `"`, `“ ”`, `„ ‟`, `＂`, `« »`, `「 」`, `『 』` delimit phrases, each closing only with its own family (`"“”„‟＂` are one family; `« »`, `「 」`, `『 』` pair with themselves); unterminated → `PARSE_UNTERMINATED_PHRASE`, a quote touching a word outside → `PARSE_AMBIGUOUS_QUOTE`, `model(s)` → `PARSE_PAREN_TOUCHES_WORD`; `\` keeps the next char in the word; field names are case-insensitive; `NEAR/` without a number → `PARSE_BAD_NEAR`. |
| Ranges | `year:2020..2026` inclusive; start > end is an error. |

## Fields
(none) → title OR abstract · `title:` · `abstract:` · `venue:` (NeurIPS, ICLR, ICML; case-insensitive, exact) ·
`year:` · `track:` (01 taxonomy; unknown value → error listing valid values) · `status:` · `source:`
(compat alias, see `.claude/skills/scholar-syntax-compat/SKILL.md`). Anything else before `:` → unknown-field error.

## AST
Discriminated union (pydantic v2, `query/ast.py`): `Or, And, Not, Term, Phrase, Near, Wildcard, Filter`.
Every node keeps its source span (groups include their parentheses and field prefix) so diagnostics and
the UI parse tree point at the input. Text leaves carry `field` (`title`/`abstract`/None); there is no
field node. `Term.token` and `Wildcard.stem` are single normalised tokens; a multi-token word is a
`Phrase`. `Filter.values` holds canonical strings, or `YearRange`s for `year`. `parse()` (`query/parser.py`)
returns `ast=None` exactly when `errors` is non-empty, never raises (property-tested: 2k examples in CI,
50k nightly), and reports one error per mistake, sorted by position. `Phrase` and `Near` carry the field;
`structure(node)` compares meaning without spans; validators enforce every invariant (`test_ast.py`).

## Canonical form
`canonical` (`query/canonical.py`, spec 02 §Outputs) is: flattened, fully parenthesised, uppercase operators (`|` → `OR`, juxtaposition → `AND`, `-` → `NOT`),
default filters made explicit (`.claude/skills/default-filters/SKILL.md`), wildcards kept
**unexpanded** (`benchmark*`, not its expansion — the expansion belongs to an `index_version`).
Top-level filters are ordered `venue`, `year`, `track`, `status`, then any other field alphabetically; the
values in a single-field OR group are sorted; one spelling per value (e.g. `venue:NeurIPS`). Decision-001
records this; snapshot tests pin it.

**Idempotence (property-tested):** `parse(canonical).canonical == canonical`, and AST → string → AST is the
identity. A change that alters any existing canonical string changes every saved record's hash: treat it as
a breaking change with a decision record.

`canonical_hash = sha256(canonical + "\0" + TOKENIZER_VERSION + "\0" + QUERY_VERSION)` (decision-003).

## Diagnostics
`{code, message, span:[start,end]}` in `warnings`, `errors` (non-empty ⇒ no search) or `translations`.
Every error carries a fix hint: unbalanced parens, empty group, short wildcard stem, unknown field, unknown
`track:` value, reversed range, all-negative query. Random garbage yields errors, never exceptions.
