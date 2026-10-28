# A group the crawler skipped as no venue held 124 papers, in three venue-years, for a month

**Key lesson:** A `not_a_v2_venue` skip in an OpenReview crawl report is a lead, not a verdict: check the group's children live (`/groups?parent=<id>`) before writing it off, because a placeholder group (domain `OpenReview.net`, no content) can hold the real venues one level down.

- **Date:** 2026-10-28 · **Task:** task-191 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_v2.py` (`_child_venues`),
  `backend/tests/fixtures/http/openreview/v2/iclr-2026/{group-re-align,groups-parent-re-align,notes-workshop-sub-venue}.json`,
  `backend/src/openproceedings/ingest/pmlr_volumes.toml` (v306), `docs/results/coverage-sources.md` §Disagreements ICML 2026

## What we set out to do
Replace the ICML 2026 coverage row with its PMLR count, crawl NeurIPS 2026 main, D&B and position, and explain the
skipped ICLR 2026 `Workshop/Re-Align` group.

## What we learned
- **Re-Align was not empty.** TASK-178 called it "an empty placeholder group (domain OpenReview.net, no content), so
  nothing was listed under it". True of the group, not of its children: `/groups?parent=ICLR.cc/2026/Workshop/Re-Align`
  lists `/Research` and `/Challenge`, both v2 venues (67 and 5 accepted). The same shape hid NeurIPS 2025
  `Workshop/DBM/Findings` (43) and NeurIPS 2024 `Competition/LMC` (9). Every coverage report since 2026-09-29 showed
  these as `skipped groups: not_a_v2_venue 1`, flagged non-routine, and nobody listed the children.
- **A handed-over volume number can be wrong.** The task brief said ICML 2026 was PMLR v308; the PMLR index lists
  v308 as the AAAI NeuroAI workshop and v306 as "Proceedings of ICML 2026". The table's heading check would have
  stopped the crawl, but read the index before writing a row.
- **v306 can't gate main by itself.** Its 6,552 entries equal the fact sheet's main + position total and carry no
  sections, so the main row takes the split from the conference's position listing (6,552 − 212 = 6,340).
- **Logged in still sees nothing for NeurIPS 2026 main.** Venueid and invitation queries return `count` 0 for
  Conference, Evaluations_and_Datasets_Track and Position_Paper_Track, while the same session reads Creative AI's
  95 notes: the papers are not public yet, which a login can't change.

## Dead ends — don't repeat these
- Re-reading the placeholder group by id (`/groups?id=`) to "check for another venue id": it says nothing; list its
  children instead.

## Decisions (and what would change them)
- The crawler lists a non-venue group's children once, never deeper: every case seen is one level. A venue two levels
  under a placeholder would show as a child reported `not_a_v2_venue` and would need the same check.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` (the group tree),
  `.claude/skills/openreview-venueids/SKILL.md` (the sub-venue form), `.claude/skills/pmlr-proceedings/SKILL.md` (v306).
- Test or hook added? — `test_openreview_v2.py` (the recorded Re-Align shapes crawl as two workshop venues; a
  non-venue group with no venue children stays `not_a_v2_venue`), `test_venueid.py` rows.
