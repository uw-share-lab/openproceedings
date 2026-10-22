---
id: decision-055
title: >-
  Bound every native id form: a key of at most 200 characters, a number of at
  most 12 digits; a record past a bound is refused, record schema 10 (TASK-281)
date: '2026-10-22 19:33'
status: accepted
---
## Context

A record id is `op:<venue>:<year>:<native>`. Its native part is validated per form (`record.PROCEEDINGS_NATIVE`, the
forum-id rule), but four forms had no length bound: `pmlr-v<N>-<key>`, `dblp-<key>`, `ojs-<id>` and
`doi-<toc>.<n>`. A hostile PMLR index entry with a 2,100-character key, or an OJS article id of thousands of digits,
gave a record whose id was as long. That id is stored in `records.jsonl`, written into every export and API response,
and is the URL `/paper/<id>`.

decision-053 caps every other stored string and deliberately leaves the id alone, since cutting an id would rename the
paper. Under it, a URL the record's own id was read from becomes an address of that id's page, rebuilt from the id, so
that URL was unbounded too: as long as the id plus a fixed host and path.

A second fault was found by the TASK-279 review (round 2): `sources/ojs.py`'s `int()` on an OAI-PMH header's article
id raised a bare `ValueError` past Python's 4,300-digit limit, aborting the harvest instead of refusing the entry. The
same `int()` met unbounded digits in `urls.pmlr` (a PMLR volume), `urls.ojs_article` and the RIS importer's volume
claims.

A bound makes a record past it invalid, so its crawler refuses it as it refuses any invalid entry. That is a refusal,
which decision-026 and decision-053 avoid for text. It is the right answer for an id: an id can't be trimmed (that
renames the paper) and no real one comes near the bounds. **The owner chose the bounds on 2026-10-22: a key of at most
200 characters, a number of at most 12 digits.**

**Measured** (`docs/results/2026-10-22-list-counts-and-native-ids.md`, run read-only over snapshot
2026-10-16-03eab0ef56c4: 173,518 records):

| Part | Longest | Bound | Ratio |
|---|---|---|---|
| a dblp key (`dblp-<key>`, ICML and AAAI) | 30 | 200 characters | 6.7× |
| a PMLR key (`pmlr-v<N>-<key>`) | 25 | 200 characters | 8× |
| a PMLR volume (`<N>`) | 3 digits | 12 digits | |
| an OJS article id (`ojs-<id>`) | 5 digits | 12 digits | |
| an ACM DOI's toc (`doi-<toc>.<n>`) | 7 digits | 12 digits | |
| an ACM DOI's paper number | 7 digits | 12 digits | |
| the whole id | 53 characters | at most 233 (a FAccT `pmlr-` id) | |

## Decision

Every native-id form is bounded, and a record past a bound is refused. The owner decided this on 2026-10-22.

- **The bounds** (`record.MAX_NATIVE_KEY` = 200, `record.MAX_NATIVE_DIGITS` = 12, in `record.PROCEEDINGS_NATIVE`):
  - a PMLR or dblp key: at most 200 characters;
  - a PMLR volume, an OJS article id, and each side of `doi-<toc>.<n>`: at most 12 digits
    (`acm_table.DOI_DIGITS` is the same bound, defined there because `record` imports that module).
  - The NeurIPS and ICLR hashes (32 hex digits) and OpenReview forum ids (4–64 characters) were bounded already.
- **A record past a bound is invalid**, so each crawler refuses the entry as it refuses any invalid one:
  - PMLR and dblp ICML skip it and count it (`skipped.invalid`);
  - the RIS importer skips it (`unresolved`; a PMLR volume past 12 digits names no volume, `no_id`);
  - dblp AAAI and Crossref stop (`invalid_record`; a Crossref DOI past the bound is `odd_doi`);
  - `sources/ojs.py` stops on an OAI-PMH article id or volume past 12 digits (`oai_unreadable`), a `CrawlError` raised
    before `int`, never a bare `ValueError`.
- **No parser reads an unbounded number.** `urls.pmlr`, `urls.ojs_article` and the RIS importer's volume read a number
  only within 12 digits after leading zeros, so no URL names a number no id can hold, and `int` never meets Python's
  digit limit. The model checks the form before it reads a PMLR volume as an int.
- **Record schema 10.** The native-id forms changed, so `RECORD_SCHEMA_VERSION` goes from 9 to 10 (record-schema skill
  §Versions).
- **decision-053's own-page rule is now always within the cap.** An address rebuilt from a bounded id is at most about
  250 characters (a PMLR page), well within 2,048. So a URL over the cap is never that page, and decision-053's
  branch "a URL that already is that page is kept whole and flagged once" is gone: such a URL is always rebuilt and
  flagged as cut. No stored URL is longer than its cap.

## Consequences

- **Code.** `ingest/record.py` (`MAX_NATIVE_KEY`, `MAX_NATIVE_DIGITS`, `PROCEEDINGS_NATIVE`, `RECORD_SCHEMA_VERSION`),
  `ingest/acm_table.py` (`DOI_DIGITS`, `paper_doi`), `ingest/urls.py` (`_NUMBER`), `ingest/ris.py` (`_int`,
  `_listing`), `ingest/sources/ojs.py` (`_number`), `ingest/sources/crossref.py` (the `odd_doi` message),
  `ingest/caps.py` (`_claim`, `_names`, `_own_page`, `_page_only`), `engine/index.py` (its id-length guard stays, for
  any id ingest misses). Tests at the bound and one past it per form (`test_record.py`), and per crawler
  (`test_pmlr.py`, `test_dblp.py`, `test_dblp_aaai.py`, `test_ris.py`, `ojs/test_ojs_parse.py`,
  `crossref/test_crossref_mine.py`, `test_urls.py`).
- **Reproducibility.** Every record of 2026-10-16-03eab0ef56c4 validates under record schema 10 (`records=173518
  valid=173518`). So `records.jsonl`, `snapshot_hash` and `index_version` are unchanged. The next snapshot built
  writes `record_schema_version` `10` in its manifest, so its files hash changes
  (`test_combined_snapshot.FILES_HASH` is re-pinned; `SNAPSHOT_HASH` is unchanged). `TOKENIZER_VERSION` and the index
  `SCHEMA_VERSION` are unchanged.
- **Exactness.** A refused entry is a paper missing from the index, which the crawl report counts or the crawl stops
  on. No real source comes near a bound.
- **Docs.** Spec 01 (§Record schema's `id` row, §Pipeline 2), the record-schema skill (§Native ids, §Versions, §The
  ingest caps), the dedup-rules and snapshots skills. decision-053 is extended: its "Not capped: `id`" now holds with
  the forms bounded, and its follow-up TASK-281 is this decision.
- **Revisit** if a real key passes 100 characters or a real number 10 digits.
