# A URL cut to a length cap can name another paper, so a cut identifier stays out of links and ids

**Key lesson:** When a length cap trims an identifier (a DOI or URL), keep the cut text only as display text: never fill the record's link slot from it (the next uncut claim does, else none), and stop identity reads from using it whenever the cut changed what it names. A cut that leaves the id alone must still count, or a record that names itself only by that URL stops the whole build.

- **Date:** 2026-10-22 · **Task:** task-279 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/caps.py` (`FIELD_CAPS`, `cut_identifier`, `unread_identifier`, `_names`, `_page_only`, `_own_page`), `backend/src/openproceedings/ingest/dedup.py` (`resolve`, `resolved_value`, `proceedings_ids`, `forum_ids`, `_names_creative_ai`, `_archive_target_cut`), `docs/results/2026-10-22-stored-string-lengths.md`, `backend/tests/unit/ingest/test_caps.py`, decision-053

## What we set out to do
Cap every stored string field that decision-026 left uncapped (DOI, URLs, author names, keywords, venue_id_raw,
an invitation claim's value, a claim's url and evidence). The owner chose "cap + trim": trimmed and flagged, never
refused.

## What we learned
- **A trimmed URL can be a valid id of another paper.** `urls.forum_id` reads `?id=` from the query, so
  `https://openreview.net/forum?pad=<2,000 chars>&id=Other12345…` cut at 2,048 reads as forum id `Other1`, which is
  valid (4–64 characters). Dedup's forum link would then merge the record with paper `Other1` in the same
  venue-year. Evidence: `test_a_cut_forum_url_that_names_another_paper_is_never_read_as_its_id`.
