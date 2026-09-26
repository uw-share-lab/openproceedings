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
2. Fold marks that only decorate a word: NFD, drop combining marks (canonical combining class ≠ 0)
   whose base character's Unicode name begins with LATIN, GREEK, CYRILLIC, HEBREW, ARABIC or EXTENDED
   ARABIC, or which is an ASCII digit, then recompose with NFC. (By name, so Coptic, IPA and phonetic letters
   follow their script: IPA `ɓ` is Latin and folds; Coptic `ϣ` does not.) So `naïve` ≡ `naive`, `ά` ≡ `α`, and Hebrew and Arabic vowel points fold (`שָׁלוֹם` ≡ `שלום`). Marks
   that spell a *different letter* are kept: Cyrillic breve (`мой` ≠ `мои`), Arabic hamza (`سؤال`), Thai
   tone marks (`ป่า` "forest" ≠ `ปา` "throw"), kana voicing (`が` ≠ `か`), and Indic viramas and vowel
   signs. A stray mark with no base letter is dropped, and a run made only of marks (a lone vowel sign) is not a
   token.
3. LaTeX, by classifying characters (so raw offsets survive):
   - `\cmd{X}` → `X`; a bare `\cmd` outside math is dropped.
   - Math regions are `$…$` (Pandoc's rule: the opening `$` is followed by a non-space, the closing `$` is
     preceded by a non-space and not followed by a digit, so `$5` and `US$ 5` are currency), `$$…$$`,
     `\(…\)` and `\[…\]`. Inside math a command name is a word (`$\epsilon$-DP` → `epsilon dp`).
   - `\%`, `\&`, `\$`, `\\` are separators; `\$` never opens math.
   - Accent macros join the word: `G\"odel`, `G\"{o}del`, `Erd\H{o}s`, `na\"{\i}ve` → `godel`, `erdos`, `naive`
     (BibTeX's dotless `{\i}`/`{\j}` inside an accent is the letter). `\-` (the
     discretionary hyphen) joins: `bench\-mark` → `benchmark`.
   - Full-width `＄` and `＼` are ordinary text, not LaTeX.
4. Split on anything that is not a letter, digit or (non-combining) mark. `vision-language` → `vision`
   `language` at consecutive positions. `GPT-4o` → `gpt` `4o`. `model's` → `model` `s`. Invisible
   characters **join** rather than split: all format characters (Cf: soft hyphen, zero-width
   space/joiner/non-joiner, direction marks, BOM), variation selectors (`❤️`, `葛󠄀`), enclosing marks
   (keycaps: `1️⃣` → `1`) and the combining grapheme joiner. The invisible math operators U+2061–2064
   (function application, times, separator, plus) **separate**.
5. **Nothing else.** No stemming, no lemmatization, no stopword removal, no synonyms, no spelling
   correction.

`tokenize(text)` returns each token with the half-open code-point span of the **raw** text it came from
(spec 04 §Conventions); `normalize(text)` is just the token strings. One raw character can yield two
tokens that share its span (`½` → `1`, `2`). The full case list is `backend/tests/golden/test_tokens.py`.

### Known limits (state these in a methods section when they matter)

- **CJK has no word segmentation.** A run of Chinese, Japanese or Korean characters is one token, so
  `信頼` does not match inside `信頼性`. Search the whole run, or use a wildcard (`信頼*`).
- **Hebrew and Arabic vowel points fold**, so a vocalised and an unvocalised spelling match each other.
  That is intended (points are optional in normal writing), but it is a fold, not an exact match.
- **Latin, Greek and Cyrillic accents fold** (`resume` ≡ `résumé`), as in every mainstream search engine.

Everything else is exact: a token matches only the identical normalised token. The corpus is
overwhelmingly English, so these limits rarely bite, but a review of non-English titles should say so.

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
  stem before `*` **or** `$` must be at least 3 characters. Every wildcard is expanded against the index's
  term dictionary. The expansion list is returned to the user. More than 200 expansions (per wildcard) is
  an error that suggests a longer stem.
- **A wildcard inside a phrase** is allowed and expanded per position: `"large language model$"` matches
  the phrase with `model` or `models` last (the Trust-Evals strings rely on this).
- **A wildcard stem that normalises to several tokens** becomes a phrase whose last token carries the
  wildcard: `gpt-4*` ≡ `"gpt 4*"`. The 3-character minimum counts the letters and digits of the whole stem
  after normalisation, and inside a phrase the earlier words count too (`gpt-4*`, `"gpt 4*"` and
  `"generative AI$"` pass; `a-b*` and `"a b*"` have 2 and fail);
  the 200-expansion cap still applies to the last token's expansions (`4*`), and exceeding it is the
  usual "use a longer stem" error. (Decision-001 records rules 1–3 of this list.)
