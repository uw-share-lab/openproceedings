---
id: decision-053
title: >-
  Cap every other stored string at ingest, trimmed and flagged; a cut DOI or URL
  is no link, and an id only if the cut left what it names unchanged (TASK-279)
date: '2026-10-22 05:31'
status: accepted
---
## Context

decision-026 (`ingest/caps.py`) caps only titles (1,000 characters) and abstracts (20,000). Every other stored string
field was uncapped. `ingest/record.py` checks a DOI's shape (`10.NNNN/suffix`, one line) and each URL's (http(s), a
host, one line), but not their length. Author names, keywords, `venue_id_raw`, an `invitation` claim's value and a
provenance claim's `url` and `evidence` had no cap at all. Snapshots store each of them, and the API shows them. Since
TASK-274 the BibTeX export escapes every field in linear time, so a long value no longer costs quadratic CPU. What
remains is size: a value of any length is stored, and written whole into every export format (BibTeX, RIS, CSV, JSONL)
and every API response. These fields come from crawled sources (Crossref, OpenAlex, OpenReview, proceedings pages, the
RIS cache), not from the reviewer (TASK-279, a follow-up from TASK-274).

The options put to the owner were:
- **Leave them uncapped.** Record why, and accept the size risk.
- **Cap + refuse.** An over-cap value drops the record or the claim. Exact, but one bad field loses a paper from
  every result set, which decision-026 rejected for the same reason.
- **Cap + trim.** decision-026's model: an over-cap value is trimmed and flagged, never refused.

**The owner chose "Cap + trim" on 2026-10-22.** The option read: "Same caps, but over-cap values are trimmed and
flagged instead of refused. Keeps every record whole, but a trimmed DOI or URL is wrong, so less safe for exactness."
The owner accepted that trade-off: a trimmed DOI or URL is no longer a valid identifier. So this record also decides
how a cut one is handled, so that it can't mislead.

**Measured** (`docs/results/2026-10-22-stored-string-lengths.md`) over snapshot 2026-10-16-03eab0ef56c4 (173,518 records, every claim included, losing claims too; counted
in NFKD, as decision-026 counts):

| Field | Longest | Where |
|---|---|---|
| DOI (`urls.doi`, record and claim) | 34 | an ICML 1990 dblp record |
| URL (`urls.forum`/`pdf`/`proceedings`, record and claim) | 154 | a NeurIPS 2024 PDF link |
| a claim's `url` | 154 | the same link |
| author name (record and claim) | 81 | |
| keyword (record and claim) | 733 | ICLR 2025 `d8hURACo0P`: abstract sentences its authors put in OpenReview's keywords field, split at commas |
| `venue_id_raw` (record and claim) | 65 | |
| an `invitation` claim's value | none held | |
| a claim's `evidence` | 469 | an AAAI 2005 dblp track claim citing its section and two archive URLs |
| `id` (not capped, below) | 53 | |

Lists: at most 95 authors and 54 keywords on one record.

**How a cut DOI or URL could mislead.** It could do so in two ways:
- **As a link.** In `urls`, it is a page link, an export field and the OpenAlex fill's DOI join key. A claim's own `url`
  is the provenance table's "source" link and the abstract's attribution link.
- **As an id.** Dedup and reconcile read ids from URL claims: proceedings ids (`dedup.proceedings_ids`), forum ids
  (`forum_ids`, the forum link) and Creative AI page parts. A prefix can be a valid id of another paper.
  `https://openreview.net/forum?pad=<2,000 characters>&id=Other12345…`, cut at 2,048, reads as forum id `Other1`.
  The forum link would then merge the record with that paper (`test_caps.py`). A venue id is read the same way: a cut
  `NeurIPS.cc/2024/Creative_AI_Track <600 characters>` is exactly the Creative AI id, and a workshop's
  `NeurIPS.cc/2024/Conference <600 characters>/Workshop/Foo` cut reads as the main conference's (the review of
  TASK-279).

Two readings were considered:
1. **A cut DOI or URL is never read as an id.** This looked safest, but dedup refuses the whole build when a
   proceedings record doesn't name itself in a `urls.proceedings`/`urls.pdf` claim. An RIS URL with a long tracking
   query (`?utm_source=…`) cut after its path still names its paper. Skipping it would turn one long URL into a refused
   build, the opposite of what the owner chose. The review found the same for a record whose id itself is over 2,000
   characters (a hostile PMLR key or OJS article id): its own page URL is cut inside the id.
