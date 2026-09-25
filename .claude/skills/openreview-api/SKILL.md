---
name: openreview-api
description: How openproceedings talks to OpenReview — which venue-years live on API v2 vs v1 (spec 01 §Sources), authentication from .env credentials, 429 and rate-limit headers, pagination, why the submission note's content.venueid is the only authority for track and status, and how v1 decisions arrive as separate notes. Use when writing, reviewing or debugging anything under backend/src/openproceedings/ingest/sources/ that calls api.openreview.net or api2.openreview.net.
---

# OpenReview API (spec 01 §Sources, §Pipeline 1)

## Which host holds which venue-year
| Host | Venue-years | Shape |
|---|---|---|
| `api2.openreview.net` (v2) | ICLR 2024+, NeurIPS 2023+, ICML 2023+ | every content value is wrapped: `content.title.value`, `content.venueid.value` |
| `api.openreview.net` (v1) | ICLR 2018–2023, NeurIPS 2021–2022 | content values are bare strings; schema differs per year, so one adapter per venue-year |

NeurIPS before 2021 and ICML 2020–2022 are **not** on OpenReview as full venues: use
`.claude/skills/neurips-proceedings/SKILL.md` and `.claude/skills/pmlr-proceedings/SKILL.md`. A venue-year
not in this table is out of scope until spec 01 adds it.

## Authentication
- The anonymous API returns 429 / `ChallengeRequiredError` almost immediately (verified 2026-09-23).
  Every crawl authenticates: `POST /login` with `{"id": <user>, "password": <password>}` returns a bearer
  token sent as `Authorization: Bearer <token>`.
- Credentials come only from `.env` (gitignored, spec 08). Never from a CLI flag, a test fixture or a log
  line. The exact variable names are fixed by the crawler config — verify at implementation time and
  document them in `CONTRIBUTING.md`.
- Log in lazily: a fully cached (warm) run must make zero network calls and need no credentials.
- Recorded fixtures must have the `Authorization` header and any token scrubbed before commit.

## Rate limits and retries
- OpenReview advertises `ratelimit-policy: 500;w=3600` (500 requests per hour per token, as measured by
  scholarmend) and sends `ratelimit-remaining` / `ratelimit-reset`. When `remaining` hits 0, sleep until
  `reset` (capped, about an hour) rather than hammering.
- On 429 honour `Retry-After` or `ratelimit-reset` from the error response. Exponential backoff of 1s, 2s,
  4s on a one-hour window just fails the run.
- Retry 429 and 5xx; raise immediately on any other 4xx (retrying a refusal spends budget).
- Validate the body (JSON parses) inside the retry loop so a truncated response is retried.
- Every call goes through the disk cache keyed by URL + params, written atomically (temp file + rename),
  so the wait is paid once ever and a crawl resumes where it stopped.

## Pagination
- Page with `limit` + `offset` and stop on a short page, not on a guessed total. Verify at
  implementation time the maximum `limit` each host accepts and whether `count` is returned.
- Sort explicitly (for example by `id` or creation time) so offsets are stable if notes are added mid-crawl;
  after the crawl, assert the number of distinct IDs equals the rows fetched.
- Cache each page under its own key (URL + params), never one blob per venue-year.

## The authority rule
**Only `content.venueid` on the submission note decides track and status.** The submission note is the
note whose `id` equals its `forum`. Two traps, both seen live:
1. Querying "any note in the forum" returned a Decision note on 25 of 96 forums. Deriving the venue from
   that note's **invitation** turned a rejected ICLR paper into ICLR main track (`zkNCWtw2fd`). Look notes up
   by `id=<forum>` and check `note.id == forum` before reading anything.
2. A note without its own `venueid` produces **no** track claim: `track=unknown`, logged, shown on
   coverage. Unresolved goes to a person; derived never ships.

Use the venueid forms in `.claude/skills/openreview-venueids/SKILL.md` to parse it.

## API v1 specifics
- Submissions are listed through the venue's submission invitation (for example a `Blind_Submission`
  invitation). Being in that list means **submitted**, never accepted.
- Decisions are **separate notes** in the same forum (a `Decision` or, for early ICLR years, a meta-review
  note, verify per year). Fetch forum replies (for example `details=directReplies`) and join on `forum`,
  not on the submission id. The decision text (`Accept (Oral)`, `Reject`, …) gives `status` and
  `presentation`, recorded as a claim whose evidence is the decision note id.
- Where a v1 year does state `content.venueid` or `content.venue` (`ICLR 2023 poster`,
  `Submitted to ICLR 2023`), prefer it and record the decision note as a second claim. Disagreement goes
  to `conflicts.csv`.
- Withdrawn and desk-rejected papers may live under separate invitations; crawl them explicitly or they
  are silently missing from the rejected/withdrawn counts.
