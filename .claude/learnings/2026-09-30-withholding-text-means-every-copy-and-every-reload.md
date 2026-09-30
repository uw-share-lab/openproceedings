# Withholding an abstract meant finding every copy of its text, and a reload that skipped an unchanged index would have skipped the takedown list

**Key lesson:** To withhold a text, list every place it is stored before writing code (the record's field, each provenance claim's `value`, `conflicts.csv`'s `value_a`/`value_b`), and make any live list the API applies a reload input of its own, because `IndexState._load` returned early (`index_unchanged`) whenever `current` hadn't moved.

- **Date:** 2026-09-30 · **Task:** task-136 · **Area:** ops
- **Artifacts:** `backend/src/openproceedings/ingest/snapshot.py` (`withhold`), `backend/src/openproceedings/api/state.py` (`_load`), `backend/src/openproceedings/takedown_check.py`, `backend/tests/unit/ingest/test_snapshot_takedowns.py`, `backend/tests/contract/test_takedowns.py`, decision-022

## What we set out to do
Build TASK-133's takedown procedure: a list that `op snapshot build` and every index version the API loads apply,
a marker distinct from "missing", and a check that nothing listed is served.

## What we learned
- A record's abstract lives in three places: `abstract`, the `value` of each `abstract` provenance claim, and,
  when two sources disagreed, both columns of its `conflicts.csv` row (evidence: a second RIS source with another
  abstract text produced `op:iclr:2024:Rej_ected-1,abstract,A synthetic abstract…,ris,A recrawled abstract…,ris,tie:ris`).
  Nulling `abstract` alone would have left the text in `/papers/{id}`'s provenance and in the snapshot directory.
- The fast path in `IndexState._load` (`if path.name == previous.index_version: return True`) meant a SIGHUP after
  editing the list would have done nothing until the next index promotion. The list is now read first on every
  load, and an unchanged index with a changed list rebuilds the bundle (`takedowns_reloaded`).
- Two builds whose records are identical but whose `conflicts.csv` differ get the same directory name, and the
  second is refused as "not this snapshot" (pre-existing: `_holds` compares the audit files). A takedown makes
  this likelier, since withholding can erase the only difference between two sources' records.
- A filter-only query (`venue:ICLR year:2024 track:(…all…) status:(…all…)`) parses and selects every record of a
  venue-year on any index version, so `op takedown check` can find a listed paper in an old version's export
  without knowing its title there (the id carries venue and year).
- A withheld record's `content_hash` must be recomputed (`PaperRecord.model_copy`), or `/papers/{id}` would send
  a record whose hash its own fields contradict.

## Dead ends — don't repeat these
- Computing `/papers` highlights on the display record with the abstract already nulled: the highlighter
  evaluates the match itself, so `matched` would turn false for a paper `/search` still counts. Highlight on the
  index's text, then drop the abstract spans.

## Decisions (and what would change them)
- Oracle leak accepted, log on the host (owner, 2026-09-30) → decision-022; reopened by a request that the text
  must not be matched at all.

## Follow-ups
- [ ] (reported to the main session, not created here) a CI job that builds `deploy/web.Dockerfile`, and the
  compose file around it (TASK-065).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/snapshots/SKILL.md` (what `withhold` removes),
  `.claude/skills/logging-standards/SKILL.md` (`takedowns_reloaded`), `.claude/agents/release-manager.md`
  (the takedown steps), spec 08 §Deploy.
- Test or hook added? — `test_a_recrawl_and_rebuild_cannot_restore_a_listed_abstract` (conflicts.csv holds
  neither text), `test_the_list_is_reread_on_reload_and_a_bad_list_changes_nothing`, and `op takedown check`'s
  mutant tests; `protect-data-dir.sh` refuses `git add` through `takedowns/`.
