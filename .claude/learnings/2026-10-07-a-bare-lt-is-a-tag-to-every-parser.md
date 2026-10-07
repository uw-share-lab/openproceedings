# A bare `<` in an abstract is a tag to every HTML parser, and an unclosed one can pull page chrome in

**Key lesson:** A stdlib `HTMLParser` (on any release) reads `<` + letter as a tag, so maths such as `if a < b and c > d` written without spaces lost its words, and an unclosed bogus element (a `<p` directly followed by `<\infty`) swallowed the rest of the page into the abstract. Decide "is this a real tag?" before the parser runs, with a linear, version-independent pre-pass (known element name, `>`-terminated, an attribute value or only HTML attribute names), then prove it by replaying the whole crawl cache old vs new and reading every changed record by hand.

- **Date:** 2026-10-07 · **Task:** task-209, task-210 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/html.py` (`escape_bare_lt`), `backend/tests/unit/ingest/test_html.py`, `backend/tests/fixtures/http/{neurips/2024/abstract-bare-lt.json,pmlr/v202/paper-bare-lt.json}`, `docs/results/2026-10-07-bare-lt.md` (+ its `-check.py`), spec 01 §Pipeline step 2, spec 08 "Python pin"

## What we set out to do
Keep the text after a bare `<` in abstracts on every crawler (TASK-209), and measure the effect on the corpus.

## What we learned
- **The damage was bigger than lost words.** Of the 41 records the replay changed, 6 PMLR abstracts (ICML
  2021–2024) had stopped at the bare `<` and then gone on with the page's "Cite this Paper / BibTeX / Endnote"
  block, because the bogus element never closed and swallowed the abstract's closing `</div>`. The old snapshot had
  `Cite this Paper` in 6 records; the new one in none (evidence: `docs/results/2026-10-07-bare-lt.md`).
- **"Known element name" alone isn't enough**: `if a<b and c>d` uses `b`, a real element. Requiring an attribute
  value, or only HTML attribute names when there is none, separates prose (`and`, `c`) from legacy markup. The
  first version allowed only HTML's boolean attributes and broke a CyberChair-shaped test page's `<table border>`
  (`test_dblp.py`): valueless legacy attributes are any attribute name, not only booleans.
- **A pre-pass is version-independent; parser hooks are not.** Escaping `<` to `&lt;` before the parser keeps
  3.12.9 and 3.12.15 byte-identical over the whole cache, and the cross-release fuzz differences left are all `<!`
  constructs (TASK-208's list); the `</script` and `<?` ones went away too.
- **An atomic group isn't enough; every run must be possessive.** Stopping each tag match at the next `<` outside a
  quoted value and making the attribute run atomic (`(?>…)`) still left the tag *name* free to give characters
  back, and on each give-back the attribute run rescanned the rest of the input: `"<a" + "\xa0x" * n` took 0.8 s at
  n = 2,000 and 3.4 s at 4,000 (the focused reviewer's CPU-growth probe; my output-only "linear" test at n = 20,000
  never saw it, since `" x"`-shaped inputs ended early). Possessive runs (`*+`, Python 3.11+) on the name, the
  attribute name and value, and the end tag's body fix it; `test_escape_bare_lt_is_linear` is a paired CPU-growth
  check (testing-standards §CPU growth checks) that fails on the old regex (ratio ~16) and passes now (~2.5).
- **Copying real markup unchanged** makes "no bare `<`, no change" checkable: every committed proceedings fixture
  page is byte-identical after the escape (a test), so the change can only touch pages that have the bug.

## Dead ends — don't repeat these
- `op eval …` on a command line is refused by the worktree-isolation guard (it matches the word `eval`); a wrapper
  script would get around it, which the rules forbid: ask the maintainer to run it.
- `multiprocessing` spawn re-imports the running script: a wrapper that reads `sys.argv[1]` at import breaks
  `op index build`'s workers. Put the source path in an environment variable and the work under `__main__`.

## Decisions (and what would change them)
- `a<b>c` stays bold markup (`ac`), as a browser shows it → telling it from maths needs context no parser has; a
  reviewer finding such an abstract in the corpus would reopen it.
- Fixtures: real cached page structure, scrubbed (decision-004), with synthetic abstracts carrying the real shapes.

## Follow-ups
- none

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: spec 01 §Pipeline step 2 and spec 08 "Python pin" state the rule; the
  html.py docstring lists it with the other reading rules.
- Test or hook added? — `backend/tests/unit/ingest/test_html.py` (bare-`<` rows, real-tag rows, fixture pages,
  linear time, every committed page unchanged).