2. **A cut DOI or URL is never a link, and is an id only if the cut left what it names unchanged; a URL the record's
   own id was read from becomes that id's page address instead.** This is the one adopted. The review reached it in
   four steps. Round 1 answered the long-id case with a note (`it named its own record`) that dedup read to keep the record
   naming itself. Round 2 showed that a source could forge that note in RIS evidence (which repeats a venue id) to make
   any record a listing, and that after a merge it named the wrong record, so the URL was kept whole instead. An
   automated security review then showed that keeping it whole had no bound (an `iclr_archive` target's id hashes the
   whole URL, so any length passed), which defeats the cap. Cutting just past the first place the URL spells the id
   came next, but round 3 showed it failed where a page's form goes on past the id (a NeurIPS or ICLR page's track
   token of any length after its hash; a PMLR GitHub asset), refusing the build, that leading zeros took it past the
   cap, and that it never checked the whole URL named the id. The rule adopted rebuilds the id's own page address
   from the parsed id: it reads no evidence, works for every form, and only the id bounds it.

## Decision

We cap every stored string field that decision-026 left uncapped at ingest. An over-cap value is trimmed and flagged,
never refused. The owner decided this on 2026-10-22.

Each cap is at least 2.7 times the longest value held, so no record of the current corpus is trimmed:

| Field | Cap (characters) | Why this length |
|---|---|---|
| DOI: `urls.doi`, record and claim | 1,000 | 29× the longest. The DOI Handbook sets no limit. A DOI link (`https://doi.org/` + DOI) stays under the URL cap |
| each URL: `urls.forum`, `urls.pdf`, `urls.proceedings`, record and claim | 2,048 | 13× the longest. The common practical URL limit (sitemaps protocol; browsers near 2,083) |
| a claim's `url` | 2,048 | as a URL |
| each author name, record and claim | 1,000 | 12× the longest |
| each keyword, record and claim | 2,000 | 2.7× the longest, which is an abstract split into keywords: a tighter cap would cut real (if misfiled) text |
| `venue_id_raw`, record and claim | 500 | 7.7× the longest. OpenReview venue ids are short paths; a cut one is no id (below) |
| an `invitation` claim's value | 500 | as a venue id (an OpenReview invitation id). None is held today |
| a claim's `evidence`, its trim notes included | 4,000 | 8.5× the longest. Evidence quotes URLs and section names |

- **Counted and cut as decision-026 cuts a title.** The NFKD length is counted. The cut falls before the last space
  that fits, else before the last base character, else where it fits. The result is then stripped of whitespace at
  both ends (`caps.cut`). This is in the same pass as decision-026's caps (`caps.cap_record`): in
  `snapshot.load_sources`, before dedup, and after the `aaai_library` and OpenAlex fills. Authors and keywords on the
  record, and every claim, are cut alike; the `urls` slots and `venue_id_raw` are re-resolved (below).
- **Flagged in the claim's evidence.** The note is `trimmed at ingest (decision-053): <what>` (`caps.CUT`). It names
  what changed: `value cut from <n> to <m> characters`, `<k> values cut to at most <cap> characters` (names,
  keywords), `url of <n> characters dropped`, `evidence cut from <n> characters`, and `not read as an id` (below). It
  goes last, after any decision-026 note, as the whole evidence or in parentheses, so an RIS route and url stay
  first. A cut evidence keeps its start and every note within 4,000. The manifest's `trimmed` names the record
  (`caps.is_trimmed` reads both notes), and the build's `snapshot_trimmed` warning counts it.
- **A cut DOI, URL or venue id never fills the record.** It is never a link, and a cut venue id is no id (a cut URL
  is an id only as the next bullet says). Its claim keeps the cut value as display text: the paper
  page's provenance shows it as plain text beside the `CUT` note (`value cut from <n> to <m> characters`). It need not
  be well formed. `dedup.resolve` takes no `urls` slot or `venue_id_raw` from a cut claim (`caps.cut_identifier`): the
  next-ranked claim that wasn't cut does, else null. `cap_record` sets the record's slots by the same rule
  (`dedup.resolved_value`), so a capped record still equals what its claims resolve to. So no page link, export or
  OpenAlex DOI join ever uses a cut value, and dedup never reads a cut venue id as Creative AI evidence. A claim's
  own `url` is only ever a link, so one over 2,048 is dropped (null), and the note gives its length.