- **Skipping every cut URL is not safe either.** `dedup._dedup` refuses the whole build when a proceedings record
  doesn't name itself in a `urls.proceedings`/`urls.pdf` claim. An RIS URL with a long tracking query
  (`?utm_source=…`, real in the fixture) cut after its path still names the paper. Skipping it would have turned one
  long URL into a refused build, the opposite of the owner's choice. So `caps._names` compares what the whole URL and
  the cut one name (`urls.native`, `forum_id`, `proceedings_parts`, and an `iclr_archive` target's hash), and only a
  cut that changed it gets `not read as an id`. Evidence: `test_a_cut_query_string_still_names_its_proceedings_paper`.
- **Dedup's input check makes the slot rule and the resolve rule one rule.** `_dedup` requires each input to equal
  what its own claims resolve to (`fields don't match its own claims`). So clearing a record's `urls` slot in
  `cap_record` only works if `resolve` also fills no slot from a cut claim (`cut_identifier`). Evidence:
  `test_a_doi_or_url_past_its_cap_leaves_its_urls_slot_empty` asserts `resolve(out.id, out.provenance)[0] == out`.
- **The evidence cap has to hold the notes, or a second pass cuts them.** `cap_record` runs again after the
  `aaai_library` and OpenAlex fills, on records it has already capped. If the cap covered only the source's evidence,
  the notes added after it could push the whole past 4,000, and the second pass would cut the notes off. So the
  source's evidence is cut to what the notes leave, and `cap_record(out) is out` is asserted after every cut.
- **decision-026's cut falls before the last space, so one giant last word is dropped whole.** An evidence of
  `<route> <url> <4,000 e's>` keeps only the route and the url. This is the specified behaviour (every Unicode form
  keeps the same words); the first test assumed a cut mid-word.
- **Measuring the corpus is cheap and settles the version question.** A plain `json.loads` pass over the 1.2 GB
  `records.jsonl` (173,518 records) took 6 s. Running the new `cap_record` over every record took 100 s and returned
  each one unchanged (`changed=0`; the 26 the manifest already lists under decision-026 stay as they were). So
  `records.jsonl`, `snapshot_hash` and `index_version` are unchanged, and nothing needs a bump.
- **The longest keyword (733 characters) is an abstract.** ICLR 2025 `d8hURACo0P`'s authors put abstract sentences in
  OpenReview's keywords field, split at commas. A cap sized at about 1.4 times that would have been tight, so the
  keyword cap is 2,000.

## Dead ends — don't repeat these
- Treating every cut DOI or URL as "never an id". That reading looks safest but refuses the build for a cut that
  harmed nothing (a long query string after a proceedings path).
- A structural marker in the value itself (a trailing `…`). Each parser treats it differently (`forum_id` fullmatches,
  `_PMLR_PATH` doesn't), so it doesn't say "not an id" reliably.

## Decisions (and what would change them)
- Caps of at least 2.7 times the corpus maximum, so the current snapshot is untouched. Revisit if a real source comes
  near a cap (decision-053 §Consequences).
- A claim's own url over its cap is dropped rather than cut, because it is only ever rendered as a link
  (`paper-view.tsx`'s "source ▸") or read as the abstract's attribution link.

## Follow-ups
- [ ] task-280 — cap how many authors and keywords a record may hold (95 and 54 at most today); decision-053 caps
  each string, not the list.
- [ ] task-281 — bound the length of a record id's native part (`pmlr-`, `dblp-`, `ojs-`, `doi-` are unbounded).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` §The ingest caps (fields, caps, the
  identifier rules), `.claude/skills/dedup-rules/SKILL.md` (the forum link skips an unread cut URL),
  `.claude/skills/snapshots/SKILL.md`, `.claude/skills/logging-standards/SKILL.md`, `CLAUDE.md` (the `caps.py`
  entry), `docs/specs/01-ingestion.md` §Pipeline 2.
- Test or hook added? — `backend/tests/unit/ingest/test_caps.py` (each field at cap−1, cap and cap+1, the identifier
  rules, two Hypothesis properties, a snapshot build).

## Addendum — 2026-10-22 (review round 1)
- **"An id only if the cut changed nothing" still refused a build.** Code, security and observability review each
  found it: a record whose id itself is over 2,000 characters (a hostile PMLR key or OJS article id; the native forms
  have no length bound) has its own page URL cut inside the id, so the URL is unread and dedup's self-naming check
  refused the whole build. The fix records, at the cut, that the whole URL named the record's own id
  (`it named its own record`, `caps.names_own_record`), and dedup takes the record as naming itself
  (`dedup._own_ids`) without reading any id from the cut text. Lesson: when a rule removes evidence, list every
  invariant that needs that evidence (here `_dedup`'s self-naming check, `is_listing`, `_cluster`'s ids) before
  calling it safe.
- **A venue id is an identifier too.** Track-classifier and dedup review: cut before its last space,
  `NeurIPS.cc/2024/Creative_AI_Track <600 characters>` is exactly the Creative AI id, and a workshop's
  `…/Conference <600 characters>/Workshop/Foo` reads as the main conference's. So a cut venue id never fills
  `venue_id_raw` and is never Creative AI evidence, like a cut URL.
- **Set a slot with the resolver's own rule, not a guess.** `cap_record` first nulled an over-cap slot while
  `resolve` took the next uncut claim, so a record with two sources' DOIs would have failed dedup's input check. Now
  both call `dedup.resolved_value` (a function-level import in `caps`, since dedup imports caps).
- **A test of a guard has to make the guard matter.** The first Creative AI URL test used a value whose whole and cut
  forms both parsed to nothing, so removing the guard left it green. The replacement makes the cut land exactly after
  `.html`, so the cut text is a Creative AI page the whole never was. A hand mutation pass (removing each new guard,
  `>` to `>=`, dropping `strip()`, the evidence budget off by one) now fails a test for each.

## Addendum — 2026-10-22 (review round 2)
- **The round-1 own-record note was forgeable, so it went.** Code, dedup and security review each showed that
  `it named its own record` could be written by a source: RIS evidence repeats a venue id
  (`scholarmend:openreview_api venueid=…`), so a venue id ending in the note made any record a listing (reconcile's
  absence demotion skipped, a correct forum-link merge refused). After a merge the note also named the survivor, not
  the listing it came from. The replacement reads no evidence: a URL that names its own record whole (decided from the
  value and the record's id) and that a cut would unname is kept whole, flagged, as before the caps. Lesson: a note
  in evidence may only ever move a value toward "used less" (out of a slot, out of evidence for a merge); a note that
  grants anything (listing status, an id) is a channel for any source that writes evidence text.
- **Check what each source puts in evidence before trusting a suffix.** Crawlers end URL claims' evidence with fixed text, but RIS
  evidence holds raw values (a URL, a venue id). The `_url` validator keeps whitespace out of URLs, so only the venue
  id carried a forgery; adding `venue_id_raw` to the identifier fields opened that channel in round 1.

## Addendum — 2026-10-22 (automated security review)
- **An exemption from a cap needs its own bound.** Round 2 kept a self-naming URL whole when a cut would unname it.
  An automated security review flagged that this had no bound: an `iclr_archive` target's id hashes the whole URL, so
  a target of any length passed, which defeats the cap. The fix cuts the URL just past the first place it spells the
  record's own id (`caps._own_prefix`, kept only if that prefix still names the id), so only the id's own length
  (TASK-281) bounds it. The hash-derived `iclr_archive` id is left out: its target is cut and unread like any other,
  and dedup lets that record stand for itself only by the crawler's own claim (`dedup._archive_target_cut`), which no
  import can write. Lesson: whenever a rule says "keep it whole", ask what bounds "whole", and test the case where
  junk follows the part that matters (now `test_a_listing_whose_own_page_url_a_cut_would_unname_becomes_its_page_and_builds`).

## Addendum — 2026-10-22 (review round 3)
- **"Cut just past the id" was a guess about URL shapes, and the shapes said no.** Round 3 found that it aborted the
  build for a NeurIPS or ICLR page whose track token after the hash is long (the path must end `-Abstract….html`) and
  for a PMLR raw GitHub asset (the key sits mid-path), let leading zeros take a URL past the cap (`v000…235`), and never
  checked that the whole URL named the record's own id (a claim for `…/v235/abcddd…` was cut to name `abc`). The rule
  now rebuilds an address of the id's page from the parsed id, per form (`caps._own_page`), and keeps it only if it names
  the same id. Lesson: when a value must keep naming something, build it from the thing it names rather than trimming
  the source's text toward it.
- **An exception that drops an id from a set weakens every guard that reads the set.** The `iclr_archive` exception
  left the record's own id out of its cluster's proceedings ids, so the two-ids guard let it title-merge into another
  ICLR paper. `_cluster` now adds it back for those records (`test_an_archive_record_with_its_target_cut_is_still_kept_apart_from_another_paper`).

## Addendum — 2026-10-22 (review round 4)
- **A cut can't land before a letter that isn't there.** `_cut` falls before the last space, else before the last
  letter or digit, that fits. A Creative AI page followed by `?` and 2,000 `&` has neither in its tail, so the cut fell
  inside `.html`, and the page was rebuilt without its track token: the record stopped being Creative AI. Now a page
  first drops its query, parameters and fragment (`caps._page_only`) when that fits and names all the whole did; only
  a page whose own path is past the cap is rebuilt. Lesson: a fallback that rebuilds a value from what it names loses
  whatever else the value carried (here a track token), so prefer the step that keeps the source's text.
- **Every form a builder handles needs its own row.** Five builder branches (dblp AAAI, DOI, the OJS journal, the
  upper-case host, the 2021 D&B round) survived mutation until the test had a row per form. The D&B round turned out
  unreachable (its paths are fixed-length, so the tail step always fits), so its code went rather than stay untested.
