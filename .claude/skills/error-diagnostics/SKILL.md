---
name: error-diagnostics
description: The single Diagnostic shape ({code, message, span}) used for parse warnings, errors and translation notices across the parser, the API error envelope and the UI squiggles, the error-code registry and naming scheme, span rules, and message style (every error has a fix hint). Use when adding or changing any error, warning or notice, touching ParseResult or the API error envelope, rendering diagnostics in the editor, or reviewing error handling.
---

# Error diagnostics — one shape everywhere

## The shape (spec 02 §Outputs, spec 04 §Conventions)
```python
class Diagnostic(BaseModel):  # frozen, extra="forbid"
    code: DiagnosticCode  # StrEnum from the registry
    message: str  # human sentence, includes the fix hint
    span: tuple[int, int] | None  # half-open [start, end) code-point offsets into the query input q
    reading: str | None  # only ever set on READING_CODES (WARN_MIXED_AND_OR); always sent (TASK-099)
```
- **`reading`** is the one code-specific field, kept on the shared shape (optional, so additive) rather than
  a per-code payload: on `WARN_MIXED_AND_OR` it is the warned level as it was read, the text at `span` with
  each `AND` group parenthesised (`a b OR c` → `(a b) OR c`), never clipped. A model validator refuses it on
  any code outside `READING_CODES`; it is **not** required there: the per-code cap's "… and N more" summary
  (`parser._capped`, which builds every code's summary alike) and a level that has errors (an error raised
  while parsing the level) carry `reading: None`, and then the message quotes the level as typed, never a reading
  (TASK-140: it
  once quoted `(a b) OR c` for `a b OR () OR c`; a property pins message ↔ `reading`; an "always set" rule 500'd the summary, TASK-099 review). The UI's "Load with parentheses" splices it over `span`; **a client never
  parses `message`** for data. Data another code needs becomes a field the same way (a spec 04 change, additive:
  nullable, null on the other codes), never prose to extract.
- `ParseResult.warnings`, `.errors`, `.translations` are all `list[Diagnostic]`. Non-empty `errors` ⇒ no
  search runs.
- API errors: `{ "error": { "code", "message", "diagnostics"?: [Diagnostic] } }`. Statuses and codes are
  exactly spec 04 §Error handling, which is the only table: 422 `PARSE_*` (a query that does not parse, on an
  endpoint that runs it, carrying 02's diagnostics with spans; `POST /parse` returns them as values in a 200), 422 `API_BAD_PARAM`, 404 `API_PAPER_NOT_FOUND` /
  `API_RECORD_NOT_FOUND`, 409 `API_INDEX_VERSION_UNAVAILABLE`, 409 `API_RECORD_MISMATCH` (export of a
  `mismatch` record), 429 `API_RATE_LIMITED` (with `Retry-After`), 503 `API_INDEX_NOT_LOADED`, 503 `API_RECORDS_STORE_FULL`, 413
  `API_BODY_TOO_LARGE` (a body over the cap), 503 `API_BUSY` (with `Retry-After`: verification slots taken, or another index version's open outlasted `pinned_open_wait_seconds`, TASK-067), 422
  `API_TOO_MANY_VERIFIED_CLAUSES` (more position-verified clauses than the instance runs; carries one located
  diagnostic per clause, decision-010), 422 `API_QUERY_TOO_COSTLY` (the clauses' position checks would read
  more candidate documents than the instance allows one query; one located diagnostic per clause with its
  counts, decision-010), 500
  `API_INTERNAL`, and 404 `API_NOT_FOUND` / 405 `API_METHOD_NOT_ALLOWED` for routing (task-034). A new or changed pair is a spec 04 change first (and breaking once released). An error envelope's `code` is typed by the `ErrorCode` schema: exactly the codes with an HTTP status, derived from the registry (`api/errors.py`); a spec 04 test reads the §Error handling table and compares it with the registry both ways, so a new `API_` code needs its table row.
- The frontend uses the generated `Diagnostic` type and draws squiggles directly from `span`. It never
  recomputes positions (`typescript-standards`).

## Registry
- One module defines every code: `backend/src/openproceedings/diagnostics.py` (spec 08 §Monorepo layout),
  and a generated table in the syntax help page (`/help/syntax`) lists them, so docs can't drift.
- Codes are `AREA_SNAKE_NAME`, stable forever once released — scripts match on them. Retire a code; never
  reuse or rename it.

| Prefix | Area | Examples (from 02 §Error handling) |
|---|---|---|
| `PARSE_` | grammar | `PARSE_UNBALANCED_PAREN`, `PARSE_EMPTY_GROUP`, `PARSE_ALL_NEGATIVE`, `PARSE_UNTERMINATED_PHRASE`, `PARSE_BAD_NEAR`, `PARSE_WILDCARD_NOT_SUFFIX`, `PARSE_EXPECTED_TERM`, `PARSE_EMPTY_TERM`, `PARSE_NESTED_FIELD`, `PARSE_TOO_DEEP`, `PARSE_WILDCARD_DETACHED`, `PARSE_AMBIGUOUS_MINUS`, `PARSE_STRAY_COLON`, `PARSE_AMBIGUOUS_QUOTE`, `PARSE_PAREN_TOUCHES_WORD`, `PARSE_TOO_LONG` |
| `WILDCARD_` | expansion | `WILDCARD_STEM_TOO_SHORT`, `WILDCARD_TOO_MANY_EXPANSIONS` (>200) |
| `FIELD_` | fields/filters | `FIELD_UNKNOWN`, `FIELD_UNKNOWN_VALUE` (lists valid `track:` values), `FIELD_RANGE_INVERTED`, `FIELD_FILTER_SYNTAX`, `FIELD_COMPAT_ONLY` (`source:` outside Scholar mode) |
| `WARN_` | warnings | `WARN_LOWERCASE_OPERATOR` ("did you mean OR?"), `WARN_LOOKALIKE_OPERATOR` (`−bias`, `‘x`), `WARN_SYMBOLS_DROPPED` (`C++` → `c`), `WARN_FILTER_SCOPE` (`year:2023 OR 2024`), `WARN_SOURCE_PARTIAL` (PMLR), `WARN_CJK_RUN`, `WARN_SPELLED_GREEK` (`alpha` finds the word only; abstracts' `$\alpha$` and `α` are indexed as `α`, decision-006), `WARN_LOOKALIKE_OPERATOR` also for a logic sign (`a ∨ b`, `¬bias`: searched as the words `vee`, `neg`), `WARN_MIXED_AND_OR`, `WARN_NESTED_FILTER` (spec 02 §Default filters): a `track:`/`status:` clause nested inside an `OR` branch does not suppress the default, e.g. `(track:workshop AND x) OR y` → "the default track/status filter still applies to the whole query; add a top-level `track:`/`status:` clause to override it", span on the nested clause |
| `COMPAT_` | translations | `COMPAT_SOURCE_ALIAS` (`source:PMLR` → `venue:ICML`), `COMPAT_POP_DOLLAR`, `COMPAT_POP_PHRASE` (decision-002), `COMPAT_NO_STEMMING` (Scholar stems; we don't) |
| `API_` | HTTP layer | the codes of spec 04 §Error handling, plus `API_REPLAY_MISMATCH` (a log code only, never an HTTP error: the replay is a `200` whose `status` field is `mismatch`) |

The registry is `diagnostics.py` (built in M1): the table above names every parse-time code; the prefixes and the rule
are the standard. The `API_` codes, and their HTTP statuses, are already fixed by spec 04 §Error handling:
use them exactly as named there.

## Span rules
- Offsets are half-open `[start, end)` ranges of **Unicode code points** over the query input `q` the user
  typed (not the canonical string, not normalized text): Python `str` indices (spec 04 §Conventions). The
  UI converts to its editor's units exactly once, in one helper (`src/api/spans.ts`) — CodeMirror uses
  UTF-16; an astral character (emoji, some math symbols) shifts every later span if unconverted. Test it.
- Zero-width spans allowed for "expected X here" at end of input.
- Scholar-mode translations point at the source token that was translated.
- `span: None` only for whole-query conditions (e.g. an all-negative query may span the whole input
  instead — prefer a span when one exists).

## Message style
- Say what is wrong, where, and how to fix it: "Wildcard stem `be*` is shorter than 3 characters — use a
  longer stem such as `bench*`." Unknown values list the valid ones.
- Never blame the user; never say "invalid query" alone.
- **Query text is quoted only through `diagnostics.clip`**, between backticks: `` f"`{clip(raw)}` …" ``, a
  slice or a single character of the input included (`clip(raw[0])`), so a message is one line of visible text,
  safe to log and copy, whatever the query holds (TASK-141). `clip` collapses each whitespace run (every
  `str.isspace()` character: newline, tab, U+2028, NBSP, …) to one space; writes a backtick and every
  invisible character (Unicode `Cc` control, `Cf` format such as a bidi override or a zero-width space, `Cs`
  lone surrogate) as its Python escape (`` ` `` → `\x60`, NUL → `\x00`, U+202E → `\u202e`), so a backtick
  typed in the query can't end the quote early (the UI's `Coded`/`Ticked` pair backticks); and shortens to 40
  code points (120 for a `WARN_MIXED_AND_OR` level or reading, 20 for `PARSE_UNTERMINATED_PHRASE`), never
  splitting an escape. A backslash is not
  escaped (LaTeX reads as typed), so `\x60` in a message may also be those four characters typed: the
  message is prose for people, and the **span** locates exactly what was typed. The `reading` **field** is
  data, never clipped or escaped (the message's quote of it is). A **fix hint** is text the user types back, so
  it quotes the query only when `diagnostics.verbatim(text)` holds (no escape needed); otherwise it says what
  to do in words (`` −foo`bar `` → "type an ASCII hyphen `-` in its place", not `-foo\x60bar`). A property
  (`test_every_message_quotes_query_text_on_one_visible_line`) and goldens (`test_parser.py::QUOTED`) pin it.
  **Request locations too:** an `API_BAD_PARAM` message quotes each parameter name and body-key location
  (pydantic's `loc`, `api/errors.py::bad_param_message`; an unknown query parameter, `api/deps.py::strict_query`)
  through `clip` (30 code points a part; pydantic's own text is escaped too, at 200), between backticks, since a
  key is the client's own text, and names at most `MAX_NAMED_PARAMS` problems, counting the rest (TASK-143; `test_422_message_is_one_visible_line_whatever_the_keys`, `test_422_message_is_bounded_whatever_the_key_or_text`
  and `test_422_names_a_few_problems_and_counts_the_rest` pin it).
- Message text is prose, not contract: codes, spans and `reading` are what clients use (they never parse
  `message`), so rewording a message is not a breaking change under `/api/v1`. Update the goldens that quote
  it deliberately (`frontend/src/help/syntax-golden.json` via `help_golden.py`, the copy deck).
- Warnings are shown, never auto-fixed (guarantee 6). A warning does not change what the query means.

## Rules
- Bad user input is a **value**, not an exception. The parser never raises (property-tested).
- Internal failures are typed exceptions (`python-standards`) mapped at the API edge to a 5xx envelope
  with a code; stack traces never reach the client.
- Adding a code: registry entry, a golden test that produces it with its span, and the help table.
