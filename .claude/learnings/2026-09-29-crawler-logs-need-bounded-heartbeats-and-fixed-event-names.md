# A full-corpus crawl needs bounded heartbeats and fixed event names, not per-record warnings

**Key lesson:** For a crawl that runs for hours, log one start line, a heartbeat at most every 30 s on the client's (injectable) monotonic clock, and one aggregate WARNING per listing or crawl. Keep per-record anomalies at DEBUG, and take every event name from a fixed constant, so a test can check that no event name is ever built at run time.

- **Date:** 2026-09-29 · **Task:** task-116 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/common.py` (`Heartbeat`), `backend/src/openproceedings/ingest/sources/http.py` (`CRAWL_EVENTS`), `backend/src/openproceedings/ingest/sources/openreview_client.py` (`EVENTS`), `backend/src/openproceedings/ingest/sources/html.py` (`HTMLBudgetError`), `backend/tests/unit/ingest/test_http.py::test_every_crawler_log_event_is_a_constant_never_built`

## What we set out to do
Close the M4 review's observability findings before the first full-corpus crawl's logs become the evidence for the coverage report.

## What we learned
- The first live crawl (2026-09-29) ran for about 10 h. During OpenReview's hourly budget waits the only line was `openreview_budget_wait`, so a stalled crawl and a paced one looked alike until a heartbeat was added (evidence: `data/crawl-logs/openreview-*.log`: 30-minute gaps between lines).
- Per-record WARNINGs (`openreview_unknown_track`, `openreview_v1_unmapped`, …) scale with the corpus. The aggregate `openreview_crawl_attention` / `listing_attention` line already carried the counts, so the per-record lines moved to DEBUG and the aggregate counts `duplicate` and `invalid` too.
- Event names built with f-strings (`f"{prefix}_budget_wait"`) can't be grepped or allow-listed. A test that parses every crawler log call and requires a constant name caught all three in the old `http.py`.
- A refusal is only actionable if it names what to redo. A projection refusal now names the canonical request (the cache key). A parser budget failure names the page and says `--refresh` (index page) or which cache entry to delete (paper page).

## Dead ends — don't repeat these
- A wall-clock heartbeat is untestable. Put it on the client's monotonic clock, which tests already fake.

## Decisions (and what would change them)
- `*_cache_expired` (INFO) and `openreview_cache_incompatible` (WARNING) still log once per cache entry: they are per-page events, not record anomalies, and rare outside a deliberate refresh. Aggregate them if a full `--refresh` run shows them flooding the log.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/logging-standards/SKILL.md` (§Crawl lines, levels), `.claude/skills/openreview-api/SKILL.md`, `docs/specs/01-ingestion.md`
- Test or hook added? — the event-name constant test and the heartbeat, attention and budget tests named in the task
