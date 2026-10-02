# A cap on combining marks must count what NFKD starts with, not only combining characters

**Key lesson:** To bound what NFKC's canonical reordering can cost, call a character a mark when its NFKD form starts with a non-zero combining class (all 922 combining characters in Unicode 15.0 plus U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F), and flag any trim by appending to the claim's evidence after what the source wrote, since `dedup.attribution` reads an RIS route and url from the evidence's first tokens.

- **Date:** 2026-10-02 · **Task:** task-155 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/caps.py`, `backend/tests/unit/ingest/test_caps.py`, decision-026, spec 01 §Pipeline 2

## What we set out to do
Bound the tokenizer's superlinear NFKC reordering on stored text (TASK-067's security review). The owner chose
8 marks per base character and 20,000-character abstracts, both trimmed and flagged, never silently.

## What we learned
- `unicodedata.combining(ch) != 0` misses five characters whose own class is 0 but whose NFKD form starts with a
  non-starter: U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F (an exhaustive scan of every code point). NFKC
  decomposes them before it reorders, so a run of them is a run of marks to the reordering. Testing NFKD's
  first character covers every combining character too (`test_every_combining_character_is_a_mark`).
- Only alternating classes are slow. `a` + (U+0301 U+0338) × 20k tokenized in 0.46 s against 0.12 s at 10k. A
  run of a single kind, or U+0F73 alternating with U+0301, stayed linear (0.03 s → 0.06 s). The capped worst
  case, 8 alternating marks on every base over 20,000 characters, tokenized in about 0.02 s.
- The RIS importer reorders marks (NFC) before any cap runs, so a test of a trimmed RIS abstract should assert
  how many marks are kept and where, not their order.
- A record and its claims must be trimmed by the same function, before dedup. Then the record's text still
  equals one claim's value (`dedup.abstract_claim` matches by equality), and the attribution survives the trim.
- Adding a manifest key only when it is non-empty (as `withheld` does) keeps a corpus within the caps
  byte-identical. That covers `records.jsonl`, the hash and the manifest's keys.

## Dead ends — don't repeat these
- Ending a run at every non-mark character. The tokenizer drops invisible characters and LaTeX `\-` and joins
  the word across them, so 8-mark runs split by U+200D, U+FE00, U+034F, U+00AD, U+20DD or `\-` reach NFC as
  one run. The security review measured 1.3 s for a 72k title, growing about 4x per doubling. A run must end
  only at a letter or digit. Test the invariant on the tokens (no token holds more than 2 × 8 + 2
  non-starters), not on the raw text.
- Benchmarking the worst case with a Latin base and U+0338. Latin marks fold away and the slash takes the
  short cluster path, so it measures nearly the cheapest input. Use a base whose marks are kept (Thai) and
  classes 220/230.
- Prefixing the note to the evidence. An RIS abstract's evidence is `scholarmend:proceedings_page <url> …`, and
  `attribution` takes the page from the token after the route. The note goes last, in parentheses.

## Decisions (and what would change them)
- A run ends only at a letter or digit, so marks after a space or punctuation are capped with the run before.
  It is stricter than "per base character", and real text (longest run 1) never needs more. Revisit if a script
  legitimately stacks marks after punctuation.
- The caps apply to the title (marks only) and the abstract (marks and length), the two tokenized and
  highlighted fields. Authors and keywords are neither, so they are not capped. Revisit if a field becomes
  searchable.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` (the ingest caps),
  `.claude/skills/snapshots/SKILL.md` (manifest `trimmed`), `CLAUDE.md` layout (`caps.py`), spec 01, decision-026
- Test or hook added? — `backend/tests/unit/ingest/test_caps.py` (an exhaustive mark-class check, both caps,
  the flags, a snapshot build, a CPU-time budget)
