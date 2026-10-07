# 02 — Query language

Status: **as-built (2026-09-25, M1)** · depends on: 01 (the venue/track/status vocabularies, `vocab.py`) · consumed by: 03, 04, 05

## Purpose

Define **exactly** what a query string means. The parser turns a string into a typed AST, rejects anything
ambiguous with a positioned error, and produces a **canonical string**. The canonical string is what search
records hash and replay. This spec is the contract for guarantees 1, 3 and 6.

## Token semantics (shared with the index tokenizer, 03)

The query side and the index side run the **same** normalization function (`normalize.py`, versioned as
`TOKENIZER_VERSION`; this is version 3, decision-033). A query is always read with the version its index was
built with: this code serves version 3 and, for the indexes built with it and the search records pinned to them,
version 2 (`SERVED_TOKENIZERS`; 03 §Versioning).

1. Unicode NFKC of the **whole text, before any other step**, then case-fold (`LLM` ≡ `llm`). So a text and its
   NFC, NFD, NFKC and NFKD forms give the same tokens (`Caf\é` is `caf e` with a precomposed `é` or with `e` +
   U+0301). Version 2 applied NFKC one character at a time after step 3 had read the raw text, so an accent
   written as `e` + U+0301 after a backslash read as the command `\e` (dropped).
2. Fold marks that only decorate a word: NFD, drop combining marks (canonical combining class ≠ 0)
   whose base character's Unicode name begins with LATIN, GREEK, CYRILLIC, HEBREW, ARABIC or EXTENDED
   ARABIC, or which is an ASCII digit, then recompose with NFC. (By name, so Coptic, IPA and phonetic letters
   follow their script: IPA `ɓ` is Latin and folds; Coptic `ϣ` does not.) So `naïve` ≡ `naive`, `ά` ≡ `α`, and Hebrew and Arabic vowel points fold (`שָׁלוֹם` ≡ `שלום`). Marks
   that spell a *different letter* are kept: Cyrillic breve (`мой` ≠ `мои`), Arabic hamza (`سؤال`), Thai
   tone marks (`ป่า` "forest" ≠ `ปา` "throw"), kana voicing (`が` ≠ `か`), and Indic viramas and vowel
   signs. A stray combining mark (class ≠ 0) with no base (a letter, digit or class-0 mark before it) is
   dropped. After NFKC, a class-0 Mn/Mc mark that step 4 doesn't make invisible is a word character (e.g.
   U+0CE2 KANNADA VOWEL SIGN VOCALIC L), so a run made only of marks (a lone vowel sign) is not a token on its
   own, but a letter written after it joins it (U+0CE2 + `x` is one word); marks NFKC decomposes into
   combining marks are stray.
3. LaTeX, by classifying characters (so raw offsets survive):
   - `\cmd{X}` → `X`; a bare `\cmd` outside math is dropped.
   - Math regions are `$…$` (Pandoc's rule: the opening `$` is followed by a non-space, the closing `$` is
     preceded by a non-space and not followed by a digit, so `$5` and `US$ 5` are currency), `$$…$$`,
     `\(…\)` and `\[…\]`. Inside math a command name is a word (`$\mathcal{L}$` → `mathcal l`), except
     that math spelled in LaTeX gives the token its Unicode spelling gives (decision-006): a Greek command
     is its letter (`$\epsilon$-DP` → `ε dp`, like `ε-DP`), an operator command its operator's name
     (`$\le$` → `leq`, like `≤`), and `^`/`_` before one letter or digit, or a braced run of them, join
     it (`$O(n^2)$` → `o n2`, like `O(n²)`).
   - `\%`, `\&`, `\$`, `\\` are separators; `\$` never opens math.
   - Accent macros join the word: `G\"odel`, `G\"{o}del`, `Erd\H{o}s`, `na\"{\i}ve` → `godel`, `erdos`, `naive`
     (BibTeX's dotless `{\i}`/`{\j}` inside an accent is the letter). `\-` (the
     discretionary hyphen) joins: `bench\-mark` → `benchmark`.
   - Step 3 reads the NFKC form, so full-width `＄` and `＼` (and small `﹩`, `﹨`) are `$` and `\`, and the Pandoc
     tests see a spacing accent (`´`, NFKC ` ́`) as a space and `½` (`1⁄2`) as a digit. (Version 2: full-width
     `＄` and `＼` were ordinary text.)
4. Split on anything that is not a letter, digit or (non-combining) mark, except that a Unicode operator
   or relation (`×`, `≤`, `→`, `∈`, …; the table is in decision-006) is a token of its own, its LaTeX name
   (`5×3` → `5` `times` `3`). `vision-language` → `vision`
   `language` at consecutive positions. `GPT-4o` → `gpt` `4o`. `model's` → `model` `s`. Invisible
   characters **join** rather than split: all format characters (Cf: soft hyphen, zero-width
   space/joiner/non-joiner, direction marks, BOM), variation selectors (`❤️`, `葛󠄀`), enclosing marks
   (keycaps: `1️⃣` → `1`) and the combining grapheme joiner. The invisible math operators U+2061–2064
   (function application, times, separator, plus) **separate**.
