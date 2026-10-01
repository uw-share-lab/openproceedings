# A property's "rows are only added" was wrong, not reconcile, because reconcile rebuilds a changed record's rows the way dedup would

**Key lesson:** When a property's "nothing is removed" oracle fails against code that recomputes derived rows from the final state, find which documented invariant wins (here: every row equals what dedup run again would write) before touching the code, and write the oracle as "only X may change, and nothing it named is lost", not "nothing is removed".

- **Date:** 2026-10-01 · **Task:** task-154 · **Area:** ingest
- **Artifacts:** b15782b; `backend/tests/unit/ingest/test_reconcile.py` (`NIGHTLY_154`, `test_only_unlisted_openreview_acceptances_change_and_only_to_unknown`, `test_a_note_whose_openreview_sources_disagree_has_each_value_against_unknown`); `.claude/skills/dedup-rules/SKILL.md`; nightly run 36723434594; c28628c (TASK-072)

## What we set out to do
Turn nightly `suite-ci` (2,000 examples) green after the reconcile property failed on its last line,
`assert set(base.conflicts) <= set(once.conflicts)  # rows are only added`.

## What we learned
- The shrunk input was a note `op:iclr:2024:IjKl9012` with a v2 claim `accepted` and a same-id v1 pool
  record `rejected`. Dedup writes one `precedence:openreview_v2` status row (accepted/v2 over rejected/v1).
  Reconcile demotes the note to `unknown` and, by design since TASK-072 (c28628c), replaces a changed
  record's precedence status rows with what its claims now resolve to: `unknown` over accepted/v2 and
  `unknown` over rejected/v1. The old row disappears, so "only added" fails.
- The code was right: keeping the stale row would contradict decision-005 (a record is what its claims
  resolve to, and the precedence row is its conflicts.csv row) and the sibling property "dedup on the output
  changes no row". The oracle had been written from the dedup-rules sentence "conflicts only gain the
  reconciled records' status rows", which was imprecise. Two documented invariants disagreed, and the one
  the rest of the system relies on (rows = dedup's rows) won.
- The fixed oracle allows exactly one kind of disappearance (a changed record's `precedence:` status row)
  and requires every non-`unknown` value that row named to still appear as `value_b` against `unknown`. Two
  reconcile mutants (drop one fresh row; drop unchanged records' status rows) are killed by it.
- Not a regression from the recent PRs (TASK-137/139/142/147): the oracle line, the v1 source in the strategy
  and the replace logic all date from TASK-072. It took 2,000 examples to draw a same-id v1 twin with a
  different status, so a 200-example PR run would rarely see it.
- The real snapshot (2026-09-29-333bf918c9b3) has no record in this case, so nothing shipped was affected.

## Dead ends — don't repeat these
- Triaging from the failure text: it read as "a NeurIPS 2024 listing" because the strategy reuses the
  NeurIPS `LISTING` URL constant for every venue's crawl. The input was ICLR. Printing the shrunk input's
  records and both conflict sets (base vs once) settled it in one run. Do that first; don't infer the venue
  from a URL a strategy fills in.
- Reaching for reconcile first because the assertion names its output. The right first question was which
  documented rule the oracle encodes and whether another documented rule contradicts it.

## Decisions (and what would change them)
- Fix the oracle and the skill sentence, leave reconcile unchanged → decision-005 and "dedup on the output
  changes no row" both require the recomputed rows. This would change only if conflicts.csv were made an
  append-only history, in which case dedup idempotence would have to change too.
- The exact shrunk input is an explicit `@example` (`NIGHTLY_154`, checked equal to the blob's input), plus a
  table test that pins the rows, so the case outlives any strategy change.

## Follow-ups
- None. Reconcile code didn't change, so no crawl replay was needed.

## Propagated to
- Skill: `.claude/skills/dedup-rules/SKILL.md` (b15782b) states the exception: a reconciled record's earlier
  `precedence:` rows give way to the ones dedup would write. `.claude/skills/property-testing/SKILL.md`
  now says that a counterexample can be the oracle's fault, how to decide, and to print the shrunk input
  before trusting the failure text.
- Test: the `@example` and the table test in `backend/tests/unit/ingest/test_reconcile.py` (b15782b).
