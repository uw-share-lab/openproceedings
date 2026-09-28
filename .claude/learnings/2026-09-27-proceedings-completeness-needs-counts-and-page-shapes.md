# Proceedings completeness needs both a verified count and the source's original page shapes

**Key lesson:** For archival proceedings, pin a verified total independently of representative fixtures and preserve each original wrapper, companion-page link and odd entity through scrubbing: a parser returning records proves only that one branch matched, not that the crawl is complete.

- **Date:** 2026-09-27 · **Task:** TASK-096, TASK-104, TASK-106 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/iclr.py`,
  `backend/src/openproceedings/ingest/sources/neurips.py`, `backend/tests/fixtures/http/scrub.py`,
  `backend/tests/fixtures/http/{iclr,neurips,pmlr}/`, `backend/tests/unit/ingest/test_{iclr,neurips,pmlr}.py`,
  `docs/research/2026-09-27-openreview-and-proceedings-facts.md`, `docs/specs/01-ingestion.md`

## What we set out to do
Fill ICLR's 2014–2016 acceptance gaps, follow NeurIPS 2025's recorded main-conference companion volume,
and replace derived parser cases with real scrubbed proceedings pages.

## What we learned
- **Counts and fixtures answer different questions.** The live ICLR archive has 35, 31 and 80 unique
  accepted conference targets for 2014, 2015 and 2016. The privacy-safe fixtures intentionally retain
  only 2, 4 and 4 parsed entries, so `test_a_nonempty_trimmed_archive_page_reports_the_verified_count_mismatch`
  pins `(stated, listed, count_ok) == (35, 2, False)`: two plausible records are still demonstrably
  incomplete.
- **A source name does not imply one DOM.** The 2014 Google Sites archive expresses entries as adjacent
  paragraphs, while the 2015/2016 DokuWiki archives use list items and section headings; 2015 also repeats
  targets across oral/poster sections and includes workshop entries that must be excluded. Keeping both
  shapes made those adapter branches testable instead of letting one successful selector masquerade as
  support for all three years.
- **Completeness includes page topology.** NeurIPS 2025 divides its proceedings between the base year page
  and a linked `vol38-main-conference` page. The fixture-backed test requires the explicit base/companion
  pair and all four resulting track classes; mining the non-empty base page alone would silently omit main,
  datasets-and-benchmarks and position papers.
- **Scrubbing must retain parser-driving anomalies.** The recorded NeurIPS author containing
  `&amp;quot;…&amp;quot;` is rewritten to a synthetic alias without normalising away the double escape.
  `test_the_recorded_2025_page_decodes_its_double_escaped_author` therefore exercises the real second-
  unescape path while containing no person's name. The recorded PMLR v28 page likewise replaces text but
  retains its older paper-page structure.

## Dead ends — don't repeat these
- Do not accept “the parser returned at least one record” as a coverage check. Compare unique parsed
  identities with an independently verified total and surface a mismatch in the crawl report.
- Do not make a scrubber emit one convenient canonical HTML form. If wrappers, sections, links or escape
  depth select an adapter branch, preserve that structure and synthesize only the sensitive text inside it.

## Decisions (and what would change them)
- Keep a separate completeness oracle (`stated`, `listed`, `count_ok`) even when a recorded fixture is
  deliberately trimmed. Remove it only if the upstream source supplies a stronger machine-verifiable
  inventory with equivalent identity and scope guarantees.
- Follow only recorded, explicitly recognised companion pages. A new “See also” target remains a warning
  until its structure and scope are captured; discovering a link alone does not broaden the crawl.

## Follow-ups
- None — TASK-096, TASK-104 and TASK-106 completed the identified work; no follow-up task was created.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/neurips-proceedings/SKILL.md`,
  `.claude/skills/pmlr-proceedings/SKILL.md`, `docs/specs/01-ingestion.md`,
  `docs/research/2026-09-27-openreview-and-proceedings-facts.md`
- Test or hook added? — `backend/tests/unit/ingest/test_iclr.py`, `test_neurips.py`, `test_pmlr.py`, plus
  structural preservation in `backend/tests/fixtures/http/scrub.py`
