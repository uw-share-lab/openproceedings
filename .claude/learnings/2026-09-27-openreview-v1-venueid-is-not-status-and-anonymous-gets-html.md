# OpenReview v1 venueids sit on rejected papers too, and anonymous requests get a 200 HTML page

**Key lesson:** In OpenReview API v1 years (ICLR ≤2023, NeurIPS 2021–2022) the bare venueid (`ICLR.cc/2022/Conference`) is on rejected submissions as well as accepted ones, so status must come from `content.venue` or the decision note, never the venueid; and an unauthenticated request gets HTTP 200 with an HTML browser-check page, so a client must reject non-JSON before parsing, not read it as an empty result.

- **Date:** 2026-09-27 · **Task:** TASK-002, TASK-048, TASK-049 · **Area:** ingest
- **Artifacts:** `docs/research/2026-09-27-openreview-and-proceedings-facts.md`, decision-012,
  decision-013, `backend/tests/fixtures/http/` (53 scrubbed fixtures, `scrub.py`)

## What we set out to do
Record the owner's two M4 decisions (index rejected/withdrawn behind `status:accepted`; crawl from 2013)
and check every "verify" fact in the ingestion skills against live OpenReview, NeurIPS proceedings and
PMLR before the crawlers are written.

## What we learned
- **v1 venueids are not status evidence.** ICLR 2022: all 2,617 blind notes carry
  `ICLR.cc/2022/Conference`, 1,523 of them `venue = ICLR 2022 Submitted`. ICLR 2023 and 2017, NeurIPS
  2021–2022 and D&B 2021 (`…/Round1`) do the same; ICLR 2017 also puts the conference venueid on workshop
  invitations. `classify_venueid` reads those as `main`/`accepted`. The v2 authority rule does not carry
  back to v1 (TASK-095).
- **The spec's premises were off in both directions.** ICLR is on OpenReview from 2013 (not 2018), but
  2015 is missing, 2014 has no decisions and 2016 has only its workshop track (TASK-096).
- **Anonymous = HTML with status 200**, not the 429 the skill expected; `count` appears on v2 only when
  `offset` is sent; `limit` caps at 1000; `x-ratelimit-reset` is an epoch while `ratelimit-reset` is
  seconds.
- **What is public differs by venue:** ICLR shows every rejected/withdrawn/desk-rejected submission;
  NeurIPS and ICML only opt-in rejected papers (the group's `public_*` flags say so), so rejected counts
  are complete only for ICLR.
- **NeurIPS proceedings URLs have no track token before 2022**, and `classify_proceedings("")` is
  `unknown`; the 2021 D&B track has its own host.
- **The v2 group is the cheapest oracle:** one `GET /groups?id=<venue>` gives the API version (`domain`),
  all four status venueids and the public flags; `/groups?parent=<Org>.cc/<Y>` maps a year.
- **Scrubbing a paper page needs a global replace:** PMLR repeats the title and authors in twitter meta
  tags and three citation boxes; per-element regexes left them in. `scrub.py` collects the real strings
  first and replaces them everywhere, and an audit compared every fixture against the raw captures.

## Dead ends — don't repeat these
- v1 `invitation=…/Paper.*/-/Decision` filters: refused ("must be a prefix regex"). Go per forum.
- Reading the decision from `details=directReplies` on ICLR 2022 blind notes: the decision was not among
  the first replies sampled; 2022 has `content.venue` anyway.

## Decisions (and what would change them)
- decision-012 (rejected/withdrawn indexed, excluded by default) and decision-013 (crawl from 2013).
- Env names are `OPENREVIEW_USERNAME`/`OPENREVIEW_PASSWORD` (the committed `.env.example`); the
  maintainer's scholarmend-era `.env` needs them added.

## Follow-ups
- [ ] TASK-094 classify NeurIPS position/competition tracks; decide the 2026 Evaluations_and_Datasets_Track.
- [ ] TASK-095 keep `classify_venueid` off v1 status; audit the M2 RIS corpus.
- [ ] TASK-096 ICLR 2014/2015/2016 acceptance sources.
- [ ] TASK-054: NeurIPS 2021 main 2,334 (proceedings) vs 2,630 (OpenReview v1 venues) unexplained.

## Propagated to
- `.claude/skills/openreview-api/SKILL.md`, `.claude/skills/openreview-venueids/SKILL.md`,
  `.claude/skills/neurips-proceedings/SKILL.md`, `.claude/skills/pmlr-proceedings/SKILL.md`,
  `.claude/skills/track-taxonomy/SKILL.md`, `.claude/skills/coverage-reporting/SKILL.md`,
  `.claude/agents/openreview-crawler.md`, `.claude/agents/proceedings-miner.md`, `docs/specs/01-ingestion.md`,
  `CONTRIBUTING.md`.
