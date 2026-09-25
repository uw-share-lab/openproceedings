---
name: usability-testing
description: The openproceedings usability-test standard — the study plan/protocol template, task-writing rules with the real review tasks (reproduce a Trust-Evals string, confirm workshop exclusions, export to Covidence, replay a search record, find missed vocabulary), think-aloud moderation, metric definitions (task success, time on task, errors, SEQ, SUS with its scoring, UMUX-Lite), sample-size guidance with its caveats, the 0–4 severity scale, and the report template. Use when planning, running or reporting a usability study, or when interpreting usability metrics.
---

# Usability testing

## Plan template (`docs/usability/<YYYY-MM-DD>-<flow>/plan.md`)
```
# <Flow> usability study
Ethics: not submitted | submitted <date> | cleared <file #>   ← no sessions before "cleared"
Decision this informs: …          Personas: …          Moderated | unmoderated, remote | in person
Environment: op serve (fixture index <index_version>), frontend build <sha>, fresh records.sqlite
Tasks: (table: id, goal as given to participant, start URL, success criterion, max time)
Metrics: per-task success, time, errors, SEQ; post-test SUS or UMUX-Lite
Data handling: recordings → lab storage / data/research/ (gitignored); repo gets de-identified report only
Pilot: date, changes made
```

## Task-writing rules
1. A goal from real review work, never an instruction. Say "Make sure your set has no workshop papers,
   and note how many were left out", not "Click the workshop checkbox".
2. Never name the control, the syntax or the product term that solves it ("wildcard", "search record").
3. Success criterion is written **before** the first session and is checkable against the API.
4. Use real material: strings from `backend/tests/fixtures/` (Trust-Evals variants), fixture record ids.
5. One goal per task. Order them from easy to hard, and don't let an earlier task leak the answer to a later one.

Core task bank:
| Id | Goal | Success |
|---|---|---|
| T1 | Run the review's main protocol string (given on paper) and report the number of papers | reported `total` matches API |
| T2 | Say how the tool read the query: which terms must all appear | identifies the AND groups from the tree |
| T3 | Confirm no workshop papers are included, and how many were left out | states `excluded.track.workshop` |
| T4 | You suspect papers saying "benchmarks" are missing. Check and fix | uses a wildcard or OR and sees the expansion |
| T5 | Get this set into a file Covidence can import | RIS downloaded, count stated before download |
| T6 | A peer reviewer sent this record link. Is the search still reproducible? | states `reproduced` or `drifted` with counts |
| T7 | Write the search sentence for your methods section | methods text copied, index version included |

## Moderation (think-aloud)
Concurrent think-aloud. Prompts are neutral only ("keep talking", "what are you looking for?"). Never
hint. If someone is stuck past the max time, note "assisted" and move on. Observer notes are
time-stamped. Debrief after the post-test questionnaire.

## Metrics
- **Task success:** success / assisted / fail. Report counts (e.g. 4/6) with an **adjusted-Wald**
  interval for small n, never a bare percentage.
- **Time on task:** successful attempts only. Report the median (geometric mean if reporting a centre
  for n < ~25), never the arithmetic mean alone.
- **Errors:** actions that move away from the goal (e.g. edits a lowercase `or` believing it's an operator).
- **SEQ:** one 7-point item after each task ("Overall, this task was…" very difficult → very easy).
- **SUS:** 10 items, 1–5. Odd items score − 1, even items 5 − score, sum × 2.5 → 0–100. Around 68 is
  commonly cited as average. It's not a percentage, and it has no meaning below about 5 participants.
- **UMUX-Lite:** 2 items, 1–7. `(item1 + item2 − 2) / 12 × 100`. Use it when session time is tight.
Verify the exact item wording against the published instrument before running.

## Sample size (formative)
About 5 participants per distinct persona finds most *common* problems (the Nielsen and Landauer
problem-discovery model). Caveats: it assumes a high per-user detection rate, so it misses rare
problems and doesn't hold across very different personas (a newcomer and a methods reviewer are two
groups). It isn't enough for benchmark metrics (SUS comparisons need far larger n). Iterate: 5 → fix →
5, rather than one 15-person round.

## Severity (0–4, shared with `heuristic-evaluation`)
0 not a problem · 1 cosmetic · 2 minor, slows or confuses · 3 major, a task fails or the reviewer reports
the wrong thing · 4 catastrophic, a wrong number or search ends up in a review. Weigh by frequency (how many hit it) and
persistence. Hiding an exclusion, interpretation or replay status is ≥3.

## Report template (`report.md`)
Summary (3 lines) · ethics status · participants by persona (codes only) · metrics table with n ·
findings (severity, heuristic id if any, "k of n participants", evidence as paraphrase, recommendation,
Backlog id) · what worked · limitations · next study.
