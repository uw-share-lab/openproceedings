# A character-by-character tokenizer can keep raw offsets and still equal the whole-string definition

**Key lesson:** Pin an offset-tracking implementation to the simplest whole-string statement of the same rule with a Hypothesis property over an adversarial alphabet. Without that property, NFKC/casefold/NFD differences between one character and a sequence go unnoticed.

- **Date:** 2026-09-25 · **Task:** task-010 · **Area:** query
- **Artifacts:** `backend/src/openproceedings/query/normalize.py`, `backend/tests/golden/test_tokens.py` (132 rows),
  `backend/tests/unit/test_normalize.py` (`reference()`, `TRICKY_ALPHABET`)

## What we set out to do
Implement the token contract with a raw↔normalized offset map for highlights, plus 100 or more golden cases.

## What we learned
- **Offsets need the per-character route.** NFKC and casefold change lengths (`ﬁ`→`fi`, `ß`→`ss`, `½`→`1⁄2`),
  so tokens are built one raw character at a time and each token keeps the raw span it came from. A single
  raw character can yield two tokens (`½` → `1`, `2`) that share its span, so the span invariant is
  "starts never go backwards", not "spans are disjoint".
- **Two steps the contract didn't state, found by writing the golden table:**
  - NFC after dropping marks, or Korean `신뢰` comes out as loose jamo. NFC runs over the whole token
    at close, so jamo split across raw characters still compose.
  - Invisible format characters (soft hyphen, zero-width space and joiner) must *join*, or
    `bench­mark` splits into two words.
  - Spec 02 and the token-contract skill now state both.
- **Some golden rows record surprising but correct contract output.** "Drop combining marks" also removes
  the Devanagari virama (`विश्वास` → `विशवास`). That's harmless for exactness, because the query and index
  sides fold identically. The row records what the contract really does rather than what one might expect.
- **LaTeX by classifying characters, not rewriting text,** keeps positions intact: `\` and command names
  outside math become separators, and a command name inside math is a word. `\$` never toggles math.
- Hypothesis's default `st.text()` never produced a combining mark after a ligature. The adversarial
  alphabet (`TRICKY_ALPHABET`) does, and it passed at 50k examples.

## Dead ends — don't repeat these
- Don't write `\uXXXX` characters raw in a Python test file: ruff format and editors render them
  invisibly, and reviewers can't read the alphabet. Use escapes.

## Decisions (and what would change them)
- A CJK run is one token (no word segmentation). If reviewers need CJK recall, that is a TOKENIZER_VERSION
  bump plus a spec 02 change, not a quiet tweak.
- scholarmend and refaudit are pinned PyPI dependencies, added when each consuming task starts (019, 036,
  050); nothing vendored, and no sibling checkouts.

## Follow-ups
- [ ] task-011: the lexer, which uses `normalize()` for term tokens.

## Propagated to
- Spec 02 §Token semantics; `.claude/skills/token-contract/SKILL.md`; the ingestion and export agents,
  skills and specs now name the PyPI APIs.

## Addendum 2026-09-25 (round 3, task-010 close, task-001 decisions)
- **Every condition in a delimiter rule needs a row that fails without it.** The Pandoc `$` rule has four
  conditions (opener not before a space, closer not after a space, closer not before a digit, `\$` never
  closes). The first rows passed with any one of them deleted. Write each row by removing one condition and
  finding an input whose tokens change, then run that mutant against the suite.
- **A task in `backlog/completed/` can't be edited.** The CLI can't find it, and hand edits are gated. Check
  every number in `--final-summary` (count the golden rows by importing the table, not with grep) *before*
  running `backlog task complete`. task-010's summary says "190+ golden rows"; the real count is 176.
- **Check a decision against its own examples.** The first draft of decision-001 put the stem minimum on the
  last token, which would have rejected `gpt-4*`, the rule's own motivating example. It now counts the whole
  written stem.

## Corrections 2026-09-25 (M1 review gate)
- The bullet above saying the Devanagari virama is dropped (`विश्वास` → `विशवास`) describes the first draft.
  As built, marks are folded only on Latin, Greek, Cyrillic, Hebrew and Arabic bases, so
  `normalize("विश्वास") == ["विश्वास"]` (spec 02 §Token semantics).
- The artifacts line's "132 rows" is out of date: `test_tokens.py` has 176 golden rows.
