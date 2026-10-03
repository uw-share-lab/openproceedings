---
id: decision-021
title: >-
  Additions to an export format are additive under api v1, and a pinned export
  whose snapshot cannot be verified withholds its abstracts (TASK-138)
date: '2026-09-30 04:35'
status: accepted
---
## Context

TASK-138 makes every export name each abstract's source (decision-018: every abstract shown or handed out is
attributed; PMLR's CC BY 4.0 asks for a citation and a link to the paper's PMLR page, and an export hands the
text out). Doing that means adding to the export formats: an RIS `N1` line, a BibTeX field, CSV columns and a
JSONL key. The api-contract rules listed "changing an export's field mapping or byte format" as breaking,
without saying whether an addition counts. For JSON responses the question is settled: a new response field is
additive (spec 04 §Conventions; decision-009 for enum values a client must expect to grow; decision-014 for the
one nullable exception), because an old client ignores what it doesn't read. There is precedent for exports
too: the M3a gate (commit `6ca7451`) appended the `record_id` and `searched_at` CSV columns and the matching
JSONL keys, and added the `record <id> · searched <date>` tail to the provenance line, within `/api/v1`.

The attribution comes from the exported index's snapshot records (`RecordFile.attributions`). A pinned export
(`index_version=`, or a search record's own index) opens an index other than the served one; its snapshot may
be missing or fail verification while the index itself is still servable (search records pin indexes, and
`op index retire` protects those, but nothing protected their snapshots). The first implementation refused such
an export (409). The owner decided otherwise on 2026-09-30.

## Decision

1. **Additions to an export format are additive under `/api/v1`.** These may be added without `/api/v2` or a
   new decision:
   - an RIS line of a tag that already repeats (such as one more `N1`), placed so every documented position
     still holds (the provenance line stays the last `N1`; the status sentence stays the first for a paper that
     is not accepted);
   - a new BibTeX field;
   - a new CSV column appended after the last one;
   - a new JSONL key.

   **Breaking**, as before: changing an existing field's value or content (BibTeX `note` included), a column's
   position, a line's documented placement, or removing anything.
2. **A pinned export whose index exists but whose snapshot can't be verified withholds its abstracts.** It is
   not refused. The same records and metadata are exported with every abstract left out: no RIS `AB`, no BibTeX
   `abstract`, CSV `abstract` empty, JSONL `abstract` null, and no abstract-source line, field or value. The
   response says so in a header, `X-Abstract-Source: unavailable` (`attributed` otherwise), and the file itself
   says so in every record, since a file outlives its response: an RIS `N1` and a BibTeX `abstract_withheld`
   field reading "Abstract withheld: its source could not be attributed on this instance (the index's snapshot
   is unavailable), so no abstract is exported (decision-018).", a CSV `abstract_withheld` column (`true` /
   `false`, appended last) and a JSONL `abstract_withheld` key (a boolean). `op export` does the same, with a
   warning on stderr, and exits 0. The withheld marker is a new field rather than a sentence in BibTeX `note`,
   because changing `note` is breaking under rule 1 and styles typeset `note` into a bibliography.

   Why: the ids, titles, authors and venue are what a search record cites and what screening imports; refusing
   the whole export for want of the attribution would make a cited set unexportable. Sending the abstracts
   without attribution would break decision-018. Withholding keeps both: the cited set is still handed over,
   and no abstract leaves without its source. A search record's replay needs only the index, so it stays
   `reproduced` in that state.

## Consequences

- **What rule 1 does not protect.** A reader that assumes a fixed shape breaks on an addition:
  - CSV readers with a fixed column list (pandas `read_csv(names=…)`, readr with fixed `col_types`, a
    spreadsheet macro that counts columns);
  - JSONL readers validating against a strict schema (`additionalProperties: false`);
  - RIS readers that take the first (or the only) `N1` as the provenance line. The documented contract is the
    **last** `N1` (spec 04 §Exports).

  Spec 04 §Exports and the api-contract skill say so, and readers are told to read CSV by header name, JSONL
  by key and the provenance from the last `N1`.
- **The TASK-138 mapping** (spec 04 §Exports): RIS `N1  - Abstract source: <site> <url>` before the provenance
  line; BibTeX `abstract_source = {<site> <url>}`; CSV `abstract_source`, `abstract_origin`, `abstract_url`,
  `abstract_withheld` appended after `searched_at`; JSONL `abstract_source` (`{source, origin, url}` or null)
  and `abstract_withheld`. An attributed rejected paper's RIS record now has three `N1` lines; Covidence
  imported the two-`N1` record cleanly (`docs/results/2026-09-27-covidence-check.md`), the three-line case is
  untested there (low risk: Covidence shows no `N1` to screeners). The Covidence fixture's records carry no
  claims, so its bytes are unchanged and the hand import stands.
- **Attribution for an old index comes from today's code.** A pinned index's attributions are computed from its
  snapshot's claims by the current `ingest/dedup.py::attribution()`, not by the code that built that index. A
  change to `attribution()` changes what an old index's export says about its sources (never its ids or text).
- **Keep a pinned index's snapshot.** There is no `op snapshot` prune or delete command (`op snapshot` has only
  `build` and `diff`), and `data/snapshots/` is write-protected, so nothing in the tooling removes one. Spec 08
  and the `snapshots` skill now say that the snapshot an index was built from must be kept while any search
  record pins that index (`op index retire`'s condition); a snapshot removed by hand makes those records'
  exports withhold their abstracts. A future prune command must refuse while a record pins an index built from
  the snapshot.
- **Reverses the first TASK-138 behaviour** (409 `API_INDEX_VERSION_UNAVAILABLE` for a pinned export without
  its snapshot), which never shipped.
- What would reopen it: a consumer that depends on a fixed export shape and can't be moved to reading by name;
  or storing the attribution in the index itself, which would remove the snapshot dependency (and change every
  `index_version`).
