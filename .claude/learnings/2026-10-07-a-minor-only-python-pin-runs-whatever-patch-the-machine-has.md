# A minor-only Python pin runs whatever patch the machine has, CVEs included

**Key lesson:** `.python-version` = `3.12` let uv run any 3.12 it found (3.12.9 here, with CVE-2025-6069 in `html.parser`); pin the exact patch release, hold `requires-python` at the first fixed patch, and prove a runtime upgrade changes no data by replaying the whole crawl cache under both interpreters and comparing the records byte for byte.

- **Date:** 2026-10-07 · **Task:** task-208 · **Area:** ops
- **Artifacts:** `.python-version`, `pyproject.toml`, `backend/pyproject.toml`, `uv.lock`, `deploy/api.Dockerfile`, `.github/dependabot.yml`, `backend/tests/unit/test_python_pin.py`, `backend/tests/unit/ingest/test_html.py`, spec 08 §Monorepo layout ("Python pin")

## What we set out to do
Move every Python pin to a release with the fix for CVE-2025-6069 (quadratic time in `HTMLParser` on malformed
input; every crawler parses pages with it), without changing the tokenizer, schema, Tantivy or any index.

## What we learned
- **Which releases hold the fix** comes from CPython itself, not from advisory aggregators: the backport PRs of
  python/cpython#135462 (#135483 for 3.12, #135482 for 3.13) give merge commits, and
  `gh api repos/python/cpython/compare/<commit>...v3.12.11` says `behind` while `...v3.12.12` says `ahead`. The
  first fixed releases are 3.12.12, 3.13.6 and 3.14.0. 3.13.5 does *not* have it: it was cut two days before the
  3.13 merge, though some advisories list it.
- **The minor-only pin was the gap.** With `3.12`, uv used the Homebrew 3.12.9 on this machine; a CI runner
  could use the image's system 3.12. The api image already ran 3.12.15 (its digest's `PYTHON_VERSION`, read from
  the registry's config blob), so only development and CI were exposed.
- **uv must know the release.** uv 0.11.18 (Homebrew) lists 3.12.13 at most; 3.12.15 arrived in uv 0.12.22
  ("Add CPython ... 3.12.15", its release notes). `uvx uv@0.12.23 python install 3.12.15` installs it without
  touching the system uv, and the older uv then finds the installed interpreter.
- **The fix changes parse output, not only speed.** At end of input, 3.12.12+ drops an unterminated construct
  that 3.12.9 emitted as text: `text_of("for all p<q we show")` is `for all p<q we show` on 3.12.9 and
  `for all p` on 3.12.15 (`x <a` → `x`, `tail <!-- c` → `tail`). Within a whole page a later `>` always exists, so
  the difference can only reach `text_of` fragments (`icml_sites.py`) and page tails.
- **It changed no record in today's corpus.** `crawl.replay_all` over an APFS clone of the cache (`cp -cR`,
  instant, so the real `data/` is never opened for writing) under 3.12.9 and 3.12.15: 168,181 records each,
  `cmp` identical. `tests.deploy.fixture_data` gives the same three `index_version`s, and `op index build` of one
  fixture snapshot gives identical segment bytes; only Tantivy's random segment names and the build time differ.
- **A timing test without a clock.** The regression test runs CPython's own pathological inputs (at n = 20,000)
  through `parse`, `text_of` and `metas`, after asserting the interpreter is a fixed release: a fixed parser takes
  milliseconds, and a vulnerable one fails the assertion at once instead of hanging for ~20 minutes, so no wall
  clock is read (testing-standards §Rules 5).

## Dead ends — don't repeat these
- `docker buildx imagetools inspect` hung for two minutes here; the registry API answers at once
  (`auth.docker.io/token`, then a `HEAD` on `/v2/library/python/manifests/<tag>` with the OCI index `Accept`
  header returns `docker-content-digest`).
- Computed `gh`/`git` arguments in a `for` loop are refused by the worktree-isolation guard: write each call out.

## Decisions (and what would change them)
- Stay on the 3.12 minor (security fixes until 2028-10) rather than move to 3.13/3.14: the CVE fix is in a 3.12
  patch, and a minor would move the ruff/mypy targets and every dependency's wheels in a security PR. A feature
  we need from a newer minor would reverse it.
- The api image's tag names the patch (`3.12.15-slim-bookworm`), so Dependabot's patch bumps arrive as PRs that
  fail `test_python_pin.py` until `.python-version` follows; minors are ignored there and done by hand.
- The EOF behaviour change is accepted as is, since it changed no record. If a future crawl's fragment ends in
  an unterminated `<x`, the text after it is dropped; whether `text_of` should keep it is an owner question.

## Follow-ups
- [ ] Owner question: should `html.text_of` keep text after an unterminated `<x` at a fragment's end (3.12.9's
  behaviour) rather than drop it (3.12.12+)? Today's corpus has none.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/python-standards/SKILL.md` (the exact pin and the floor);
  spec 08 §Monorepo layout ("Python pin") and §CI ("Dependabot"); `README.md` and `CONTRIBUTING.md` (uv 0.12.22+).
- Test or hook added? — `backend/tests/unit/test_python_pin.py` (pins agree; the interpreter has the fix) and
  `test_malformed_markup_parses_in_linear_time` in `backend/tests/unit/ingest/test_html.py`.
