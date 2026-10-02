---
id: decision-026
title: >-
  Cap combining-mark runs at 8 per base character and abstracts at 20,000
  characters at ingest; trimmed text is flagged in its claim's evidence and the
  manifest (TASK-155)
date: '2026-10-02 01:11'
status: accepted
---
## Context

TASK-067 made the tokenizer's own scan of a run of combining marks linear, but CPython's NFKC canonical
reordering, which the tokenizer runs (spec 03), is still superlinear when the marks' combining classes alternate:
`a` + `̸́` × n tokenizes in about 2 s at 80k characters and 15 s at 200k (measured 2026-10-01). A `q`
is capped at 2,000 code points, but a stored title or abstract had no cap. A hostile abstract would cost the
index build and every search that highlights it (TASK-155, from the TASK-067 security review).

The options were:
- cap a run of marks;
- cap an abstract's length;
- both.

For each, text over the cap could be truncated, refused (the record dropped), or only reported. Refusing a
record loses a paper from every result set over a defect in one field. Reporting alone leaves the cost in place.
Trimming changes the stored text, so it must be visible. The real corpus leaves room for both caps (snapshot
2026-09-29-d552baa07aed, 95,877 records holding 218,727 abstract texts across records and claims):
- The longest abstract is 4,995 characters, and the longest abstract claim is 5,729. The p99.9 is about 2,440.
- The longest run of marks in any title or abstract, record or claim, is 1.

## Decision

The owner decided both caps on 2026-10-01:
- **Marks.** We cap every run of combining marks in a title or abstract at 8 marks per base character and
  drop the extras.
- **Length.** We cap every abstract at 20,000 characters (code points) and truncate it.

Both trims are flagged, never silent:
- **In the record.** Each claim whose value was trimmed carries a note in its `evidence`:
  `trimmed at ingest (decision-026): <n> combining marks dropped past 8 per base character; cut from <n> to
  <kept> characters`. It is the whole evidence when the source gave none. Otherwise it follows the source's
  evidence in parentheses. The paper page shows it in the provenance table.
- **In the snapshot manifest.** A `trimmed` key lists the ids of the records with any trimmed title or abstract
  claim. That includes a claim precedence overruled.
- **In the build log.** The build log counts them. `snapshot_built` and `snapshot_exists` carry `trimmed`, and a
  WARNING `snapshot_trimmed` is logged once per build when the count is non-zero.

Details:
- **What a mark is.** A character whose compatibility decomposition (NFKD) starts with a non-zero canonical
  combining class. That is every combining character (922 in Unicode 15.0), plus five that decompose to one
  (U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F).
- **What a run is.** The marks after one base character, or at the start of the text. A base character is a
  letter or digit that is not a mark. Any other character neither counts nor ends a run:
  - **Invisible characters** (zero-width joiner, variation selector, grapheme joiner, soft hyphen, enclosing
    mark, LaTeX `\-`). The tokenizer drops these and joins the word across them, so marks on both sides reach
    NFC as one run. The review measured a title of 8-mark runs split by zero-width joiners at 1.3 s for 72k
    characters, growing about 4x per doubling, when each separator still started a new run.
  - **Spaces and punctuation.** Marks after them are capped with the run before. Real text never needs this,
    since its longest run is 1.

  With this rule, no word the tokenizer forms holds more than 2 × 8 + 2 consecutive non-starters after NFD
  (tested), so its NFC is linear.
- **Cut ends.** A cut abstract is stripped of trailing whitespace and `…`, since a record refuses either. The
  note gives the length kept.
- **Titles.** They get the mark cap only, which makes their cost linear. A title length cap would only add a
  backstop. The owner did not decide one, and the TASK-155 security review proposed 1,000 code points. It is
  left to the owner (TASK-155 notes, deferrals).

## Consequences

- **Where it runs.** `ingest/caps.py` runs once, in `snapshot.load_sources`, before dedup. Every source's claims
  are trimmed alike, so they compare as they did. The record's own field and its claims hold the same trimmed
  text, so `content_hash` and the abstract's attribution (decision-018) stay consistent.
- **Cost.** The largest abstract the caps allow is 20,000 characters of a Thai base with 8 alternating marks
  (classes 220 and 230), all one word. Tokenizing it stays within 20x plain text of the same length and under
  0.5 s (`test_caps.py`). The measured time is about 0.03 s, against 0.014 s for plain text.
- **Reproducibility.** Text within both caps is returned unchanged, and the `trimmed` key is written only when
  some record is trimmed. A corpus with nothing over the caps therefore snapshots byte-identically:
  `records.jsonl`, `snapshot_hash` and `index_version` are unchanged. The 2026-09-29 cache rebuilt to the same
  records (TASK-155 notes). A future crawl that brings text over a cap changes that record's `content_hash` and
  the snapshot's hash, as any content change does. `op snapshot diff` shows it.
- **Exactness.** The tokenizer drops marks on Latin, Greek, Cyrillic, Hebrew and Arabic letters (spec 02
  §Token semantics), so those match as before. For marks the fold keeps (Thai tones, kana voicing, Indic signs),
  a query word with more than 8 marks on one letter can't match the trimmed text. Only a deliberately hostile
  word reaches that, since real text has at most 1.
- **Older snapshots.** An index build tokenizes `records.jsonl` without re-checking the caps. Snapshots built
  before this decision are trusted because the 2026-09-29 corpus was measured: its longest run is 1 and its
  longest abstract 4,995 characters. A snapshot from an unaudited cache should be rebuilt under the caps
  before it is indexed.
- **Where else.** Recorded in spec 01 §Pipeline 2 and §Record schema, the record-schema skill, the snapshots
  skill (the manifest's `trimmed`) and the logging-standards skill (the log fields). The caps are applied by the
  snapshot build. `PaperRecord` itself does not refuse text over them.
- **Revisit** if a real source carries an abstract near 20,000 characters, or a script that needs more than 8
  marks on one base.
- **Out of scope.** Authors and keywords are neither tokenized nor highlighted, so they are not capped.
  `conflicts.csv` rows a crawl found inside one source (`with_crawl_conflicts`) keep that source's raw texts,
  since they are not indexed.

