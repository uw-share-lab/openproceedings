---
id: TASK-027
title: Highlights from the AST with code-point spans over raw text
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:55'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Highlights, spec 04 span units.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Spans are half-open code points over the raw stored field, via the normalize offset map
- [x] #2 Phrase spans and expanded wildcard terms highlighted exactly; nothing else
- [x] #3 Astral-plane character golden case
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented engine/highlight.py: highlights(ast, record, expansions) evaluates the AST on one record over tokenize's offset map (half-open code points over the raw stored field). A term or expanded wildcard term lights each matching token; a phrase lights one span per occurrence; NEAR lights the operand occurrences in a pair within the distance; AND its children; OR only matching children; NOT and filters nothing. A node that doesn't match has no spans (enforced once in node()), so a branch that didn't match lights nothing. Overlaps merge. LaTeX commands light their name (tokenize's offsets exclude the backslash). Tests: the highlighter's verdict == ReferenceEngine membership on all 200 records for the 44 golden queries (spans in bounds, sorted, disjoint, each covering a real token); an astral-plane title (emoji + NFKC-mapped math letters) in code points; phrase spans; wildcard (* and $) expansions only; unmatched OR branches and a true NOT light nothing; NEAR pairs only, either order; fielded terms; overlap merge; LaTeX. Mutants 6/7 killed; the survivor (NOT returning its child's spans) is equivalent: a true NOT has a false child, which has no spans.
<!-- SECTION:NOTES:END -->
