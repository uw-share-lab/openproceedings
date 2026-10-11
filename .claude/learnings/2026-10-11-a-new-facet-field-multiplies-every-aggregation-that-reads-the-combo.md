# A new fast field in a facet combo multiplies every aggregation that reads the combo, and only the 80k bench showed it

**Key lesson:** When a field joins an engine's facet combo, make each aggregation read only the fields its caller filters on, and find the cost with the synthetic 80k bench (`tests.bench.report_80k`), not the real-corpus bench, because the real corpus hides a field that follows another one.

- **Date:** 2026-10-11 · **Task:** TASK-215, TASK-220 (decision-049, new venues milestone C; follow-ups TASK-230..232) · **Area:** engine, eval
- **Artifacts:** commits `f5dad7bd` (index schema 4), `566cafcd` (the fix), `docs/results/2026-10-11-bench.md`, `docs/results/2026-10-10-bench-group-counts.md`, `docs/specs/03-search-engine.md` §Performance budgets, `docs/results/2026-10-11-perf-regression.md` (the bisect and profiles)

## What we set out to do
Add `abstract_kind` as a raw fast field (index schema 4) and verify milestone C on the real data: snapshot diff, index parity, coverage and benchmarks.

## What we learned
- **A fifth combo level multiplied the group counts' work.** `TantivyEngine.counts` aggregated every tree's base over the engine's whole combo, though a count sums only the combos that pass its trees' top-level filters (usually just track and status). On the synthetic 80k corpus, where abstract presence is random per record, a counted base went from 1,080 combos to 1,250-1,722. `main-3-sources` went from 74.9 ms (before group counts) to 632.8 ms p95; the bisect pinned it to `f5dad7bd`.
- **The p95 cliff was garbage collection.** The memo kept about 60% more combo tuples, which survive into generation 2 while the report holds the resident 80k corpus (about 810k tracked objects), so a full GC of roughly 500 ms ran 10 times in 200 rounds against 3 (`gcprobe`); 5% slow rounds is exactly where p95 sits.
- **The real corpus hid it.** There `abstract_kind` follows venue, so it adds few combos, and the real-corpus group-count report stayed in budget (worst p95 76.5 ms) while the synthetic one did not.
- **The fix is to aggregate less, not to cache more.** `counts` now aggregates the union of its trees' top-level filter fields (or `status` alone when none filters), and the bitwise path reads the same narrowed fields. Facets still aggregate the whole combo, because `abstract_kind` is a facet. Membership and counts are unchanged (the oracle and property tests in `test_group_counts.py` pass, plus two new tests that failed before the fix). `main-3-sources` is 110.7 ms after it.
- **The baseline was stale.** The 2026-10-02 bench (68.8 ms) predates group counts (TASK-176, TASK-197), and `report_80k` was not re-run after they landed, so dev was already about 125 ms p50 before milestone C. A budget claim is only as old as the last run of the report that backs it.
- **A kind change that no content hash shows needs its own diff key.** `abstract_kind` is derived and never hashed, so a record whose abstract came from nowhere (`none`) and now from OpenAlex changes no `content_hash` of the fields a reader cares about. `op snapshot diff` therefore reports `abstract_kind` as its own key with `[old, new]` pairs and a transition tally (`none->openalex`: 2,158), and the real build's check was that this tally equalled `attached_doi + attached_title` and that `changed` was exactly the `abstract` field.
- **Retire an old schema before adding a new one.** Schema 2 was checked with `op index retire --dry-run` (0 pins) and its code path and tests dropped before schema 4 was added, so served schemas stayed at two and the engine's per-schema `SchemaForm` stayed small. The four local schema-2 indexes were deleted on 2026-10-10 with the owner's approval.

## Dead ends — don't repeat these
- Citing the real-corpus bench alone as proof that a schema change is within budget.
- Benchmarking a "quiet" machine without checking `sysctl -n vm.loadavg` at both ends: a first rerun of `report_80k` at a start load of 7.2 overwrote the file and was invalid.
- Comparing against the last report without checking it covers the feature (group counts) under test.

## Decisions (and what would change them)
- `main-3-sources` at 110.7 ms is reported honestly in spec 03 and filed as TASK-230, not hidden by a harness tweak → the excess is TASK-176's counting (65 ms without it) and part harness (the resident corpus) → fixed by splitting counted trees across workers, or by an owner decision to accept the miss on a synthetic corpus.

## Follow-ups
- [x] TASK-230 — `/search` first page for main-3-sources over 100 ms on the synthetic 80k
- [x] TASK-231 — owner review of the OpenAlex fill's refusals
- [x] TASK-232 — a source for the 3,648 AAAI 1980-2008 records without an abstract (done: the final rebuild gives 4,536 of 4,709 AAAI's own abstract)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `docs/specs/03-search-engine.md` §Performance budgets (the miss and the regression stated); `.claude/skills/index-versioning/SKILL.md` (schema 2 retired before schema 4); no skill rule for the combo yet.
- Test or hook added? — yes, in the branch: `test_counts_aggregate_only_the_fields_their_trees_filter` and `test_a_count_of_trees_without_filters_aggregates_one_field` (`566cafcd`); no hook.

## Addendum, 2026-10-11: the CI bench caught a cold path the reports missed, and the merge queue merged anyway
- **CI's `bench` job compares every benchmark's minimum with the base.** It failed on PR #134: seven cold `match_ids` benchmarks with exclusion accounting were 31-40% slower. `exclusions.excluded`'s default counter aggregated the engine's whole five-field combo, though exclusions read only track and status; `search.run` already passed `over=ORDER`, so only the default path (benchmarks, tests, reports) paid. Fixed in `b74c38b7`, and `51b0577f` nests the aggregation fewest-valued first, so full-combo facets run within 20% of base too.
- **`bench` is not a merge-queue required check.** The queue merged PR #134 at its earlier head while `bench` was red. Push a fix as its own follow-up PR, and read every check (not only the required ones) before treating a PR as done.
