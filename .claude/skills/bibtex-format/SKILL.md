---
name: bibtex-format
description: The openproceedings BibTeX export standard — @inproceedings entries for accepted papers and @unpublished for every other status, the <firstauthorlast><year><firsttitleword> key scheme with a/b de-duplication, field set, brace and special-character escaping, and the exact behaviour of refaudit's BibTeX parser that every export must satisfy. Use when writing or reviewing the BibTeX exporter in backend/src/openproceedings/export.py, `op export --format bibtex`, or a .bib fixture.
---

# BibTeX export (spec 04 §Exports)

## Entry shape
```
@inproceedings{doe2024scaling,
  title     = {{Scaling Trust Benchmarks}},
  author    = {Doe, Jane and Roe, Richard},
  booktitle = {International Conference on Learning Representations (ICLR 2024)},
  year      = {2024},
  abstract  = {…},
  abstract_source = {PMLR https://proceedings.mlr.press/v202/okafor23a.html},
  url       = {https://…},
  doi       = {…},
  keywords  = {main, status:accepted},
  openproceedings_id = {op:iclr:2024:iilhN2MycO},
  note      = {openproceedings a1b2c3d4e5f6 · query 9f8e7d… · exported 2026-09-25}
}
```
- Every value is **brace-delimited**, even `year`. Never quote-delimited: quotes and braces have
  different escaping rules, and one convention keeps the escaping code small.