5. **Nothing else.** No stemming, no lemmatization, no stopword removal, no synonyms, no spelling
   correction.

`tokenize(text)` returns each token with the half-open code-point span of the **raw** text it came from
(spec 04 §Conventions); `normalize(text)` is just the token strings. One raw character can yield two
tokens that share its span (`½` → `1`, `2`); two spans overlap only on exactly one code point that folds to
several pieces. In a combining-slash cluster (a character, then marks including U+0338, folded whole) each
piece spans what it came from, so in `x½` + U+0338 + `y` the slash is `2y`'s alone (`x1` spans `x½`), and a
U+0345 that folds to `ι` after an operator starts its own word at its mark (task-075). The one exception: the
pieces before the first raw U+0345 end at it, even if a later mark belongs to them (`=` + U+0345 + U+0338:
`neq` spans only `=`, and the slash is in the `ι` word's span), since two contiguous spans can't split
interleaved marks. Markup before a character that folds to several pieces belongs to its first piece only,
in or out of a slash cluster (`\"⑴`: `1` spans `⑴` alone, (2,3), where it spanned the markup, (0,3), before
task-075). No span decides what parses: the lexer's detached-wildcard test reads the stem's folded pieces
(`tokenize_with_tail`, §Grammar; decision-008). (Tokens no longer carry task-075's `reach`: after
decision-008 nothing read it, so it was retired.) LaTeX markup that opens a word (an accent macro, `\-`, a math
`^`/`_`) is part of that word's span (`\"{O}del` spans all eight characters); a math command's span is its
name, and a word after an operator command starts after the operator's name. The full token case list is
`backend/tests/golden/test_tokens.py`; the span cases are in `backend/tests/unit/test_normalize.py`.

### Known limits (state these in a methods section when they matter)

- **CJK has no word segmentation.** A run of Chinese, Japanese or Korean characters is one token, so
  `信頼` does not match inside `信頼性`. Search the whole run, or use a wildcard on a stem of at least
  three characters (`信頼性*`); `WARN_CJK_RUN` flags every CJK term. Japanese corner brackets that touch
  text (`深層学習「…」モデル`) are `PARSE_AMBIGUOUS_QUOTE`: put spaces around a quoted part.
- **Hebrew and Arabic vowel points fold**, so a vocalised and an unvocalised spelling match each other.
  That is intended (points are optional in normal writing), but it is a fold, not an exact match.
- **Latin, Greek and Cyrillic accents fold** (`resume` ≡ `résumé`), as in every mainstream search engine.
- **No stemming.** `benchmark` does not match `benchmarks`, and `LLM` does not match `LLMs`; plurals and
  other endings count only through an explicit `$` or `*`. Google Scholar stems, so a Scholar string run
  unchanged identifies fewer records here; in Scholar mode `COMPAT_NO_STEMMING` lists the terms affected,
  and the UI offers to write `$` after them in the query text (§Word forms). That is an edit of the string,
  never a way of matching: `benchmark$` is `benchmark` or `benchmarks`, not every form Scholar counts.
- **Title and abstract only.** Scholar also searches full text; openproceedings never does (guarantee 2).
- **Math is matched by its Unicode spelling** (decision-006): a Greek letter is searched as the letter
  (`α`, not `alpha`; `WARN_SPELLED_GREEK` says so when a query spells the name), an operator by its LaTeX
  name (`times`, `leq`), and some names are also ordinary words (`in`, `times`, `sum`; decision-006 lists
  them), so searching the word also finds the symbol. A logic sign in a query (`∨`, `∧`, `¬`) is such a
  word, never an operator (`WARN_LOOKALIKE_OPERATOR`), and a wildcard straight after an operator is
  `PARSE_WILDCARD_DETACHED`.

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
  parentheses, the query parses by precedence **and** raises a warning (`WARN_MIXED_AND_OR`, one per
  level that mixes, spanning that level). The UI shows the parsed tree, so the user sees how it was read.
  The warning's `reading` field is that level as it was read: the text at its span with each `AND` group
  in parentheses and the branches joined by ` OR ` (`a b OR c` → `(a b) OR c`; a nested level inside a
  branch is quoted as typed and keeps its own warning). Replacing the span with it gives the same
  canonical form and one warning fewer (property-tested). It is never clipped, unlike the reading the
  message quotes (TASK-099). It is null when there is no faithful reading to offer: on a level that has errors
  (an error raised while parsing the level: `a b OR () OR c`, where the failed branch has no text in the
  tree, or `a b () OR c`, where the AND group's node stops before `()`, so the reading would drop it), and
  on the "… and N more like these." summary past 20 warnings, which stands for several levels. The message
  never quotes a reading the field doesn't carry: on a level that has errors it quotes the level as typed
  (clipped like a reading), spans the whole level, and says to fix the errors first, then add parentheses
  (TASK-140).
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
  - Double quotes delimit phrases: `"`, `“ ”`, `„ ‟`, `＂`, `« »`, `「 」`, `『 』`, `〝 〞 〟`, `″`. A phrase closes only with a
    quote of its opener's family (the English-style double quotes `"“”„‟＂` are one family and close each
    other; `« »`/`» «`, `「 」` and `『 』` pair only with themselves), so a foreign quote inside a phrase is
    punctuation (`"trust 「in」 AI"` is one phrase). A quote touching a letter or digit on the outside
    (`"trust in "AI"`, `a"b c"`, a possessive `"GPT-4"'s`, a decomposed accent `cafe\u0301"x"`) is
    `PARSE_AMBIGUOUS_QUOTE` (its span covers the rest of the glued text: one mistake, one error), and a parenthesis glued to a word or phrase
    (`model(s)`, `"a"(b)`) is `PARSE_PAREN_TOUCHES_WORD`: both would otherwise silently split a query. A filter
    value is no exception, whatever its form or place: `year:2021(x)`, `venue:iclr(x)`, the range
    `year:2020..2022(x)` and a value inside its group (`year:(2021(x))`, one error) are all refused, and the
    message names the field and says to put a space before the `(`, or, inside the group, to close the group
    first (decision-028); a text field's word
    (`title:model(s)`) keeps the plural hint. A `)` glued to a
    following field prefix (`(x)year:2021`) and a group glued to a group (`year:(2021)(x)`, `(a)(b)`) split no
    word or value and are accepted, as they must be: a facet click splices `field:(…)` over a clause that may
    follow a `)` directly. A glued value is still checked as a value (`year:..2022(x)` is also
    `FIELD_UNKNOWN_VALUE`). A filter value (bare, negated or in its group) is never searched as text, so it gets
    none of the warnings about how text is searched (`WARN_SYMBOLS_DROPPED`, `WARN_CJK_RUN`, `WARN_SPELLED_GREEK`,
    a logic sign's `WARN_LOOKALIKE_OPERATOR`): `year:..2022` is `FIELD_UNKNOWN_VALUE` only.
    A backslash keeps the next character in the word
    (`G\"odel`). Characters whose NFKC form is a syntax character (full-width `（ ）｜：－＊＂`, …) act as
    it, because the tokenizer applies NFKC too; super/subscript parentheses are notation, not grouping. LaTeX
    math is found as the query's tokenizer finds it, so under version 3 `＄f(x)＄` is one word, its `＼` keeps the
    next character, and a query typed in NFC or NFD parses to the same canonical string.
  - `-` is `NOT` when it starts a primary (after whitespace, `(`, `|` or a field's `:`) and touches what
    it excludes. A word that starts with `-` anywhere else (`a - b`, `"x"-based`, `--x`) is
    `PARSE_AMBIGUOUS_MINUS`. A word starting with a look-alike dash (any Unicode dash other than the
    ASCII-equivalent hyphen-minus, or the minus sign `−`) or with `‘` or `` ` `` is searched as written with
    `WARN_LOOKALIKE_OPERATOR`. An ASCII `'` is an apostrophe and raises nothing.
  - A field is a letter, then letters/digits/underscores, then `:`; names are case-insensitive, so an
    unknown one (`intitle:`, `título:`) is an error rather than a silent search. `title: trust` is fine;
    `title :trust` is `PARSE_STRAY_COLON`. `source:` is Scholar syntax: in native mode it is
    `FIELD_COMPAT_ONLY` (Scholar mode translates it to `venue:`).
  - Wildcards: `*` or `$` at the end of a word, directly after a letter or digit (`vision-*` is
    `PARSE_WILDCARD_DETACHED`). That is judged on the stem's **folded pieces** (steps 1–4 of §Token
    semantics; decision-008), since look-alikes act as what they fold to: the last piece must be a letter
    or digit. Invisible characters, folded-away marks and LaTeX markup that joins a word (`bench\-*`) are
    not pieces, and marks that make no word (a lone vowel sign after a separator, `vision-ަ*`) leave the
    separator as the last piece, so that is detached too. So `abcd⒈*` (`⒈` is `1.`) is detached like `abcd1.*`, and so is `abcd⒈̸*` (the U+0338
    on the `.` folds away); `abcd⑴*` (`⑴` is `(1)`) is detached after `)`; `abcd½*` (`½` is `1⁄2`, last
    piece `2`) is attached, `"abcd1 2*"`. The error names the piece and what it came from (`.` from
    `⒈`). A `*` or `$` elsewhere (`behavio$r`, `model$*`) is
    `PARSE_WILDCARD_NOT_SUFFIX`, except inside LaTeX math (found exactly as the tokenizer finds it, so
    `$f(x)$-DP` is one word) and a `$` before a digit (currency, `US$5`).
  - A bare uppercase `NEAR` between terms is `PARSE_BAD_NEAR` (Web of Science reads it as `NEAR/15`);
    `NEAR/n` takes n ≤ 100.
  - A word or phrase part that loses something to the tokenizer raises `WARN_SYMBOLS_DROPPED`: leading
    or trailing symbols (`C++` → `c`, `.NET` → `net`) or a bare LaTeX command outside math
    (`\epsilon-greedy` → `greedy`, and `\alpha{}-divergence`, since empty braces keep nothing; `\cmd{X}`
    keeps `X` and accent macros are part of the word, so neither warns). A word starting with `‘` or `` ` ``,
    or a `’` that a later `’` pairs with, raises `WARN_LOOKALIKE_OPERATOR` (a lone `’80s` is an elision).
- `NEAR/n` works within one field, is unordered, and allows at most n intervening words. Tantivy's slop
  semantics are documented in 03 and must agree with the reference matcher. Its two operands are words,
  wildcards or phrases (not groups or filters) in the same field, and `NEAR` does not chain
  (`a NEAR/3 b NEAR/2 c` is an error; join pairs with `AND`).
- `title:`/`abstract:` apply to every term in what follows (`title:(a OR b)`); a different text field
  nested inside (`title:(abstract:x)`) is an error. Filters may appear anywhere (inside a text field's group
  they raise `WARN_FILTER_SCOPE`, since they filter whole papers), including inside a text
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
| `track:` | filter | 01 taxonomy (`main`, `datasets_benchmarks`, `workshop`, …). `datasets_benchmarks` includes NeurIPS 2026's renamed `Evaluations_and_Datasets_Track`, and `position` includes the NeurIPS and ICML position-paper tracks (TASK-094) |
| `status:` | filter | `accepted`, `rejected`, `withdrawn`, … |
| `source:` | compat | Scholar-style. Mapped to `venue:` through an alias table ("neural information processing systems", "PMLR" → ICML *with a warning* because PMLR hosts other venues). Unknown values are errors, never silent substrings. |

### Default filters

When a query has no **top-level** `track:` clause, the parser adds
`track:(main OR datasets_benchmarks OR position)`. When it has no top-level `status:` clause, it adds
`status:accepted`. Defaults are **made explicit in the canonical string**, so the saved string shows them.
The UI toggles edit these same clauses; they are not a separate state.

- **What `status:accepted` removes** (decision-012). The index holds every public submission, so the
  status default excludes `rejected`, `withdrawn`, `desk_rejected` and `unknown` records, each counted in
  its own exclusion bucket (03 §Exclusion accounting). Those buckets are complete for ICLR, which
  publishes every submission, and a floor for NeurIPS and ICML, which publish rejected papers only when
  the authors opt in (01 §Status handling). `status:(accepted OR rejected)` or removing the default brings
  them into the result set. The index covers each venue from its first year a source holds: NeurIPS from 1987, ICML from 1988,
  ICLR from 2013 (decision-047, which superseded decision-013's 2013 floor); a year range is always a `year:`
  clause the user writes, never a default. Before 2013 only NeurIPS and ICML are indexed, so a search without
  a `year:` clause compares venues over different year spans.

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
  string that parses on its own. Records reproduce it by replaying `canonical`, and exclusion accounting
  uses `ParseResult.identification_ast` (the same set as a tree; None = every record), never the string.
  `WARN_NESTED_FILTER` fires whenever a default applies, whether inserted, typed or replayed, once per
  nested clause of that field.

### Filter clauses (what a facet click edits)

The UI's facet and include clicks rewrite `q` (spec 05 §URL is state). They never re-parse filters on the
client: `POST /parse` reports each filter field's clause as `filters` (decision-011, TASK-078). The report
is `query/clauses.py::filter_clauses(q, parse(q, mode))`, a separate function rather than a `ParseResult`
field, because it parses the edited string, which `/search` and replay don't need.

```python
ParsedFilters = {venue: ParsedClause, year: ParsedYearClause, track: ParsedClause, status: ParsedClause}
ParsedClause  = {field, negated: bool, span: [start, end] | None, toggleable: bool,
                 reason: ClauseReason | None, blocking_spans: [[start, end]],
                 values: [str] | None}                                       # sorted
ParsedYearClause = {…the same…, ranges: [YearRange] | None}                  # sorted, merged
ClauseReason = "multiple_clauses" | "nested" | "mixed_fields" | "negated"
             | "too_long" | "too_deep" | "unparsable_edit"                    # an open set
```

"Top-level" is judged on the **flattened canonical tree**, the one the default rule reads: parenthesised
`AND` groups are flattened, `NOT NOT x` is `x`, and an `OR` of one field's filters is one clause. For each field:

| The field has | `span`, `values` | `toggleable`, `reason` |
|---|---|---|
| one top-level clause, written as one top-level conjunct | the written conjunct's code-point span (all of `(track:a OR track:b)` or `NOT NOT track:a`, so a splice replaces it whole); the canonical values | true |
| one, negated (`-track:workshop`, `NOT (track:a OR track:b)`) | its span and values, `negated: true` | false, `negated` (adding a value inside it would flip what it removes) |
| more than one (`track:workshop llm AND (venue:NeurIPS track:workshop)`; two written copies the canonical form deduplicates, `track:main track:main`) | null | false, `multiple_clauses` (a splice over one leaves the other ANDed in) |
| none top-level, but nested under an `OR` or `NOT` group | null | false, `mixed_fields` if a top-level `OR` joins filters of several fields (`track:workshop OR venue:ICLR`), else `nested` |
| none at all | zero-width `(len(q), len(q))`, the default's spot; the default's values (track, status), every vocabulary value (venue), or `1000..9999` (year) | true: a click writes it out as `(q) AND field:(…)` |

**`blocking_spans`** (TASK-091, additive): for `multiple_clauses`, `nested` and `mixed_fields`, the clauses
behind the reason, so the UI can point at them ("Show the clauses", spec 05) without walking the AST: the
code-point span in `q` of each written top-level conjunct (`AND` groups flattened, nothing else rewritten)
that holds a filter of the field anywhere, sorted. `track:workshop llm AND (venue:NeurIPS track:workshop)`
gives both `track:workshop`; `llm (a OR track:workshop)` gives `(a OR track:workshop)`; `track:main NOT NOT
(track:main a)` gives `track:main` and `NOT NOT (track:main a)`. Empty for every other clause, toggleable or
not (the other reasons are about the edit, not about clauses in `q`).

A nested clause beside a single top-level one doesn't block it (`track:main (track:workshop OR x)` edits
`track:main`); the nested one stays applied, as the disjunctive facet counts assume (decision-001).

**The caps.** A click always writes the grouped form, `field:(v1 OR …)`, even for one value (`field:(v)`;
the same canonical form and hash as `field:v`), so its `)` ends every edit and no edit can touch a group
that follows the clause (`track:(main OR workshop)(x OR y)` → `track:(workshop)(x OR y)`, where a bare
`track:workshop(x OR y)` would be `PARSE_PAREN_TOUCHES_WORD`, as would any value glued to a `(`, a full year range
included; decision-028). A toggleable clause is checked by making the
widest edit a click can make and parsing it in the query's mode: every vocabulary value (for year,
`MAX_YEAR_RANGES` = 4 disjoint `dddd..dddd` ranges, the most a year action writes; see below), spliced over
the span or wrapped around `q`, exactly as the reducer writes it. Every narrower edit is then sound too: a
property test (`test_clauses.py`) applies every single-value toggle and include, and year clauses of up to
four generated ranges, to every toggleable clause of generated queries and checks that the edited query
parses and that nothing outside the clicked field's top-level clause changes. If that edited `q` is refused, the clause is not
toggleable: `too_long` (over 2,000 code points, raw or canonical: decision-008), `too_deep` (the wrap nests
`q` one level deeper, so a `q` already 64 deep is `PARSE_TOO_DEEP`) or `unparsable_edit` (any other
error; for example a `q` ending in an escaping backslash, which would escape the wrap's `)`). It is also not
toggleable if the edited `q` does not end with exactly that one top-level clause of the field
(`multiple_clauses`, e.g. `track:main NOT NOT (track:main a)`). A splice inside `q` adds no nesting:
`track:(…)` is not a group level. The check is conservative near the cap, since it tests the widest edit
and not the value clicked. Every field with no clause is checked by one parse that writes them all out at
once, and each alone only when that edit can't be made (the answer is the per-field one; a property test
compares them); a typed clause costs one parse of its own. So `/parse` adds one parse for a query with no
typed clause, and at most five (`test_clauses.py` counts them), so the worst case, short words near the
cap where the combined wrap is too long to write at once and each field is checked alone, is about six
parses of `q`.

**Year edits** (TASK-092). The year control's actions (set a range, clear, add a range, remove a range) write
the whole year clause from the reported `ranges`: sorted, with overlapping or adjacent ranges joined as the
canonical form joins them, one year written bare (`year:(2018..2020 OR 2022..2024)`, `year:(2024)`), grouped
like every clause. Clearing writes every year, `year:(1000..9999)`, in place: the clause is rewritten, never
deleted, since deleting it could leave an operator with nothing after it. A year clause of more than
`MAX_YEAR_RANGES` ranges (4) is edited in the query text instead: the reducer refuses it
(`TOO_MANY_RANGES`), so every year edit is at most the widest one `/parse` checked, raw and canonical.
Goldens: `frontend/src/lib/filter-clause-golden.json` (clicks) and `frontend/src/lib/year-clause-golden.json`
(year actions, with `MAX_YEAR_RANGES` and the year bounds), read by `backend/tests/unit/test_clauses.py`,
`backend/tests/contract/test_parse_filters.py` and the reducer's test.

### Word forms (what "Add `$`" edits)

Scholar mode's `COMPAT_NO_STEMMING` notice tells the reader to add `$` or `*` where other endings should
count. The UI can write the `$` for them (spec 05 §Components 1), as an edit of `q` the reader triggers and
sees: the engine, tokenizer and index are untouched (guarantee 1), the `$` is in the query string (guarantee
3), and its expansions are reported like any wildcard's (guarantee 6). The UI never re-parses the query to
find the terms: `POST /parse` reports each place a `$` can go as `word_forms` (TASK-175), which is
`query/wordforms.py::word_forms(q, parse(q, mode))`, a separate function for the reason `filter_clauses` is.

```python
WordForm = {term: str,            # as the notice names it: normalised tokens, a phrase's joined by spaces
            at: int,              # code-point offset in q: the end of the word, or of a phrase's last word, as the
                                  #   lexer ends it: after an invisible character that joins the word (a
                                  #   zero-width space after `trust` gives 6, not 5)
            insert: str}          # the text to insert at `at`, as it is: "$" or "$ "
word_forms -> [WordForm] | None   # in order of `at`; None exactly when errors is non-empty; [] in native mode
SkippedTerm = {term: str,         # as the notice names it, like WordForm.term
               reason: str}       # too_short | symbol | dollar_nearby | operator_word | too_long | unconfirmed
word_forms_skipped -> [SkippedTerm] | None  # each named term offered in no place, once, in the notice's order
```

Both are `query/wordforms.py::report(q, result)` (TASK-192), served beside each other by `POST /parse`. Every
term the notice names is in exactly one of them: offered (in at least one place), or skipped with the first
reason that refuses it. The reasons are the table's rows below (`too_short`, `symbol`, `dollar_nearby`,
`operator_word`, from `exact.py::dollar_verdicts`), plus `too_long` (the length budget, below) and
`unconfirmed`, which has two sources: `dollar_verdicts` gives it to a leaf whose shape it doesn't know (no
word or phrase lexeme in the leaf's span, two of them, or a phrase with no parts), and `wordforms.report` to
every term when the read-back refuses the edits for a reason the rules did not foresee (nothing is offered
then). The tests hold that neither happens. `reason` is an open enum (spec 04 §Conventions): a new lexer rule may add
one.

A term is offered when the notice names it (a word or phrase with no wildcard; `NEAR` operands and terms
under `NOT` included; one entry per place it is written) and `$` is a valid wildcard on it **as written**:

| Term | Offered | Why |
|---|---|---|
| `trust`, `LLM`, `title:trust`, `-bias`, `(model)` | `trust$`, `LLM$`, `title:trust$`, `-bias$`, `(model$)` | a word of at least 3 letters or digits |
| `"large language model"`, Scholar's unquoted `large language model \| …` | `"large language model$"`, `large language model$` | a phrase takes `$` on its **last word** only, as the review's strings write it; the earlier words count toward the stem, so `"generative AI"` is offered. Inner words are left alone: a `$` there is valid (§Grammar) but the notice names the phrase as one term, and the reader can type it |
| `vision-language`, `gpt-4` | `vision-language$`, `gpt-4$` | a word of several tokens is a phrase; the same rule |
| `model$`, `bench*`, `"large$ language model"` | no | already a wildcard; a phrase holding one is not named by the notice |
| `AI`, `"a b"` | no | under 3 letters or digits: `AI$` would be `WILDCARD_STEM_TOO_SHORT` |
| `C++`, `trust?`, `"what is trust?"` | no | `$` must directly follow a letter or digit (`PARSE_WILDCARD_DETACHED`) |
| `US$5`, `$f(x)$-DP`, `G\"odel`, `LLM` in `(model$\|LLM)` | no | the unspaced run the word is in (up to whitespace or a quote, where the lexer looks for LaTeX math) already holds a `$` or a backslash, and a second `$` would close math |
| a lowercase `and`, `or`, `not` or `near/3` (any case or width: `And`, `ｏｒ`) | no | the lexer's `WARN_LOWERCASE_OPERATOR` and Scholar mode's phrase grouping (decision-002) know the word by its text: `and$` would lose the warning, and `trust \| LLM and` would become `trust$ \| "LLM$ and$"`, another query. As the last word of a quoted phrase it is an ordinary word (`"supply and"` → `"supply and$"`) |
| `venue:ICLR`, `year:2020..2024`, `source:PMLR` values | never | filter values are not terms and take no wildcards |

Two offered words in one unspaced run (`(model|LLM)`) would read as LaTeX math once both had a `$`
(`(model$|LLM$)`), so every one but the last gets `insert` `"$ "`: `(model$ |LLM$)`. The space changes
nothing else, and with it any subset of the edits is sound.

The report is then **read back**: the server makes every edit at once, parses the result in the query's mode,
and requires the tree to be the original with exactly those leaves made `$` wildcards. If it is not, nothing
is offered (`[]`, each term `unconfirmed`). The rules above are meant to allow only what the read-back
accepts; the one thing they cannot see is the edited query, or its canonical form, passing the
2,000-code-point cap. Then the terms whose `$` fit are offered and the rest are `too_long` (TASK-192): terms
are taken in the order they are first written, each in every place it is written or in none (the UI adds a
term's `$` everywhere), and a term that doesn't fit doesn't stop a later, smaller one. The raw length of a
choice is counted exactly (a `$ ` whose neighbour in the run is not chosen is a bare `$`), and any subset of
the chosen inserts is shorter. The canonical form is a **budget**, because the reader may tick any subset of
the offered terms and some `$` shorten it (a quoted `"and"` becomes `and$`; `trust OR trust$` dedupes to
`trust$`), so a set can fit while a subset without such a term does not (review of TASK-192): each term costs
one code point per place, counted from the canonical form of the query as typed, never less, so one term's
savings never pay for another. That is the most a `$` adds for a term that takes it in every place it is
written, since such a term is edited alike everywhere and the canonical form's deduped subtrees stay equal.
A term the rules refuse in another place (`trust? OR trust`, deduped to `trust`) can make them differ. With
deduping off, any edit's canonical form is at most the typed query's plus one per place, so what deduping
saved in the typed query bounds what all such terms together bring back: the first one offered pays it,
once. When that doesn't fit, a term's own change is rendered and paid instead (never less than nothing), for
one such term per query; a later one is `too_long`. One is sound: on top of that term's edit every other
offered term takes its `$` in every place it is written, so it keeps the deduped subtrees equal and adds at
most one per place, and any subset is at most the rendering plus one per place of the rest. Two are not:
costs rendered one term at a time don't add. In `(trust AND model) OR (trust$ AND model?) OR (trust? AND
model)` each of `trust$` and `model$` alone leaves two of the three copies equal, and together they split
them into three (review round 2 of TASK-192); rendering terms jointly would bound only the sets rendered,
not every subset the reader can tick. `POST /parse` is public and runs this as the reader types, so the
budget is linear in the places (a bisect each) and renders the canonical form at most twice (a hostile
near-cap query takes under 30 ms; one rendering per such term once took 0.9 s). The offered set is
read back as a whole. Because the budget is an upper bound, a term named `too_long` may in fact have fit
(its own or another offered term's `$` would have shortened the canonical form, or it was past the
rendering limit); it is never offered when some subset with it would not fit. `test_wordforms.py` pins each row above and checks, for generated
queries and every Trust-Evals string, that every subset of the edits (each alone, all together, and every
combination of the first six, since the reader may tick any) changes only the terms it names, and that the
read-back refuses nothing the rules allow short of the cap. That last check is a test, not a proof: it is how
the operator-word row was found (review of TASK-175), and a new text-dependent rule in the lexer or `compat.py`
needs its row here. The UI's splice is checked against the server's own
(`frontend/src/lib/word-forms-golden.json`, generated by `test_frontend_word_forms_golden.py`).

The notice's own example goes by the same rule (`query/exact.py::dollar_places`, the one implementation both
use; TASK-181): "(e.g. `trust$`)" names the first term that can take a `$` as written, a phrase quoted whole
since its earlier words count toward the stem (`"foundation model$"`, `"gpt 4$"`), and a lowercase operator word
quoted too (`"and" trust` gives `"and$"`, what Add `$` writes there; unquoted it would be the lowercase-operator
row above), so the example is always a query both modes read as that term made a `$` wildcard. A term whose
example would pass 40 characters (the most a message quotes) is passed over, and when
no term qualifies (`AI C++ or`, which once suggested `ai$`) the sentence has no example. The notice's code and
span are unchanged, and it does not depend on the read-back.

`$` is not stemming: `benchmark$` matches `benchmark` and `benchmarks` (and any other indexed word one
character longer), never `benchmarking`. A reader who wants every ending types `*`.

## Compatibility input modes

The review's existing strings must work **unchanged** or come back with a precise explanation:
- **Scholar/PoP mode** (`parse(q, "scholar")`, `query/compat.py`): accepts `OR` / `|`, `source:` and
  quoted phrases. PoP's `$` is interpreted as the WoS zero-or-one wildcard, and the parser says so in a
  notice (`COMPAT_POP_DOLLAR`). `source:` values translate through an exact alias table (never a
  substring match; every value in the review's 17 corpus exports is covered) to `venue:`, with a
  `COMPAT_SOURCE_ALIAS` notice each; PMLR also raises `WARN_SOURCE_PARTIAL`; an unknown value is an error.
  An OR of sources collapses to one `venue:(…)` clause. A wildcard in a `source:` value (quoted or not)
  is an error, and a bare source name OR-joined to a `source:` filter (`source:ICLR OR PMLR`) raises
  `WARN_FILTER_SCOPE`. **Decision-002:** a run of two or more
  juxtaposed unquoted words forming one `|`/`OR` item is a phrase (a lowercase `and`/`or`/`not` or a
  word with no letters or digits ends the run instead of joining it) (`(large language model$ | LLM)` →
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
ParseResult = {               # `query/parser.py`; every Optional below is None exactly when errors is non-empty
  mode: "native" | "scholar",
  ast: Node | None,            # the tree as typed (spans into q): Or, And, Not, Term, Phrase, Near, Wildcard, Filter
  effective_ast: Node | None,  # canonical tree with the default filters: what the engine runs
  canonical: str | None,       # render(effective_ast): fully parenthesised, uppercase operators, defaults
                               #   explicit, filters ordered venue, year, track, status (§Canonical form)
  canonical_hash: str | None,
  identification_query: str | None,  # canonical without default conjuncts; "" = every record
  identification_ast: Node | None,    # the same set as a tree (None = every record): what counts use
  defaults: [ "track" | "status" ],   # fields whose top-level clause is the default
  warnings: [Diagnostic],      # {code, message, span:[start,end], reading}; reading: only ever a str on
                               #   WARN_MIXED_AND_OR (§Grammar, Precedence; null there too when there's none
                               #   to offer), null on every other code
  errors: [Diagnostic],        # non-empty ⇒ no search
  translations: [Diagnostic],  # Scholar-mode rewrites and notices (e.g. COMPAT_NO_STEMMING)
}
filter_clauses(q, parse(q, mode)) -> ParsedFilters | None   # `query/clauses.py`: None exactly when errors
                                                              #   is non-empty (§Filter clauses; /parse `filters`)
word_forms(q, parse(q, mode)) -> [WordForm] | None           # `query/wordforms.py`: None exactly when errors
                                                              #   is non-empty (§Word forms; /parse `word_forms`)
```

`canonical` is deterministic: `parse(canonical).canonical == canonical`. That idempotence is tested with
property tests. `canonical_hash = sha256(canonical + "\0" + tokenizer_version + "\0" + QUERY_VERSION)` (decision-003),
`tokenizer_version` being the one the query was parsed with (the index's; `ParseResult.tokenizer_version`):
NUL separators keep the parts apart, and a query-semantics bump changes the hash. `canonical` and `canonical_hash` are None when there are errors.

Canonical form (`query/canonical.py`) is a normal form: nested `AND`/`OR` are flattened; in every `AND`,
text conjuncts keep their written order and filter conjuncts follow in the decision-001 order (a
positive filter before a negated one of the same field); an `OR` of filters on one field becomes one
filter (in any OR, at the first one's position); values are sorted and deduplicated, and overlapping or
adjacent year ranges merge; duplicate conjuncts and disjuncts are dropped; `NOT NOT x` is `x`; OR branches
keep their written order; a bare term that a sibling filter's field could read as a value is quoted
(`venue:ICLR OR "neurips"`); every text leaf carries its field prefix
(`title:(a OR b)` → `(title:a OR title:b)`). `gpt-4*` prints as `"gpt 4*"` (in a phrase the earlier
words count toward a wildcard's stem). Semantically equal spellings
(`trust venue:ICLR`, `venue:iclr Trust`) therefore share one hash. `QUERY_VERSION`
(`openproceedings.query`) is `"2"` (decision-008: canonical overflow and folded-piece wildcard detachment; decision-028 left it at
`"2"`, since refusing a range glued to `(` changes no canonical string).

## Error handling

Every error has a span and a fix hint: unbalanced parentheses, an empty group, a wildcard stem that is too
short or not at the end of a word, an unterminated phrase, `NEAR/` without a whole-number distance or
with a bad operand, a missing operand (`a OR`), a word or phrase with no letters or digits (`a ~ b`), a
nested text field, a malformed filter group, nesting deeper than 64, an ambiguous `-`, a stray `:`, a
detached or mid-word wildcard, `source:` outside Scholar mode, an unknown field, an unknown filter value
(listing the valid ones), a range with start > end, an all-negative query, a quote or parenthesis glued
to a word (`"trust in "AI"`, `model(s)`) or a `(` glued to a filter value (`year:2020..2022(x)`), or a query
longer than 2,000 code points (`PARSE_TOO_LONG`, checked before any other work). The canonical string is capped too: a query whose canonical form (the
defaults explicit, ` AND ` for juxtaposition, a field prefix on every leaf, parentheses) is over 2,000 code
points is `PARSE_TOO_LONG`, spanning the whole input and saying how much the canonical form adds
(decision-008), since a search record keeps that string and replay re-parses it. So every accepted query's
canonical string is itself accepted. So there is no single effective input limit: it depends on how much
the canonical form adds per term. The shortest refused inputs, measured with the parser (the defaults added;
2- to 8-letter words): `abstract:(w w w …)` field groups are the worst case, from 373 (2-letter words) to
802 (8-letter) code points, since every term gains `abstract:` and ` AND `; `-x` lists in Scholar mode 705–1,145;
juxtaposed words 827 (2-letter), 967 (3), 1,163 (5), 1,340 (8); `title:(a OR b …)` groups 970–1,300; plain
`OR` lists about 1,928. The error states how far the canonical form is over the cap and why. Diagnostics are capped at 20 per code ("… and N more"), and user text
quoted in a message is clipped to at most 40 displayed characters (120 for a `WARN_MIXED_AND_OR` level or
reading, 20 for an unterminated phrase; escapes count toward the limit), so no diagnostic grows with the input.
The quote is one line of visible text: whitespace runs are one space, and a backtick or an invisible (control,
format or surrogate) character is written as its escape (`\x60`, `\x00`, `\u202e`), so a backtick in the query
can't end the message's quoting. A fix hint quotes the query only when it needs no escape, since it is text to
type back. This is display only: `q`, spans and `reading` keep the text exactly as typed, and the canonical form is
never escaped (TASK-141; error-diagnostics skill). The codes are in
`diagnostics.py`; the `PARSE_*`, `FIELD_*` and `WILDCARD_*` errors are 422s where a query is run (spec 04); `/parse`
returns them as values.

## Testing

- The golden token table above, plus about 100 or more normalization cases (Unicode dashes, ligatures, LaTeX, digits).
- The Trust-Evals strings as snapshot fixtures.
- Hypothesis property tests: canonical round-trips, AST → string → AST is the identity, and random
  garbage never crashes the parser (it gives errors, not exceptions).
