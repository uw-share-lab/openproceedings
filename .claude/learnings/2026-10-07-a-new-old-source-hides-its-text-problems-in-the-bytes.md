# A new pre-2013 source hides its text problems in the bytes, so scan the real cache before trusting its text

**Key lesson:** Before an old source's text goes into records, scan the real crawl cache for what tests can't show (placeholder abstracts, PDF-extractor codes such as `(cid:173)`, and pages decoded with the wrong charset), and record each page's charset in its table with a runtime guard: cp1252-decoded text that re-encodes to valid UTF-8 means the row is wrong.

- **Date:** 2026-10-07 · **Task:** TASK-203, TASK-204, TASK-205, TASK-206 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/{common,dblp,dblp_xml,icml_sites}.py`, `ingest/dblp_icml.toml`, `ingest/icml_sites.toml`, `docs/research/2026-10-06-pre-2013-neurips-icml-sources.md`, `docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`, decision-047

## What we set out to do
Index NeurIPS from 1987 and ICML from 1988 (decision-047): lower the NeurIPS miner's floor, read ICML 1988–2012
from a pinned dblp release, and attach abstracts from the official ICML pages that survive.

## What we learned
- **The code change for NeurIPS was one line; the text was not.** The 1987–2012 year pages have the 2013 shape, so
  only `FIRST_YEAR` moved. But a focused reviewer scanning the shared cache found 50 abstract pages (1987–2003)
  whose abstract is the placeholder `Abstract Unavailable`, which would have become a searchable abstract, and
  1,650 pre-2004 pages with `(cid:N)` extractor codes (`princi(cid:173) ples`), which split words so `principles`
  never matched. Neither shows in a scrubbed fixture (evidence: the review notes; `common.PLACEHOLDERS`,
  `common.repair_pdf_codes`).
- **Old servers send bare `text/html`, and one year can mix encodings.** Every ICML page was served with no charset;
  most are cp1252, but five 2007 Internet Archive captures (148, 225, 245, 260, 326) are UTF-8. Decoding them as
  cp1252 gave `Shannonâ€™s`; a reviewer found three, and the runtime guard (`icml_sites._utf8_in_cp1252`) found the
  other two in the cache at once. The cache stores decoded text, so fixing the row also means deleting or
  refreshing those entries.
- **dblp.xml frames records on shared lines.** `</incollection><inproceedings key=…>` sits on one line, so a reader
  that assumes a record starts a line misses records. Streaming the gz line by line, finding start tags anywhere
  in a line, and handing each `conf/icml/` record to expat with the pinned DTD for its entities reads 17,115 records
  of a 1.1 GB file in about 75 s, and refuses anything the framing can't account for.
- **dblp.org is off limits; DROPS is the sanctioned route.** robots.txt disallows everything and pages sit behind a
  bot challenge, but the monthly release on drops.dagstuhl.de has a DOI and an md5 for each file. Pinning the DOI,
  size and sha256 makes the records reproducible; the release's latest file was dated 2026-10-03, not the 1st.
- **Exact title keys attach about half the ICML abstracts, and the misses are genuine.** 1,290 of 2,675 dblp records
  got an abstract. Of the 46 unmatched page entries, 42 have a near dblp title that is the same paper retitled
  (`Online Learning of Pseudo-Metrics` / `Online and batch learning of pseudo-metrics`) or one dblp spells differently
  (`Graphbased`), and 4 have none (checked by listing the nearest dblp title), so a fuzzy rule would have had to
  guess which near title is the paper.

## Dead ends — don't repeat these
- Trusting a survey's single "this page is cp1252" note for a year: recognise it by any `â€` or `Ã` in a cached
  page. Check every page, not one sample.
- `grep -c` on these pages printed nothing (ugrep in this shell); count with Python instead.

## Decisions (and what would change them)
- `(cid:173)` is joined and other codes become a space at ingest, as decision-044 does for control characters →
  the tokenizer would otherwise split real words → revisit if a source's codes ever mean something else.
- Short extractor fragments are kept and counted (`abstract_short`), never dropped → dropping text is a guess → a
  decision with the owner could drop them.
- 1997 and 1998 submission abstracts (with contact details) are not used → an owner question (no task id was
  reserved for this branch).

## Follow-ups
- None filed: the 1997/1998 submission abstracts are an owner question, raised with the PR (no task id was
  reserved for this branch).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/neurips-proceedings/SKILL.md` (placeholders, PDF codes),
  `.claude/skills/record-schema/SKILL.md` (sources, native id), `.claude/skills/snapshots/SKILL.md` (dblp cache),
  CLAUDE.md layout.
- Test or hook added? — `backend/tests/unit/ingest/test_neurips.py` (placeholder, PDF codes, short abstracts),
  `test_icml_sites.py` (wrong-charset guard, official hosts), `test_dblp_xml.py` (shared-line framing).
