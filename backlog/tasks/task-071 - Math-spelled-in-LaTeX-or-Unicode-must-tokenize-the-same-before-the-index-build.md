---
id: TASK-071
title: >-
  Math spelled in LaTeX or Unicode must tokenize the same (before the index
  build)
status: To Do
assignee: []
created_date: '2026-09-26 15:53'
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
- [ ] #1 Decision recorded (which spelling is canonical for Greek letters, operators, super/subscripts)
- [ ] #2 Every pair above tokenizes identically; golden rows for each; exhaustive and property suites green
- [ ] #3 TOKENIZER_VERSION bumped; spec 02 §Token semantics and the token-contract skill updated
<!-- AC:END -->
