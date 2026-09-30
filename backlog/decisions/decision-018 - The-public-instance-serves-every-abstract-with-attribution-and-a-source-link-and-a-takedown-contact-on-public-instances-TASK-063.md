---
id: decision-018
title: >-
  The public instance serves every abstract, with attribution and a source link,
  and a takedown contact on public instances (TASK-063)
date: '2026-09-30 01:06'
status: accepted
---
## Context

Spec 00 open question 1 (M6): can a public instance serve abstracts? The search is over titles and abstracts
(guarantee 2), and the result list, the paper page and every export (RIS, CSV, BibTeX, JSONL) carry the full
abstract, so the question is whether a public deployment may show and hand out that text. The code is MIT
either way, and the corpus is never committed to git. This record states the sources' terms as read on
2026-09-29 and the project owner's decisions. It is not legal advice.

Where the served abstracts come from (spec 01 §Sources; abstract precedence is OpenReview first, decision-005):

| Source | Venue-years it supplies abstracts for | Terms (checked 2026-09-29) |
|---|---|---|
| OpenReview | ICLR 2013, 2014 and 2016–2023 (API v1) and 2024+ (v2); NeurIPS 2021+; ICML 2023+. ICLR 2014 is on OpenReview without decisions: in the 2026-09-29 snapshot its 88 notes give 34 of the 35 accepted main records their abstract (through the archive's linked forum ids) and 54 records of status `unknown`. ICLR 2016 has only its workshop track there (125 notes, status `unknown`). ICLR 2015 is not on OpenReview ([`docs/results/2026-09-29-coverage.md`](../../docs/results/2026-09-29-coverage.md)). | [Terms of use](https://openreview.net/legal/terms), current version "Last updated: September 24, 2024". "Metadata" includes "an Article's title, Authors, Submitter, abstract…", and "To the extent that the Submitter or OpenReview has a copyright interest in metadata associated with a Work, a Creative Commons Public Domain Dedication (CC0 1.0) will apply." The CC0 clause is in the 22 Sep 2023 version of the terms and absent from the 24 May 2022 version, so for ICLR, NeurIPS and ICML **2024+** OpenReview's terms dedicate the abstracts under CC0; earlier OpenReview years are not clearly covered. Each note has a per-paper `license` field, but the crawl's public projection drops it (`_public_projection` in `backend/src/openproceedings/ingest/sources/openreview_client.py`), so records don't carry it. |
| NeurIPS proceedings (`proceedings.neurips.cc`) | NeurIPS 2013–2020 (the only source before 2021); later years only for papers OpenReview lacks | [Copyright FAQ](https://neurips.cc/FAQ/Copyright): authors keep copyright and grant NeurIPS a non-exclusive licence. The FAQ grants no licence to third parties. |
| PMLR (`proceedings.mlr.press`) | ICML 2013–2022; 2023+ only for papers OpenReview lacks | PMLR's [publication agreement](https://proceedings.mlr.press/pmlr-license-agreement.html) grants the public a CC BY 4.0 licence and requires any attribution to include "a citation to the original publication of the article in the proceedings as well as a hyperlink to the PMLR web site linking to the original paper"; the page states no start volume. The [ICML 2017 publication agreement](https://media.nips.cc/Conferences/ICML2017/permission_to_publish_icml2017.pdf) (v70) has the same CC BY 4.0 grant and attribution clause, so v70 is the first ICML volume known to be CC BY. ICML 2018–2022 (v80–v162) are taken to be under the same agreement; their per-year forms were not each checked. ICML 2013–2016 (v28, v32, v37, v48): no CC BY grant found. What was checked: the [ICML 2016 permission to publish form](https://icml.cc/2016/wp-content/uploads/permission_to_publish_icml2016.pdf) (v48) grants IMLS, ICML and JMLR the right to publish and nothing to the public, and the authors "reserve all other proprietary rights … including copyright"; the 2013–2015 forms were not found or checked. |
| ICLR archive (`iclr.cc/archive`) | none | No licence, but the archive supplies no abstract (spec 01 §Sources). Its ICLR 2015 and 2016 conference records, and one accepted ICLR 2014 record, have `abstract=null`, so there is nothing to serve. |
| arXiv | not used | Metadata, abstracts included, is [CC0](https://info.arxiv.org/help/license/index.html). A possible future source for the unlicensed years; not crawled. |

So three groups of served abstracts have no licence to redistribute that we found: NeurIPS 2013–2020 (and any
later paper filled from the proceedings), ICML 2013–2016 (no CC BY grant found; the 2016 form checked), and
OpenReview years before the CC0 clause (ICLR 2013, 2014 and 2016–2023, NeurIPS 2021–2023, ICML 2023) unless a
paper's own `license` says otherwise.

**The basis for the unlicensed years**, to put to the University of Waterloo copyright office (TASK-135):
fair dealing under the Canadian Copyright Act, s. 29 (research, private study, education), assessed with
the six factors of *CCH Canadian Ltd. v. Law Society of Upper Canada*, 2004 SCC 13: the purpose of the
dealing, its character, its amount, alternatives to it, the nature of the work, and its effect on the
work. The purpose is systematic-review research; each abstract is shown with attribution and a link to its
source, which the service sends readers to.

What comparable services do (checked 2026-09-29): dblp shows no abstracts, for copyright reasons; OpenAlex
ships abstracts only as an inverted index, "for legal reasons"; Semantic Scholar shows them on its site;
Google Scholar requires the source sites it indexes to show abstracts.

Options considered:
- (a) **Serve no abstracts publicly** (dblp's choice). Titles alone would be searchable on the public
  instance, which breaks guarantee 2 for its users and makes the exports useless for screening.
- (b) **Serve only licensed abstracts**: PMLR v70+ (CC BY 4.0), OpenReview under the CC0 clause (2024+) or
  a per-paper licence. Needs a per-record licence the records don't carry today, and leaves NeurIPS before
  2021 and the early OpenReview years title-only.
- (c) **An inverted index or snippets only** (OpenAlex's choice). The search needs the exact text for
  highlights and exports, and a systematic review screens on the abstract.
- (d) **Serve every abstract, with attribution and a source link per record, and a takedown contact on a
  public instance.** Chosen.

The project owner was asked what to do if the copyright office objected, and answered (2026-09-29): "lets
just show the abstracts". There is no fallback to (b).

## Decision

The project owner decided on 2026-09-29 that the public instance shows every abstract in the index, each
record attributed to its source with a link to it, and that a public instance names a takedown contact.
The unlicensed years rest on fair dealing alone. Consulting the University of Waterloo copyright office
before the public launch is recommended (TASK-135), not a gate (following from the owner's answer that the
abstracts stay shown).

## Consequences

- **Per record: attribution and a source link.** Wherever an abstract is shown, the record names where it
  came from and links to that page (the OpenReview forum, the NeurIPS proceedings page or the PMLR page).
  PMLR's CC BY 4.0 terms require a citation and a hyperlink to the PMLR site, so a PMLR abstract appears
  with its citation (authors, title, venue and year) and its `proceedings` link. What exists already: the
  paper page (`frontend/src/components/paper/paper-view.tsx`) lists authors and the Links section, and its
  provenance table names the `abstract` claim's source with a "source" link. The result list
  (`frontend/src/components/search/hit-item.tsx`) shows the abstract with the outbound links but no
  authors and no statement of which source the abstract came from: TASK-134, a launch prerequisite.
- **A takedown contact on public instances** (the procedure below is superseded in part by decision-022,
  TASK-136, which built it). Every page of a public instance names a contact for rights
  holders (TASK-133). Private, local and development deployments may omit it. None exists in the code or
  docs yet. TASK-133's proposed procedure, not yet decided, is to withhold that record's abstract from the
  next `index_version` (the record stays, matched on title, as a missing abstract already is; spec 01
  §Error handling). A known gap in that procedure: older `index_version`s still serve the abstract while
  search records pin them, because `op index retire` refuses to retire a pinned version (spec 08 §CLI);
  TASK-133 must settle how a takedown reaches them. (Settled by decision-022, TASK-136: every loaded index version withholds a listed abstract at serve time, and pinned versions keep matching on it.)
- **Copyright office: recommended, not a gate.** TASK-135 puts the Context above to the copyright office;
  TASK-069 records its outcome, if any, before launch and does not wait on it. Whatever the answer, the
  owner's decision is to show the abstracts; only a new decision superseding this one changes that.
- **Launch path.** TASK-069 (public launch) depends on TASK-133 (takedown contact), TASK-134
  (attribution in the result list), TASK-136 (takedown tooling) and TASK-138 (exports name the abstract's
  source), all in m-6.
- **Fixtures and git are unchanged.** Decision-004 (synthetic test fixtures, real-corpus checks run
  locally) said to revisit when this question was answered. This record covers serving abstracts on a
  deployment, not committing them: the corpus stays out of git, and fixtures stay synthetic. A CC BY PMLR
  subset as a second fixture (decision-004's suggestion) remains possible and would need its own record.
- **Reproducibility.** No existing version changes: this decision alters no matching, filter, record or
  `index_version` input, and existing search records replay unchanged.
- **What would reopen it.** A takedown request that disputes fair dealing; the copyright office's answer,
  if the owner then decides differently; a change to any source's terms; or adopting arXiv's CC0 metadata
  as an alternative abstract source for the unlicensed years.
- **Docs.** Spec 00 §Open questions Q1 is closed with a link here; spec 08 §Deploy and the README state what
  a public instance serves and its prerequisites.
