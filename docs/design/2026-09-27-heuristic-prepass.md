# M3b design — heuristic pre-pass and dispositions

Status: **done** · Backlog: TASK-033 AC#2 · Standard: `heuristic-evaluation` (Nielsen N1–N10, search heuristics
S1–S6, the four walkthrough questions, severity 0–4 → Must/Should/Nit) · Docs reviewed:
[search workspace](2026-09-27-search-workspace.md), [builder](2026-09-27-concept-group-builder.md),
[export, records and paper](2026-09-27-export-records-and-paper.md),
[coverage and syntax help](2026-09-27-coverage-and-syntax-help.md), [copy deck](2026-09-27-copy-deck.md)

Two passes ran on 2026-09-27:
1. **Self-check** by the designer while drafting (findings SC-n). Each was fixed in the draft before the
   auditor saw it.
2. **usability-auditor pre-pass** (read-only, run as a separate agent over the finished drafts), in design-doc
   mode: cognitive walkthrough of eight flows as the newcomer student and the lead reviewer, then the heuristic
   pass. Verdict on the drafts: **REQUEST CHANGES** (8 Must, 15 Should, 8 Nit). All of them are dispositioned
   below. After the fixes no severity 3–4 finding is open, which is `ux-design`'s handoff rule.

Dispositions: **fixed** (the doc and section changed), **task** (needs work outside this design; recorded in the
implementing task's notes for the main session to file as a Backlog task, since worktree agents don't create
task ids), **rejected** (with the reason).

## Auditor findings

### Must (severity 4–3)
| Id | Heuristic, sev. | Finding | Disposition |
|---|---|---|---|
| M1 | N4/S2, 3 | Include button showed 205 (facet count) but its accessible name and the checkbox label said 212 (bucket), and the live region announced 624 (412 + 212) instead of the new `total` | **fixed**: search workspace §W5 Include buttons and §Interaction spec use 205 and 617; a test checks name = label |
| M2 | S3, 3 | After an include the track field is a user limit, its buckets drop to 0, and the 4 competition / 3 unknown papers it still leaves out were named nowhere | **fixed**: §W5 "A field that is a user limit" (banner names the limit) and the Limits line itemises what it leaves out from `facets` |
| M3 | N1/S4, 3 (also ux-reviewer: guarantee 4) | `POST /records` takes only `{q, mode}`; a hot swap between search and save would freeze the query on another index while the dialog showed the old total | **fixed** in export doc §S2 (compare the 201's `index_version`, warning SV-8) + **task**: optional `RecordRequest.index_version` pin (TASK-044 notes) |
| M4 | S3/S4, 3 | Drifted record didn't show `replay.excluded` / `excluded_match`, so a peer reviewer couldn't check the exclusions | **fixed**: export doc §R2 "Exclusions on re-run", copy RC-3a |
| M5 | S1, 3 | A pasted concept list (`trust, reliance` or `trust or reliance`) in one builder term silently became one phrase | **fixed**: builder §States "Pasted list in one term" (Split into n terms by default) and the "searched as one phrase" chip note |
| M6 | S1, 3 | Diagnostics row said "searched query" in W5 but "draft" in W3; "Show how it was read" on a draft warning opened the searched query's tree | **fixed**: §W3 "Two interpretations, both labelled" (draft row and tree labelled "Draft — not searched"; a "Searched query: n warnings" line stays) |
| M7 | S1/N1, 3 | Changing the Syntax select wasn't counted as a dirty draft, so a facet click could silently drop a mode change | **fixed**: the draft is `(text, mode)` (§W3, §States, `DRAFT_DIRTY`), Revert restores the mode |
| M8 | S5/N9, 3 | Pasting the review's Scholar string in native mode gave nine `FIELD_COMPAT_ONLY` errors whose fix (rewrite `source:` by hand) loses the protocol string as typed | **fixed**: §W3 "Read as Google Scholar syntax" action (a draft mode change, text untouched) and collapsed repeats ("9 ×") |

### Should (severity 2)
| Id | Heuristic | Finding | Disposition |
|---|---|---|---|
| S1 | N4 | Identified and unclassified totals computed by the client | **fixed + task**: export doc §API fields makes `identified_total`/`unclassified_total` a blocking dependency of TASK-044 AC#1; unclassified itemised per map on the record page |
| S2 | S3 | Export warned about status only; track isn't visible in Covidence either | **fixed**: export doc §E2 track warning, copy EX-E3a |
| S3 | N9 | Same index, different `X-Total` was worded as "the index changed" | **fixed**: export doc §E1, copy EX-E3b (a bug message) |
| S4 | S4 | Record page shows nothing during a 429/503 | **task**: `?replay=false` proposal (TASK-044 notes); until then RC-16 wait state |
| S5 | S3/N9 | Include whose facet count is 0 had no design | **fixed**: §W5 "An include that would add 0" |
| S6 | S3/S6 | Zero results lacked the Limits line and an exact-matching hint | **fixed**: §W8, copy ER-9 |
| S7 | S5 | Mixed AND/OR warning didn't show where to add parentheses | **fixed**: "Load with parentheses" (draft only, from the server's reported reading), copy ED-17 |
| S8 | N5 | Builder told readers to edit limits in Filters, which a dirty draft disables | **fixed**: builder §B1, copy BD-4 |
| S9 | N4 | One "Search in" menu per group row labelled "(per term)" | **fixed**: scope on each chip (builder §B1) |
| S10 | N4 | Builder disabled Search when empty, contradicting "the client never blocks a search" | **fixed**: Search stays enabled; the server's `PARSE_EXPECTED_TERM` answers (builder §States, BD-5) |
| S11 | N2/N6 | Examples labelled "from a real review" weren't verbatim; main-7 not offered | **fixed**: §W1 offers `main-7-most-updated` verbatim in Scholar mode; others labelled plainly |
| S12 | N4 | W11 said "split into several searches", the deck says "shorten" | **fixed**: W11 uses ED-11 |
| S13 | N2 | Include description said "adds `track:workshop`" (which would mean workshops only) | **fixed**: "Adds workshop to the track filter, `track:(… OR workshop)`" (BN-3) |
| S14 | N5/N6 | "Edit `year:`" appended a second `year:` clause | **fixed**: selects the existing clause, else inserts a selected `year:2020..2026` placeholder |
| S15 | N10 | Help examples always opened in native mode | **fixed**: each example carries its mode |

