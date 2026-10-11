---
id: decision-004
title: Test fixtures are synthetic; real-corpus checks run locally (task-006)
date: '2026-09-26 15:43'
status: accepted
---
## Context

Spec 00 open question 1 (whether abstracts may be redistributed) is unresolved until M6, and the repo is
public, so nothing whose licence is unknown may be committed. The differential suite (task-028) needs a
~5,000-record corpus, and tests may never call real APIs (CLAUDE.md, 2026-09-25), which rules out fetching
fixtures at test time. The review lead chose synthetic fixtures (2026-09-26).

## Decision

1. **The 5k differential fixture is synthetic**, generated deterministically by a committed script (as
   `tests/fixtures/corpus/make_reference_200.py` does for the golden 200): realistic vocabulary, phrases,
   plurals and near-misses, LaTeX, Unicode (marks, CJK, NFKC forms), missing abstracts, and every
   venue × year × track × status combination so filters and exclusion accounting are exercised.
2. **Recorded HTTP fixtures for crawlers keep the real response structure but not the real text.** A
   recording is taken by a person with `op ingest` (never by a test), then scrubbed: titles, abstracts,
   authors and other free text are replaced with synthetic text of the same shape; ids, venueids,
   invitations, dates, pagination and headers stay real, since they are what the adapters parse.
3. **Real-corpus checks run locally, never in CI**: tokenizer parity over the full corpus (task-029) and
   anything else that needs real text read the maintainer's own snapshot under `data/` (gitignored).

## Consequences

- CI is fully reproducible and redistributable; no licence question blocks M2–M5.
- Synthetic text can miss real-world oddities, so the local parity run (task-029) and the Scholar
  comparison (task-056) are where those surface; each oddity found becomes a golden row in synthetic form.
- Bibliographic metadata of a whole proceedings stays real where the adapters don't parse it and every
  committed recording already keeps it: a PMLR volume index's editors in `<title>`, the `og:`/meta tags and
  the JSON-LD `description` (v28–v267 and FAccT 2018's v81, noted 2026-10-10 in milestone B's review); the
  scrub replaces the `<p><strong>Editors: …` line only.
- Revisit when question 1 is answered (M6): a CC BY subset could then join as a second fixture.
