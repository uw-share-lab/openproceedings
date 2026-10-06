---
id: TASK-184
title: 'op serve flags for the comparison caps, cooldown factor and upload weight'
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:05'
labels:
  - ops
  - api
milestone: m-6
dependencies: []
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-177 exposes only --compare / --no-compare; the caps, compare_cooldown_factor, compare_upload_weight and compare_token_ms are ApiConfig values an operator cannot set from the command line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each has a flag documented in spec 08 and deploy/README.md, validated at start, and shown in /meta where it is a limit
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. op serve flags for every compare cap (body, records, line length, results, response bytes, seconds, upload seconds, slots) and for compare_cooldown_factor, compare_upload_weight, compare_token_ms; unset flags keep ApiConfig's defaults.
2. Validated at start by the config (range; finite floats), refused as usage naming the option.
3. /meta limits.compare gains the two caps it didn't state (max_upload_seconds, max_concurrent); the three costs are not limits (like export_weight) and are not in /meta.
4. make openapi; spec 04/08 and deploy/README; tests in test_compare.py.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Flags: --compare-max-body-bytes, --compare-max-records, --compare-max-line-chars, --compare-max-results, --compare-max-response-bytes, --compare-max-seconds, --compare-upload-seconds, --comparison-slots, --compare-cooldown-factor, --compare-upload-weight, --compare-token-ms; each named after its ApiConfig/RateLimit field so a refusal names it. Unset flags keep the config defaults (one source). The five float fields now refuse inf/nan (allow_inf_nan=False). /meta limits.compare gains max_upload_seconds and max_concurrent (the two caps decision-035 lists that /meta didn't state); cooldown factor, upload weight and token ms are costs, not limits, so not in /meta (like export_weight). Contract: make openapi (openapi.json, schema.ts), compare-fixture.json regenerated. Tests: test_compare.py -k 'serve or meta or caps' 30 passed; test_serve, test_abuse_limits(_r3), test_frontend_compare_fixture, test_openapi 73 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op serve takes a flag for every POST /compare cap and for compare_cooldown_factor, compare_upload_weight and compare_token_ms, each validated at start by the config (range, finite) and refused as usage naming the field; /meta limits.compare now also states max_upload_seconds and max_concurrent. Documented in spec 04 (§Comparing, §Implementation notes), spec 08 (op serve row, §Deploy) and deploy/README.md §Tuning comparisons. Verified by test_compare.py's new serve-flag tests (every flag sets its field, every bad value refused, /meta states set caps) and the contract snapshot tests.
<!-- SECTION:FINAL_SUMMARY:END -->