### Nit (severity 1)
| Id | Finding | Disposition |
|---|---|---|
| N1 | Index versions drawn as prefixes or "64 hex" | **fixed**: the whole 12-character value everywhere |
| N2 | "Filters (2 active)" on a query with no limits | **fixed**: 0 |
| N3 | Expansion line showed 3 terms then +9, rule says 8 | **fixed** |
| N4 | Default track clause order differs from spec 05 §8's example | **fixed** in copy BN-4: the clause text is the server's, not the spec example's order |
| N5 | papers/records, `desk_rejected`/"desk rejected", raw mode names | **fixed**: records for the index (CV-1, home line), badge wording rule (RH-10), mode in words (PA-2) |
| N6 | Nine `COMPAT_SOURCE_ALIAS` lines | **fixed**: repeated codes collapse (§W3) |
| N7 | Help "Try it" searched while home examples only load | **fixed**: "Search with this example ▸" |
| N8 | Docs claimed a finished pre-pass and cited ids that didn't exist yet | **fixed**: statuses now "reviewed, handed off after the pre-pass", ids point here |

Cross-references (not re-reported here): the 500 ms silent `aria-disabled` window for `STALE_CLAUSE` (W13) goes
to accessibility-auditor at TASK-046; M3 is also ux-reviewer's (guarantee 4).

