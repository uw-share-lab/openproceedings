---
name: openreview-api
description: How openproceedings talks to OpenReview — which venue-years live on API v2 vs v1 (spec 01 §Sources, verified live 2026-09-27), authentication from .env credentials and the HTML challenge anonymous callers get, rate-limit headers, pagination (limit ≤ 1000, count only with offset), why the submission note's content.venueid decides track and status in v2 but not in v1, how v1 decisions arrive, and the recorded fixtures. Use when writing, reviewing or debugging anything under backend/src/openproceedings/ingest/sources/ that calls api.openreview.net or api2.openreview.net.
---

# OpenReview API (spec 01 §Sources, §Track taxonomy)

Every fact here was checked live on 2026-09-27 (TASK-002). The evidence, counts and example ids are in
`docs/research/2026-09-27-openreview-and-proceedings-facts.md`; one recorded response per shape is under
`backend/tests/fixtures/http/openreview/` (§Fixtures).

## Which host holds which venue-year
| Host | Venue-years | Shape |
|---|---|---|
| `api2.openreview.net` (v2) | ICLR 2024+ (incl. Tiny Papers 2024, Blogposts 2024+), NeurIPS 2023+ (incl. D&B 2023), ICML 2023+ | every content value is wrapped: `content.title.value`, `content.venueid.value` |
| `api.openreview.net` (v1) | ICLR 2013, 2014, 2016–2023 (2016: workshop track only; Tiny Papers and Blogposts 2023), NeurIPS 2021–2022 (main and D&B) | content values are bare strings; schema differs per year, so one adapter per venue-year |

- Not on OpenReview: ICLR 2015 (no group), the ICLR 2016 conference track, NeurIPS before 2021, ICML
  before 2023 (`ICML.cc/2020/Conference` exists but has no public notes). Use
  `.claude/skills/neurips-proceedings/SKILL.md` and `.claude/skills/pmlr-proceedings/SKILL.md`; ICLR's
  gaps are TASK-096.
- `GET /groups?id=<venue>` on api2 tells the version of any venue: a v2 group has `domain = <its id>` and
  a `content` block naming its venueids; a v1 group has `domain = null` and a `web` script. A note is only
  on its own host: the other one answers `404 NotFoundError` by id, and an empty list (not an error) to a
  venueid query. Pick the host from this table; never "try v2, fall back to v1".
- `GET /groups?parent=<Org>.cc/<Y>&select=id` maps a year's groups (tracks, `Workshop`,
  `Workshop_<City>`, proposal groups) in one request.

## Authentication
- **Anonymous access does not work.** api2 and api1 `/notes` answer an anonymous request with **HTTP 200
  and an HTML "Verifying your browser" page** (a Turnstile challenge), not JSON and not 429. Check the
  `content-type` is JSON before parsing, and treat HTML as an authentication failure, never as an empty
  page.
- `POST https://api2.openreview.net/login` with `{"id": <user>, "password": <password>}` returns
  `{"token": …}`; send `Authorization: Bearer <token>`. The same token works on api1.
- Credentials come only from `.env` (gitignored, spec 08) as **`OPENREVIEW_USERNAME`** and
  **`OPENREVIEW_PASSWORD`** (`.env.example`, `scripts/setup-dev.sh`, `CONTRIBUTING.md`). scholarmend's
  `SCHOLARMEND_OPENREVIEW_*` names are not read; pass our values to its `login(user, password)`. Never
  from a CLI flag, a fixture or a log line.
- Log in lazily: a fully cached (warm) run must make zero network calls and need no credentials.
- Fixtures never contain the token or the `Authorization` header (the scrubber keeps only the content-type
  and rate-limit headers).

## Rate limits and retries
- api2 budgets per resource: `/notes` `ratelimit-policy: 500;w=3600`, `/groups` `700;w=3600`, with
  `ratelimit-remaining` and `ratelimit-reset` (**seconds from now**). It also sends `x-ratelimit-reset`, an
  epoch timestamp: don't mix them up. When `remaining` hits 0, sleep until `reset` (capped at about an hour).
