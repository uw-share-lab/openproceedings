# uv 0.13 moves `uv.lock`'s revision from 3 to 5 on any rewrite, so every Dependabot uv PR stopped on it

**Key lesson:** Before reading a lock-header PROBLEM as a newer uv on Dependabot's side, rebuild the PR's lock from dev's with the repo's pinned uv (`uvx uv==<pin> lock -P <pkg>==<ver> …`) and diff it with the PR's: identical means the header move is the pin's own.

- **Date:** 2026-10-29 · **Task:** n/a · **Area:** tooling
- **Artifacts:** `.claude/scripts/dependabot/uv_lock.py` (`REVISION_MOVES`), `.claude/scripts/tests/dependabot_cases.py` (the eight revision rows), `.claude/scripts/mutants/dependabot.json`, PRs #201 and #206

## What we set out to do
Clear #206 (the uv group), which `uv_lock.py` stopped with "PROBLEM uv.lock: `revision` changed" (3 → 5), as the 2026-10-27 cloud run had stopped #201, which #206 replaced.

## What we learned
- **The move is the pin's own.** Starting from dev's `uv.lock` (revision 3), `uv lock -P` for #206's five versions
  under uv 0.13.4 (dev's pin when #206 opened) or 0.13.5 (dev's pin since #218) writes revision 5 and a lock
  byte-identical to #206's.
- **`uv lock --check` hides it.** Under 0.13.4, 0.13.5 and 0.13.6, `--check` accepts dev's revision-3 lock as current;
  only a rewrite moves the header. Nothing on dev rewrote the lock after the 0.13 bump on 2026-10-16, so the first
  Dependabot uv PR under 0.13 was the first to show it.
- **A PROBLEM line can be a stale rule, not a bad PR.** The header check had no way to say "this move is expected",
  so every uv PR from then on would have stopped on it.

## Dead ends — don't repeat these
- Reading the PROBLEM line as "Dependabot runs a newer uv" and waiting for the 0.13.5 bump to settle it: that bump
  has landed (#218), and the lock still writes revision 5 under it, so it settled nothing.

## Decisions (and what would change them)
- Allow exactly `(3, 5)`, as ints (the owner, 2026-10-29: "Teach the checker"). A downgrade, another move, a float, and a
  removed or added `revision` stay PROBLEMs. A uv that writes revision 6 adds a pair here, in its own reviewed PR.

## Follow-ups
- None. #206 is re-checked with dev's new checker once this merges.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/commands/dependabot-review.md` step 2's `uv` row and spec 08 §CI
  "Dependabot" say which move passes.
- Test or hook added? — `dependabot_cases.py` (accepted 3 → 5; refused 5 → 3, 3 → 4, 5 → 6, removed, added, 3.0 → 5, and 3 → 5
  with another header change) and four mutants in `mutants/dependabot.json`.