## Self-check findings (designer, fixed while drafting)
| Id | Heuristic, sev. | Finding | Fix |
|---|---|---|---|
| SC-1 | S3, 3 | On narrow screens the banner sat inside the collapsed Filters panel | banner above the Filters button (§W14) |
| SC-2 | N3/N5, 3 | A facet click with unsearched edits would discard them | `DRAFT_DIRTY` (§W13) |
| SC-3 | S3/S1, 3 | Zero results showed no banner, so all-excluded hits looked like no hits | banner and open tree on zero results (§W8) |
| SC-4 | N1, 3 | After a 422 the old results looked current | stale block naming their query, Restore it (§W6) |
| SC-5 | N9, 2 | `WILDCARD_TOO_MANY_EXPANSIONS` appears only after Search, unexplained | ED-10 (§W7) |
| SC-10 | N9, 3 | Read-only builder said "too complex" without saying what | names the first construct and its span (builder §Fit table, B2) |
| SC-11 | N3, 3 | Switching tabs could reformat an untouched query | untouched text round-trips byte for byte |
| SC-12 | — (a11y) | Focus lost after removing a group | focus rule (builder §Interaction) |
| SC-13 | N9, 2 | Builder diagnostics unattached to a term | per-term diagnostics |
| SC-20 | S3, 3 | Export into Covidence with rejected papers screeners can't see (observed: `docs/results/2026-09-27-covidence-check.md`) | status warning E2 |
| SC-21 | S4, 3 | Export after a hot swap could hand over another set | `index_version` pinned to the shown one; header check E3 |
| SC-22 | S4, 3 | Drifted styled like success, without a reason | warn styling, changed inputs named (R2) |
| SC-23 | S4, 4 | Mismatch could still offer methods text or export | not rendered (R4) |
| SC-24 | N5, 3 | Saving is permanent and public, silently | confirm dialog S1 |
| SC-30 | S4, 2 | Coverage wording "crawl" for a Scholar-dates window | neutral "Collected" until the API exposes the kind |
| SC-31 | N10, 2 | Help and parser could drift | generated from goldens, test on a missing code |
| SC-32 | N4, 2 | Coverage row totals summed on the client | only API totals; cells shown as given |

## Cognitive walkthrough (auditor, on the drafts; ✗ cells now fixed)

Q1 = tries the right effect, Q2 = notices the action, Q3 = associates action and effect, Q4 = sees progress.
Each cell: newcomer / lead.

| Flow step | Q1 | Q2 | Q3 | Q4 | Fixed by |
|---|---|---|---|---|---|
| a1 Paste main-7 (native default) | ✓/✓ | ✗/✓ | ✗/✓ | ✓/✓ | M8 |
| a2 Set Scholar, Search | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | (N6) |
| b1 Read `be*` / `or` diagnostics | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| b2 `be*` → `bench*` | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| b3 `or` → `OR`, mixed AND/OR warning | ✓/✓ | ✓/✓ | ✗/✓ | ✗/✗ | S7, M6 |
| c1 Include workshop from the banner | ✓/✓ | ✓/✓ | ✗/✓ | ✓/✓ | M1 |
| c2 Read the state after including | ✓/✓ | ✓/✓ | ✓/✓ | ✗/✗ | M2 |
| d1 Export ▾ → RIS | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| d2 RIS with workshops included | ✓/✓ | ✗/✗ | ✓/✓ | ✓/✓ | S2 |
| e1 Save search record | ✓/✓ | ✓/✓ | ✓/✓ | ✗/✗ (index swap) | M3 |
| e2 Copy methods text | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| f1 Peer reviewer opens a drifted record | ✓/✓ | ✓/✓ | ✓/✓ | ✗/✗ | M4 |
| f2 Open the added/removed diff | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| f3 Record while the server is busy | ✓/✓ | ✗/✗ | — | ✗/✗ | S4 (task) |
| g1 Build three groups | ✓/✓ | ✓/✓ | ✗/✓ | ✓/✓ | M5, S9 |
| g2 Change a limit from the builder | ✓/✓ | ✓/✓ | ✗/✗ | ✗/✗ | S8 |
| g3 Switch to Text | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| h1 Zero results, all workshop | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ | — |
| h2 Include from W8 | ✓/✓ | ✓/✓ | ✓/✓ | ✓/✓ (✗ if the facet is 0) | S5 |

## Not covered by this pass
A heuristic pass on paper can't show real misreadings. TASK-047 (usability round 1, after the full system)
tests the assumptions the docs mark as such: newcomer Boolean errors, pages vs scroll, the include wording, the
methods-text paste target.
