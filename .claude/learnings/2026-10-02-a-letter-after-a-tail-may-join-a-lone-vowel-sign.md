# A letter after a tail is a word of its own, but that word can start with a lone vowel sign

**Key lesson:** When a tokenizer property fails, run the example through the tokenizer, the whole-string `reference()` and the frozen pre-088 loop first. If all three agree, the property's oracle is wrong: here "a letter after a tail is exactly `x`" forgot that a marks-only run makes no token alone but starts a word with the next letter.

- **Date:** 2026-10-02 · **Task:** n/a (nightly property failure) · **Area:** query
- **Artifacts:** `backend/tests/unit/test_normalize.py` (`test_tail_says_whether_a_letter_after_the_text_joins_its_last_word`),
  `backend/tests/golden/test_tokens.py`

## What we set out to do
Triage the nightly falsifying example `text='ೢ'` (KANNADA VOWEL SIGN VOCALIC L): `normalize('ೢx')`
is `['ೢx']`, but the property expected `['x']`.

## What we learned
- U+0CE2 is category Mn with **combining class 0**, so `unicodedata.combining()` is 0. By step 5 of the
  contract it is a non-combining mark, so it is a word character, and the "stray mark with no base is dropped" rule
  (combining marks only) doesn't apply to it. Alone, it is a marks-only word, which `close()` drops. With a
  letter after it, it is part of the word `ೢx`. The tokenizer, `reference()` and
  `tests/unit/tokenize_before_088.py` all give `['ೢx']`, so TASK-088 didn't change this, and
  TOKENIZER_VERSION stays at 2.
- The `Tail` is right for its one consumer: the lexer rejects `ೢ*` because the stem is too short, and
  rejects `abcd-ೢ*` as detached (its tail is still `-`).
- The same over-strict oracle would also have failed on `abcd-ೢ` (tail `-`, then `['abcd', 'ೢx']`).
  Hypothesis just hadn't generated that case yet.

## Dead ends — don't repeat these
- Don't treat every `Mn` character as a combining mark. Check `unicodedata.combining(c)`: Indic vowel signs
  such as U+0CE2 and U+093F are Mn or Mc with class 0, so they are word characters.

## Decisions (and what would change them)
- We fixed the oracle, not the tokenizer. The new check is that the earlier tokens are unchanged and that the
  new last word is `x` after zero or more marks, the first of class 0. Dropping a leading class-0 vowel sign would need a
  TOKENIZER_VERSION bump and a spec 02 change.

## Follow-ups
- None (no tokenizer change).

## Propagated to
- Test: explicit `@example`s and `Tail` rows in `test_normalize.py`; golden rows `ೢ`, `ೢx` and
  `abcd-ೢx` in `test_tokens.py`.
- Wording: "a stray mark with no base is dropped" read as covering class-0 vowel signs, which is the misreading
  behind the oracle. The token-contract skill (step 3), spec 02 §Token semantics step 2 and the `normalize.py`
  docstring now say stray *combining* marks (class ≠ 0), and that a letter after a lone vowel sign joins it.
- Lexer and parser rows: `\u0ce2*` (stem too short) in `test_lexer.py`, `abcd-\u0ce2*` (detached) in `test_parser.py`.
- Oracle: the new word's marks-only head must start on a class-0 mark, with `@example("abc-\u0301")`, so a
  stray combining mark that stopped being dropped would still fail.
