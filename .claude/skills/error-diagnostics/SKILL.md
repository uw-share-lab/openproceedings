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
```
- `ParseResult.warnings`, `.errors`, `.translations` are all `list[Diagnostic]`. Non-empty `errors` ⇒ no
  search runs.
- API errors: `{ "error": { "code", "message", "diagnostics"?: [Diagnostic] } }`. A parse error is **422**
  carrying 02's diagnostics with spans. Other codes: 400 bad parameter, 404 unknown record/paper, 409 a
  pinned `index_version` not available, 429 rate limited.
- The frontend uses the generated `Diagnostic` type and draws squiggles directly from `span`. It never
  recomputes positions (`typescript-standards`).

## Registry
- One module defines every code: `backend/src/openproceedings/diagnostics.py` (spec 08 §Monorepo layout),
  and a generated table in the syntax help page (`/help/syntax`) lists them, so docs can't drift.
- Codes are `AREA_SNAKE_NAME`, stable forever once released — scripts match on them. Retire a code; never
  reuse or rename it.
| Prefix | Area | Examples (from 02 §Error handling) |
|---|---|---|
| `PARSE_` | grammar | `PARSE_UNBALANCED_PAREN`, `PARSE_EMPTY_GROUP`, `PARSE_ALL_NEGATIVE` |
| `WILDCARD_` | expansion | `WILDCARD_STEM_TOO_SHORT`, `WILDCARD_TOO_MANY_EXPANSIONS` (>200) |
| `FIELD_` | fields/filters | `FIELD_UNKNOWN`, `FIELD_UNKNOWN_VALUE` (lists valid `track:` values), `FIELD_RANGE_INVERTED` |
| `WARN_` | warnings | `WARN_LOWERCASE_OPERATOR` ("did you mean OR?"), `WARN_MIXED_AND_OR`, `WARN_NESTED_FILTER` (spec 02 §Default filters): a `track:`/`status:` clause nested inside an `OR` branch does not suppress the default, e.g. `(track:workshop AND x) OR y` → "the default track filter still applies to the whole query; add a top-level `track:` clause to override it", span on the nested clause |
| `COMPAT_` | translations | `COMPAT_SOURCE_ALIAS` (`source:PMLR` → `venue:ICML`), `COMPAT_POP_DOLLAR` |
| `API_` | HTTP layer | `API_BAD_PARAM`, `API_RECORD_NOT_FOUND`, `API_INDEX_UNAVAILABLE`, `API_RATE_LIMITED`, `API_REPLAY_MISMATCH` (logged; the replay *status* field value stays `mismatch`) |
Exact names are set when the registry is created; the prefixes and the rule are the standard. A code a


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
- Warnings are shown, never auto-fixed (guarantee 6). A warning does not change what the query means.

## Rules
- Bad user input is a **value**, not an exception. The parser never raises (property-tested).
- Internal failures are typed exceptions (`python-standards`) mapped at the API edge to a 5xx envelope
  with a code; stack traces never reach the client.
- Adding a code: registry entry, a golden test that produces it with its span, and the help table.
