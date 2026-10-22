# A URL cut to a length cap can name another paper, so a cut identifier stays out of links and ids

**Key lesson:** When a length cap trims an identifier (a DOI or URL), keep the cut text only as display text: clear the record's link slot, make dedup fill no slot from it, and stop identity reads from using it whenever the cut changed what it names. A cut that leaves the id alone must still count, or a record that names itself only by that URL stops the whole build.

- **Date:** 2026-10-22 · **Task:** task-279 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/caps.py` (`FIELD_CAPS`, `cut_identifier`, `unread_identifier`), `backend/src/openproceedings/ingest/dedup.py` (`resolve`, `proceedings_ids`, `forum_ids`, `_names_creative_ai`), `backend/tests/unit/ingest/test_caps.py`, decision-053

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
- **decision-026's cut falls before the last space, so one giant last word goes whole.** An evidence of
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

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` §The ingest caps (fields, caps, the
  identifier rules), `.claude/skills/dedup-rules/SKILL.md` (the forum link skips an unread cut URL),
  `.claude/skills/snapshots/SKILL.md`, `.claude/skills/logging-standards/SKILL.md`, `CLAUDE.md` (the `caps.py`
  entry), `docs/specs/01-ingestion.md` §Pipeline 2.
- Test or hook added? — `backend/tests/unit/ingest/test_caps.py` (each field at cap−1, cap and cap+1, the identifier
  rules, two Hypothesis properties, a snapshot build).