- api1 sends `180;w=60` to anonymous callers and no rate-limit headers to authenticated ones; pace it the
  same way (one request every one or two seconds was never throttled).
- On 429 honour `Retry-After` or `ratelimit-reset`. Exponential backoff of 1s, 2s, 4s on a one-hour window
  just fails the run.
- Retry 429 and 5xx; raise immediately on any other 4xx (retrying a refusal spends budget).
- Validate the body (JSON, not the challenge page) inside the retry loop so a truncated response is retried.
- Every call goes through the disk cache keyed by URL + params, written atomically (temp file + rename),
  so the wait is paid once ever and a crawl resumes where it stopped.

## Pagination
- `limit` ≤ **1000** on both hosts: `limit=1001` is `400 ValidationError` "limit must be <= 1000".
- v2 returns `count` **only when the request has an `offset` parameter** (`offset=0` is enough); v1
  returns it on every `/notes` response. Page with `limit=1000&offset=…`, stop on a short page, and then
  check distinct ids == rows fetched == `count`.
- Both hosts accept `select=` (`select=id,content.venueid`) to fetch ids only, e.g. for counting.
- Sort explicitly (for example by `number`) so offsets are stable if notes are added mid-crawl.
- Cache each page under its own key (URL + params), never one blob per venue-year.
- v1 `invitation=` must be a **prefix** regex: `ICLR.cc/2020/Conference/Paper.*/-/Decision` is refused
  (400). Get v1 decisions per forum (`?forum=<id>`) or with `details=directReplies` on the submission
  listing. A `?forum=` listing is not ordered: find the submission by `id == forum`.

## The authority rule
**In v2, only `content.venueid` on the submission note decides track and status.** The submission note is
the note whose `id` equals its `forum`. Two traps, both seen live:
1. Querying "any note in the forum" returned a Decision note on 25 of 96 forums. Deriving the venue from
   that note's **invitation** turned a rejected ICLR paper into ICLR main track (`zkNCWtw2fd`). Look notes up
   by `id=<forum>` and check `note.id == forum` before reading anything.
2. A note without its own `venueid` produces **no** track claim: `track=unknown`, logged, shown on
   coverage. Unresolved goes to a person; derived never ships.

