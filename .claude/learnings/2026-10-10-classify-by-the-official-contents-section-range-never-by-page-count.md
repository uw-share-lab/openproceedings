# A short entry is not a section: the official contents' page ranges classify, page counts mislead

**Key lesson:** Classify a proceedings' non-paper sections by the page range its official table of contents gives each section (a `[[section]]` row with its source), never by page count or title words, and let that range win over any inference; when no contents page exists, say the range is inferred from position, and pin the per-year counts with a replay over the pinned data.

- **Date:** 2026-10-10 · **Task:** task-224, task-225, task-226 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/dblp_aaai.toml`, `backend/src/openproceedings/ingest/acm_proceedings.toml`, `backend/tests/unit/ingest/test_track_rules_replay.py`, `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` §AAAI 1993–2008 sections, decision-050

## What we set out to do
Move AAAI 1993–2008's and AIES 2018–2023's student abstracts, consortium, demo, IAAI and robot entries, invited talks and keynotes out of track `main`.

## What we learned
- A page-count rule is wrong both ways. The task's "≤2 pages" list (767 AAAI entries) missed long entries in the same sections (NumaoTN02a, ZhouH02, TaylorS06, ValenteJV06, Wang06, HanF08 have 3+ pages) and all 231 IAAI papers, and it caught full papers that dblp only gives a start page for (GaurJH97) and the 2008 Short Papers, a technical section (evidence: report-226 §4 and the replay counts).
- AIES 2023's student block holds 12 entries of 3–6 pages between the 2-page ones. A "≤2 pages" filter would have left them `main` inside a student block. The range gives 31 (evidence: `fixtures/pinned/aies-2018-2023-pages.json`, replay test).
- The official contents beat earlier inference. ChangN94, which TASK-225 would have kept `main`, is listed under the 1994 Student Abstracts, and ArkinF97, guessed to be a competition abstract, is listed under Invited Talks.
- The AAAI contents pages of 1996–1999, 2000, 2004 and 2005 leave the IAAI papers out entirely; those papers are on the separate `IAAI/iaai<yy>contents.php` pages. An "unmatched" block in a join is a sign to look for a second contents page before calling it unresolved.
- dblp page fields have typos (`855-1856`, `1020-1015`, `1802-1893`, `1853-`). Keying a range on the *start* page leaves only one entry (BlackH06) that needs a key row.

## Dead ends — don't repeat these
- Planning key rows for every odd page field: two of the three proposed rows were redundant once start pages were parsed.
- Calling a block "unresolved" before checking the companion conference's contents page (IAAI): one Wayback fetch per year resolved 89 more entries.

## Decisions (and what would change them)
- Page-range `[[section]]` rows, not page counts or per-key rows, because a section is a page range in the printed volume and a row can cite its source. This would change if an official per-paper section label became readable (for example the ACM DL for AIES 2018–2023).

## Follow-ups
- [ ] none filed. Sultanik05, Thornton05 and WangL05 stay `main` and unresolved, with the reason in the task-226 notes; no official page lists them.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/track-taxonomy/SKILL.md` (track rows name the section ranges); spec 01 track table.
- Test or hook added? — `backend/tests/unit/ingest/test_track_rules_replay.py` (exact counts over the pinned data), plus `stale_section` stops in both crawlers.