- **A cut URL is an id only if the cut left what it names unchanged.** At the cut, `caps._names` compares what the
  whole URL and the cut one name: `urls.native`, `urls.forum_id`, `urls.proceedings_parts`, and an `iclr_archive`
  `urls.proceedings` target's id (it hashes the whole URL). If anything differs, the note adds `not read as an id`
  (`caps.unread_identifier`). Dedup's identity reads then skip the claim: `proceedings_ids`, `forum_ids` and the
  Creative AI evidence. A long query string after a proceedings page's path leaves what the URL names unchanged.
- **A page past its cap first drops its tail.** If a cut at the cap would change what a URL names, the URL without
  its query, parameters and fragment is kept when it fits and names all the whole did, track token included
  (`caps._page_only`): a long tail after a page never cuts into the page.
- **A URL the record's own id was read from becomes an address of that id's page.** If neither a cut at the cap nor
  dropping the tail keeps the URL naming what it did, but the whole names the record's own proceedings id (`urls.native`: the miner read the id from it), the value
  becomes an address of the id's page, rebuilt from the parsed id (`caps._own_page`; it names the id, though it need
  not be the address the site serves): a NeurIPS or ICLR page
  `…/paper_files/paper/<year>/hash/<hash>-Abstract.html` on its own host, a PMLR paper
  `proceedings.mlr.press/v<N>/<key>.html`, a dblp record page, an OJS article on its journal, a DOI link. It is kept
  only if it names the same id. Flagged `value cut from <n> to <m> characters, rebuilt as the page of the record id it
  names`, it counts as a cut, so it fills no slot, but it still names the record, so dedup's input check passes. A
  URL that already is that page is kept whole and flagged once (`value of <n> characters kept, …`); it stays a valid
  link. The page is the id's length plus a fixed host and path, so leading zeros and any text past the id are gone,
  and only an id near or over the cap (a hostile PMLR key, dblp key, OJS article id or ACM DOI number; the native forms have no length
  bound, TASK-281) takes it past the cap. It is decided from the value and the record's id, never from evidence, so no
  text a source writes can claim it.
- **An `iclr_archive` target is cut like any other.** Its id hashes the whole target, so no prefix names it: an
  over-cap target is cut at the cap and unread. Dedup's input check then accepts the record as standing for itself
  (`dedup._archive_target_cut`), as it did whole, but only when the unread claim is the `iclr_archive` crawler's own
  `urls.proceedings` claim and the id is an `iclr-` one: no import writes that claim, so none can claim the
  exception. Dedup also puts the record's own id back among its cluster's proceedings ids, so the two-ids guard still
  keeps it apart from another ICLR paper with the same title.
- **Reserved.** No miner or importer may end a claim's evidence with the `CUT` note. `cut_identifier` and
  `unread_identifier` read it, as `dedup.is_absence` reads `not listed:`. A forged `value cut` note only takes a value
  out of the record's slots or Creative AI evidence, and lists the record in the manifest's `trimmed` (`is_trimmed`
  reads the note on any claim, since an evidence cut can land on any field). A forged `not read as an id` note would also hide that URL's ids
  from dedup's identity reads (listing, the self-naming check, the never-merge guards), so it matters which claims can
  carry one: none can today. A URL holds no whitespace (`record._url`), so an RIS URL claim's evidence
  (`scholarmend:<route> <url>`) can't end in a note, which needs ` (` before it, and every crawler ends its URL
  claims' evidence with fixed text the note can't match. The forgery round 2 found was on a venue id, which is no URL and only ever leaves the slot.
- **Not capped:**
  - `id`. An id is identity: cutting it would rename the paper. Its native part is validated per form, but the
    `pmlr-`, `dblp-`, `ojs-` and `doi-` forms have no length bound; bounding them is a refusal and a record schema
    change, so it is TASK-281.
  - A `twin` claim's ids. Each must be a record of the snapshot (`snapshot.render`).
  - The enums and `year`.
  - The number of authors or keywords on a record. This decision caps each string, not the list.

## Consequences

