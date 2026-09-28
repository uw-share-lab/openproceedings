# Every paged OpenReview listing needs an ignored-offset guard, and the crawler must log in only on a cache miss

**Key lesson:** Put the "this page repeats ids already seen" check inside the one paging helper that every listing (groups and notes) goes through, not in the notes listing alone: a server that ignores `offset` otherwise loops forever on any listing longer than a page; and log in lazily inside the client so a run served from the cache needs no credentials, which is what makes `--offline` replay and `op snapshot build` work on a machine without `.env`.

- **Date:** 2026-09-27 · **Task:** TASK-050 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_client.py`,
  `backend/src/openproceedings/ingest/sources/openreview_v2.py`,
  `backend/tests/unit/ingest/test_openreview_v2.py` (`test_an_ignored_offset_is_refused_not_looped`),
  `backend/tests/unit/ingest/openreview_fakes.py`

## What we set out to do
Build the OpenReview API v2 crawler (auth, pacing, 429 handling, resumable cache, records, `op ingest
openreview`) and test it only against the TASK-002 recorded fixtures.

## What we learned
- **The first version hung a test, not failed it.** The repeat check lived in the notes listing; the
  group-tree listing (`/groups?parent=`) paged through the same generator without it, so the
  ignored-offset test (five year-level groups, page size 2) spun forever. Moving the check into `_pages`
  covers every listing (evidence: the test now raises `CrawlError` in milliseconds).
- **scholarmend's `login` can't be reused as-is:** it calls urllib directly (so a fake transport can't
  see it, and a test would need the network), follows redirects, and reads the HTML challenge page as a
  `JSONDecodeError`. The client logs in through its own transport instead; scholarmend's `Cache` (atomic,
  sha256-named, key stored beside the payload) is reused unchanged.
- **Pacing moves the fake clock:** the first GET after login is `min_interval` later, so a cache entry's
  `fetched_at` is not the clock's start. Assert against the paced time, not `EPOCH`.
- **The dry run is an offline crawl that notes misses per branch**, so one uncached listing doesn't hide
  the rest of the venue-year's plan.

## Dead ends — don't repeat these
- Running `pytest` on a new crawler without a timeout: a paging bug shows up as a hang. Use
  `timeout 100 uv run pytest … -o faulthandler_timeout=10` to get the stack.

## Decisions (and what would change them)
- Group discovery walks `?parent=` listings and skips `proposal` groups and non-v2 groups → the research run
  described the tree but recorded no `?parent=` listing → a recorded listing that shows other non-venue
  groups (committees, tutorials) would add skip rules.
- Presentation (`oral`/`spotlight`/`poster`) is not parsed from `content.venue` → the strings vary per
  venue-year and need a table (research doc) → a per-venue-year presentation table.

## Follow-ups
- [ ] (proposed, no task yet) record a `?parent=` group listing per venue before the first full crawl.
- [ ] (proposed, no task yet) presentation claims from `content.venue` via a per-venue-year table.
- [ ] (proposed, no task yet) a cache TTL (spec 01 §Pipeline 1 says "with a TTL"); today `--refresh` is manual.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` §The v2 crawler as built;
  `.claude/skills/snapshots/SKILL.md` (manifest `sources.openreview_v2`); `CLAUDE.md` layout; spec 01 §CLI.
- Test or hook added? — `test_an_ignored_offset_is_refused_not_looped`,
  `test_a_finished_crawl_replays_offline_with_no_credentials_and_no_request`.
