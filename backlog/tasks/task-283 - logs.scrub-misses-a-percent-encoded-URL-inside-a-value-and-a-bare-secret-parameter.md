---
id: TASK-283
title: >-
  logs.scrub misses a percent-encoded URL inside a value, a bare secret
  parameter, and a JSON-shaped secret
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-23 15:06'
updated_date: '2026-10-23 19:05'
labels:
  - logging
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-275's round-2 and round-3 security reviews (2026-10-23), pre-existing: scrub matches a secret parameter only after ?, &, # or ;, on the text as written. So ?next=https%3A%2F%2Fh%2F%3Ftoken%3Dabc (a redirect target, percent-encoded), a bare access_token=abc with nothing before it, a JSON-shaped secret such as an OAuth error body {"access_token": "abc"} quoted in exception text, and Bearer%20abc are logged in clear. None is on a current path: OpenReview's bearer token travels in a header, and httpx error text carries only the request URL. Options: decode percent-escapes in a value before matching (bounded, linear), start a parameter at any non-name character, and/or redact a JSON string value whose key holds a secret word; each must stay linear and only add redaction.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scrub redacts a secret parameter inside a percent-encoded URL value, or the limit is documented in logging-standards with the owner's decision
- [x] #2 scrub redacts a bare secret=value at the start of the text or after a non-name character, with an over-redaction check on ordinary prose, or the limit is documented
- [x] #3 linear on hostile input (CPU-growth test), and every string scrub redacted before is still redacted (old-vs-new comparison)
- [x] #4 scrub redacts a JSON-shaped secret ("access_token": "abc") in text, with an over-redaction check, or the limit is documented
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
At the owner's request (2026-10-23), in TASK-275's branch: a parameter name starts after any non-name character; percent-encoded userinfo and parameters get their own patterns; a quoted key with a secret word loses its quoted value; every pattern names its secret as group v so scrub is one loop; superset test against the pre-TASK-275 query pattern, examples, growth cases.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-23: done in TASK-275's branch at the owner's request. logs._SCRUBS: userinfo, encoded userinfo (%3A%2F%2F…%40), parameters starting after any non-name character (a bare token=; prose monkey=1 loses its value, documented), encoded parameters (%3F|%26|%23|%3B name %3D value, value stopping at %26/%23), quoted key + quoted value (JSON and a dict's repr; unquoted values and JSON escaped inside a string are left), bearer. The old equality test became a superset test: every character the pre-TASK-275 query pattern redacted falls in a v span of the new one, over every string up to 6 characters of '?&=sig #'. Growth: 13 new shapes, linear at 20k vs 80k on an idle machine.

2026-10-23: the automated commit review's three gaps fixed: a quoted value takes its own quote and an optional b prefix ({"token": 'abc'}, {'token': b'abc'}); an encoded scheme may start right after another escape (%22https%3A…); an encoded value runs to %26, %23, a raw &, #, whitespace or a quote (ab!c*d(e)/f:g was cut at !). All linear at 20k vs 80k.

2026-10-23 review round 5: three reviewers found passes hiding secrets from later ones (a parameter value eating a quoted value's closing quote, or Bearer; encoded userinfo swallowing &password=…%40). scrub now redacts the union of every pattern's v spans over the text as given (logs.secret_spans), and a whole-scrub superset test against origin/dev's two sequential passes replaces the one-pattern one. Also: an encoded parameter starts wherever a plain one would (after a non-name character or a non-name escape: ?state=token%3Dx); a quoted parameter value is taken whole (token='a b'); _WORDS gains cookie, credential, bearer; bearer may be followed by %20 or + (Bearer%20abc, named in the description, was still in clear); encoded userinfo excludes raw &#?;="'. Double encoding (%253D) is documented as not decoded.

2026-10-23: the automated review of ab3c9b29: encoded userinfo's value is broad again ([^%/\s@] or a non-/ non-@ escape): a password may hold raw ' (encodeURIComponent leaves it), and with the union of spans a run into a later &password= loses nothing.

2026-10-23 review round 6: correction to the round-5 note: the whole-scrub superset test was added beside the one-pattern test, not in place of it. Round 6: a parameter value takes a URL's userinfo inside it whole (origin/dev's userinfo pass removed # and & from it first, so ?token=a://x#y@SECRET leaked @SECRET under the union; qa-auditor), with a targeted superset generator; bearer right after an escape (?h=Authorization%3A%20Bearer%20abc; security-reviewer) and after %09; an encoded name after a % that starts no escape; growth rows for %2D/%2E/_ starts, x:// runs, unclosed quoted values; examples for quoted values with the other quote, escaped quotes and backslash-newline. A value quoted with JSON-escaped quotes ends at its first whitespace (documented).
<!-- SECTION:NOTES:END -->
