# The OJS OAI-PMH server hides papers behind one 500 and duplicate set names, and only a real-data run showed what tests missed

**Key lesson:** Harvest ojs.aaai.org from the journal-wide ListIdentifiers inventory (per-set ListRecords for metadata, GetRecord for gaps), never from `set=` or one token chain alone, and give every new source a self-naming test (`urls.native()` reads back its id) and an attribution test (abstracts link to the paper, not the listing URL) before its first real run.

- **Date:** 2026-10-10 · **Task:** decision-049 (new venues, milestone A; follow-ups TASK-214..220) · **Area:** ingest, tooling
- **Artifacts:** `.superpowers/sdd/2026-10-09-new-venues-milestone-a/progress.md`, `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`, commits `70b97eeb`, `880606ea`, `673112f6`, `aa668b59`, `d0eea48a`, `fdcea53d`, `57c82ad0`, `ba294afe`

## What we set out to do
Index AAAI 2010–2026, AIES 2024–2025 and IASEAI 2026 from ojs.aaai.org over OAI-PMH (166,759 records in the first snapshot, +25,634; final: 166,757, +25,632, after AAAI 2023's two Errata became front matter).

## What we learned
- **One unrenderable article cuts the chain.** Article 39173 makes the ListRecords page holding it HTTP 500; resumption tokens chain pages, so everything after offset 23,400 was unreachable (ledger, Task 6).
- **Set names are not unique.** `EAAI-POS` and `EAAI-FP` occur twice, `EAAI-Full` and `EAAI-FULL` both exist, so `set=` reaches one section per name: 5 live 2014 papers (19039–19043) came from no set and 19 came twice (ledger, Task 6 round 2). The journal-wide ListIdentifiers chain (53 pages) passes 39173 cleanly. Built as `70b97eeb`/`880606ea`: inventory = truth, per-set ListRecords = bulk metadata, GetRecord for gaps, a cached 5xx replayed offline, an unreachable article named by an `[[unavailable]]` row or the crawl stops.
- **39173 is not a paper.** dblp's pinned release has exactly 4,920 `aaai.v40` DOIs, none 39173; Crossref 404; GetRecord and the page still 500 (`ba294afe`). Check a second source before filing a "missing paper" task.
- **The snapshot build refused `op:aaai:2013:ojs-8500`**: its article URL is an OJS public id (`/article/view/1678-1679`), so `urls.native()` could not name it (dedup.py: "a proceedings record must name itself"). Fix `673112f6`: `urls.proceedings` is always the numeric article URL (the site redirects it). Unit tests had passed.
- **The final review found `dedup.attribution` linking abstracts to the OAI ListRecords (token) URL** instead of the paper (`aa668b59`).
- **A "the gate catches it" ruling needs the gate's code read.** The count mismatch was ruled "reported; the coverage `--check` fails it", but `--check` does not look at listings; reverted to a `count_mismatch` crawl stop, as dblp does (`d0eea48a`).
- **A regex XML-prolog skip (`(?:<\?.*?\?>|<!--.*?-->)*`) backtracked exponentially** on untrusted server output; the background security scan and the task review both caught it; replaced by a linear `bytes.find` loop with timing-bounded tests (`fdcea53d`).
- **Task 1 ran only unit and contract tests**, so the differential suite's vocab-derived combination count (14 tracks against a 9-track synthetic corpus) broke unnoticed until Task 6 (`57c82ad0`). Pinning the corpus to its old tuples kept fixtures stable, but the test must read the corpus's own tuples, not `vocab.TRACKS`.
- **e2e `reuseExistingServer` attached to the owner's dev servers** on :3000/:8000 (main-branch code, real index): all 66 tests failed. With `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100`, 66 pass.
- **The C `ET.XMLParser` has no `.parser` attribute**, so expat handlers (DOCTYPE refusal) need `xml.parsers.expat` driving an `ET.TreeBuilder` (ledger, Task 4).

## Dead ends — don't repeat these
- `set=` as the harvest unit, or one journal-wide ListRecords chain: either silently loses or duplicates papers.
- A listing-count check left to a coverage gate that never reads listings.
- Running only unit and contract tests after a vocab change.
- A bare `make e2e` from a worktree while the owner's dev servers run.

## Decisions (and what would change them)
- Inventory-first harvest costs +53 requests per AAAI crawl → complete and reachable → reverse only if OJS gets unique set names and stable pages.
- AAAI 2023 `Errata` is front matter (counted, never records) → errata are not papers → the owner can revert from a snapshot diff.

## Follow-ups
- [x] TASK-214..220 are already filed (`70a0f782`: milestones B and C, IASEAI 2027, AIES 2026, owner review of six sections, official counts, quiet bench re-run). No task for 39173: it is a broken entry.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` (self-naming and attribution tests for a new source), `.claude/skills/pr-workflow/SKILL.md` (full `make test` for `vocab.py`), `.claude/skills/testing-standards/SKILL.md` (e2e ports from a worktree; timing-bounded tests for untrusted input)
- Test or hook added? — yes, in the branch: self-naming and attribution tests (`673112f6`, `aa668b59`), adversarial-timing prolog tests (`fdcea53d`); no new hook.
