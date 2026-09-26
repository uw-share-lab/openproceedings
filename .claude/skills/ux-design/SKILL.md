---
name: ux-design
description: The openproceedings design process and design-doc standard — when a feature needs a design doc, the docs/design/<date>-<feature>.md template, the required states table (empty, loading, error, zero results, too many results, read-only builder, drifted record, narrow viewport), wireframe conventions, and the principles for an expert research tool (transparency over magic, show the system's interpretation, reversible actions, URL-is-state, dense but scannable). Use when designing, reviewing or implementing any new page, component or flow, or when judging whether a design is complete.
---

# UX design for openproceedings

## Principles (expert research tool, not a consumer search box)
| Principle | What it means here | Violation example |
|---|---|---|
| **Transparency over magic** | The tool never does something the reviewer didn't write. Wildcards, defaults, translations are shown (guarantee 6). | "Did you mean benchmarks?" auto-applied; a hidden synonym |
| **Show the system's interpretation** | The parsed tree, the canonical string with defaults made explicit, the expansion list, all one click away and never hidden behind a mode. | Mixed AND/OR accepted with no tree link |
| **Reversible actions** | Every facet toggle or include is a `q` edit, so Back and the editor both undo it. The query text is never lost across Text/Builder toggles. | Builder edit that discards the text draft |
| **URL is state** | Whatever changes the result set is in `q` (guarantee 3). Designs write the URL before and after each action. | A "hide workshops" switch stored in local state |
| **Dense but scannable** | Numbers first, `tabular-nums`, monospace for queries/versions. Hierarchy by type weight, not whitespace. | Hero banner, cards with one number each |
| **Exact numbers** | Counts are exact and come from the API. No "400+", no client arithmetic beyond display. | "About 400 results" |
| **Recall and precision stay in the user's hands** | The tool shows what to consider (expansions, excluded counts, facet counts) and the reviewer decides. | Auto-including rejected papers "for completeness" |

## When a design doc is required
A new route, a new component in the `/search` workspace, a change to a flow in spec 05 §Components, any
new state the API can put the UI in, or a change to the methods text. Copy-only or styling fixes need no
doc. They follow `ui-design-system` and `ux-writing`.

## Required states table (every row designed, or marked "unreachable because …")
| State | Trigger | Must show |
|---|---|---|
| Empty | `/search` with no `q` | editor focus, example review strings, coverage summary line |
| Loading | search in flight | previous results kept (`keepPreviousData`), a quiet indicator, no layout jump |
| Parse error | 422 with diagnostics | squiggle + diagnostics row with the server message and fix hint. No stale results presented as current |
| Server error | 5xx / network | error code, retry. The query is preserved |
| Index unavailable | 409 pinned `index_version` | which version was requested, which is current, the replay implication |
| Zero results | `total: 0` | the canonical string, the exclusion banner (maybe the hits were excluded), the expansions, the tree |
| Too many expansions | `WILDCARD_TOO_MANY_EXPANSIONS` | the stem, the count, the suggestion to lengthen it |
| Large set | `total` in the thousands | exact total, export still whole-set, paging stable |
| Builder read-only | AST doesn't fit | why (the blocking construct), how to go back to Text |
| Record reproduced / drifted | `/record/[id]` | status, `+added / −removed` with a diff link. `mismatch` shown as an error, never as normal |
| Narrow | 360 px | filters behind "Filters (n active)", nothing hidden without a count |

## Design-doc template (`docs/design/<YYYY-MM-DD>-<feature>.md`)
```
# <Feature> — design
Status: draft | reviewed | handed off · Backlog: task-NNN · Spec: 05 §…
## Problem and job   (persona, JTBD statement, evidence links or "assumption")
## Flow              (Mermaid flowchart; q before/after each action)
## States            (the table above, every row)
## Wireframes        (ASCII per state; numbers labelled with API fields)
## Interaction spec  (keyboard path, focus after each action, live announcements, what changes the URL)
## Copy              (every string; new ones flagged for ux-writer)
## API fields needed (existing / missing → proposed task)
## Evidence          (hci-researcher notes: claim → verdict → verified source)
## Heuristic pass    (usability-auditor findings and dispositions)
## Open questions    (including any spec 05 deviation)
```

## Wireframe conventions
ASCII in a fenced block, spec 05's box characters, one wireframe per state. `[Button]`, `☑/☐`, `▾`
for menus, `⚠` for warnings. Numbers are realistic but labelled (`412 {total}`). Mermaid `flowchart TD`
for flows, `stateDiagram-v2` for component state.

## Handoff
A doc is ready when every state row is designed, every API field exists or has a task, and the
heuristic pass has no open severity 3–4 finding. `frontend-engineer` builds from it, and the PR links it.
