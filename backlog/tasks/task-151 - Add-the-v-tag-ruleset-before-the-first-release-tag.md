---
id: TASK-151
title: Add the v* tag ruleset before the first release tag
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:05'
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
- [ ] #1 A tag ruleset targeting `refs/tags/v*` is active on uw-share-lab/openproceedings: tag creation is restricted to maintainers (the bypass list names only the maintainer role or team), and updating and deleting a matching tag are blocked for everyone
- [ ] #2 `gh api repos/uw-share-lab/openproceedings/rulesets --jq '.[] | select(.target == "tag") | .name'` (spec 08 §Release step 6) prints the ruleset's name; the output is pasted into the task notes
- [ ] #3 Spec 08 §Branch protection records the date the ruleset was applied and its name, as it does for the branch rules
<!-- AC:END -->
