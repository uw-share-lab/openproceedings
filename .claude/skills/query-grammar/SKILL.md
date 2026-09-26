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
| A WORD that normalizes to 0 tokens | Error with a span (e.g. a bare `--`). Verify the exact code at implementation time. |
| Phrases and `NEAR/n` | One field only; never across title and abstract. |
| Ranges | `year:2020..2026` inclusive; start > end is an error. |

## Fields
(none) → title OR abstract · `title:` · `abstract:` · `venue:` (NeurIPS, ICLR, ICML; case-insensitive, exact) ·
`year:` · `track:` (01 taxonomy; unknown value → error listing valid values) · `status:` · `source:`
(compat alias, see `.claude/skills/scholar-syntax-compat/SKILL.md`). Anything else before `:` → unknown-field error.

## AST
Discriminated union (pydantic v2): `Or, And, Not, Term, Phrase, Near, Wildcard, Filter`. Every node keeps
its source span so diagnostics and the UI parse tree point at the input.

## Canonical form
`canonical` is: fully parenthesised, uppercase operators (`|` → `OR`, juxtaposition → `AND`, `-` → `NOT`),
default filters made explicit (`.claude/skills/default-filters/SKILL.md`), filters sorted, wildcards kept
**unexpanded** (`benchmark*`, not its expansion — the expansion belongs to an `index_version`).
Pick one deterministic filter order and one spelling per value (e.g. `venue:NeurIPS`), record it as a
Backlog.md decision (`backlog decision create`, `.claude/skills/decision-records/SKILL.md`), and pin it
with snapshot tests.

**Idempotence (property-tested):** `parse(canonical).canonical == canonical`, and AST → string → AST is the
identity. A change that alters any existing canonical string changes every saved record's hash: treat it as
a breaking change with a decision record.

`canonical_hash = sha256(canonical + TOKENIZER_VERSION)`.

## Diagnostics
`{code, message, span:[start,end]}` in `warnings`, `errors` (non-empty ⇒ no search) or `translations`.
Every error carries a fix hint: unbalanced parens, empty group, short wildcard stem, unknown field, unknown
`track:` value, reversed range, all-negative query. Random garbage yields errors, never exceptions.
