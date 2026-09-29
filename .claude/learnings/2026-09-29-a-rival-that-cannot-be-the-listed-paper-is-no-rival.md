# A same-title workshop or rejected note kept 212 proceedings papers from merging with their OpenReview note

**Key lesson:** An ambiguity rule that counts every same-title cluster as a rival is too blunt: first set aside the clusters that can never be the listed paper (a track the proceedings don't host, or a not-accepted status), then judge the rest with the unchanged merge rule. Keep `unknown` a rival, and check any chained group against the whole-group rule, so the change can only add merges that were blocked by impossible candidates.

- **Date:** 2026-09-29 · **Task:** task-126 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/dedup.py` (`_merging`, `_not_the_listed_paper`), `backend/tests/unit/ingest/test_dedup.py`, `backend/tests/unit/ingest/test_dedup_props.py`

## What we set out to do
Explain NeurIPS 2023/2024 main and 2021 D&B over their official counts in the first full coverage trial, where `conflicts.csv` showed `title_key ambiguous_not_merged` rows for the extra records.

## What we learned
- Every blocked group outside NeurIPS 2021 D&B held a proceedings listing, its accepted main-track note, and an accepted workshop note of the same title. The track rule already refused workshop-into-listing, but the ambiguity check still counted the workshop note as a rival, so the real pair never merged.
- NeurIPS 2021 D&B's 11 round-2 papers had a rejected round-1 note with the same title. Proceedings list only accepted papers, so the rejected note can't be the listing.
- Setting those clusters aside gave 212 new merges and none removed, and moved NeurIPS 2021 D&B, 2023-2025 main and D&B and ICLR 2024/2025 onto their official counts. The M4 gate went from 36/44 to 43/44 (ICLR 2013 is the documented exception).
- Why a set-aside note can't merge through a second title key is subtle and differs by case: a track one is set aside again (or refused on forum ids), while a status one can join a chain, and the whole-chain re-check refuses it only because every non-listing record has its own forum id. The first write-up credited `_mergeable` for both; the review caught it, and a unit test now pins the status case.

## Dead ends — don't repeat these
- Setting aside every non-accepted cluster before trying the whole group: a lone rejected note must still merge with its listing (decision-005 lets the proceedings decide status), so status only breaks a tie.

## Decisions (and what would change them)
- `unknown` track or status stays a rival: it may be the listed paper. Revisit only if `conflicts.csv` shows many real pairs blocked by `unknown` rivals.

## Follow-ups
- [ ] task-054 — part 2: rebuild the real snapshot and index on `dev` with TASK-123 to TASK-126 and commit the dated coverage report

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/dedup-rules/SKILL.md`, `docs/specs/01-ingestion.md`
- Test or hook added? — the set-aside cases in `test_dedup.py` and the set-aside property in `test_dedup_props.py`
