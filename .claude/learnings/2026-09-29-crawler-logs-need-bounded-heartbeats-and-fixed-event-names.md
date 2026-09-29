# A full-corpus crawl needs bounded heartbeats and fixed event names, not per-record warnings

**Key lesson:** For a crawl that runs for hours, log one start line, a heartbeat at most every 30 s on the client's (injectable) monotonic clock, and one aggregate WARNING per listing or crawl. Keep per-record anomalies at DEBUG, and take every event name from a fixed constant, so a test can check that no event name is ever built at run time.

- **Date:** 2026-09-29 · **Task:** task-116 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/common.py` (`Heartbeat`), `backend/src/openproceedings/ingest/sources/http.py` (`CRAWL_EVENTS`), `backend/src/openproceedings/ingest/sources/openreview_client.py` (`EVENTS`), `backend/src/openproceedings/ingest/sources/html.py` (`HTMLBudgetError`), `backend/tests/unit/ingest/test_fetch.py::test_every_crawler_log_event_is_a_constant_never_built`

## What we set out to do
Close the M4 review's observability findings before the first full-corpus crawl's logs become the evidence for the coverage report.

## What we learned
- The first live crawl (2026-09-29) had been running 8.6 h by 14:45Z (the first log line was at 06:07:56Z; NeurIPS 2025 was still crawling). Its OpenReview logs have long silences, measured as the gaps over 10 min between consecutive lines in `data/crawl-logs/openreview-*.log`. ICLR had 26.4 and 32.3 min while v1 forums were being fetched, with no `budget_wait` at all: the crawl was working and said nothing. NeurIPS had 51.2 min and ICML 50.3 min after an `openreview_budget_wait` (wait_s 2973 and 2934). Without a heartbeat, a stalled crawl and a working one look the same.
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
- Test or hook added? — `test_fetch.py::test_every_crawler_log_event_is_a_constant_never_built`, `test_openreview_v2.py::test_the_heartbeat_is_due_at_most_every_30_seconds_of_monotonic_time`, the per-API start-and-heartbeat and `test_per_note_anomalies_are_debug_and_the_crawl_has_one_attention_warning` tests in `test_openreview_v1.py`/`test_openreview_v2.py`, `test_openreview_client.py::test_a_projection_refusal_names_the_canonical_request_and_nothing_else`, and the budget tests in `test_neurips.py`/`test_pmlr.py`/`test_iclr.py`
