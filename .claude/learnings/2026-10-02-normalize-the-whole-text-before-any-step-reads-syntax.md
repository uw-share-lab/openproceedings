# A tokenizer that normalizes per character after a syntax scan is form-dependent; NFKC the whole text first

**Key lesson:** If any step of a tokenizer reads syntax (LaTeX here) before Unicode normalization, the same text in NFC and NFD (or NFKC) can tokenize differently; make the canonical form step 1 over the whole text, keep raw offsets with a per-character owner map (`normalize._View`), and when the change needs a `TOKENIZER_VERSION` bump, keep the old version served (`SERVED_TOKENIZERS`, a frozen copy of its code) and pass the index's version to every reader of text, the parser and `canonical_hash` included, or records pinned to old indexes stop reproducing.

- **Date:** 2026-10-02 · **Task:** n/a (owner decision 2026-10-02; TASK-168's finding) · **Area:** query
- **Artifacts:** `backend/src/openproceedings/query/normalize.py` (`_view`, `_owners`, `TokenizerForm`), `backend/tests/unit/test_tokenizer_versions.py`, `backend/tests/unit/tokenizer_v2/`, `backend/tests/contract/test_records.py::test_a_record_saved_on_a_tokenizer_2_index_reproduces_after_the_tokenizer_3_build`, `docs/results/2026-10-02-tokenizer-3.md`

## What we set out to do

Make every Unicode form of a text tokenize alike (NFD `Caf\é` gave `caf`, NFC `caf e`), without breaking the replay of records pinned to existing indexes.

## What we learned

- "All four forms alike" means `tokens(t) == tokens(NFKC(t))`, so the canonical step has to be NFKC, not NFC: NFC-first still splits `\ﬁ`, `$x^²$` and full-width `＼`. A consequence: full-width `＄`/`＼` become LaTeX (spec 02 said they were text).
- Token texts are exact by construction (the old loop run on `NFKC(text)`); only spans need care. Replaying NFKD, canonical ordering and composition on (character, raw range) pairs gives each NFKC character its raw characters; interleaved marks (`=` + U+0345 + U+0338) need the old task-075 rule (first span ends where the second starts) to keep spans disjoint.
- A tokenizer version is not only an index input: the parse (terms), `canonical_hash`, the highlighter and the lexer's LaTeX scan all depend on it, so the version must come from the engine's manifest (`TantivyEngine.tokenizer_version`), not the module constant. `replay` now parses with the tokenizer of the index it runs on.
- Recovery found that re-parsing a query on its target version is too late if its initial current-version parse refuses it. API exports and CLI search/export/save now check raw length, select the index, then validate once with its tokenizer. Source aliases, scope warnings and filter-edit splice/wrap probes must also pass that version.
- The editor needs the same version boundary: independent server-generated v2/v3 goldens caught 47 lexer/Lezer differences, and a live CodeMirror meta switch needs a language compartment to preserve selection and undo history. Missing or unsupported metadata defaults to the current lexer.
- The 95,877-record local corpus had no title/abstract token changes; all 14 historical saved records reproduced on their pins, and new-only replay reported tokenizer drift with no ID changes (result document).
- Hypothesis found two real bugs in the first draft: `first_math_end` answering for a `\(` region, and the lexer's own Pandoc checks reading raw characters where the tokenizer reads NFKC (a spacing accent after `$` is a space; `½` begins with a digit).

## Dead ends — don't repeat these

- Translating only the four `$`/`\` look-alikes in the tokenizer: compatibility characters next to them (`´`, `½`, `ﬁ`) still change LaTeX decisions; only whole-text NFKC is form-independent.
- Calling the raw scan as `math_regions(text, "2")` to mean "as it stands": a version string standing for a behaviour; use a helper (`_regions`) and branch on the form.

## Decisions (and what would change them)

- Tokenizer 3 = NFKC first; serve 2 and 3 (decision-031). Retire 2 once no record pins a tokenizer-2 index.

## Follow-ups

- Allocate the final tokenizer decision ID after the controller resolves the provisional decision-031 collision; the reference above remains provisional until then.

## Propagated to

- Skill / agent / CLAUDE.md updated? — `.claude/skills/token-contract/SKILL.md`, `.claude/skills/index-versioning/SKILL.md`, `.claude/skills/codemirror-lezer/SKILL.md`, specs 02/03/04
- Test or hook added? — `test_tokenizer_versions.py` (frozen-copy equality, four-form property, NFC/NFD parse property), golden `FORMS`/`CHANGED_IN_3`, nightly exhaustive four-form check, contract replay test; target-selection/source/filter regression tests; independent v2/v3 editor goldens and live meta-switch/undo test

## Addendum — 2026-10-02

The schema-3 performance branch and tokenizer-3 branch change independent inputs. Merging one version
selector over the other strands valid legacy indexes. Preserve both explicit build parameters and both
manifest dispatch tables, then test schema 2/3 × tokenizer 2/3: the schema-ranking property and verified
clause tests run for each tokenizer; tokenizer-pinned replay runs for each schema; schema-pinned replay
runs for each tokenizer. The integration focused run passed 227 tests (`/tmp/tokenizer-perf-integration-focused.log`).
Propagated to the index-versioning skill and the parametrized engine/record tests. Historical real-corpus
figures above describe the earlier replay run; this integration result uses synthetic snapshots.
