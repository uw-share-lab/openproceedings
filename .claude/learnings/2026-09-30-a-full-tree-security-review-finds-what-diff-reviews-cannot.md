# A full-tree security review found three Musts that every diff review had passed

**Key lesson:** Before a public release, review the whole tree by attack surface, not by diff. Look for three things a diff review can't see: an id-keyed list applied to data written under other ids, a per-character loop that rescans ahead, and a case-table row that passes only because of what its fixture happens to contain.

- **Date:** 2026-09-30 · **Task:** task-067 · **Area:** ops
- **Artifacts:** `backend/src/openproceedings/query/normalize.py` (`_tokenize_each_char`), `backend/src/openproceedings/takedowns.py` (`same_paper`), `backend/src/openproceedings/api/state.py` (`Served.withheld_in`, `_open_turn`), `backend/src/openproceedings/takedown_check.py` (`_other_ids`), `.claude/hooks/protect-data-dir.sh`, `.claude/hooks/lib/cmdparse.py`, decision-022's addendum

## What we set out to do
Run TASK-067 AC#1 before an instance goes public. Five `security-reviewer` passes ran in parallel, one per
surface: the API and what it runs; ingest and crawlers; the takedown tooling (TASK-136); hooks and scripts;
CI, deploy, dependencies and the frontend. Then fix every Must and Should.

## What we learned
- **A per-character loop that scans ahead is quadratic, and here any client could reach it.** For each
  combining mark, `_tokenize_each_char` scanned the rest of the mark run and moved on by one character. Measured:
  `tokenize("́" * 20000)` took 13.4 s, and one 2,000-code-point `q` cost about 135 ms against about 3 ms
  for a normal search. The per-diff reviews of the tokenizer checked exactness, never cost on hostile input.
  The fix finds each run's end once, and tokens are unchanged: the frozen `tokenize_before` differential now also
  draws mark-heavy text. The existing `test_script_join_is_linear` pattern (CPU time, best of 9, a 4x input
  must cost under 8x) caught the regression at once.
- **A list keyed by id misses the same thing stored under another id.** The takedown list withheld the exact
  id on every version. An older version that held the paper under its pre-rekey id, or as a duplicate a later
  build merged, served the abstract, and `op takedown check` passed because it looked only for the listed id.
  `snapshot.withhold` already followed ids *forward* (build time). Nothing followed them *backward* (serve
  time, older versions). `same_paper` now takes the connected component over every snapshot's merges plus
  shared native ids.
- **A case-table row can pass by fixture accident.** The `git add -fA` rows in
  `test-openproceedings-gates.sh` were blocked only because the table's repo contains `ops/Takedowns/`. The
  `data/` check looked only at literal path arguments. In a repo with `data/` and no takedowns dir, `git add
  -fA` staged the corpus. When you add a row, ask which part of the fixture makes it pass.
- **Fail-closed rules need every trigger, not just the likely one.** A missing takedown list failed a load only
  when a list was already applied or the *served* snapshot had withheld something. A cold start after "list the
  id, SIGHUP" but before the rebuild, or after `current` was rolled back, served every listed abstract. Now
  a public `op serve` (off loopback) requires the list, and so does any snapshot on disk that withheld one.
- **A header-safety error can carry the secret.** `http.client` rejects a CR/LF header with a `ValueError`
  whose message quotes the whole `Bearer <token>`. `cli.main` printed it unscrubbed. The token's shape is now
  checked at login, and the transport maps `ValueError` to its type name only.

## Dead ends — don't repeat these
- Running the new linearity test red at full size: the quadratic version took over 2 minutes (9 repeats at
  20k). Show red with one small timing snippet, and keep the full test for green.
- Letting a background helper "wait for the mutation run" ended its turn with no report. Tell helpers to run
  mutation in the foreground and report after it.

## Decisions (and what would change them)
- Native ids are treated as one paper across venues and years (OpenReview forum ids, PMLR volume keys, NeurIPS
  hashes are the sources' own). Two different papers sharing a native id would over-withhold one abstract, the
  safe direction. A source whose native ids repeat across papers would reverse this.
- `op takedown check` flags another id only when title *and* authors match, so a different paper with the same
  title is not a permanent false failure.
- The pinned-open wait is bounded at 2 s, then 503 with Retry-After. It is a refusal, not a queue. A deployment
  whose legitimate pinned exports collide often would raise `pinned_open_wait_seconds`.

## Follow-ups
- [ ] task-148 — CI builds `deploy/web.Dockerfile` (confirmed by this review; also where to check the image's non-root runtime and whether Next needs a writable `.next/cache` before files are copied root-owned)
- [ ] task-149 — digest-pin `node:22-bookworm-slim` (confirmed)
- [ ] task-150 — Dependabot ignores `tantivy` (confirmed)
- [ ] task-065 — the api container mounts only a directory holding `withheld.txt`, never the log, and runs as neither root nor the operator (confirmed); rate limits and CORS on the deployed instance (TASK-067 AC#2)

## Propagated to
- Agent updated? — `.claude/agents/security-reviewer.md` (§How you work: hostile-input cost of per-character
  loops, id-keyed lists across versions, and case-table rows that pass by fixture accident)
- Test or hook added? — `backend/tests/unit/test_normalize.py` (`test_a_run_of_marks_is_linear`),
  `backend/tests/contract/test_takedowns.py` (the `aliased` store), `.claude/hooks/tests/` rows for every bypass
