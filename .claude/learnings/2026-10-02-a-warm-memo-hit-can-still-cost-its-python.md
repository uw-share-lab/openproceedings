# A warm facet-memo hit still pays for its Python, and a clause's isolated cost isn't its cost in a search

**Key lesson:** Profile the warm path before blaming a collection: TASK-166's +31% was the Python loop over hundreds of memoised facet combos, not Tantivy. Time a clause inside the whole search, alternated old against new, before you estimate a schema change: the `"AI agent$"` id set's isolated cost fell from 11.3 to 6.2 ms with an indexed u64 `ord`, but the overloaded warm-search measurements show no measurable end-to-end difference.

- **Date:** 2026-10-02 · **Task:** TASK-166, TASK-167 · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/engine/tantivy_engine.py` (`facets`/`combos` `over`), `backend/src/openproceedings/search.py`, `backend/tests/bench/exclusions_alternate.py`, `backend/tests/bench/verified_forms.py`, `docs/results/2026-10-02-exclusions-and-verified-forms.md`

## What we set out to do

TASK-166: let callers that need only exclusion counts skip the facet-combination aggregation. TASK-167: remove the ~10 ms the `"AI agent$"` clause's id set costs on each search, or show that no change is worth making.

## What we learned

- Exclusion accounting on a warm engine never collects again (the combos are memoised). Its cost was `facets`' Python loop over every (venue, year, track, status) combo (1,080 on the 5k broad query; cProfile: `facets` and its `all()` took about 75% of the call). Aggregating only track and status (`over`) leaves 45 combos.
- A verified clause's ids are rebuilt as a term set on every search. An indexed u64 term set resolves 2–9x faster than one on the text `id` when timed alone. Inside a whole search, though, the set is one MUST clause that the rarer clauses drive, so the warm search barely moves (29.4 vs 29.7 ms synthetic, 26.4 vs 25.6 ms real).
- A plain SCHEMA_VERSION bump makes `unservable()` refuse every existing index, which strands pinned records. The fix is to serve the previous schema too, with its own path.

## Dead ends — don't repeat these

- A const-0 `regex_phrase_query` (each wildcard an alternation of its expansions) matched the verified ids exactly but cost about 2–4x the id set: it reads positions for every candidate.
- `term_set_query` on the fast-only `ord` field fails with "Field "ord" is not indexed". A fast field doesn't stand in for an indexed one.
- On this shared machine the load averaged 30-230 during the first runs. Alternate the two paths round by round, record the load, and rerun when it's quieter.

## Decisions (and what would change them)

- TASK-167: SCHEMA_VERSION 3 indexes `ord`, and the code serves schema 2 beside it (`SERVED_SCHEMAS` → `SchemaForm`), so records pinned to a schema-2 index still replay `reproduced` (checked on the real index with records saved by the pre-change code). Kept by owner decision despite the small end-to-end gain. Schema 2 is retired once no record pins a schema-2 index.
- The two-version pattern (a per-index form, read from the manifest, that the engine branches on) is also what a TOKENIZER_VERSION bump that must keep old indexes replayable would follow.

## Follow-ups

- none

## Propagated to

- Skill / agent / CLAUDE.md updated? — `.claude/skills/ast-compilation/SKILL.md` (the `over` narrowing), spec 03 §Exclusion accounting
- Skill updated: `index-versioning` §Two served schemas, `tantivy-indexing`.
- Test or hook added? — `backend/tests/unit/engine/test_facets_equal.py`, `backend/tests/unit/test_search_overlap.py`, `backend/tests/unit/engine/test_served_schemas.py`, `backend/tests/contract/test_records.py` (schema-2 replay)

## Addendum — 2026-10-02

Recovery review corrected the historical 0–3% interpretation: no measurable end-to-end gain was shown on
the overloaded machine. `tests.bench.id_sets` separates Python query construction from Tantivy collection
on the actual same-snapshot index pair, with lazy ordinal-table first-use, subsequent-use and retained-memory
measurements. Cold benchmarks reset `_ords` alongside compiled, verified, expansion and facet memos. The
original broad COMBO benchmark remains; a separate defaults benchmark measures the narrower caller.

A schema-only benchmark also verifies both manifests and compares snapshot, tokenizer, ranking and Tantivy
inputs before timing: identical IDs do not establish identical titles/abstracts. The negative-control test
keeps IDs equal while changing each manifest input and proves the benchmark guard refuses it.
