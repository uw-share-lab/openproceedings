# 02 — Query language

Status: **draft for review** · depends on: nothing · consumed by: 03, 04, 05

## Purpose

Define **exactly** what a query string means. The parser turns a string into a typed AST, rejects anything
ambiguous with a positioned error, and produces a **canonical string**. The canonical string is what search
records hash and replay. This spec is the contract for guarantees 1, 3 and 6.

## Token semantics (shared with the index tokenizer, 03)

The query side and the index side run the **same** normalization function (`normalize.py`, versioned as
`TOKENIZER_VERSION`):

1. Unicode NFKC, then case-fold (`LLM` ≡ `llm`).
2. Fold diacritics (`naïve` ≡ `naive`): NFD, drop combining marks, recompose with NFC. This changes
   characters, not words, so it is not stemming. It also removes combining marks in other scripts (the
   Devanagari virama), identically on the query and index side.
3. LaTeX: `\cmd{X}` → `X`, and a bare `\cmd` outside math is dropped. Inside math `$…$`, command names
   are words (`$\epsilon$-DP` → `epsilon dp`). `\%`, `\&`, `\$` and `\\` are separators, and `\$`
   never opens math.
4. Split on anything that is not a letter, digit or (non-combining) mark. `vision-language` → `vision`
   `language` at consecutive positions. `GPT-4o` → `gpt` `4o`. `model's` → `model` `s`. Invisible format
   characters (soft hyphen, zero-width space and joiner) join rather than split: `bench\u00admark` →
   `benchmark`.
5. **Nothing else.** No stemming, no lemmatization, no stopword removal, no synonyms, no spelling
   correction.

`tokenize(text)` returns each token with the half-open code-point span of the **raw** text it came from
(spec 04 §Conventions); `normalize(text)` is just the token strings. One raw character can yield two
tokens that share its span (`½` → `1`, `2`). The full case list is `backend/tests/golden/test_tokens.py`.

Consequences, which are also golden tests:

| Query | Matches | Does not match |
|---|---|---|
| `benchmarking` | "benchmarking" | "benchmark", "benchmarks" |
| `trust` | "trust", "Trust", "trust-aware" | "trustworthy", "trustworthiness", "distrust" |
| `LLM` | "LLM", "llm" | "LLMs" (write `LLM$` or `LLM*`) |
| `vision-language` | "vision-language", "vision language", "Vision–Language" | "visionlanguage" |
| `"trust in AI"` | the phrase with "in" kept | "trust AI" |

## Grammar (EBNF)

```
query      = or_expr ;
or_expr    = and_expr , { ( "OR" | "|" ) , and_expr } ;
and_expr   = not_expr , { [ "AND" ] , not_expr } ;          (* juxtaposition = AND *)
not_expr   = [ "NOT" | "-" ] , primary ;
primary    = "(" , or_expr , ")" | near | field_term | term ;
near       = operand , "NEAR/" , INT , operand ;             (* unordered, ≤ INT words apart *)
field_term = FIELD , ":" , ( term | "(" , or_expr , ")" | range ) ;
term       = PHRASE | WORD ;                                  (* WORD may contain * or $ *)
range      = INT , ".." , INT ;
FIELD      = "title" | "abstract" | "venue" | "year" | "track" | "status" | "source" ;
```

Rules:
- **Operators are uppercase only.** `and`, `or` and `not` are ordinary search terms. A lowercase `or`
  between terms produces a warning ("did you mean OR?") but is still searched as a term.
- **Precedence:** `NOT` > `AND` > `OR`. When `AND` and `OR` are mixed at the same level without
  parentheses, the query parses by precedence **and** raises a warning. The UI shows the parsed tree, so
  the user sees how it was read.
- A leading `NOT` or `-` on its own (an all-negative query) is an error. There has to be something to
  subtract from.
- **Wildcards are opt-in and suffix-only:** `benchmark*` means zero or more characters.
  `model$` means zero or one character (Web of Science semantics, so `model$` → model, models). The
  stem before `*` must be at least 3 characters. Every wildcard is expanded against the index's term
  dictionary. The expansion list is returned to the user. More than 200 expansions is an error that
  suggests a longer stem.
