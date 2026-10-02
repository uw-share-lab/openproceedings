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
2026-09-29-d552baa07aed, 218,727 records):
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
  20,000 characters`. The note is appended after any evidence the source gave. The paper page shows it in the
  provenance table.
- **In the snapshot manifest.** A `trimmed` key lists the ids of those records.

Details:
- **What a mark is.** A character whose compatibility decomposition (NFKD) starts with a non-zero canonical
  combining class. That is every combining character, plus five that decompose to one (U+0F73, U+0F75, U+0F81,
  U+FF9E, U+FF9F). A run is the marks after one base character, or at the start of the text.
- **Cut ends.** A cut abstract is stripped of trailing whitespace and `…`, since a record refuses either.
- **Titles.** They get the mark cap only. They are short, so the mark cap alone bounds their cost.

## Consequences

- **Where it runs.** `ingest/caps.py` runs once, in `snapshot.load_sources`, before dedup. Every source's claims
  are trimmed alike, so they compare as they did. The record's own field and its claims hold the same trimmed
  text, so `content_hash` and the abstract's attribution (decision-018) stay consistent.
- **Cost.** Tokenizing the largest abstract the caps allow (8 alternating marks on every base, 20,000
  characters) costs about what plain text of that length does (`test_caps.py`).
- **Reproducibility.** Text within both caps is returned unchanged, and the `trimmed` key is written only when
  some record is trimmed. A corpus with nothing over the caps therefore snapshots byte-identically:
  `records.jsonl`, `snapshot_hash` and `index_version` are unchanged. The 2026-09-29 cache rebuilt to the same
  records (TASK-155 notes). A future crawl that brings text over a cap changes that record's `content_hash` and
  the snapshot's hash, as any content change does. `op snapshot diff` shows it.
- **Exactness.** A query word with more than 8 marks on one letter can't match the trimmed text. A query can
  only reach that with a deliberately hostile word, since real text has at most 1.
- **Where else.** Recorded in spec 01 §Pipeline 2 and §Record schema, the record-schema skill and the
  snapshots skill (the manifest's `trimmed`).
- **Revisit** if a real source carries an abstract near 20,000 characters, or a script that needs more than 8
  marks on one base.
- **Out of scope.** Authors and keywords are neither tokenized nor highlighted, so they are not capped.
  `conflicts.csv` rows a crawl found inside one source (`with_crawl_conflicts`) keep that source's raw texts,
  since they are not indexed.

