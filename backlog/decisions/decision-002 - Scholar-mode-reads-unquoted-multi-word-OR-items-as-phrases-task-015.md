---
id: decision-002
title: Scholar mode reads unquoted multi-word OR items as phrases (task-015)
date: '2026-09-26 02:55'
status: accepted
---
## Context

The Trust-Evals protocol's Publish-or-Perish variant (`main-2-pop` in
`backend/tests/fixtures/queries/trust-evals.txt`) writes unquoted multi-word items between `|`
separators: `(large language model$ | LLM | foundation model$ | …)`. Google Scholar binds `|`/`OR` tighter
than juxtaposition, so Scholar actually ran `large AND language AND (model$ OR LLM OR foundation) AND …`.
The review clearly meant phrases: the equivalent boolean string (`main-1`) quotes them. Openproceedings'
native precedence (AND tighter than OR) gives a third reading. The choice changes that string's result
set, so it was put to the review lead (2026-09-25), who chose the intent reading. The review's primary
string (`main-7-most-updated`) quotes all its phrases and is unaffected.

## Decision

In `mode="scholar"` only, a run of two or more juxtaposed unquoted words with an `OR`/`|` directly on at
least one side, bounded by `OR`/`|`, a parenthesis or the query's edge, is read as one phrase
(`large language model$` → `"large language model$"`, the wildcard expanded at its position per
decision-001). Each rewrite raises a `COMPAT_POP_PHRASE` translation notice with its span. A lowercase
`and`/`or`/`not` (which keeps its own lowercase-operator warning) or a word with no letters or digits ends a
run rather than disappearing into a phrase (task-015 review). Native mode is unchanged.

## Consequences

- `main-2-pop` parses to the same query as `main-1` apart from the wildcards, and the golden snapshots
  show it.
- A Scholar-mode string that relied on Scholar's real precedence is read differently from what Scholar
  ran. The translation notice says so for every rewritten run, and the Scholar comparison (task-056)
  must note it.
- Changing this is a `QUERY_VERSION` bump and a new decision.
