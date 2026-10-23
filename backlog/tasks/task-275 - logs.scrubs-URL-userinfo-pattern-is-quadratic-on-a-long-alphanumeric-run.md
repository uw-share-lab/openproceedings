---
id: TASK-275
title: logs.scrub's URL-userinfo pattern is quadratic on a long alphanumeric run
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-20 15:18'
updated_date: '2026-10-23 15:06'
labels:
  - logging
  - security
dependencies: []
ordinal: 182000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-272's security sweep (2026-10-20), pre-existing: logs.py _URL_USERINFO.sub in scrub() takes 317 ms on a 20k alphanumeric run and 11.1 s on 100k; every log message and exception passes through it, so long crawled text reaching a log line pays it. Reviewer's candidate (identical sub output on 6.7M short strings, ~2 ms at 100k): (?<![a-zA-Z0-9+.-])(?P<pre>[0-9+.-]*+)(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*+://)[^/\s@]+@ replaced with \g<pre>\g<scheme>…@ (a plain lookbehind would stop redacting '1a://user@').
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scrub's userinfo redaction is linear with identical output (exhaustive short-string comparison), with a CPU-growth test
- [x] #2 _SECRET_QUERY (the second quadratic pattern in scrub) is linear with identical output on names of [a-z0-9_] (same comparison), with a CPU-growth test on ? + token x n
- [x] #3 Review follow-ups fixed at the owner's request: a query name may hold - . % (X-Amz-Signature, api-key, api%5Fkey are redacted), and every log key, top-level and nested, is scrubbed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Anchor _URL_USERINFO at a run's start (the reviewer's candidate); time every other pattern in scrub on the same shapes; exhaustive old-vs-new comparison of scrub with the old patterns swapped back; CPU-growth tests that fail on the old patterns.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-281 review (2026-10-22): a NeurIPS listing warning also logs its see-also links uncapped, so a hostile listing can put long text through scrub(); fixing scrub's growth here covers it.

2026-10-23: _URL_USERINFO now (?<![a-zA-Z0-9+.-])(?P<pre>[0-9+.-]*+)(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*+://)[^/\s@]+@ (the reviewer's candidate). Timing every pattern in scrub found a second: _SECRET_QUERY took 452 ms on '?' + 'token' x 4,000 (16x for 4x), its lazy scan re-reading the name once per secret word; now a lookahead for the word and a possessive name run. Tests compare scrub against the old patterns (swapped back on logs) over every string up to 6 characters of two alphabets; a one-off run compared each pattern alone over every string up to 7 (7.8M): no difference. Growth checks on four shapes fail on the old patterns and pass now. Tests: backend/tests/unit/test_logs.py.

2026-10-23 review round 1: qa-auditor's Must (no test caught (?P<pre>[0-9]*+), which leaks .a://u@h: 7 characters, past the exhaustive length) fixed with named examples; growth cases now run a+ and a- and a query name of -%. too. At the owner's request two gaps the review found were fixed in this task: _SECRET_QUERY's name class is now [a-z0-9_.%-] (security-reviewer), and _clean/_fields scrub every key (observability-reviewer). Both only widen redaction; the old-pattern comparison's alphabet leaves out -.% and examples cover them.

2026-10-23 review round 2: code-reviewer's Should (two keys scrubbing alike kept only the last value) fixed with _put (name#2, #3, …) at both sites; qa-auditor's Must (dropping . from the lookahead class alone leaked ?client.secret=) fixed with that example; growth cases now repeat the word after each added name character. Round-2 nits fixed: # and ; start a parameter (fragments' #access_token=), Bearer <token> is redacted (_BEARER), the text formatter JSON-encodes a key that is not a plain name. Deferred as TASK-283: percent-encoded URLs inside a value, and a bare token= with no ?&#; before it.
<!-- SECTION:NOTES:END -->
