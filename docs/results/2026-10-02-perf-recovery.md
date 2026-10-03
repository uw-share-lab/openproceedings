# TASK-166/167 recovery measurements

The historical `2026-10-02-exclusions-and-verified-forms.md` measurements ran at load 30–155 on 8 CPUs.
They show no measurable end-to-end schema gain. The isolated 11.3 → 6.2 ms claim is historical and lacked
a committed in-index harness separating Python construction from Tantivy collection.

The recovery uses read-only, same-snapshot schema-2/schema-3 indexes and the shared `heavy.sh` lock.
`tests.bench.id_sets OLD_INDEX NEW_INDEX 100` measures the abstract AI-agent wildcard clause's text-id
and ordinal query construction separately from collection of preconstructed queries. It reports ordinal
table first/subsequent construction, whole-tree compile with verified/expansion caches warm but compiled
cache cleared (table first use versus retained), compile memo hits, and retained table memory from the
dict plus integer values, excluding existing id strings. This is an object-size estimate, not RSS.

`tests.bench.exclusions_alternate 5k 200` compares all-facet COMBO aggregation and track/status ORDER
aggregation, alternated each round, asserting equal exclusion counts before timing. Warm runs keep the
facet memo; cold aggregation runs clear only that memo. Load is printed before each phase.
`test_bench` preserves the original all-facet broad benchmark and adds the narrower caller separately.

`tests.bench.schemas_alternate OLD_INDEX NEW_INDEX 200` checks every Trust-Evals string's whole ID and
float-score order in every sort, facets and exclusions before timing whole warm searches alternately.

`tests.bench.report_80k ../docs/results/2026-10-02-schema-3-bench.md` builds its own synthetic 80k index.
Cold runs clear every engine cache: compiled queries, verified clauses, wildcard expansions, facet combos
and the lazy ordinal lookup. The opened index and OS page cache remain warm. Exclusion-only reporting
uses `over=ORDER`; older reports retained some caches and aggregated COMBO, so cold columns are not
comparable. Fresh measurements and exact validation evidence are added after the locked run completes.