- `title` gets an inner brace pair so that bibliography styles keep its capitalisation.
- **Only `status: accepted` is `@inproceedings`** (spec 04 §Exports, task-004 review). Any other status
  (`rejected`, `withdrawn`, `desk_rejected`, `unknown`) is `@unpublished`, with **no `booktitle`**. Its
  `note` is `Submitted to <venue string>, status: <status in words>. <provenance line>`: `desk rejected`,
  never `desk_rejected`, since a bare `_` in a typeset `note` breaks LaTeX (`keywords` keep the machine form
  `status:desk_rejected`). Any other `_` in `note` (a record id's) is written `\_`. A rejected paper must
  never become a citation into a conference.
- `booktitle` is the same venue string as RIS `T2` (`vocab.venue_name()`, also importable from `export`,
  `.claude/skills/ris-format/SKILL.md`). It is the conference's name, not a proceedings title, since workshop
  and rejected papers are in no proceedings. `keywords = {<track>, status:<status>}` on every entry. Provenance
  goes in `note = {openproceedings <index_version> · query <canonical_hash> · exported <UTC date>}`, plus
  ` · record <record_id> · searched <UTC date>` for an export pinned by a search record (spec 04 §Exports),
  the same line as RIS `N1`: `·` is U+00B7, the dates `YYYY-MM-DD` UTC. Omit `doi`, `url` and
  `abstract` when they are absent. Never write an empty field.
- `openproceedings_id = {<id>}` is on **every** entry (spec 04 §Exports), so a round-trip recovers the id
  of every record, proceedings-only ones (PMLR, NeurIPS `nips-<hash>`) included, which have no forum `url`
  to parse. refaudit's field regex `(\w+)\s*=` accepts the underscore.
- `abstract_source = {<site> <url>}` after `abstract`, when the abstract has an attribution (TASK-138,
  decision-018; spec 04 §Exports): the same words as RIS's `N1  - Abstract source:` line (the results list's
  site name, ` (via RIS import)` for a `ris` claim, the url when there is one), from the snapshot's
  `RecordFile.attributions`. Escaped like every value (`_braced`, as in `url`: a url's `%`, `&`, `#` gain a
  backslash, `@` is written `{@}`, and when its braces don't balance every brace is dropped). A new field, not a change to `note`: `note` keeps exactly the provenance line (after the `Submitted
  to` sentence), so it stays additive (decision-021); refaudit's `(\w+)\s*=` reads the name and styles don't
  print it. When a pinned export's snapshot can't be verified (decision-021) there is no `abstract` and no
  `abstract_source`; instead `abstract_withheld = {Abstract withheld: … (decision-018).}` (`export.WITHHELD`), a
  field rather than a sentence in `note`, since changing `note` is breaking and styles typeset it.
- `author`: `Last, First` joined by ` and `. Brace a name that contains the word `and` or a comma, or
  that is an organisation (`{OpenAI Team}`).

## Key scheme
`<firstauthorlast><year><firsttitleword>`, for example `doe2024scaling`.
1. Family name of the first author, from `.claude/skills/record-schema/SKILL.md` (do not guess by
   splitting a display name). No author: `anon`.
2. The four-digit year.
3. The first word of the title. Spec 04 does not skip stopwords, so `A Survey …` gives `…a`. Keep the
   literal rule unless a spec PR changes it.
4. Each part is NFKD-folded to ASCII, lower-cased and stripped to `[a-z0-9]`. refaudit's key regex
   rejects `,`, whitespace and braces. LaTeX handles non-ASCII keys badly.
5. **De-duplication (decision-007):** the first paper with a key keeps it **bare**; each later one, in the
   export's id order, takes the next suffix not yet issued in the file: `a`, `b`, … `z`, `aa`, `ab`, …. A
   paper whose real key equals an issued suffix moves on (`smith2024deepa` → `smith2024deepaa`). This is
   what Better BibTeX and JabRef do, and it streams with a set of issued keys (all-suffixed would need a
   pre-pass). Pinned by `test_three_colliding_keys_the_first_bare_then_a_then_b`.

Keys are unique **within one file** only. The same paper can get a different key in a different query's
export: a superset keeps earlier keys only when the added colliding papers sort after them
(`test_a_superset_keeps_keys_unless_an_added_paper_sorts_first`). Never present a key as a stable
identifier. The id lives in `openproceedings_id`.

## Escaping
Abstracts contain real LaTeX (`$\epsilon$-DP`, `\textbf{63.7\%}`). Keep it; escaping it would change the
text screeners see.
- **Braces must balance** in every value. If a value's braces don't balance (counted with and without
  regard to backslashes), drop every brace in it, and the backslash that escaped one (`_debraced`): BibTeX
  counts braces without regard to backslashes while refaudit honours `\{`, so an escaped brace would be read
  differently by the two and could swallow the next entry. Balanced, unescaped braces stay (`{BERT}`).
- Escape bare `%` as `\%` (an unescaped `%` comments out the rest of the line in LaTeX), and bare `&` and
  `#`. A bare `_` is escaped as `\_` only in `note`, which styles typeset; other values keep it (a url's or
  an id's `_`, and `$…$` math, must read back unchanged).
- The `@type{key,` pattern must never appear inside a value. refaudit finds entries with a regex over
  the whole file, not only at line starts. Write `@` in values as `{@}`.
- Collapse newlines inside values to spaces (refaudit normalises whitespace anyway).
- `export._braced` runs once per field of every exported record, so each pass is skipped when its
  character doesn't occur (no brace: no balance count; no `&%#`: no escaping; no `@`: no `{@}`), and `&%#`
  are escaped in one pass that reads each backslash run whole (`(\\*)([&%#])`, escaped only after an even
  run). A speed-up here must stay byte-identical: `tests/unit/test_export_braced.py` holds `_braced` to a
  frozen copy of the pre-guard function under Hypothesis.

## refaudit's parser (`refaudit.bibtex`, from the pinned `refaudit` PyPI package)
- Entries match `@(\w+)\s*[{(]\s*([^,\s{}]+)\s*,`. `@comment`, `@preamble` and `@string` are skipped.
  Macros are **not** expanded, so never emit `@string` or bare macro values (`booktitle = neurips`).
- Field names match `(\w+)\s*=`, lower-cased. A field repeated in one entry keeps the **last** value.
- An unbalanced brace runs to the end of the file and swallows every later entry, **with no error**.
- Files are read as UTF-8 with `errors="replace"`, so bad bytes turn into U+FFFD instead of failing.

## Tests (`backend/tests/contract/`)
Parse the exported file with `refaudit.bibtex.parse_string` (`refaudit` is a pinned root dev dependency,
added with task-036; never vendored) and assert: the entry count equals `X-Total`, keys are unique, the ids
recovered from `openproceedings_id` equal `match_ids` (a PMLR-only fixture record included), `title` (minus its protective outer braces), `author`, `year` and `abstract`
round-trip after whitespace normalisation, and the unbalanced-brace, `%`, `@` and non-ASCII-author fixtures parse into the right
number of entries. `abstract_source` round-trips to the snapshot's attribution
(`backend/tests/contract/test_export_attribution.py`), and a url with `%`, `&` and `#` in it swallows no later
entry.
