---
name: bibtex-format
description: The openproceedings BibTeX export standard — @inproceedings entries, the <firstauthorlast><year><firsttitleword> key scheme with a/b de-duplication, field set, brace and special-character escaping, and the exact behaviour of refaudit's BibTeX parser that every export must satisfy. Use when writing or reviewing the BibTeX exporter under backend/src/openproceedings/api/exporters/, `op export --format bibtex`, or a .bib fixture.
---

# BibTeX export (spec 04 §Exports)

## Entry shape
```
@inproceedings{doe2024scaling,
  title     = {{Scaling Trust Benchmarks}},
  author    = {Doe, Jane and Roe, Richard},
  booktitle = {International Conference on Learning Representations (ICLR 2024)},
  year      = {2024},
  url       = {https://…},
  doi       = {…},
  abstract  = {…},
  keywords  = {main},
  openproceedings_id = {op:iclr:2024:iilhN2MycO},
  note      = {openproceedings a1b2c3d4e5f6 · query 9f8e7d… · 2026-09-25}
}
```
- Every value is **brace-delimited**, even `year`. Never quote-delimited: quotes and braces have
  different escaping rules, and one convention keeps the escaping code small.
- `title` gets an inner brace pair so that bibliography styles keep its capitalisation.
- `booktitle` is the same venue string as RIS `T2` (`.claude/skills/ris-format/SKILL.md`). `keywords` is
  the track. Provenance goes in `note = {openproceedings <index_version> · query <canonical_hash> · <UTC
  date>}` (spec 04 §Exports), the same line as RIS `N1`: `·` is U+00B7, the date `YYYY-MM-DD` UTC. Omit `doi`, `url` and `abstract` when they
  are absent. Never write an empty field.
- `openproceedings_id = {<id>}` is on **every** entry (spec 04 §Exports), so a round-trip recovers the id
  of every record, proceedings-only ones (PMLR, NeurIPS `nips-<hash>`) included, which have no forum `url`
  to parse. refaudit's field regex `(\w+)\s*=` accepts the underscore.
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
5. **De-duplication:** collisions are resolved by suffixing `a`, `b`, `c`, … in the export's stable
   order. Decide once whether the first occurrence stays bare (streamable with a seen-dict) or also gets
   `a` (needs a pre-pass over the set). Pin the choice with a fixture that has three colliding papers.
   Past `z`, continue with `aa`.

Keys are unique **within one file** only. The same paper can get a different key in a different query's
export. Never present a key as a stable identifier. The id lives in `openproceedings_id`.

## Escaping
Abstracts contain real LaTeX (`$\epsilon$-DP`, `\textbf{63.7\%}`). Keep it; escaping it would change the
text screeners see.
- **Braces must balance** in every value. If a value's braces don't balance, escape every brace in it as
  `\{`/`\}`. refaudit's brace matcher skips the character after a backslash, so escaped braces are safe.
- Escape bare `%` as `\%` (an unescaped `%` comments out the rest of the line in LaTeX), and bare `&`,
  `#` and `_` outside math.
- The `@type{key,` pattern must never appear inside a value. refaudit finds entries with a regex over
  the whole file, not only at line starts. Write `@` in values as `{@}`.
- Collapse newlines inside values to spaces (refaudit normalises whitespace anyway).

## refaudit's parser (`refaudit/src/refaudit/bibtex.py`, read-only reference)
- Entries match `@(\w+)\s*[{(]\s*([^,\s{}]+)\s*,`. `@comment`, `@preamble` and `@string` are skipped.
  Macros are **not** expanded, so never emit `@string` or bare macro values (`booktitle = neurips`).
- Field names match `(\w+)\s*=`, lower-cased. A field repeated in one entry keeps the **last** value.
- An unbalanced brace runs to the end of the file and swallows every later entry, **with no error**.
- Files are read as UTF-8 with `errors="replace"`, so bad bytes turn into U+FFFD instead of failing.

## Tests (`backend/tests/contract/`)
Parse the exported file with refaudit's `parse_string` (as a test-only dependency or a vendored copy;
decide at implementation time) and assert: the entry count equals `X-Total`, keys are unique, the ids
recovered from `openproceedings_id` equal `match_ids` (a PMLR-only fixture record included), `title` (minus its protective outer braces), `author`, `year` and `abstract`
round-trip after whitespace normalisation, and the unbalanced-brace, `%`, `@` and non-ASCII-author fixtures parse into the right
number of entries.