- **Phrases** keep word order and adjacency within **one field**. A phrase never spans the title and the
  abstract.
- `NEAR/n` works within one field, is unordered, and allows at most n intervening words. Tantivy's slop
  semantics are documented in 03 and must agree with the reference matcher.

## Fields and filters (guarantee 3: filters live in the query)

| Field | Kind | Values |
|---|---|---|
| (none) | text | title OR abstract |
| `title:` / `abstract:` | text | that field only |
| `venue:` | filter | `NeurIPS`, `ICLR`, `ICML`. Case-insensitive, exact. |
| `year:` | filter | `2024`, `2020..2026` (inclusive) |
| `track:` | filter | 01 taxonomy (`main`, `datasets_benchmarks`, `workshop`, …) |
| `status:` | filter | `accepted`, `rejected`, `withdrawn`, … |
| `source:` | compat | Scholar-style. Mapped to `venue:` through an alias table ("neural information processing systems", "PMLR" → ICML *with a warning* because PMLR hosts other venues). Unknown values are errors, never silent substrings. |

### Default filters

When a query has no **top-level** `track:` clause, the parser adds
`track:(main OR datasets_benchmarks OR position)`. When it has no top-level `status:` clause, it adds
`status:accepted`. Defaults are **made explicit in the canonical string**, so the saved string shows them.
The UI toggles edit these same clauses; they are not a separate state.

- **A default is recognised by its content, not by where it came from.** A top-level AND conjunct that
  exactly equals a default clause is treated as the automated default, whether the parser inserted it,
  the user typed it, or it came from pasting a canonical string back in. So `trust`, its canonical string,
  and a replay of that string all give the same `excluded` (03). Golden cases pin input → canonical →
  re-parse → toggle-off-and-on.
- **Only top-level AND conjuncts suppress a default.** A `track:`/`status:` clause nested inside an `OR`
  branch (`(track:workshop AND x) OR y`) does not suppress it. The parser adds the default anyway and raises
  the warning `WARN_NESTED_FILTER`: "the default track/status filter still applies to the whole query; add
  a top-level `track:`/`status:` clause to override it".
- **Identification string.** `identification_query` is the canonical string with the default conjuncts
  removed. It is what PRISMA's "records identified" count is computed from (03 §Exclusion accounting, 05
  §Save search record). The API returns and search records store both strings.

## Compatibility input modes

The review's existing strings must work **unchanged** or come back with a precise explanation:
- **Scholar/PoP mode:** accepts `OR` / `|`, `source:` and quoted phrases. PoP's `$` is interpreted as the
  WoS zero-or-one wildcard, and the parser says so in a notice.
- The parser returns `translations[]`, for example: "`source:PMLR` → `venue:ICML` (PMLR also hosts other
  venues; only ICML is indexed)."

Fixture: every string in the Trust-Evals protocol (the six variants of the main, narrow,
human-centred and LLM-as-judge strings) parses without errors, and its canonical form is snapshot-tested.

## Outputs

```python
parse(q: str, mode="native"|"scholar") -> ParseResult
ParseResult = {
  ast: Node,                 # discriminated union: Or, And, Not, Term, Phrase, Near, Wildcard, Filter
  canonical: str,            # fully parenthesised, uppercase operators, defaults made explicit, sorted filters
  warnings: [Diagnostic],    # {code, message, span:[start,end]}
  errors: [Diagnostic],      # non-empty ⇒ no search
  translations: [Diagnostic],
}
```

`canonical` is deterministic: `parse(canonical).canonical == canonical`. That idempotence is tested with
property tests. `canonical_hash = sha256(canonical + TOKENIZER_VERSION)`.

## Error handling

Every error has a span and a fix hint: unbalanced parentheses, an empty group, a wildcard stem that is too
short, an unknown field, an unknown `track:` value (listing the valid values), a range with start > end,
or an all-negative query.

## Testing

- The golden token table above, plus about 100 or more normalization cases (Unicode dashes, ligatures, LaTeX, digits).
- The Trust-Evals strings as snapshot fixtures.
- Hypothesis property tests: canonical round-trips, AST → string → AST is the identity, and random
  garbage never crashes the parser (it gives errors, not exceptions).
