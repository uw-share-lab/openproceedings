---
id: TASK-236
title: >-
  Record the exact URLs and read dates of the OpenAlex licence pages and
  aaai.org/robots.txt
status: In Progress
assignee: []
created_date: '2026-10-11 05:08'
updated_date: '2026-10-16 16:26'
labels:
  - docs
  - new-venues
dependencies: []
priority: low
ordinal: 165000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The research note cites OpenAlex's Pricing page without its exact URL and aaai.org's robots.txt (Crawl-delay: 43200) without the date it was read; the review had no network to fix either (hci-researcher, gate C round 1). On the next session with network, open each page, record its full URL and the date read in the research note's §OpenAlex licence and §Sources checked, quote only the shortest exact phrase, and cite OpenAlex's own terms or data-licence page if it has one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The research note gives the full URL and read date of OpenAlex's Pricing page, its work-object page, its terms or data-licence page if one exists, and https://www.aaai.org/robots.txt
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: recorded in the research note (§ojs.aaai.org, §OpenAlex Licence, §Licence posture, §Sources checked): https://help.openalex.org/access/pricing/ ('a CC0 public-domain license'), https://help.openalex.org/data/works/attributes/ (the old work-object URL redirects there; 'for legal reasons'), https://openalex.org/terms and its canonical PDF https://openalex.org/OpenAlex_termsofservice.pdf (revised 2026-10-02; 'freely revocable, limited license', republication without 'prior written consent' prohibited: contradicts the Pricing page's CC0), no separate data-licence page (llms.txt index), and https://www.aaai.org/robots.txt -> https://aaai.org/robots.txt (Crawl-delay: 43200), all read 2026-10-16. The ToS/CC0 conflict is reported to the lead for an owner decision; nothing changes the fill.

2026-10-16 (owner via lead): the ToS/CC0 conflict is folded into TASK-135 (now a launch gate); OpenAlex stays the decision-049 fallback until it is answered. README and spec 01 point to TASK-135; README says the copyright consultation is a launch gate since 2026-10-16.
<!-- SECTION:NOTES:END -->
