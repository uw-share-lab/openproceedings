---
id: decision-027
title: >-
  A filter value glued to a following parenthesis is refused like a glued word;
  a closing parenthesis glued to a field prefix stays accepted; QUERY_VERSION
  stays 2 (TASK-158)
date: '2026-10-02 04:13'
status: accepted
---
## Context

Spec 02 §Grammar refuses a parenthesis glued to a word or phrase (`model(s)`, `"a"(b)`:
`PARSE_PAREN_TOUCHES_WORD`), because the glued parenthesis silently splits the query into an AND. Its
§Filter clauses caps paragraph relies on that for filter values (a bare `track:workshop(x OR y)` "would be
`PARSE_PAREN_TOUCHES_WORD`"). The lexer applied it to WORD and PHRASE lexemes only, so a full year range,
lexed as a RANGE, was exempt: `year:2020..2022(x)` parsed as `x AND year:2020..2022` while `year:2021(x)`,
`venue:iclr(x)`, `track:main(x)` and `title:y(x)` were refused. On the `)` side every field prefix was
accepted (`(x)year:2021`, `(x)title:y`) while a following word or phrase (`(x)y`, `(x)"a"`) was refused
(TASK-153 review deferral, TASK-158).

Options: (a) refuse a filter clause glued to a parenthesis on both sides; (b) refuse a value glued to a
following `(` whatever its form, and keep a `)` glued to a field prefix accepted; (c) list the glued forms
that are accepted, leaving the range exempt.

(a) was implemented first and failed the facet-click property: a click splices `field:(…)` over a clause's
span, and that span can follow a `)` directly. The real Trust-Evals strings do this
(`…"evaluation framework")(source:ICLR OR source:ICML OR …)`): the venue splice writes
`…)venue:(ICLR)`, which (a) refuses, so the clause could no longer be edited; `year:(2019)status:accepted`
lost its year edit the same way. (c) keeps a rule that depends on how a value is lexed, which no reader can
see.

## Decision

(b). A `(` glued to a preceding word, phrase or range is `PARSE_PAREN_TOUCHES_WORD`, so every filter value is
treated alike (`year:2020..2022(x)` is refused like `year:2021(x)`, and so is a value inside its group,
`year:(2021(x))`, with one error, not also `FIELD_FILTER_SYNTAX`). When the glued term is a filter field's
value the message names the field and value and how to fix it with a query that parses: a space before the
`(` or a group of values for a bare value (without rewriting the clause of a negated one, which would drop
its `-`), and closing the group first for a value inside `field:(…)`, where a space would leave a malformed
group;
a text field's word (`title:model(s)`) keeps the plural hint. A `)` glued to a
following field prefix stays accepted: a field name ends at its `:`, so nothing is split, and `(x)year:2021`
can only mean `x AND year:2021`. A group glued to a group (`year:(2021)(x)`, `(a)(b)`) splits no value either
and stays accepted.

Two diagnostics that went with it: a glued parenthesis no longer hides the value's own check, so
`year:..2022(x)` and `year:2020..(x)` report `FIELD_UNKNOWN_VALUE` on the value as well as the glue
(the parser's "already reported?" check ignores the glue error for a filter value); and a filter field's
value (bare, negated, in its group, or nested in it) no longer gets the warnings about how text is searched:
`WARN_SYMBOLS_DROPPED` (`year:..2022` read as the search word `2022`), `WARN_CJK_RUN`, `WARN_SPELLED_GREEK`
(already skipped for a bare value) and a logic sign's `WARN_LOOKALIKE_OPERATOR`. Each such value is refused by
its own value check anyway.

**`QUERY_VERSION` stays `"2"`.** decision-003 puts it in `canonical_hash` so that one canonical string with
two meanings gets two hashes, and decision-008 bumped it because an accepted query's own canonical string
could be refused on replay. Here no canonical string changes meaning or acceptance: the canonical form joins
clauses with ` AND ` and never writes a value directly before `(`, so every stored `canonical` and
`identification_query` re-parses exactly as before, and a saved search replays `reproduced`. Only typed input
with a full range `a..b` glued to a following `(` that used to parse is now refused.
Bumping would change every hash and make every saved record replay `drifted` for no change in meaning.

## Consequences

- Newly refused: a typed query with a full range glued to a following `(` (`year:2020..2022(x)`). Its fix,
  `year:2020..2022 (x)`, gives the canonical string it gave before.
- A record saved before this change from such a typed query keeps that text as its `input`, which the record
  page shows ("Copy the query as typed") and the methods text quotes ("The input as typed was …"). Pasted
  back, that input is now refused; the canonical and identification strings the record cites beside it still
  parse, re-run with the same hash and replay `reproduced`, and adding the space gives the same canonical
  string. Nothing has been released, and the project's data directory holds no records store (checked
  2026-10-02), so no saved record has such an input.
- Still accepted: `(x)year:2021`, `(x)venue:iclr`, `(x)title:y`, `(x)track:main`, `year:(2021)(x)`.
- No canonical string, hash or token changes; `TOKENIZER_VERSION` and `QUERY_VERSION` stay `"2"`.
- Pinned by `test_parser.py::test_a_parenthesis_glued_to_a_filter_clause` (both modes),
  `test_a_spaced_or_accepted_glued_clause_has_a_canonical_string_that_replays`,
  `test_an_open_year_range_value_is_refused_without_a_text_warning` and rows in `test_lexer.py`; the
  facet-click properties (`test_clauses.py`) and the frontend lexer golden (regenerated) still pass.
- Spec 02 (§Grammar, §Filter clauses, §Error handling), `lexer.py`'s docstring and the `query-grammar` skill
  say so.
