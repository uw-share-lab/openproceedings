---
id: decision-018
title: >-
  The public instance serves every abstract, with attribution, a source link and
  a takedown contact; copyright-office sign-off before launch (TASK-063)
date: '2026-09-30 00:49'
status: accepted
---
## Context

Spec 00 open question 1 (M6): can a public instance serve abstracts? The search is over titles and abstracts
(guarantee 2), and the result list, the paper page and every export (RIS, CSV, BibTeX, JSONL) carry the full
abstract, so the question is whether the public deployment may show and hand out that text. The code is MIT
either way, and the corpus is never committed to git. This record states the sources' terms as read on
2026-09-29 and the project owner's decision. It is not legal advice.

Where the served abstracts come from (spec 01 §Sources; abstract precedence is OpenReview first, decision-005):

| Source | Venue-years it supplies abstracts for | Terms (checked 2026-09-29) |
|---|---|---|
| OpenReview | ICLR 2013 and 2017+; NeurIPS 2021+; ICML 2023+ | [Terms of use](https://openreview.net/legal/terms), current version "Last updated: September 24, 2024". "Metadata" includes "an Article's title, Authors, Submitter, abstract…", and "To the extent that the Submitter or OpenReview has a copyright interest in metadata associated with a Work, a Creative Commons Public Domain Dedication (CC0 1.0) will apply." The CC0 clause is in the 22 Sep 2023 version of the terms and absent from the 24 May 2022 version, so ICLR, NeurIPS and ICML **2024+** abstracts are explicitly dedicated; earlier OpenReview years are not clearly covered. Each note has a per-paper `license` field, but the crawl's public projection drops it (`_public_projection` in `backend/src/openproceedings/ingest/sources/openreview_client.py`), so records don't carry it. |
| NeurIPS proceedings (`proceedings.neurips.cc`) | NeurIPS 2013–2020 (the only source before 2021); later years only for papers OpenReview lacks | [Copyright FAQ](https://neurips.cc/FAQ/Copyright): authors keep copyright and grant NeurIPS a non-exclusive licence. No licence to third parties. |
| PMLR (`proceedings.mlr.press`) | ICML 2013–2022; 2023+ only for papers OpenReview lacks | v70 onward (ICML 2017+): [CC BY 4.0](https://proceedings.mlr.press/pmlr-license-agreement.html); attribution must include a citation and a hyperlink to the PMLR site. ICML 2013–2016 (v28, v32, v37, v48): no CC licence ("Authors retain copyright"). |
| ICLR archive (`iclr.cc/archive`) | none | No licence, but the archive supplies no abstract: its ICLR 2014–2016 records have `abstract=null` (spec 01 §Sources), so there is nothing to serve. |
| arXiv | not used | Metadata, abstracts included, is [CC0](https://info.arxiv.org/help/license/index.html). A possible future source for the unlicensed years; not crawled. |

So three groups of served abstracts have no licence to redistribute: NeurIPS 2013–2020 (and any later paper
filled from the proceedings), ICML 2013–2016, and OpenReview years before the CC0 clause (ICLR 2013 and
2017–2023, NeurIPS 2021–2023, ICML 2023) unless a paper's own `license` says otherwise.

What comparable services do (checked 2026-09-29): dblp shows no abstracts, for copyright reasons; OpenAlex
ships abstracts only as an inverted index, "for legal reasons"; Semantic Scholar shows them on its site;
Google Scholar requires the source sites it indexes to show abstracts.

Options considered:
- (a) **Serve no abstracts publicly** (dblp's choice). Titles alone would be searchable on the public
  instance, which breaks guarantee 2 for its users and makes the exports useless for screening; the full
  search would exist only on private or local deployments.
- (b) **Serve only licensed abstracts**: PMLR v70+ (CC BY 4.0), OpenReview under the CC0 clause (2024+) or
  a per-paper licence; `abstract` withheld elsewhere. Needs a per-record licence the records don't carry
  today, and leaves NeurIPS before 2021 and the early OpenReview years title-only.
- (c) **An inverted index or snippets only** (OpenAlex's choice). The search needs the exact text for
  highlights and exports, and a systematic review screens on the abstract.
- (d) **Serve every abstract, with attribution and a source link per record and a takedown contact**, and
  rely on Canadian fair dealing for the unlicensed years. Chosen.

## Decision

The project owner decided on 2026-09-29 that the public instance shows every abstract in the index. Each
record is attributed to its source and links to it, and every deployment names a takedown contact. For
years with no licence we rely on fair dealing under the Canadian Copyright Act, s. 29 (research, private
study, education), assessed with the six factors of *CCH Canadian Ltd. v. Law Society of Upper Canada*,
2004 SCC 13 (purpose, character, amount, alternatives, nature of the work, effect of the dealing). Sign-off
from the University of Waterloo copyright office is a prerequisite for the public launch (TASK-069).

## Consequences

- **Per record: attribution and a source link.** Wherever an abstract is shown or exported, the record
  names where it came from and links to that page (the OpenReview forum, the NeurIPS proceedings page or
  the PMLR page). PMLR's CC BY 4.0 terms require a citation and a hyperlink to the PMLR site, so a PMLR
  abstract appears with its citation (authors, title, venue and year) and its `proceedings` link.
  What exists already: the paper page (`frontend/src/components/paper/paper-view.tsx`) lists authors and
  the Links section, and its provenance table names the `abstract` claim's source with a "source" link.
  The result list (`frontend/src/components/search/hit-item.tsx`) shows the abstract with the outbound
  links but no authors and no statement of which source the abstract came from. Records carry no licence
  field. Closing these is launch work (TASK-069 or a task it spawns), not part of this record.
- **A takedown contact on every deployment.** Every page names a contact for rights holders, and a request
  is handled by withholding that record's abstract from the next `index_version` (the record stays, matched
  on title, as a missing abstract already is; spec 01 §Error handling). No takedown contact exists in the code
  or docs yet; TASK-065 (deploy) or TASK-069 (launch) adds it.
- **Copyright-office sign-off before launch.** TASK-069 does not make the instance public until the
  University of Waterloo copyright office has signed off on this basis. Private, local and development
  deployments are unaffected: the corpus stays out of git and each operator builds their own.
- **If sign-off is refused**, the public instance falls back to option (b): it shows only licensed
  abstracts (PMLR v70+ under CC BY 4.0, OpenReview abstracts under the CC0 clause or a per-paper licence)
  and withholds the rest, which stay searchable only on private deployments. That needs a licence per
  record: keeping OpenReview's per-paper `license` in the public projection and in the record schema (a
  spec 01 change and a new `index_version`), or a venue × year licence table. Search results on the public
  instance would then differ from a private one over the same snapshot, so the withheld set must be part
  of what `index_version` identifies and shown in coverage (guarantee 6). A supersede record replaces this
  one if that happens.
- **Fixtures and git are unchanged.** Decision-004 (synthetic test fixtures, real-corpus checks run
  locally) said to revisit when this question was answered. This record covers serving abstracts on a
  deployment under fair dealing and the sources' licences, not committing them: the corpus stays out of
  git, and fixtures stay synthetic. A CC BY PMLR subset as a second fixture (decision-004's suggestion)
  remains possible and would need its own record.
- **Reproducibility.** Nothing changes: this decision alters no matching, filter, record or
  `index_version` input, and existing search records replay unchanged. A takedown removes an abstract only
  from a later `index_version`; records cited against earlier versions replay against those.
- **What would reopen it.** The copyright office's answer; a takedown request that disputes fair dealing;
  a change to any source's terms; or adopting arXiv's CC0 metadata as an alternative abstract source for
  the unlicensed years.
- **Docs.** Spec 00 §Open questions Q1 is closed with a link here; spec 08 §Deploy and the README state what
  a public instance serves and its prerequisites.
