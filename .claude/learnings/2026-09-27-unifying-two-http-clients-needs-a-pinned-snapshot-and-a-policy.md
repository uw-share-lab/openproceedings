# Two crawlers' HTTP clients unified only once their differences were a Policy and the snapshot hash was pinned first

**Key lesson:** Before merging two fetch/retry/cache stacks, pin one combined snapshot built from every source's recorded fixtures (its `snapshot_hash` and a hash of the whole directory) and keep a copy of a cache the old code wrote; then carry every retry difference the old tests pin (a `+1 s` pad on server-named waits, capping vs aborting a long wait, backing off after the last attempt, the body cap, the truncation check) as a field of one `Policy`, rather than "improving" them away.

- **Date:** 2026-09-27 · **Task:** TASK-103 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/http.py` (`Policy`, `HttpClient`, `ResponseCache`),
  `backend/src/openproceedings/ingest/sources/common.py` (`Report`, `Crawls`),
  `backend/tests/unit/ingest/test_combined_snapshot.py`, `backend/tests/unit/ingest/test_http.py`

## What we set out to do
Fold the proceedings fetcher (`http.Fetcher`) and the OpenReview client into one transport, clock, retry,
cache, marker/replay and error hierarchy without changing a byte of what a crawl records.

## What we learned
- **The two clients' tests pin opposite retry rules.** Proceedings: `Retry-After: 7` sleeps 7 s, a 7,200 s
  hint aborts the crawl, a 5xx backs off 5, 10, 20 s and sleeps after the third attempt too. OpenReview:
  `Retry-After: 30` sleeps 31 s, 999,999 s is capped at 3,701 s, 1, 2, 4, 8 s plus jitter and no sleep after
  the last try. One loop with `hint_pad`, `cap_waits`, `wait_after_last`, `backoff` and `expect` passes both
  suites unchanged (evidence: `uv run pytest backend/tests/unit/ingest`, 725 passed).
- **The snapshot pin catches what the unit tests can't.** Report windows moved from ISO strings (OpenReview)
  to datetimes (shared `Report.fetched`), cache keys now pass through one `canonical(…, keep_query=True)`, and
  replay order became `sorted(key)`: any slip there changes records or `crawl_window`, and only the
  combined v2 + v1 + NeurIPS + PMLR snapshot hash shows it (`ff71377d…`, identical before and after).
- **Old caches must replay, so layouts stay and only the mechanism is shared.** A codec per source keeps the
  proceedings' fixture-shaped `pages/` entries and OpenReview's scholarmend `{key, payload}` documents; a cache
  written by the pre-refactor code (kept in the scratchpad) rebuilt the same snapshot byte for byte.
- **Existing tests pin wording from both sides:** `test_cli` wants `not in the cache (offline)` and the
  OpenReview CLI test wants `not cached`, so the one `CacheMiss` message carries both.
- **A shared dataclass base with a per-source constant:** `@dataclass(kw_only=True)` on the base, and
  `source: str = field(default=SOURCE, init=False)` in the OpenReview reports, keeps `CrawlReport("ICLR", 2021)`
  positional while `ListingReport` re-declares `source` as its first positional field.

## Dead ends — don't repeat these
- Clamping the padded wait a second time: `min(hint, max_wait) + pad` then `min(…, max_wait)` turns 3,701 s
  back into 3,700 s. Bound once, then pad.
- Positional test doubles: `Response(url, status, …)` vs `Response(status, headers, body)` can't both be one
  class; the shared helpers had to move to keywords (the test files themselves only changed imports).

## Decisions (and what would change them)
- The proceedings crawlers no longer follow redirects (they used to follow any, then refuse an off-host final
  URL): one transport, no redirects, a 3xx is `HTTPRefused` → a live NeurIPS/PMLR URL that redirects would
  need an on-host redirect rule in `Policy`.
- A body over the cap is refused at once for every source (OpenReview used to retry it); a corrupt OpenReview
  cache entry is a `CacheError` (it used to be a silent miss and refetch).

## Follow-ups
- [ ] (proposed, no task yet) move the per-source ingest loops (`exclusive` lock, crawl, write the marker) into
  `common` next to `Crawls`, so `op ingest` shares one loop as replay does.
- [ ] (proposed, no task yet) drop the duplicate proceedings/OpenReview HTTP-property tests in `test_fetch.py`
  and `test_openreview_client.py` now that `test_http.py` covers every source.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` (as built),
  `.claude/skills/snapshots/SKILL.md` (the one replay), `.claude/skills/repo-conventions/SKILL.md`, `CLAUDE.md`
  layout, spec 01 §Pipeline and §CLI, spec 08 layout.
- Test or hook added? — `backend/tests/unit/ingest/test_combined_snapshot.py` (the pinned hashes),
  `backend/tests/unit/ingest/test_http.py` (allowlist, off-host answers, body cap and error hierarchy for all
  three sources; the scholarmend-layout cache replays).