- **Code.** `ingest/caps.py` (`FIELD_CAPS`, `MAX_DOI`, `MAX_URL`, `MAX_AUTHOR`, `MAX_KEYWORD`, `MAX_VENUE_ID`,
  `MAX_INVITATION`, `MAX_EVIDENCE`, `IDENTIFIERS`, `cut`, `cut_identifier`, `unread_identifier`, `_names`,
  `_page_only`, `_own_page`),
  `ingest/dedup.py` (`resolve`, `resolved_value`, `proceedings_ids`, `forum_ids`, `_names_creative_ai`,
  `_archive_target_cut`, `_cluster`), `eval/scholar_compare.py` (no cut DOI as a join key). Tests are in
  `backend/tests/unit/ingest/test_caps.py`: each field at cap−1, cap and cap+1, the identifier rules (a forum id cut
  short, a query string cut, a URL rebuilt as its own record's page (junk past the id, an id spelled twice, a NeurIPS or ICLR track
  token, a PMLR GitHub asset, leading zeros, each form: dblp ICML and AAAI, OJS AIES and IASEAI, doi.org, dx.doi.org
  and percent-encoded DOIs, an upper-case host), a page whose tail of symbols is dropped so its Creative AI token
  stays, an `iclr_archive` target cut and still standing for its record (only by
  the crawler's own claim, and still kept apart from another paper), a page rebuilt only for the record's own id, a
  forged venue-id note, an OJS id past Python's int digit
  limit, a cut venue id and a cut page as Creative AI evidence, a slot taken from the next claim), a cut that keeps
  evidence and notes within the cap, two Hypothesis properties (a cut never passes its cap and text within it is
  unchanged; a capped record is within every cap and capping it again changes nothing), and a snapshot build that cuts
  a long author name, names its record and logs the count.
- **Reproducibility.** Running `cap_record` over every record of 2026-10-16-03eab0ef56c4 returned each one unchanged
  (`changed=0`; the 26 records decision-026 already trimmed stay as they were). A value within every cap is returned
  as it is, and `cap_record` returns the record itself. So `records.jsonl`, the manifest's `trimmed`, `snapshot_hash`
  and `index_version` are unchanged, and no new snapshot or index is needed.
  - `RECORD_SCHEMA_VERSION` is not bumped: the stored shape is unchanged, and the caps belong to the build, not the
    model, as decision-026's do.
  - `TOKENIZER_VERSION` and the index `SCHEMA_VERSION` are not bumped: nothing tokenized or indexed changes.
  - A future crawl that brings a value over a cap changes that record's claims, and so its snapshot line and the
    snapshot hash, as any content change does. `op snapshot diff` shows it.
- **Exactness.** A trimmed DOI or URL is wrong, as the owner accepted. It is never presented as a working link, and
  never used as an id that names a paper it didn't name whole.
  - **No refusal, and no unbounded value.** A record whose own page URL a cut at the cap would unname gets an address
    of its id's page, and an `iclr_archive` record stands for itself with its target cut, so dedup's input check passes.
    No URL is longer than its cap but by the id it names: the one stored string still unbounded is the id itself
    (TASK-281).
  - **A hidden id.** An unread cut URL hides what the whole URL named from the never-merge guards too (two distinct
    forum ids, two proceedings ids). That only happens when a URL passes 2,048 characters with an id that isn't the
    record's own (a record's own id stays seen: its page, or an `iclr_archive` record's id). No real URL does
    (the longest is 154); the other rules (venue, year, track, titles) still apply.
  - **Losing the slot.** A record whose only DOI is cut loses its DOI link, and with it the OpenAlex fill's DOI
    route.
- **Docs.** Spec 01 (§Record schema, §Pipeline 2, §5's `trimmed`), the record-schema skill (§The ingest caps), the
  dedup-rules skill (the forum link), the snapshots skill, the logging-standards skill and `CLAUDE.md` (`caps.py`)
  describe it. decision-026 is extended, not superseded: its title and abstract caps and its note are unchanged, and
  its "Out of scope: authors and keywords" no longer holds for their length.
- **Revisit** in either case:
  - A real source comes within 2× of a cap. The keyword cap is the closest, at 2.7× an abstract misfiled as keywords.
  - A source writes evidence that ends with a `CUT` note.
- **Follow-ups.** TASK-280: cap the number of authors and keywords on a record. TASK-281: bound the length of a
  record id's native part.
