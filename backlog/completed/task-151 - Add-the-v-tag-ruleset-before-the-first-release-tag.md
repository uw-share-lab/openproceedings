---
id: TASK-151
title: Add the v* tag ruleset before the first release tag
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:05'
updated_date: '2026-10-02 00:03'
labels:
  - ops
milestone: m-6
dependencies: []
references:
  - docs/specs/08-ops-and-tooling.md
priority: medium
ordinal: 127000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-066 (PR #54) deferral. Spec 08 §Branch protection says that before the first release tag a maintainer adds a tag ruleset on `v*`: only maintainers create one, and none is updated or deleted, because a moved tag would silently re-section `CHANGELOG.md` (`changelog.py` places each PR under the oldest tag that holds it) and break the "run that release's tag" route to reproducing an old search record. §Release step 6 checks it with `gh api repos/<owner>/<name>/rulesets --jq '.[] | select(.target == "tag") | .name'` and pastes the output into the promotion PR. The repository has no rulesets today: `gh api repos/uw-share-lab/openproceedings/rulesets` returned `[]` on 2026-09-30. This is a repository-settings change a maintainer applies by hand in GitHub (Settings → Rules → Rulesets, or the REST API); no code change is expected beyond recording it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One or more active tag rulesets target `refs/tags/v*` on uw-share-lab/openproceedings: creating a matching tag is restricted to maintainers (the maintainer role or team is the only bypass actor on the ruleset that restricts creation), and updating and deleting a matching tag are blocked by a ruleset with an empty bypass list, because a ruleset's bypass list covers every rule in it
- [x] #2 `gh api repos/uw-share-lab/openproceedings/rulesets --jq '.[] | select(.target == "tag") | .name'` (spec 08 §Release step 6) prints the rulesets' names; the output is pasted into the task notes
- [x] #3 Spec 08 §Branch protection and §Release step 6 record the date the rulesets were applied, their names, and that the check may print more than one name
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Applied by a maintainer on 2026-10-01 via gh api (not by this PR): ruleset 24290624 'Release tags: maintainers only create' (rule creation; bypass RepositoryRole 2 maintain and 5 admin, mode always) and 24290628 'Release tags: immutable' (rules update and deletion; empty bypass list), both active, target tag, include refs/tags/v*. Admin as a second bypass actor on the creation ruleset is no wider than the maintainer role in effect (an admin can edit rulesets anyway). Output of `gh api repos/uw-share-lab/openproceedings/rulesets --jq '.[] | select(.target == "tag") | .name'` on 2026-10-01:
```
Release tags: immutable
Release tags: maintainers only create
```
Spec 08 §Branch protection and §Release step 6 record the date, the names and that the check prints more than one name.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The v* tag rulesets (applied by a maintainer 2026-10-01) are verified with gh api and recorded: names, date and the multi-name check in spec 08 §Branch protection and §Release step 6; the check's output is in the notes.
<!-- SECTION:FINAL_SUMMARY:END -->
