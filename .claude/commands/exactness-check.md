---
description: Exactness check for the current branch — runs exactness-guardian and differential-tester in parallel on the branch diff and reports any counterexample query where TantivyEngine and ReferenceEngine disagree
argument-hint: "(optional) focus area or query, e.g. \"NEAR with multi-token operands\" or a counterexample string"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Check guarantee 1 (exactness) for the current branch. Focus (if given): $ARGUMENTS

1. **Scope.** `git fetch origin dev`, then `git diff --name-only origin/dev...HEAD`. Print the changed
   files under `backend/src/openproceedings/query/`, `backend/src/openproceedings/engine/` and
   `backend/tests/`. If none changed and no focus was given, say so and stop.
2. **Spawn both in one message, in parallel:**
   - `exactness-guardian` (`.claude/agents/exactness-guardian.md`): review the diff range
     `origin/dev...HEAD` against `docs/specs/02-query-language.md` and `docs/specs/03-search-engine.md`,
     with a counterexample query for every Must.
   - `differential-tester` (`.claude/agents/differential-tester.md`): run `uv run pytest
     backend/tests/differential -q` at the CI profile, plus the nightly profile if the diff touches
     compile, tokenizer or oracle code. Extend the strategies to the node kinds the diff touches, and shrink
     every mismatch.
   Pass both the focus text above, if any.
3. **Cross-check.** Run every counterexample query from either agent through both engines:
   `op search --explain --engine tantivy "<q>" --ids` and `--engine reference`. Keep only the confirmed
   ones as counterexamples, and list the rest as unconfirmed suspicions.
4. **Report:**
   - the guardian's findings (Must / Should / Nit) and its verdict
   - examples run, seed and profile, and node kinds covered
   - confirmed counterexamples as `query · only-in-tantivy ids · only-in-reference ids · suspected compile
     row`
   - an overall verdict: **EXACT** (guardian APPROVE and 0 confirmed counterexamples) or **NOT EXACT**

This command does not replace `/review-gate` and records no approval. Fixes go through `index-engineer` or
`reference-oracle-keeper`, and then the normal closing workflow.
