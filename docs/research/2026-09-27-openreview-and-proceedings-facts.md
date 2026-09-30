# OpenReview and proceedings facts, checked live (TASK-002/050/096/104/106, 2026-09-27)

A manual research run before the M4 crawlers (TASK-050–054), extended while implementing the v2 crawler,
the ICLR archive and later proceedings fixtures (TASK-050/096/104/106). It checked every fact the ingestion skills and spec 01
marked "verify" against the live services, for every venue-year from 2013 (decision-013).
Requests were read-only, about one every two seconds, with a descriptive `User-Agent`, and honoured
`Retry-After`; about 400 OpenReview requests (within the 500/hour notes and 700/hour groups budgets) and about 35 proceedings pages.
No bulk data was kept. Recorded, scrubbed fixtures of each response shape are under
`backend/tests/fixtures/http/` (§Fixtures). Counts are as of 2026-09-27 and will move as venues publish.

## The fact table

| Venue | Years | Source | Status representation | Abstract | Auth |
|---|---|---|---|---|---|
| ICLR | 2013 | OpenReview v1, `ICLR.cc/2013/conference/-/submission` (67) | `content.decision` on the submission: `conferenceOral-iclr2013-conference`, `conferencePoster-iclr2013-conference`, `…-workshop` (32), `reject` (12). Track and status both come from that string. No venueid. | all 67 | login |
| ICLR | 2014 | v1 submissions plus the public ICLR conference-proceedings archive | `content.decision` is `submitted, no decision` on all 88 OpenReview submissions, but the archive lists 35 accepted conference targets. Archive membership supplies accepted/main; OpenReview supplies abstracts where identities later join. | archive: none | archive: none; OR: login |
| ICLR | 2015 | public ICLR accepted-main archive | ICLR 2015 has no OpenReview group. The archive supplies 31 unique accepted conference targets; oral/poster duplicates collapse and its separate workshop section is excluded. | none | none |
| ICLR | 2016 | v1 workshop submissions plus the public ICLR accepted-main archive | The conference track is not on OpenReview (`ICLR.cc/2016/conference/-/submission` has 0 notes); the archive supplies 80 accepted conference targets. | archive: none | archive: none; OR: login |
| ICLR | 2017 | v1, `ICLR.cc/2017/conference/-/submission` (490), `ICLR.cc/2017/workshop/-/submission` (161) | Every conference note has `venueid = ICLR.cc/2017/conference` (lower-case `conference`), **including 245 rejected** (`venue = Submitted to ICLR 2017`) and 47 `ICLR 2017 Invite to Workshop`. 53 workshop-invitation notes also carry the conference venueid. Status and track come from `venue` only. | all | login |
| ICLR | 2018 | v1, `ICLR.cc/2018/Conference/-/Blind_Submission` (935), `…/-/Withdrawn_Submission` (83) | No venue/venueid on submissions. Decision is a separate note, invitation `ICLR.cc/2018/Conference/-/Acceptance_Decision` (935), `content.decision` = `Accept (Oral)` (23) / `Accept (Poster)` (314) / `Invite to Workshop Track` (90) / `Reject` (508). | all | login |
| ICLR | 2019 | v1, `…/2019/Conference/-/Blind_Submission` (1,419), `…/-/Withdrawn_Submission` (160) | No venue/venueid. Decision is the meta-review: `ICLR.cc/2019/Conference/-/Paper<N>/Meta_Review`, `content.recommendation` = `Accept (Oral)` / `Accept (Poster)` / `Reject`. | all | login |
| ICLR | 2020 | v1, Blind (2,213), Withdrawn (369), Desk_Rejected (12) | No venue/venueid. `ICLR.cc/2020/Conference/Paper<N>/-/Decision`, `content.decision`. | all | login |
| ICLR | 2021 | v1, Blind (2,594), Withdrawn (403), Desk_Rejected (17) | Accepted notes have `venueid = ICLR.cc/2021/Conference` and `venue = ICLR 2021 {Oral,Spotlight,Poster}` (859); rejected ones have neither (1,735); decision note `Paper<N>/-/Decision`. One withdrawn-invitation note (`xGZG2kS5bFk`) carries `venue = ICLR 2021 Poster`. | all | login |
| ICLR | 2022 | v1, Blind (2,617), Withdrawn (779), Desk_Rejected (26) | Every blind note has `venueid = ICLR.cc/2022/Conference`, **including 1,523 rejected** (`venue = ICLR 2022 Submitted`); accepted: `ICLR 2022 {Oral,Spotlight,Poster}` (1,094). Withdrawn notes have `venue = venueid = ""` (770) or none (9). | all | login |
| ICLR | 2023 | v1, Blind (3,792), Withdrawn (1,145), Desk_Rejected (18) | Every blind note has `venueid = ICLR.cc/2023/Conference`, **including 2,219 rejected** (`Submitted to ICLR 2023`); accepted: `ICLR 2023 notable top 5%` (90), `notable top 25%` (281), `poster` (1,202). Withdrawn: `""`. | all | login |
| ICLR | 2024–2026 | OpenReview v2 | `content.venueid` suffix: bare = accepted, `/Rejected_Submission`, `/Withdrawn_Submission`, `/Desk_Rejected_Submission`. 2025: 3,703 / 4,908 / 2,991 / 70. All public (`public_submissions`, `public_withdrawn_submissions`, `public_desk_rejected_submissions` all true). | 100% of accepted | login |
| NeurIPS | 2013–2020 | proceedings.neurips.cc | Listed = accepted (2013: 360, 2020: 1,898). No track token in the URL (`<sha>-Abstract.html`). No rejected papers. | on the abstract page | none |
| NeurIPS | 2021 | v1 `NeurIPS.cc/2021/Conference/-/Blind_Submission` (2,768); proceedings main (2,334); D&B on OpenReview v1 `…/Track/Datasets_and_Benchmarks/Round1` (144) and `/Round2` (108), D&B proceedings on `datasets-benchmarks-proceedings.neurips.cc` (174) | Main: `venueid = NeurIPS.cc/2021/Conference` on all but 2, `venue = NeurIPS 2021 {Oral,Spotlight,Poster}` or `NeurIPS 2021 Submitted` (136 opt-in public rejected). D&B: the bare Round venueid on **every** note, rejected included (Round 1: 66 accepted, 78 `Submitted to …`). | all | login (OR), none (proc.) |
| NeurIPS | 2022 | v1 Blind (2,824), D&B `NeurIPS.cc/2022/Track/Datasets_and_Benchmarks/-/Submission` (163); proceedings | Main: `venueid = NeurIPS.cc/2022/Conference` on all; `venue = NeurIPS 2022 Accept` (2,671 = proceedings) or `NeurIPS 2022 Submitted` (153). D&B: only the 163 accepted are public. | all | login |
| NeurIPS | 2023–2025 | v2 plus proceedings | venueid suffix as for ICLR v2. Rejected only when the authors opted in (2024 main: 201); withdrawn/desk-rejected ≈ none public (`public_*` all false). The 2025 proceedings split Creative AI onto the year page and main/D&B/position onto `vol38-main-conference`. | 100% of accepted | OR: login; proceedings: none |
| NeurIPS | 2026 | v2 groups exist (Conference, `Evaluations_and_Datasets_Track`, Position, Creative AI, Competition) | No main-track notes public yet (0 on 2026-09-27); Creative AI has 95. | – | login |
| ICML | 2013–2022 | PMLR v28, v32, v37, v48, v70, v80, v97, v119, v139, v162 | Listed = accepted. `ICML.cc/2020/Conference` exists on OpenReview but has no public notes. | on the paper page | none |
| ICML | 2023–2025 | v2 + PMLR v202, v235, v267 | venueid suffix; rejected only opt-in (2025: 162), none for 2023–2024. 2024 position papers sit inside `ICML.cc/2024/Conference` with no marker (2,610 = v235's 2,610). 2025 has `ICML.cc/2025/Position_Paper_Track` (73). | 100% of accepted | login |
| ICML | 2026 | v2 (6,341 main, 213 position); PMLR volume not yet listed | as 2025 | 100% | login |

## OpenReview

### Hosts and API versions
- The venue group's `domain` field says which API holds a venue: a v2 venue's group has
  `domain = <its id>` and a `content` block with its venueids; a v1 venue's group has `domain = null`
  and only a `web` script (whose constants name its invitations). One `GET /groups?id=<venue>` on api2
  answers the question for any venue, v1 or v2 (the groups table is shared).
- v2 (`api2.openreview.net`): ICLR 2024+, NeurIPS 2023+ (including 2023 D&B), ICML 2023+, ICLR Tiny
  Papers 2024 and Blogposts 2024+.
- v1 (`api.openreview.net`): ICLR 2013, 2014, 2016–2023 (and Tiny Papers / Blogposts 2023),
  NeurIPS 2021–2022 (main and D&B).
- A v1 note is not on api2 and a v2 note is not on api1: both answer `404 NotFoundError` by `id`
  (fixture `openreview/v2/errors/v1-note-not-found.json`). A venueid query on the wrong host returns
  an empty list, not an error, so a crawler must pick the host from the table above, never by falling
  back.
- Group tree (`GET /groups?parent=<Org>.cc/<Y>&select=id`) is the cheapest manual map of a year: it lists
  `Conference`, `Workshop`, `Workshop_<City>`, the tracks and the proposal groups. The crawler deliberately
  omits `select=id`, because its cache boundary must inspect each returned group's `readers` ACL before
  retaining even the id.

### Authentication
- **Unauthenticated access does not suffice.** Anonymous `GET` on api2 `/notes` and api1 `/notes`
  returns **HTTP 200 with an HTML "Verifying your browser" page** (a Cloudflare Turnstile challenge), not a
  429 and not JSON (fixture `openreview/v2/errors/anonymous-challenge.json`). A client must check the
  `content-type` is JSON before parsing, and treat HTML as "not authenticated", never as an empty result.
- `POST https://api2.openreview.net/login` with `{"id", "password"}` returns `{"token": …}`; the same
  bearer token works on api1.
- `.env` variable names: this project's `.env.example` names `OPENREVIEW_USERNAME` and
  `OPENREVIEW_PASSWORD`. During the 2026-09-27 run, the maintainer's Scholarmend-era `.env` had only
  `SCHOLARMEND_OPENREVIEW_USER` / `SCHOLARMEND_OPENREVIEW_PASSWORD`; the crawler intentionally ignores
  those legacy names. The main checkout was corrected before the 2026-09-29 TASK-107 run, and
  `env_credentials()` then reported configured without exposing either value. `.env.example`,
  `scripts/setup-dev.sh` and `CONTRIBUTING.md` all use the crawler's two supported names.

### Rate limits
- api2 sends per-resource budgets: notes `ratelimit-policy: 500;w=3600`, groups `700;w=3600`, plus
  `ratelimit-remaining` and `ratelimit-reset` (seconds from now) and `x-ratelimit-reset` (an epoch
  timestamp). Use `ratelimit-reset`, not the epoch header.
- api1 sends `180;w=60` to anonymous callers and no rate-limit headers to authenticated ones.
- No 429 was seen in the run (paced at one request per two seconds).

### Pagination and counting
- `limit` must be ≤ 1000 on both hosts: `limit=1001` is `400 ValidationError` "limit must be <= 1000"
  (fixture `openreview/v2/errors/limit-over-1000.json`; v1 answers the same).
- **`count` appears only when the request has an `offset` parameter** (even `offset=0`): v2
  `?content.venueid=…&limit=1&offset=0&select=id` → `{"notes": [...], "count": 2260}` (fixture
  `notes-count.json`); without `offset` the response is `{"notes": [...]}`. v1 returns `count` on every
  `/notes` response.
- Both hosts accept `select=` (e.g. `select=id,content.venueid`), which cuts a page to its ids.
- v1 invitation queries must be a *prefix* regex: `invitation=ICLR.cc/2020/Conference/Paper.*/-/Decision`
  is `400 "invitation must be a prefix regex"`. Fetch v1 decisions through each forum
  (`?forum=<id>`, or `details=directReplies` on the submission listing), not by invitation.
- A `?forum=<id>` listing is not ordered with the submission first (ICLR 2018 fixture): find the
  submission by `id == forum`.

### Access lists (readers / nonreaders)
- **API v1 writes `nonreaders: null` on public notes** (2026-09-29, TASK-119). One authenticated read of
  `GET https://api.openreview.net/notes?invitation=ICLR.cc/2017/workshop/-/submission&limit=1000&offset=0`
  returned `count` 161: every note had `readers: ["everyone"]`, 102 had `nonreaders: []` and 59 had
  `nonreaders: null` (tallied with `Counter(repr(n.get("nonreaders", "<absent>")) for n in notes)`; only ids
  and ACLs were printed). The same read of `ICLR.cc/2017/conference/-/submission` (490 notes) found no null
  `nonreaders`. A null excludes no one; the client treats it as `[]` (`_world_readable`). Fixture
  `openreview/v1/iclr-2017/note-workshop-null-nonreaders-live.json` (note `SJGfklStl`, fetched by id).

### How status is represented (the key finding)
- **v2:** the submission note's `content.venueid` suffix is the status, and the group's content names
  the four venueids (`submission_venue_id`, `rejected_venue_id`, `withdrawn_venue_id`,
  `desk_rejected_venue_id`; fixture `iclr-2025/group-conference.json`). Checked on ICLR 2024–2026,
  NeurIPS 2023–2025 (main, D&B, position, competition, Creative AI), ICML 2023–2026 (main, position),
  workshops. `…/Submission` (under review) is declared on every group but had no public note on
  2026-09-27 (every decided venue shows 0).
- **v1: `content.venueid` is not status evidence.** ICLR 2017, 2022 and 2023, NeurIPS 2021–2022 and
  D&B 2021 put the bare venue path on rejected submissions too, and ICLR 2017 puts the conference
  venueid on workshop invitations. In v1 the status comes from `content.venue` (where the year has it)
  or the decision note; the venueid only confirms venue and year. `classify_venueid` read
  `ICLR.cc/2022/Conference` as `main`/`accepted`, so it must never be applied to a v1 note's venueid for
  status. TASK-095 made it return `unknown` status for every v1 venue-year.
- v1 `venue` vocabulary seen: `ICLR 2017 {Oral,Poster,Invite to Workshop}`, `Submitted to ICLR 2017`;
  `ICLR 2021 {Oral,Spotlight,Poster}`; `ICLR 2022 {Oral,Spotlight,Poster,Submitted}`; `ICLR 2023
  {notable top 5%,notable top 25%,poster}`, `Submitted to ICLR 2023`; `NeurIPS 2021
  {Oral,Spotlight,Poster,Submitted}`; `NeurIPS 2022 {Accept,Submitted}`; `NeurIPS 2021 Datasets and
  Benchmarks Track (Round N)` / `Submitted to …`; `NeurIPS 2022 Datasets and Benchmarks ` (trailing
  space); `Submitted to Tiny Papers @ ICLR 2023` (all 219: no decisions in the venue string);
  `Blogposts @ ICLR 2023`, `… Conditional`, `Submitted to Blogposts @ ICLR 2023`.
- v2 `venue` vocabulary (presentation): `ICLR 2024 {oral,spotlight,poster}`, `ICLR 2025
  {Oral,Spotlight,Poster}`, `ICLR 2026 {Oral,Poster}`; `NeurIPS 2023–2025 {oral,spotlight,poster}`;
  `NeurIPS 2024 Track Datasets and Benchmarks {Oral,Spotlight,Poster}`; `ICML 2023 {Poster,OralPoster}`,
  `ICML 2024 {Oral,Spotlight,Poster}`, `ICML 2025 {oral,spotlightposter,poster}`, `ICML 2026
  {regular,spotlight}`; `Tiny Papers @ ICLR 2024 {Archive,Present,Notable}`. Case and wording vary per
  year, so presentation parsing needs a per-venue-year table, not a regex.
- **What is public:** ICLR publishes every rejected, withdrawn and desk-rejected submission (every
  year with decisions on OpenReview: 2013 and 2017–2023 on v1; 2024+ with all three flags true). NeurIPS and ICML set all three flags false: rejected papers appear only when
  the authors opt in (NeurIPS 2023: 176, 2024: 201, 2025: 254; ICML 2025: 162, 2026: 214; ICML 2023–2024: 0),
  and withdrawn or desk-rejected ones almost never (NeurIPS 2023: 1). Workshops set their own flags.

#### TASK-107 authenticated v1 follow-up (2026-09-29)

- One `?invitation=…&limit=1&offset=0` response is now recorded for every v1 venue-year with a group.
  The newly recorded main-listing totals are ICLR 2017–2022: 490, 935, 1,419, 2,213, 2,594 and 2,617;
  NeurIPS 2021–2022: 2,768 and 2,824. ICLR 2015 still has no group.
- ICLR withdrawn-listing totals are 83 (2018), 160 (2019) and 369 (2020). Desk-rejected totals are
  12 (2020), 17 (2021) and 26 (2022). The exact invitations already named by the adapters are therefore
  live-proven rather than inferred from adjacent years.
- ICLR 2020 paper 2594 and ICLR 2021 paper 2910 both carry a public decision note whose exact decision is
  `Accept (Poster)`. The v1 adapters now map that string to accepted/poster in both years.
- The full 2026-09-29 crawl's tally of ICLR decision notes (from the cached v1 responses): 2018
  `Reject` 496, `Accept (Poster)` 314, `Invite to Workshop Track` 90, `Accept (Oral)` 23; 2019 meta-review
  `recommendation` `Reject` 917, `Accept (Poster)` 478, `Accept (Oral)` 24; 2020 `Reject` 1,526, `Accept
  (Poster)` 531, `Accept (Spotlight)` 108, `Accept (Talk)` 48; 2021 decision notes `Reject` 1,735 (the crawl
  reads a 2021 decision note only when `content.venue` leaves the forum open, so its tally sees only those;
  `Accept (Poster)` is verified on paper 2910). Every string seen is now mapped (TASK-123).
- `ICLR.cc/2023/BlogPosts/-/Blind_Submission` is the BlogPosts listing (19 notes); a recorded note says
  `Blogposts @ ICLR 2023` and has venueid `ICLR.cc/2023/BlogPosts`.
- NeurIPS 2021 and 2022 both accept the exact public main-track `Withdrawn_Submission` and
  `Desk_Rejected_Submission` invitation queries, and all four return count 0. The crawler now records those
  zeroes instead of reporting the invitations as unverified. The NeurIPS 2022 Datasets and Benchmarks
  submission listing has 163 notes; its recorded example uses the already-known trailing-space venue label.
- The ICLR 2017 public notes reconfirm both schema variants: `authors` can be one unsplit string, and
  `ICLR 2017 Invite to Workshop` is carried by `content.venue`. A workshop listing viewed with a role-bearing
  account returned a non-world-readable row and was deliberately discarded; only public-by-id evidence is
  committed.

#### TASK-125: NeurIPS 2021 notes that repeat a paper (2026-09-29 crawl cache)

- NeurIPS 2021's main Blind_Submission listing holds **300 papers twice**: two notes with different ids and
  numbers (e.g. `-K4tIyQLaY` #292 and `BW2Z6B7S9KZ` #8244) whose content is identical (title, authors,
  authorids, abstract, keywords, TL;DR, pdf path, venue, venueid) apart from `_bibtex`, which embeds the id.
  By status: 297 accepted (267 poster, 25 spotlight, 5 oral) and 3 opt-in rejected. The 297 are the gap
  between the 2,630 OpenReview-accepted main papers (TASK-054's note) and the official 2,334: 2,333 remain
  accepted after the collapse. Dedup refused each such title group as two submissions, so neither note merged
  with its proceedings record.
- The v1 crawler now collapses them (`openreview_v1.collapse_duplicate_submissions`; spec 01 §Sources): an
  offline replay of the real cache imports 2,720 NeurIPS 2021 records from 3,020 notes, with 300
  `duplicate_submission`, keeping the lower number (`-K4tIyQLaY`). Every other v1 venue-year (ICLR
  2013–2023, NeurIPS 2022) and every v2 venue-year (ICLR 2024–2025, ICML 2023–2025, NeurIPS 2023–2025)
  collapses 0. A full offline `op snapshot build` from that cache then has NeurIPS 2021 main at 2,335
  accepted (2,333 merged with the proceedings, 1 OpenReview-only, 1 proceedings-only) against the official
  2,334, where the trial had 2,929 (2,036 merged, 595 OpenReview-only, 298 proceedings-only).
- The kept note (lowest number) is a tie-break, not the one the proceedings name: the cached NeurIPS 2021
  proceedings pages link the kept forum for 177 of the 297 accepted pairs and the dropped forum for 120 (never
  both, never neither), e.g. `0hJ-U3aqUDf` #401 kept while the proceedings link `rvKD3iqtBdk` #3462. Harmless
  while the NeurIPS importer doesn't claim that link as `urls.forum` (dedup-rules skill).
- Same pdf but not the same paper by content, kept apart: NeurIPS 2021 `W6e384Lkjbw` (#5999, no `venue`,
  so status unknown) and `rDdb26AQ0SO` (accepted); ICLR 2018's 24 pdfs listed as a blind note and a
  withdrawn note (status differs, authors differ on 12).
- The NeurIPS 2021 D&B surplus (185 accepted vs 174 official in the trial) is **not** this: OpenReview's D&B
  rounds hold exactly 174 accepted notes, and its 11 same-title pairs are a Round 1 rejection and a Round 2
  acceptance with different pdfs (resubmissions). The crawl keeps both notes, and dedup still refuses to guess
  which one a proceedings record is, so those 11 stay unmerged.

#### TASK-050 authenticated v2 fixture follow-up (2026-09-29)

- Root `?parent=` responses are now recorded without `select=id` for ICML 2023 and all three 2026 venues.
  They contain 2, 4, 10 and 4 public groups respectively (ICML 2023, ICLR 2026, NeurIPS 2026, ICML 2026),
  including the complete public group documents needed to enforce the cache ACL boundary.
- One nonempty note listing is recorded for each previously missing venue-year: ICML 2023 Conference
  (1,828), ICLR 2026 Conference (5,351), NeurIPS 2026 Creative AI (95), and ICML 2026 Conference (6,341).
  The one retained note per listing is scrubbed; the real counts, venueids and venue labels remain evidence.
- NeurIPS 2026's Conference group has no `venue_id` yet and its bare group-id listing is empty. The first
  nonempty public bare group-id listing is `Creative_AI_Track`; the conservative classifier keeps that form at
  `other` / `unknown`, as it already did for 2025, rather than deriving acceptance from `content.venue`.
- Every response passed `OpenReviewClient`'s world-readable public projection before capture. Tests feed
  the scrubbed exchange back through the real cache codec and then replay it with an offline client that
  has neither credentials nor a transport call; the full-crawl offline replay test remains alongside it.

### venueid forms confirmed (each with a fixture or a checked id)

| Form | Example (checked) | Track / status |
|---|---|---|
| `<Org>.cc/<Y>/Conference/Desk_Rejected_Submission` | ICLR 2024 `mnyXZBa5dP`; ICLR 2025 (70), 2026 (908) | main / desk_rejected |
| `<Org>.cc/<Y>/Conference/Submission` | declared by every v2 group (`submission_venue_id`); no live note | main / unknown |
| `NeurIPS.cc/2023/Track/Datasets_and_Benchmarks` (+ `/Rejected_Submission`) | 322 accepted, 16 rejected | datasets_benchmarks |
| `NeurIPS.cc/<Y>/Datasets_and_Benchmarks_Track` (2024, 2025; no `Track/`) | 2024: 459; 2025: 497 | datasets_benchmarks |
| `NeurIPS.cc/2026/Evaluations_and_Datasets_Track` | group exists (NeurIPS renamed the D&B track for 2026); no notes yet | datasets_benchmarks (TASK-094; `other` before it) |
| `NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1`, `/Round2` | `iBLHqLgbRn` (rejected, bare Round1) | datasets_benchmarks / status from `venue` only |
| `NeurIPS.cc/2025/Position_Paper_Track` (+ `/Rejected_Submission`) | 40 accepted, 55 rejected | position (TASK-094; `other` before it) |
| `ICML.cc/<Y>/Position_Paper_Track` | 2025: 73; 2026: 213 | position |
| ICML 2024 position papers | inside `ICML.cc/2024/Conference`, no marker | unknown (as `volumes.py` already does for v235) |
| `ICLR.cc/2023/TinyPapers` (v1), `ICLR.cc/2024/TinyPapers` (v2) | 2023: 219 (all "Submitted to"); 2024: 192 | tiny_papers |
| `ICLR.cc/2023/BlogPosts` (v1), `ICLR.cc/<Y>/BlogPosts` (v2, 2024–2026) | spelling `BlogPosts` confirmed | blogpost |
| `NeurIPS.cc/2024/Competition_Track`, `NeurIPS.cc/2025/Competition_Track` | 2024: 16 | competition (TASK-094; `other` before it) |
| `NeurIPS.cc/<Y>/Creative_AI_Track` | 2025: 92; 2026: 95 | other |
| `<Org>.cc/<Y>/Workshop/<name>/Rejected_Submission` | `ICLR.cc/2025/Workshop/ICBINB/Rejected_Submission` (12) | workshop / rejected |
| `<Org>.cc/<Y>/Workshop_<City>/<name>` | `NeurIPS.cc/2025/Workshop_Mexico_City/ResponsibleFM` (105) | workshop / accepted |
| `ICLR.cc/2017/conference` (lower case, v1) | 490 notes, all statuses | parses as `other` today; v1 only |
| Other year-level groups seen | `NeurIPS.cc/2024/High_School_Projects_Track`, `NeurIPS.cc/2025/Education_Program`, `NeurIPS.cc/2026/Education_Track`, `NeurIPS.cc/2024/Competition/LMC`, `NeurIPS.cc/2022/Challenge/CellSeg`, `NeurIPS.cc/2019/Reproducibility_Challenge` | not in the taxonomy (`other` if ever crawled) |

Workshop names include hyphens and digits (`SCI-FM`, `CLRLC-LLMs`, `7HVU`).

## ICLR accepted-paper archive (iclr.cc/archive)
- The official archive fills exactly the conference-acceptance gaps OpenReview cannot: 2014 has
  submissions but no decisions, 2015 is absent from OpenReview, and 2016 has only workshop submissions.
- The recorded pages contain 35 (2014), 31 (2015), and 80 (2016) unique accepted conference targets.
  The 2015 accepted-main page repeats some targets under oral/poster headings and also contains a workshop
  section; identity-based deduplication and section scoping are therefore part of the adapter contract.
- The 2014 page is Google Sites markup: 34 entries are a title `<p>` followed by an author `<p>`, but one,
  "Unit Tests for Stochastic Optimization" (arXiv 1312.6055), is a bare `<span><b><a>` whose authors are the
  first `<i>` of the following `<div>`, a `<div>` that then holds every later entry. The first full crawl's
  coverage trial (2026-09-29) counted 34 of 35 until the parser read it (TASK-124).
- The archive lists title and authors but no abstract. Most entries target arXiv; a target is the stable
  identity evidence. OpenReview forum targets retain the forum id, while other canonical targets use
  `iclr-<sha256(target)[:32]>`. Fragment-only page changes cannot change an id.

## NeurIPS proceedings (proceedings.neurips.cc)
- The site index `https://proceedings.neurips.cc/` links every year 1987–2025. Year pages are
  `/paper_files/paper/<YYYY>`; each entry is `<li class="<track>" data-track="<track>">` with
  `<a title="paper title" href="…">` and `<span class="paper-authors">`.
- **URL grammar by year:** 1987–2021 main: `/paper_files/paper/<Y>/hash/<sha>-Abstract.html` (no track
  token; `data-track="none"`). 2022–2023: `-Abstract-Conference.html` and
  `-Abstract-Datasets_and_Benchmarks.html`. 2024+: `-Abstract-Datasets_and_Benchmarks_Track.html`.
  2025 adds `-Abstract-Position_Paper_Track.html`; Creative AI uses
  `-Abstract-Creative_AI_Track.html` on the base page.
- Counts per year page: 2013: 360, 2020: 1,898, 2021: 2,334 main, 2022: 2,671 + 163 D&B, 2023: 3,218 +
  322 D&B, 2024: 4,034 + 459 D&B. The 2025 base page lists 64 Creative AI papers and links its
  `vol38-main-conference` companion, whose 5,823 entries are 5,286 main, 497 D&B and 40 position papers
  (response SHA-256 `48c2de5e5acae991a8b88eaa00174387a7ce066efeb337e30593989bd5015c9a`).
  The crawler follows this recorded pair; an unfamiliar “See also” page remains a warning rather than
  silently expanding scope.
- **NeurIPS 2021 D&B has a separate host:** `https://datasets-benchmarks-proceedings.neurips.cc/paper/2021`
  (the host's index lists only 2021) with 174 papers, `…/hash/<sha>-Abstract-round1.html` (66) and
  `-Abstract-round2.html` (108), `<li class="roundN">` entries and authors in `<i>`. These counts equal
  OpenReview's accepted Round 1 (66) and Round 2 (108).
- Abstract page: `<meta name="citation_title">`, `citation_author` metas, `<h1 class="paper-title">`,
  `<p class="paper-authors">`, `<span class="paper-track">` (2022+), and `<p class="paper-abstract">`.
  Pre-2022 pages also link `<sha>-Metadata.json` and `<sha>-Reviews.html`.
- Double escaping is real: the 2025 index has `Chenyue &amp;quot;xdd44&amp;quot; Dai`.
- Cross-check (TASK-052/072): 2022 main 2,671 and D&B 163, 2023 main 3,218 and D&B 322, 2024 D&B 459
  all equal OpenReview's accepted counts. **2024 main: proceedings 4,034, OpenReview 4,035** (one
  paper to reconcile). **2021 main: proceedings 2,334, OpenReview v1 venues say 2,630 accepted**
  (2,286 poster + 284 spotlight + 60 oral) — explained by the TASK-125 section above (297 accepted notes listed twice).

## PMLR (proceedings.mlr.press)
- The index `https://proceedings.mlr.press/` lists every volume as
  `<li><a href="vN"><b>Volume N</b></a> <title></li>` (326 volumes).
- ICML volumes (heading verified on each volume page, `<h2>Volume N: International Conference on
  Machine Learning, <dates>, <place></h2>`; paper count = `<div class="paper">` entries):

| Volume | ICML | Papers | Index title |
|---|---|---|---|
| v28 | 2013 | 283 | ICML 2013 Proceedings |
| v32 | 2014 | 310 | ICML 2014 Proceedings |
| v37 | 2015 | 270 | ICML 2015 Proceedings |
| v48 | 2016 | 322 | ICML 2016 Proceedings |
| v70 | 2017 | 434 | Proceedings of ICML 2017 |
| v80 | 2018 | 621 | Proceedings of ICML 2018 |
| v97 | 2019 | 773 | Proceedings of ICML 2019 |
| v119 | 2020 | 1,084 | Proceedings of ICML 2020 |
| v139 | 2021 | 1,183 | Proceedings of ICML 2021 |
| v162 | 2022 | 1,233 | Proceedings of ICML 2022 |
| v202 | 2023 | 1,828 | Proceedings of ICML 2023 (= OpenReview accepted 1,828) |
| v235 | 2024 | 2,610 | Proceedings of ICML 2024 (= OpenReview 2,610, position papers included, unmarked) |
| v267 | 2025 | 3,330 | Proceedings of ICML 2025 (= OpenReview 3,257 main + 73 position) |
| – | 2026 | – | not on PMLR on 2026-09-27 |

  v28 and v32 are split into "Cycle 1/2/3 Papers" sections; no volume marks position papers.
- NeurIPS competition volumes: v123 (2019 Competition and Demonstration Track, 23 papers), v133
  (2020, 20), v176 (2021 Competitions and Demonstrations Track, 36, sections "Competitions" and
  "Demonstrations"), v220 (2022 Competition Track, 20).
- ICML workshop volumes exist and must never be ICML main: v27 (2011 workshop), v184 (ICML 2022
  Healthcare AI workshop), v251 (GRaM at ICML 2024), v292 (TerraBytes at ICML 2025); many NeurIPS
  workshop volumes too (v116, v136, v137, v163, v181, v187, v210, v226, v239, v262).
- Recorded paper entries in v202, v235 and v267 link the OpenReview forum
  (`openreview.net/forum?id=…`), which gives the PMLR ↔ OpenReview join for 2023+ without title matching;
  the recorded v28 paper page confirms the pre-OpenReview shape has no such link.
- Paper page (`/vN/<key>.html`): `citation_title`, `citation_author` metas, `<div id="abstract"
  class="abstract">`; the title and authors are repeated in twitter meta tags and the BibTeX, Endnote
  and APA boxes.

## Fixtures
`backend/tests/fixtures/http/` holds the recorded, scrubbed responses above: 29 OpenReview v2,
46 v1, 3 ICLR archive, 8 NeurIPS proceedings and 8 PMLR files. Each is
`{"_recorded", "request": {"method", "url", "authenticated"}, "response": {"status", "headers", "json" | "text"}}`.
`scrub.py` (no network code) made them from the raw captures: titles, abstracts, authors, author ids,
keywords, reviews and emails are synthetic; ids, venueids, venue strings, decisions, invitations, dates and
rate-limit headers are real (decision-004). Long listings are trimmed (the `_recorded.trimmed` field says
how). `backend/tests/unit/ingest/test_venueid.py` reads every recorded OpenReview note (TASK-094/095/097);
the crawler tasks read the rest. TASK-097 re-recorded the v2 Tiny Papers 2024 and
`Workshop_Mexico_City` notes after the scrubber fix; their real venue labels are retained and table-tested.

## Follow-ups
- TASK-094: classify.py venueid table: NeurIPS `Position_Paper_Track` → position, `Competition_Track`
  → competition (both verified), and a spec decision for `Evaluations_and_Datasets_Track` (2026).
- TASK-095: v1 venueids are not status evidence: keep `classify_venueid` off v1 notes' status, and
  audit the M2 RIS corpus for ICLR 2017/2022/2023, NeurIPS 2021–2022 and D&B 2021 records whose
  `accepted` came from a bare v1 venueid.
- The NeurIPS 2021 and 2024 main-track count gaps go to TASK-054 (notes added there).
