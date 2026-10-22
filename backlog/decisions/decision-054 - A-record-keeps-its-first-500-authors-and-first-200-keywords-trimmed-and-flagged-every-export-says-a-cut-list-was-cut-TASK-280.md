---
id: decision-054
title: >-
  A record keeps its first 500 authors and first 200 keywords, trimmed and
  flagged; every export says a cut list was cut (TASK-280)
date: '2026-10-22 19:33'
status: accepted
---
## Context

decision-053 caps the length of each author name (1,000 characters) and each keyword (2,000) at ingest, but not how
many a record holds. A source could still send any number of names or keywords. Each is stored in the snapshot and
written into every export and API response (TASK-280, a follow-up from TASK-279).

The options were the ones decision-053 weighed for a string: leave the lists uncapped, cap and refuse the record, or
cap and trim (decision-026's model). Refusing loses a paper from every result set over one field, which decision-026
and decision-053 both rejected. **The owner chose "cap + trim" on 2026-10-22, at 500 authors and 200 keywords.**

A trimmed author list is a citation that names fewer authors than the paper has, so this record also decides how an
export says so.

**Measured** (`docs/results/2026-10-22-list-counts-and-native-ids.md`, run read-only over snapshot
2026-10-16-03eab0ef56c4: 173,518 records, every claim included, losing claims too):

| List | Most on a record | Most on a claim | Cap | Ratio |
|---|---|---|---|---|
| authors | 95 | 95 | 500 | 5.3× |
| keywords | 54 | 54 | 200 | 3.7× |

## Decision

A record keeps its first 500 authors (`caps.MAX_AUTHORS`) and its first 200 keywords (`caps.MAX_KEYWORDS`;
`caps.LIST_CAPS`). An over-cap list is trimmed and flagged, never refused. The owner decided this on 2026-10-22.

- **Where.** In decision-026's and decision-053's one pass (`caps.cap_record`, `caps._claim`), on the record and every
  claim alike, so a capped record still equals what its claims resolve to.
- **The list first, then its items.** The count is cut before decision-053 cuts each name or keyword, so a long name
  past the kept ones is dropped with them, never counted as cut.
- **Flagged** in the claim's evidence: `trimmed at ingest (decision-054): kept the first <n> of <m> values`
  (`caps.COUNT`). It goes before any decision-053 note, as the whole evidence or in parentheses, because the `CUT`
  note stays last (`cut_identifier` and the evidence cut read it there). `caps.is_trimmed` reads it, so the
  manifest's `trimmed` names the record and the build's `snapshot_trimmed` warning counts it.
- **Every export says so.** `caps.listed_total` reads how many values the source listed off the note.
  `snapshot.RecordFile.lists_cut` keeps it per record (id → `authors`/`keywords` → that count), read off a claim
  whose value is the record's own list. The exporters (`op export`, `GET /export`, `POST /compare`'s RIS) write:

  | Format | A cut author list | A cut keyword list |
  |---|---|---|
  | BibTeX | `and others` after the last kept author (BibTeX's own "et al.") | (keywords aren't exported) |
  | RIS | one `N1  - Author list cut: the first 500 of the <m> authors its source lists are given (decision-054).`, after the status sentence. Not an `AU` line: RIS has no "et al." tag, and Covidence would import one as an author | (keywords aren't exported) |
  | CSV | last column `lists_cut`: `authors <m>`, `authors <m>; keywords <k>`, or empty | likewise |
  | JSONL | `lists_cut` (`{"authors": <m>}`), only on a record with a cut list | likewise |

  When the snapshot can't be verified, no list is named cut (as for twins, TASK-162).
- **Only the note's own form counts.** `listed_total` answers only for a list exactly at the cap whose note says it
  kept exactly the cap of more. Evidence that merely reads like the note says nothing of a shorter list.
- **Reserved.** No miner or importer may end a list claim's evidence with the `COUNT` note. A forged one could only
  add `and others` to a record whose list is exactly at the cap, and list it in `trimmed`. None can today: every
  source's authors and keywords evidence ends in fixed text, or (an OpenReview v1 author list it split) in the raw value
  as JSON, closed by a quote or bracket the note can't end with.

## Consequences

- **Code.** `ingest/caps.py` (`MAX_AUTHORS`, `MAX_KEYWORDS`, `LIST_CAPS`, `COUNT`, `listed_total`, `_claim`,
  `cap_record`, `is_trimmed`), `ingest/snapshot.py` (`RecordFile.lists_cut`), `export.py` (`ListsCut`,
  `authors_cut`, the four writers, CSV's `lists_cut` column), `api/export.py`, `api/compare.py`, `cli.py`. Tests:
  `backend/tests/unit/ingest/test_caps.py` (each list at count−1, count and count+1; a cut list with a cut name, both
  notes in order; `listed_total` refusing look-alike notes; an RIS import of 501 authors) and
  `backend/tests/contract/test_lists_cut.py` (the snapshot reader and every export format, `GET /export` and
  `op export`; a record with no cut list exports byte for byte as without the map).
- **Reproducibility.** `cap_record` returned every record of 2026-10-16-03eab0ef56c4 unchanged (`changed=0`; the 26
  flagged are decision-026's). So `records.jsonl`, `snapshot_hash` and `index_version` are unchanged.
  `RECORD_SCHEMA_VERSION` is not bumped for this decision: the stored shape is unchanged, and the caps belong to the
  build, as decision-026's and decision-053's do (decision-055 bumps it, for the id forms). `TOKENIZER_VERSION` and the
  index `SCHEMA_VERSION` are unchanged: authors and keywords aren't tokenized.
- **Exports.** CSV gains one last column, `lists_cut`, so every earlier column keeps its position. A record with no cut
  list is byte for byte what it was in RIS, BibTeX and JSONL. No API response model changes (`openapi.json` is
  unchanged).
- **Exactness.** A cut author list is a citation with fewer names than the paper has. The export says so in every
  format, and the record keeps the first names in the source's order, so the first author (the BibTeX key's) is
  unchanged.
- **Docs.** Spec 01 (§Record schema, §Pipeline 2, §5's `trimmed`), spec 04 (§Exports), the record-schema,
  bibtex-format, ris-format, api-contract, snapshots and logging-standards skills, and `CLAUDE.md` (`caps.py`).
  decision-053 is extended, not superseded: its "Not capped: the number of authors or keywords" no longer holds.
- **Revisit** if a real source comes within 2× of a cap (a record of 250 authors or 100 keywords).
