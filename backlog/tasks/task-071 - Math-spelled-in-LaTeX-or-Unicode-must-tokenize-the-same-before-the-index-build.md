---
id: TASK-071
title: >-
  Math spelled in LaTeX or Unicode must tokenize the same (before the index
  build)
status: In Progress
assignee: []
created_date: '2026-09-26 15:53'
updated_date: '2026-09-26 17:03'
labels:
  - query
  - exactness
milestone: m-2
dependencies: []
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-09-26 while checking OpenReview vs PMLR abstracts (another session's comparison: OR '5.7×' vs PMLR '5.7$\times$'). The token contract gives different tokens for the same math: '5.7×' -> 5 7 but '5.7$\times$' -> 5 7 times; '$\leq$' -> leq but '≤' -> nothing; '$\alpha$-DP' -> alpha dp but 'α-DP' -> α dp; '$O(n^2)$' -> o n 2 but 'O(n²)' -> o n2. A query for alpha misses abstracts that write α, whichever source they came from. Needs a decision (which spelling is the token) and a TOKENIZER_VERSION bump, so it must land before task-023 builds an index. Recommendation to put to the review lead: map LaTeX math commands to their Unicode characters before tokenizing (Greek letters -> the Greek letter token; operators and relations such as \times, \cdot, \leq, \to -> symbols, i.e. separators), and fold a lone Greek letter both ways? (decide), keeping superscript digits as separate tokens.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision recorded (which spelling is canonical for Greek letters, operators, super/subscripts)
- [x] #2 Every pair above tokenizes identically; golden rows for each; exhaustive and property suites green
- [x] #3 TOKENIZER_VERSION bumped; spec 02 §Token semantics and the token-contract skill updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User decision 2026-09-26 (asked with previews): (1) Greek letters: canonical token is the Unicode letter; $\alpha$ and α both -> α; a query must contain α (typing alpha finds only the spelled word). (2) Operators and relations: spelled tokens; × and $\times$ both -> times, ≤ and $\leq$ -> leq, etc. Spelling = the LaTeX command name; the full symbol<->command table goes in the decision record for the user to check, flagging collisions with ordinary words (∈ -> in, times). (3) Super/subscripts: joined; O(n²) and $O(n^2)$ both -> o n2 (NFKC reading), so a query for n doesn't match n². Record as a decision (backlog decision), implement with a TOKENIZER_VERSION bump before task-023.

Implemented (decision-006, TOKENIZER_VERSION 2): query/mathsyms.py holds the Greek and operator tables; normalize.py maps Greek commands in math to the letter (SUB mask state), operator commands and Unicode operators to the LaTeX name as a token of their own, and joins ^/_ before one letter/digit or a braced run. Golden rows pin every pair both ways; the whole-string reference models operators; exhaustive (OP_EXHAUSTIVE=1) and property suites green; Trust-Evals canonical hashes regenerated (strings unchanged).
<!-- SECTION:NOTES:END -->
