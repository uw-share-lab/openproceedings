---
name: ux-writing
description: The openproceedings voice and wording standard — precise, plain, never cute; the message pattern "what happened → why → how to fix" anchored to the quoted span; the glossary of product terms used identically in UI, docs, exports and methods text (canonical query, index version, excluded, limit, expansion, search record, reproduced/drifted, …) with words to avoid; and worked messages for the real spec 02 diagnostics. Use when writing or reviewing any user-facing string, diagnostic message, banner, empty state, help page or the methods text.
---

# UX writing

## Voice
Precise, plain, calm. Write it the way a careful methods section is written. Name the number, the term
and the field. No exclamation marks, no "oops", no jokes, no "smart", no "AI-powered", no "we found".
Second person for instructions ("Use a longer stem"). No blame ("You made an error" becomes a
description of the query). Sentence case. Query text, canonical strings and versions in monospace.

## Message pattern (diagnostics, errors, notices)
`<what happened, quoting the span> — <why, in query-language terms>. <How to fix, with a valid example>.`
The span is the quoted text. The UI underlines it, and the message quotes it so the sentence stands alone
(screen readers, logs, copied text). Unknown values list the valid ones from `/meta`. Warnings describe
how the query **was read**. They never claim to have fixed it.

## Worked examples (spec 02 §Error handling and §Compatibility. Codes per `error-diagnostics`)
| Code | Message |
|---|---|
| `PARSE_UNBALANCED_PAREN` | "`(trust OR reliance` has no closing parenthesis. Add `)` where the group ends." |
| `PARSE_EMPTY_GROUP` | "`()` is an empty group. Remove it or put a term inside." |
| `PARSE_ALL_NEGATIVE` | "`NOT workshop` only removes papers, so there is nothing to remove them from. Add a term to search for, e.g. `benchmark NOT workshop`." |
| `WILDCARD_STEM_TOO_SHORT` | "Wildcard stem `be*` is shorter than 3 characters. Use a longer stem such as `bench*`." |
| `WILDCARD_TOO_MANY_EXPANSIONS` | "`tr*` matches 1,340 terms, more than the 200 allowed. Use a longer stem such as `trust*`." |
| `FIELD_UNKNOWN` | "`author:` is not a searchable field. Fields are `title`, `abstract`, `venue`, `year`, `track`, `status`, `source`." |
| `FIELD_UNKNOWN_VALUE` | "`track:poster` is not a track. Tracks are `main`, `datasets_benchmarks`, `position`, `workshop`, … (from `/meta`)." |
| `FIELD_RANGE_INVERTED` | "`year:2026..2020` starts after it ends. Write `year:2020..2026`." |
| `WARN_LOWERCASE_OPERATOR` | "`or` is lowercase, so it was searched as a word. Write `OR` to combine terms." |
| `WARN_MIXED_AND_OR` | "AND and OR are mixed without parentheses. Read as `(A AND B) OR C`. Add parentheses to choose. [show tree]" |
| `COMPAT_SOURCE_ALIAS` | "`source:PMLR` → `venue:ICML`. PMLR also hosts other venues, and only ICML is indexed." |
| `COMPAT_POP_DOLLAR` | "`model$` means zero or one extra character (`model`, `models`), as in Web of Science." |
These are drafts. The registry holds the shipped text, and golden tests pin it (number formatting included).

## Glossary (use exactly these. Same word in UI, docs, RIS `N1`, methods text)
| Term | Meaning | Not |
|---|---|---|
| query | what the user typed (`input`) | search term, prompt |
| canonical query | the fully parenthesised form with defaults explicit | normalized query, final query |
| index version | `index_version`, the searched snapshot | database version, build |
| papers / records | "papers" for hits in the UI. "records" in PRISMA and methods text | results, items, documents |
| match / matched | contains the exact normalized token | relevant, similar, related |
| excluded | removed by a **default** filter (track/status), counted in the banner | hidden, filtered out, dropped |
| limit | a filter the user wrote (`year:`, `venue:`). Not an exclusion | filter (ambiguous) |
| default filter | a clause added when the query has none (`track:`, `status:`) | preset, smart filter |
| expansion | the terms a wildcard matched | variants, suggestions, synonyms |
| translation | a Scholar/PoP construct rewritten to native syntax, with the reason | conversion, auto-fix |
| warning / error | read-with-caveat / not searched | issue, problem |
| search record | the frozen, citable search at `/record/[id]` | saved search, bookmark |
| reproduced | replay status: the same `index_version` and `query_version` were available, and `ids_hash` and `excluded` are equal | passed, verified |
| drifted | replay status: only a different index or query version is available; always shown with the reason (which inputs changed) and `+added / −removed` | changed, outdated |
| mismatch | replay status: the same versions, but the ids or `excluded` differ. A bug, shown as "do not cite" | failed, error |
| near-miss suggestion | phase 2 panel, never part of the set | result, recommendation |
Never write "stemmed", "fuzzy", "about", "~", "400+", or "results may vary".

## Standing strings
- Exclusion banner: `excluded: 212 workshop · 4 competition · 88 rejected`, with the unclassified line
  under it (`3 unclassified`, spec 05 §Components 5), and `excluded: none` when 0.
- Zero results: "0 papers match `<canonical>`." Then the banner, then "Check the expansions and the tree."
- Methods text: spec 05 §8 verbatim (`prisma-reporting`). Change it only by spec PR.
