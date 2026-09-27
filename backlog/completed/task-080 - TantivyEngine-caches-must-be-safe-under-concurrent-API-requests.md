---
id: TASK-080
title: TantivyEngine caches must be safe under concurrent API requests
status: Done
assignee:
  - '@index-engineer'
created_date: '2026-09-27 07:26'
updated_date: '2026-09-27 07:40'
labels:
  - api
  - engine
milestone: m-3
dependencies:
  - TASK-034
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-034. The API serves one TantivyEngine to every request, and sync handlers run in FastAPI's thread pool, so its per-engine caches are touched concurrently. Two check-then-read sites can raise KeyError (a 500) when another thread clears the cache in between: engine/tantivy_engine.py compile() ('if key in self.compiled: return self._copy(self.compiled[key])' vs the clear() at >1,000 entries) and engine/compile.py verified() ('if key not in self.verified_cache: ... ; ids = self.verified_cache[key]' vs TantivyEngine.compile's self.verified.clear()). expand() has the same shape with self.expanded. Fix with a single .get() read (or a lock) and add a threaded test. Must land before task-035's routes serve traffic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No cache read in TantivyEngine/Compiler can observe a key vanish between check and read (single .get() or a lock)
- [x] #2 A test runs many searches from several threads against one engine while the caches are forced to clear, with no exception and identical results to a serial run
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Audit every shared mutable cache/memo in engine/ and query/ reachable from a served TantivyEngine. 2. Name the clear thresholds (class attributes) so a test can shrink them. 3. Threaded test first (8 threads, thresholds 0, tiny switch interval) vs a serial run; show it fails on the old code. 4. Fix: single .get() reads + tolerate recomputation (values are pure functions of the immutable index). 5. Mutate the fix back; micro-timing before/after; full pytest, make lint/tooling/mutate-changed.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Audit (every shared mutable object a served TantivyEngine reaches):
- compiled (engine): check-then-read race → KeyError. FIXED: one .get().
- verified (engine, passed to Compiler as verified_cache): not-in / store / re-read race → KeyError. FIXED: one .get(), compute into a local, store the complete list.
- expanded (engine): already one .get(); entries stored complete (tuple or int). SAFE; comment added.
- len>bound then clear() on each memo: not atomic, harmless (double clear or a few entries of overshoot); bounds named MAX_COMPILED/MAX_VERIFIED/MAX_EXPANDED so tests can shrink them.
- Compiled memo entries: stored after Compiler.compile returns, never mutated; callers get _copy (own lists); the shared tantivy.Query is immutable. SAFE.
- Compiler (self.out, lists), facets' local compiled dict, expansions() dict, normalize._Closers.tables, highlight._Highlighter: per call. SAFE.
- searcher / index / ids / ranking: read-only after __init__; tantivy Searcher and Query used concurrently in the threaded test without error. SAFE.
- Module-level dicts (mathsyms, lexer, parser, vocab, defaults, diagnostics, export, index.RANKING_PARAMS): constants, never mutated after import. No lru_cache anywhere in engine/ or query/.
Why no lock: every memo value is a pure function of its key and the immutable index, so a clear or a lost race only recomputes the same value; a lock would either serialise searches (held across verification, seconds cold) or need per-key locks, for no correctness gain.
Reproduction: on plain dicts under CPython 3.12 the in→[key] window has no eval-breaker point (switches happen only at calls/backward jumps), so the race was latent (real under free-threaded builds or any Python-level hook). The test swaps each memo for a dict subclass that yields the GIL inside every op; old code failed 3/3 (KeyError on compiled and on verified).
Mutation (5 runs each): M1 compiled in/[] KeyError 5/5; M2 verified re-read KeyError 5/5; M3 expanded in/[] KeyError 5/5; M4 verified list published before filled: results differ from serial 5/5. Fixed code 5/5 pass (~2 s).
Micro-timing, 5k fixture, best of 7 (before → after): compile memo hit 38.0 → 37.3 µs; search main-1 warm 0.864 → 0.863 ms; compile with verified hit 114.7 → 118.7 µs (noise).
Checks: uv run pytest 2354 passed, 1 skipped (OP_EXHAUSTIVE); make lint ok; make tooling ok; make mutate-changed 7 mutants, 0 problems (tooling mutants only; engine mutants run by hand above).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
TantivyEngine's memos are safe under concurrent API requests. compile() and Compiler.verified() now read their memo entry with one .get() and store only complete values (expand() already did), so a clear from another thread can't raise KeyError; a race only recomputes the same value from the immutable index. The clear bounds are named class attributes (MAX_COMPILED/MAX_VERIFIED/MAX_EXPANDED). New tests/unit/engine/test_concurrency.py: 8 threads x 12 rounds x 12 queries (match_ids, pages, sorts, facets, explain) against one engine with bounds 0 and GIL-yielding memos, asserting no exception and results equal to a serial run; fails on the old code and on each of four mutants. No latency change measurable. The contract is in the ast-compilation skill.
<!-- SECTION:FINAL_SUMMARY:END -->