Each v2 venue's group names its four venueids (`submission_venue_id`, `rejected_venue_id`,
`withdrawn_venue_id`, `desk_rejected_venue_id`) and whether rejected/withdrawn/desk-rejected submissions
are public (`public_submissions`, `public_withdrawn_submissions`, `public_desk_rejected_submissions`: true
for ICLR, false for NeurIPS and ICML, whose rejected papers are public only on the authors' opt-in).
Parse venueids through `.claude/skills/openreview-venueids/SKILL.md`.

## API v1: the venueid is not status evidence
- **v1 puts the bare venue path on rejected papers too**: ICLR 2017 (`ICLR.cc/2017/conference`, lower
  case, also on workshop invitations), ICLR 2022 and 2023, NeurIPS 2021–2022, NeurIPS 2021 D&B
  (`…/Round1`), ICLR 2023 Tiny Papers and Blogposts. `classify_venueid("ICLR.cc/2022/Conference")` says
  `main`/`accepted`, so it must never set a v1 note's status (TASK-095). The venueid only confirms venue,
  year and track. **Enforced:** `classify_venueid` returns status `unknown` for any venueid in a v1
  venue-year (`classify.is_v1`), and the RIS importer marks such a status claim `(API v1 venue-year: not
  status evidence)`. A v1 adapter takes status from `classify_v1_venue(content.venue)` (exact strings from
  the table below; an unlisted one is `unknown`), the decision note, or the withdrawn / desk-rejected
  invitation (decision-012).
- Status per v1 year (the submission invitation lists what was **submitted**, never what was accepted):

| Year | Submissions | Status from |
|---|---|---|
| ICLR 2013 | `ICLR.cc/2013/conference/-/submission` | `content.decision` on the submission: `conference{Oral,Poster}-iclr2013-{conference,workshop}`, `reject` (track too) |
| ICLR 2014 | `ICLR.cc/2014/{conference,workshop}/-/submission` | none: `submitted, no decision` → `unknown` |
| ICLR 2016 | `ICLR.cc/2016/workshop/-/submission` | none → `unknown` (workshop track) |
| ICLR 2017 | `ICLR.cc/2017/{conference,workshop}/-/submission` | `content.venue`: `ICLR 2017 {Oral,Poster}`, `ICLR 2017 Invite to Workshop`, `Submitted to ICLR 2017` |
| ICLR 2018 | `ICLR.cc/2018/Conference/-/Blind_Submission` | decision note `ICLR.cc/2018/Conference/-/Acceptance_Decision`, `content.decision` (`Accept (Oral)`, `Accept (Poster)`, `Invite to Workshop Track`, `Reject`) |
| ICLR 2019 | `…/2019/Conference/-/Blind_Submission` | meta-review `ICLR.cc/2019/Conference/-/Paper<N>/Meta_Review`, `content.recommendation` |
| ICLR 2020–2021 | `…/-/Blind_Submission` | `ICLR.cc/<Y>/Conference/Paper<N>/-/Decision`, `content.decision`; 2021 accepted notes also carry `venue`/`venueid` |
| ICLR 2022–2023, NeurIPS 2021–2022 | `…/-/Blind_Submission` | `content.venue` (`ICLR 2022 Submitted`, `Submitted to ICLR 2023`, `NeurIPS 2022 Accept`, …) or the decision note |
| NeurIPS 2021 D&B | `NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round{1,2}/-/Submission` | `content.venue` (`Submitted to …` = rejected) |
| NeurIPS 2022 D&B | `NeurIPS.cc/2022/Track/Datasets_and_Benchmarks/-/Submission` | only accepted papers are public |

- Withdrawn and desk-rejected papers live under their own invitations
  (`…/-/Withdrawn_Submission`, `…/-/Desk_Rejected_Submission`); crawl them explicitly or they are silently
  missing from the counts. Their `venue`/`venueid` are empty or absent, and one ICLR 2021 withdrawn-invitation
  note (`xGZG2kS5bFk`) says `ICLR 2021 Poster`: that disagreement is a `conflicts.csv` row, never resolved
  by the invitation.
- Record the decision note id (or the venue string) as the status claim's evidence, and a
  `presentation` claim when the decision states one.

## The v2 crawler as built (TASK-050)
- `ingest/sources/openreview_client.py`: `OpenReviewClient`, the shared `http.HttpClient` (TASK-103: one
  transport, allowlist, pacing, retry and cache for every crawler) with OpenReview's `POLICY` and its login on
  top, over a swappable `transport` (default: urllib, **no redirects**, 60 s timeout, 64 MiB body cap, a body over
  it refused at once) and `clock` (tests use a fake one). Hosts are an allowlist
  (the base URL is fixed; nothing is fetched from a URL a response names). Login lazily through the same
  transport (not scholarmend's `login`, which bypasses it and would read the challenge page as a JSON error);
  a 401 or a 200 HTML page logs in again once, then `OpenReviewAuthError`. Pacing `min_interval` (1 s),
  budget wait on `ratelimit-remaining: 0`, 429 → `Retry-After` (seconds or HTTP date) → `ratelimit-reset` →
  backoff, 5xx / network / truncated JSON → `min(2^n, 60) s + jitter`, `max_attempts` 6, every wait capped at
  3,701 s. Cache: `http.ResponseCache` under `<data-dir>/cache/openreview/v2/http/` in the layout scholarmend's
  `Cache` wrote (`{key, payload}`, so an older cache replays), keyed by the canonical URL (parameters sorted),
  storing `{url, fetched_at, headers (content-type and ratelimit-* only), json}`; an unreadable entry, or one
  naming another URL, is a `CacheError` (delete it), never a silent refetch. Errors are the shared
  `http.SourceError` family (`CacheMiss`, `RetriesExhausted`, `HTTPRefused`; `OpenReviewAuthError` on top).
- `ingest/sources/openreview_v2.py`: `crawl` (groups → venueids → pages → records), `note_record` (the
  authority rule), `ingest` (writes `…/v2/crawls/<Venue>-<Year>.json` for a finished crawl) and `replay`
  (what `op snapshot build` calls). The group-tree enumeration (`?parent=` listings, containers, the
  `proposal` skip) is built from the research run's description; no `?parent=` listing is recorded yet, so
  record one per venue before the first full crawl.

## The v1 crawler as built (TASK-051)
- `ingest/sources/openreview_v1.py`: `ADAPTERS`, one `Adapter` per venue-year (ICLR 2013–2023 including an
  empty 2015, NeurIPS 2021–2022). Each names its exact listing invitations (with the track submitted to and
  the role: `submission`, `withdrawn`, `desk_rejected`), where status comes from (`decision_field`, `none`,
  `venue`, `decision_note`, `venue_then_decision_note`), its decision table and its `coverage_gaps`.
  `api_for(venue, year)` picks v1 or v2; `op ingest openreview` sends each year to its API.
- `make_client` points the shared client at `https://api.openreview.net`, logs in on api2
  (`login_base`), and caches under `<data-dir>/cache/openreview/v1/http/`; crawl files go to
  `…/v1/crawls/<Venue>-<Year>.json` and `replay` rebuilds them offline for `op snapshot build`.
- Listings use `?invitation=<exact>` with `limit`/`offset` and no `sort` (the v1 sort parameter isn't verified;
  rows == distinct ids == `count` catches a listing that moved). Decision notes come from `?forum=<id>`, only
  for years whose status needs one and notes without a deciding venue string: a note counts as the decision
  only if its invitation is the year's exact one (with `Paper<number>` of this submission), its `forum` is
  the submission and its `replyto` is the submission.
- Status strings are exact-match tables (`classify_v1_venue` for `content.venue`, the adapter's tables for
  `content.decision` and decision notes). Only strings seen live are listed: ICLR 2020's and 2021's accept
  decision strings are not, so those notes are `unknown` and counted in the report's `unmapped` until a live
  accepted forum is recorded. The v1 venueid confirms venue and year and must agree with the decided track.
- A note's own disagreement (withdrawn invitation vs an accepted `content.venue`, two decision notes, a
  venueid naming another track) makes that field `unknown` and adds an `unresolved:openreview_v1` row that
  `snapshot.with_crawl_conflicts` writes to `conflicts.csv` (following merges to the surviving record).
- Early ICLR 2017 notes give `content.authors` as one string: kept out (`authors_unsplit` in the report), never
  split by guess. Not crawled until verified live: ICLR 2023 Blogposts, NeurIPS 2021–2022 withdrawn and
  desk-rejected invitations (each named in the year's `coverage_gaps`).

## Fixtures
`backend/tests/fixtures/http/openreview/{v1,v2}/<venue>-<year>/*.json`, one file per exchange:
`{"_recorded", "request": {"method", "url", "authenticated"}, "response": {"status", "headers", "json" |
"text"}}`. They cover each v2 status suffix, D&B, position, competition, Creative AI, Tiny Papers,
Blogposts, workshop and city-workshop forms, a group's venueid block, the `count`/`offset` shape, the
`limit` error, the cross-host 404 and the anonymous challenge page; and each v1 year's status carrier
above. `backend/tests/fixtures/http/scrub.py` turns a raw capture into a fixture (titles, abstracts,
authors, ids of people and free text become synthetic; decision-004). Recording is a manual run, never a
test: add a capture for every new shape, scrub it, and read the diff before committing.
