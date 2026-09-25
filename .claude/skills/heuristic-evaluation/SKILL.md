---
name: heuristic-evaluation
description: Heuristic evaluation and cognitive walkthrough standard for openproceedings — Nielsen's 10 usability heuristics adapted with concrete examples from this product, six search-specific heuristics (interpretation visibility, recall-vs-precision control, exclusion visibility, reproducibility affordances, query-error recovery, vocabulary discovery), the four cognitive-walkthrough questions, and the 0–4 severity scale mapped to Must/Should/Nit. Use when running or reviewing a heuristic pass on a frontend diff or design doc, acting as usability-auditor, or rating the severity of a usability problem.
---

# Heuristic evaluation

## Nielsen's 10, applied here
| Id | Heuristic | In openproceedings |
|---|---|---|
| N1 | Visibility of system status | `total`, `index_version`, parse state and export count always visible. The diagnostics summary updates after the debounced `/parse` |
| N2 | Match between system and the real world | Reviewers' words: "records removed before screening", "search string", "Covidence". `datasets_benchmarks` shown as `D&B` with full name |
| N3 | User control and freedom | Every facet/include is a `q` edit, undone by Back or by editing. Toggling Text/Builder never loses the query |
| N4 | Consistency and standards | One term per concept (`ux-writing` glossary). Scholar-style `OR`/quotes work, and translations are announced |
| N5 | Error prevention | Autocomplete for `track:`/`venue:` from `/meta`. The mixed AND/OR warning with `[show tree]` before searching |
| N6 | Recognition rather than recall | Field and value completion, example strings on `/`, `/help/syntax` one link away from every diagnostic |
| N7 | Flexibility and efficiency | Keyboard-only drafting, paste-in protocol strings, URL sharing, builder for novices and text for experts |
| N8 | Aesthetic and minimalist design | Dense but quiet (`ui-design-system`). No decoration competing with counts or the banner |
| N9 | Recognize, diagnose, recover from errors | Every error has a span, the quoted text and a fix hint (`error-diagnostics`, `ux-writing`) |
| N10 | Help and documentation | `/help/syntax` generated from the golden table. Diagnostics link to the relevant section |

## Search-specific heuristics
| Id | Heuristic | Pass means | Typical failure |
|---|---|---|---|
| S1 | **Interpretation visibility** | The user can see how the query was read: tree, canonical string with defaults, operator precedence | Tree hidden when AND/OR mixed. Canonical not copyable |
| S2 | **Recall-vs-precision control** | The user can deliberately widen (wildcard, OR, include) or narrow, and sees the effect in exact counts | Wildcards available but expansion list truncated without `+N` |
| S3 | **Exclusion visibility** | Every default-filter exclusion is counted and includable, even when 0 | Banner absent on zero results, when the hits were all workshops |
| S4 | **Reproducibility affordances** | Save record, permanent link, methods text, replay status are findable where the reviewer finishes | Methods text missing `index_version`. `drifted` styled like success |
| S5 | **Query-error recovery** | From an error, the user reaches a valid query without leaving the editor or losing text | Error clears the results and the query. Hint says "invalid query" |
| S6 | **Vocabulary discovery** | The user can find the terms they're missing (expansions, facet counts, highlighted terms in hits) | `benchmarking` matches nothing of `benchmarks` and nothing suggests `benchmark*` |

## Cognitive walkthrough (per step of the changed flow)
1. Will the user try to achieve the right effect?
2. Will the user notice that the correct action is available?
3. Will the user associate the correct action with the effect they want?
4. After the action, will the user see that progress is being made toward the goal?
Walk it as the newcomer student, then as the lead reviewer (`user-research`). A "no" on any question is a
finding, rated below.

## Severity and mapping to review findings
| 0–4 | Meaning | Review severity |
|---|---|---|
| 4 | Catastrophic: a wrong search, count or method could be reported | **Must** |
| 3 | Major: task fails, or a guarantee (interpretation, exclusion, replay) is hidden | **Must** |
| 2 | Minor: slows or confuses, recoverable | **Should** |
| 1 | Cosmetic | **Nit** |
| 0 | Not a usability problem | not reported |
Rate by impact × frequency × persistence. Every finding names its heuristic id, the state and the
reproduction. Don't re-report what `ux-reviewer` (guarantee conformance) or `accessibility-auditor`
(WCAG) owns. Cross-reference them instead.
