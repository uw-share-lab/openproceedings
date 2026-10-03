---
name: user-research
description: User-research standard for openproceedings — the interview guide skeleton for systematic reviewers, the persona set (lead reviewer, second screener, methods peer reviewer, newcomer student) with their jobs-to-be-done, the review-workflow journey (Scholar/PoP drafting → search → export → dedup → Covidence → screening → PRISMA reporting → peer review/replay), affinity-mapping synthesis, and privacy rules (roles and codes, never names). Use when planning interviews or contextual inquiry, writing personas, JTBD or journey maps, recruiting for a study, or naming who a design serves.
---

# User research

## Personas (proto-personas until interviews confirm. Mark each claim evidence or assumption)
| Persona | Context | Main jobs | Biggest risk for them |
|---|---|---|---|
| **Lead reviewer** | Owns the protocol and the search strings. Reports in the methods section | Formulate and refine the Boolean string. Get a reportable, replayable search into Covidence | Reporting a count that silently included workshops or stemmed matches |
| **Second screener** | Screens titles/abstracts in Covidence. Seldom writes queries | Understand why a record is in the set. Trace it back to the search | Can't tell whether an odd record came from a wildcard expansion |
| **Methods peer reviewer** | Reads the paper and wants to check the search | Replay the search and confirm the count and exclusions | A record link that shows `drifted` with no explanation |
| **Newcomer student** | First review, limited Boolean fluency | Turn concept lists into a working query without syntax errors | Lowercase `or`, mixed AND/OR, too-short wildcard stems |

## Jobs to be done (`When <situation>, I want to <motivation>, so I can <outcome>`)
- When my protocol string was written for Scholar, I want to run it unchanged and see any translation,
  so I can report one search across sources.
- When I get a count, I want to see what the tool left out and why, so I can fill the PRISMA
  "removed before screening" box.
- When I suspect missed vocabulary, I want to see which terms my wildcards and phrases actually matched,
  so I can widen recall deliberately.
- When a peer reviewer questions my search, I want to hand over a link that replays it, so the numbers
  can be checked without me.
- When I screen an unexpected record, I want to see which terms matched it, so I can judge whether the
  string is too broad.

## Journey (the review workflow the product sits in)
```
protocol → draft strings (Scholar/PoP, spreadsheets) → run search (openproceedings) → export RIS
→ dedup across databases → Covidence import → title/abstract screening → full text → PRISMA flow
→ methods section → peer review / replay (search record)
```
For each stage, record: actions, tools, artefacts, pains, workarounds, and where openproceedings touches it.
Render as a table or a Mermaid `journey` in `docs/research/`.

## Interview guide skeleton (45–60 min, semi-structured)
1. Consent confirmed, recording on only if consented (2 min).
2. Role and experience: reviews done, databases used, Boolean comfort (5 min).
3. **Last review, walked through**: "Show me / tell me how you built the search for your last review."
   Probe each journey stage (20 min).
4. Critical incidents: a time a search result surprised you, and a time a peer reviewer questioned a
   search (10 min).
5. Reporting: how you filled PRISMA and the methods text, and what you couldn't report (5 min).
6. (Optional) React to a current flow. That's evaluative, so keep it short and last (5–10 min).
7. Anything we didn't ask. Thanks, and the next step.
Rules: ask about past behaviour, not hypothetical preference. No leading questions ("wouldn't it be
useful if…"). Ask "why" at most three levels deep.

## Synthesis (affinity mapping)
1. One observation per note, tagged with participant code and journey stage. Facts, not interpretations.
2. Cluster bottom-up, then name each cluster as an insight sentence.
3. Each insight carries support ("4 of 6, across 3 personas") and at least one de-identified example.
4. Insights → design implications → Backlog tasks. Contradictions are kept and reported, not averaged.

## Privacy rules
- Roles and codes (P1, P2…) only. Never names, institutions small enough to identify, emails or faces.
- Raw material and the code key stay in lab storage or `data/research/` (gitignored). Per `hci-methods`, the
  public repo gets de-identified synthesis only.
- Quote verbatim only if consent covers publication. Otherwise paraphrase.
- Unpublished review topics or strings a participant shares are confidential research data.
