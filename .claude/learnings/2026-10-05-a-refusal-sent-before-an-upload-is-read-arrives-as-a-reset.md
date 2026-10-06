# A refusal sent before an upload is read arrives as a reset connection, and an e2e spec with a fixed port tested the wrong server

**Key lesson:** When a route takes a body of megabytes, any refusal sent before the body is read (a 429 from middleware, a busy slot) reaches a real client as "connection reset", not as the refusal, so read and discard what arrives for a bounded moment first; and check a design's cost on the real corpus before fixing the API's shape, without `tracemalloc` on, because here one comparison was 18 s of CPU and the planned "one request per export" would have multiplied it.

- **Date:** 2026-10-05 · **Task:** task-177 · **Area:** api, frontend, tooling
- **Artifacts:** `backend/src/openproceedings/api/compare.py`, `backend/src/openproceedings/api/middleware.py` (`drain`, `BodyLimit.streamed`), `backend/tests/contract/test_compare.py`, `frontend/e2e/spec05.spec.ts`, `frontend/playwright.config.ts`, `backend/tests/e2e/fixture_server.py`

## What we set out to do
Serve TASK-056's RIS comparison to any user: `POST /compare` with the reviewer's file as the body, capped,
never stored or logged, off on a public instance unless its operator turns it on, with a panel on the search
page.

## What we learned
- **An early refusal is a reset.** `TestClient` never shows it: in process, the whole body is "sent" before
  the app answers. Over a real socket (`op serve` on a scratch copy of index `05a0541717f6`, a 3.7 MB file),
  the 429 that `RateLimit` sent without reading the body reached `urllib` as `ECONNRESET`, and so did the
  route's own 503 at first. `middleware.drain` now reads and discards the rest for at most 2 s before such a
  refusal (still counted against the body cap, nothing held); after it the same run got its 429 as a 429. A
  browser would have shown "couldn't reach the server" for a rate limit.
- **Measure the request, not the plan.** The design had `format=ris` and per-list CSV as further requests.
  One comparison of the review's export (1,834 records) took 18 to 24 s, almost all of it `ReferenceEngine`
  deciding the classes over phrases with inflected forms (`cProfile`: `_occurrences`). A second request for an
  export would have re-uploaded the file and paid that again, and with the slot-time debit locked the reader
  out of search. Everything a click needs is now in the one answer (`csv`, `added_ris`, `reason_totals`).
- **`tracemalloc` lies about time.** `MatchIndex.build` measured 52 s with tracing on and 13 s without; the
  comparison 180 s and 18 s. Trace memory in one run and time in another.
- **A fixed port in one spec tested someone else's server.** `playwright.config.ts` reuses a server already
  on its port (outside CI), and `spec05.spec.ts` called `http://127.0.0.1:8000` directly. With the owner's
  instance on 8000 and 3000, a run on other ports still sent that one request to the owner's API (a read-only
  `/search`; the test failed on a total of 62 against 52, which is how it showed). The ports are now
  `OP_E2E_API_PORT` / `OP_E2E_WEB_PORT` in the config, the fixture server and every spec that calls the API.
- **A response field added to `/meta`'s `limits` broke four pinned tests and one fallback object** (`Limits`
  literals in `syntax-help.tsx` and the test stub's `META`): a typed literal of a response model is a second
  copy of its shape. `tsc` found the frontend ones only when the e2e build ran, since Vitest doesn't type-check.

## Dead ends
- Bounding a line's length with one regex (`[^\n]{N}`): it rescans from every start position, quadratic on a
  long line. A `str.find` loop over the lines, after `str.count("\n")` has capped their number, is linear.
- A multipart upload: Starlette's parser spools a part over 1 MB to a temporary file, which is the file
  written to disk. The raw body with a required content type needs no parser at all.

## Propagated to
`fastapi-conventions` (the `async` exception, `streamed` bodies, `drain`, per-index data on the bundle),
`api-contract` (§A file as a request body), `testing-standards` (e2e ports), spec 04 §Comparing with a RIS
file, spec 05 §Testing.

## Addendum — 2026-10-06
- **A fixture that freezes "today" must patch every module that imported the clock function by name.** `test_compare.py`'s `fixed_date` patched `export.utc_date` and `api.compare.utc_date`, but one test also reads `GET /export`, whose `api.export` module holds its own reference; it passed only while the real UTC date was the frozen `2026-10-05` and failed for every PR from 00:00 UTC on 2026-10-06. Evidence: the failing diff (`exported 2026-10-06` against `2026-10-05`). Lesson: when a test freezes a date with `monkeypatch.setattr(module, "fn", …)`, grep for every `from … import fn` the test exercises; a test pinned to a date that is today passes until midnight.