- **Phrases** keep word order and adjacency within **one field**. A phrase never spans the title and the
  abstract.
- **Lexical details** (`query/lexer.py`; the module docstring is the full list). Nothing in a query is
  silently reinterpreted: every ambiguous spelling is an error or a warning.
  - Double quotes delimit phrases: `"`, `“ ”`, `„ ‟`. A backslash keeps the next character in the word
    (`G\"odel`). Characters whose NFKC form is a syntax character (full-width `（ ）｜：－＊＂`, …) act as
    it, because the tokenizer applies NFKC too; super/subscript parentheses are notation, not grouping.
  - `-` is `NOT` when it starts a primary (after whitespace, `(`, `|` or a field's `:`) and touches what
    it excludes. A word that starts with `-` anywhere else (`a - b`, `"x"-based`, `--x`) is
    `PARSE_AMBIGUOUS_MINUS`. A word starting with a look-alike dash (`−bias`, `–bias`) or a single quote
    is searched as written with `WARN_LOOKALIKE_OPERATOR`.
  - A field is a letter, then letters/digits/underscores, then `:`; names are case-insensitive, so an
    unknown one (`intitle:`, `título:`) is an error rather than a silent search. `title: trust` is fine;
    `title :trust` is `PARSE_STRAY_COLON`. `source:` is Scholar syntax: in native mode it is
    `FIELD_COMPAT_ONLY` (Scholar mode translates it to `venue:`).
  - Wildcards: `*` or `$` at the end of a word, directly after a letter or digit (`vision-*` is
    `PARSE_WILDCARD_DETACHED`). A `*` or `$` elsewhere (`behavio$r`, `model$*`) is
    `PARSE_WILDCARD_NOT_SUFFIX`, except inside LaTeX math (found exactly as the tokenizer finds it, so
    `$f(x)$-DP` is one word) and a `$` before a digit (currency, `US$5`).
  - A bare uppercase `NEAR` between terms is `PARSE_BAD_NEAR` (Web of Science reads it as `NEAR/15`);
    `NEAR/n` takes n ≤ 100.
  - A word whose trailing `+`/`#` the tokenizer drops (`C++` → `c`) raises `WARN_SYMBOLS_DROPPED`.
- `NEAR/n` works within one field, is unordered, and allows at most n intervening words. Tantivy's slop
  semantics are documented in 03 and must agree with the reference matcher. Its two operands are words,
  wildcards or phrases (not groups or filters) in the same field, and `NEAR` does not chain
  (`a NEAR/3 b NEAR/2 c` is an error; join pairs with `AND`).
- `title:`/`abstract:` apply to every term in what follows (`title:(a OR b)`); a different text field
  nested inside (`title:(abstract:x)`) is an error. Filters may appear anywhere, including inside a text
  field's group.
- A filter takes one value or an `OR` group of values of that field only (`venue:(NeurIPS OR ICLR)`);
  `AND`, `NOT` or juxtaposition inside a filter group is an error, and values take no wildcards. Values are
  checked against `backend/src/openproceedings/vocab.py` (spec 01's vocabularies) and are case-insensitive;
  `venue:` values take their canonical spelling (`neurips` → `NeurIPS`).
- Groups and `NOT`s nest at most 64 deep (`PARSE_TOO_DEEP`).
- `year:` values are four-digit years (1000–9999). A bare value OR-joined to a filter of its field
  (`year:2023 OR 2024`, `venue:ICLR OR NeurIPS`) is searched as text, as written, and raises
  `WARN_FILTER_SCOPE` suggesting `year:(2023 OR 2024)`.
- `NOT NOT a` means `a`, so it is not all-negative. A one-word group counts as a word for `NEAR`.
- One mistake gives one error: an error already reported inside a span suppresses follow-on errors there,
  while separate mistakes are each reported.

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
- **As built** (`query/defaults.py`). "Top-level" is judged on the canonical tree, so `(a track:x) b` has
  `track:x` at the top level. A top-level `NOT track:x` is the user's own track clause and also suppresses
  the default. A default-equal clause is the default only when it is the **only** top-level clause of its
  field (the parser would not add a default next to `track:workshop`, so a typed default-equal clause
  there is the user's). `ParseResult.ast` is the tree as typed; `effective_ast` is the canonical tree with
  the defaults (inserted ones have the zero-width span `(len(q), len(q))`), which the engine runs;
  `defaults` names the fields whose top-level clause is the default, for the exclusion buckets.
  `identification_query` is `""` when the query was nothing but defaults (every record). If a query's only
  positive clause was a default (`status:accepted NOT track:workshop`), `identification_query` is
  all-negative (`NOT track:workshop`): a well-defined set the engine counts from the tree, but not a
  string that parses on its own. Records reproduce it by replaying `canonical`.

## Compatibility input modes

The review's existing strings must work **unchanged** or come back with a precise explanation:
- **Scholar/PoP mode** (`parse(q, "scholar")`, `query/compat.py`): accepts `OR` / `|`, `source:` and
  quoted phrases. PoP's `$` is interpreted as the WoS zero-or-one wildcard, and the parser says so in a
  notice (`COMPAT_POP_DOLLAR`). `source:` values translate through an exact alias table (never a
  substring match; every value in the review's 17 corpus exports is covered) to `venue:`, with a
  `COMPAT_SOURCE_ALIAS` notice each; PMLR also raises `WARN_SOURCE_PARTIAL`; an unknown value is an error.
  An OR of sources collapses to one `venue:(…)` clause. **Decision-002:** a run of two or more
  juxtaposed unquoted words forming one `|`/`OR` item is a phrase (`(large language model$ | LLM)` →
  `("large language model$" OR llm)`, `COMPAT_POP_PHRASE`), as the review intended; Google Scholar itself
  binds `|` tighter. The output is native: the canonical string re-parses in native mode unchanged.
- The parser returns `translations[]`, for example: "`source:PMLR` → `venue:ICML` (PMLR also hosts other
  venues; only ICML is indexed)."

Fixture (snapshots in `backend/tests/golden/trust_evals_canonical.json`; the review's primary string is
`main-7-most-updated`): every string in the Trust-Evals protocol (`backend/tests/fixtures/queries/trust-evals.txt`: the
seven variants of the main string, the last marked "Most Updated", plus the narrow, human-centred and
LLM-as-judge strings) parses without errors, and its canonical form is snapshot-tested.

## Outputs

```python
parse(q: str, mode="native"|"scholar") -> ParseResult
ParseResult = {
  ast: Node,                 # discriminated union: Or, And, Not, Term, Phrase, Near, Wildcard, Filter
  canonical: str,            # fully parenthesised, uppercase operators, defaults made explicit, sorted filters
                             #   (top-level filters ordered venue, year, track, status, then others
                             #   alphabetically; values in a single-field OR group sorted)
  warnings: [Diagnostic],    # {code, message, span:[start,end]}
  errors: [Diagnostic],      # non-empty ⇒ no search
  translations: [Diagnostic],
}
```

`canonical` is deterministic: `parse(canonical).canonical == canonical`. That idempotence is tested with
property tests. `canonical_hash = sha256(canonical + "\0" + TOKENIZER_VERSION + "\0" + QUERY_VERSION)` (decision-003):
NUL separators keep the parts apart, and a query-semantics bump changes the hash. `canonical` and `canonical_hash` are None when there are errors.

Canonical form (`query/canonical.py`) is a normal form: nested `AND`/`OR` are flattened; in every `AND`,
text conjuncts keep their written order and filter conjuncts follow in the decision-001 order (a
positive filter before a negated one of the same field); an `OR` of filters on one field becomes one
filter (in any OR, at the first one's position); values are sorted and deduplicated, and overlapping or
adjacent year ranges merge; duplicate conjuncts and disjuncts are dropped; `NOT NOT x` is `x`; OR branches
keep their written order; a bare term that a sibling filter's field could read as a value is quoted
(`venue:ICLR OR "neurips"`); every text leaf carries its field prefix
(`title:(a OR b)` → `(title:a OR title:b)`). A wildcard whose last token is shorter than the stem
minimum is hyphen-joined to the tokens before it (`gpt-4*` → `"gpt-4*"`). Semantically equal spellings
(`trust venue:ICLR`, `venue:iclr Trust`) therefore share one hash. `QUERY_VERSION`
(`openproceedings.query`) is `"1"`.

## Error handling

Every error has a span and a fix hint: unbalanced parentheses, an empty group, a wildcard stem that is too
short or not at the end of a word, an unterminated phrase, `NEAR/` without a whole-number distance or
with a bad operand, a missing operand (`a OR`), a word or phrase with no letters or digits (`a - b`), a
nested text field, a malformed filter group, nesting deeper than 64, an ambiguous `-`, a stray `:`, a
detached or mid-word wildcard, `source:` outside Scholar mode, an unknown field, an unknown filter value
(listing the valid ones), a range with start > end, or an all-negative query. The codes are in
`diagnostics.py`.

## Testing

- The golden token table above, plus about 100 or more normalization cases (Unicode dashes, ligatures, LaTeX, digits).
- The Trust-Evals strings as snapshot fixtures.
- Hypothesis property tests: canonical round-trips, AST → string → AST is the identity, and random
  garbage never crashes the parser (it gives errors, not exceptions).
