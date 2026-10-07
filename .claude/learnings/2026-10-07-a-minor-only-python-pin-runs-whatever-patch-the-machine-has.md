# A minor-only Python pin runs whatever patch the machine has, CVEs included

**Key lesson:** `.python-version` = `3.12` let uv run any 3.12 it found (3.12.9 here, with CVE-2025-6069 in `html.parser`); pin the exact patch release, hold `requires-python` at the first fixed patch, prove a runtime upgrade changes no data by replaying the whole crawl cache under both interpreters byte for byte, and fuzz the HTML layer across the two releases, because a CVE fix can change what the parser reads, not only how fast.

- **Date:** 2026-10-07 · **Task:** task-208 · **Area:** ops
- **Artifacts:** `.python-version`, `pyproject.toml`, `backend/pyproject.toml`, `uv.lock`, `deploy/api.Dockerfile`, `.github/dependabot.yml`, `backend/tests/unit/test_python_pin.py`, `backend/tests/unit/ingest/test_html.py`, `backend/src/openproceedings/ingest/sources/html.py`, spec 08 §Monorepo layout ("Python pin"), `docs/results/2026-10-07-python-upgrade.md` (+ its `-check.py`)

## What we set out to do
Move every Python pin to a release with the fix for CVE-2025-6069 (quadratic time in `HTMLParser` on malformed
input; every crawler parses pages with it), without changing the tokenizer, schema, Tantivy or any index.

## What we learned
- **Which releases hold the fix** comes from CPython itself, not from advisory aggregators: the backport PRs of
  CPython issue #135462 (PRs #135483 for 3.12, #135482 for 3.13) give merge commits, and
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
- **Keeping a `>`-free tail as text makes the two releases agree there, and stays linear.** `feed` leaves the
  unfinished end in `rawdata`; handing a tail with no `>` to `handle_data` before `close` (`html._feed_all`) gave
  output identical to the old code on 3.12.9 over 200,000 seeded malformed strings (a seeded fuzz of `text_of`,
  `parse`/`node_text` and `metas`, run under each interpreter from a copy of each `html.py`). Emitting *every*
  tail as text was wrong: an unterminated `<!--` before later markup leaked the tags into the text. Emulating
  3.12.9 exactly is impossible without its quadratic re-scan, which was the CVE.
- **The fix series also widened raw text, and my first fuzz couldn't see it.** 3.12.12+ reads `title`,
  `textarea`, `xmp`, `iframe`, `noembed`, `noframes` and `plaintext` bodies as raw text: one unclosed `<title>`
  turns a listing's later rows into literal text and hides a later `citation_title` meta (the dedup auditor
  found it by diffing the two stdlib `html/parser.py` files). My fuzz atoms had none of those tags, so it reported
  "only comments". Overriding `set_cdata_mode` to pass only `script` and `style` (`_RawTextParser`) restores
  3.12.9's reading; with those tags added to the atoms, old code on 3.12.15 differs from 3.12.9 on 61 % of
  strings, the new code on 20 %, nearly all through `<!` constructs (a tail with a `>`, `<!-->`, `--!>`), and
  the new code on 3.12.9 on none. Read the stdlib diff before trusting a fuzz's alphabet.
- **The bundled expat moved too** (2.7.1 → 2.8.5, which `dblp_xml.py` parses dblp's release with); the dblp
  replay was identical.
- **It changed no record in today's corpus.** `crawl.replay_all` over an APFS clone of the cache (`cp -cR`,
  instant, so the real `data/` is never opened for writing) under 3.12.9 (old code) and 3.12.15 (old and final code): 168,181
  records each, `cmp` identical. `tests.deploy.fixture_data` gives the same three `index_version`s, and `op index build` of one
  fixture snapshot gives identical segment bytes; only Tantivy's random segment names and the build time differ.
- **A timing test without a clock.** The regression test runs CPython's own pathological inputs (at n = 20,000)
  through `parse`, `text_of` and `metas`, plus two tails with a `>` that do reach `close`, after asserting the
  interpreter is a fixed release: a fixed parser takes milliseconds, and a vulnerable one fails the assertion at
  once (without it, the two `close` inputs would take about 8 s each on 3.12.9), so no wall clock is read
  (testing-standards §Rules 5).

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
- A `>`-free tail stays text (`_feed_all`) rather than following 3.12.12+'s drop: the focused review found the
  pre-2013 ICML pages are sliced into tag-free fragments (`icml_sites.py`) where `p<q` can end the input, and
  dropping the words after it would be silent loss. A reason to follow the HTML5 reading instead (say, a page
  whose tail is markup without a `>`) would reverse it. Likewise raw text stays `script`/`style` only.
- No `python_version` in the snapshot manifest: the exact pin plus the manifest's `openproceedings_version`
  (whose tag pins `.python-version`) already name the interpreter, and the field would make snapshot bytes
  depend on the build host. Raised with the owner.

## Follow-ups
- [ ] Owner (reported, not filed: task ids are created by the main session) — text between a bare `<` and a later
  `>` is dropped on every release (`if a<b and c>d then` → `if ad then`): a pre-existing loss of abstract words,
  found by the review-methodologist.
- [ ] Owner — record the interpreter in the snapshot manifest after all? (Decision above.)
- The remaining 3.12.12+ readings change no record today; a crawl that meets one shows up in `op snapshot diff`.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/python-standards/SKILL.md` (the exact pin and the floor);
  spec 08 §Monorepo layout ("Python pin"), §CI ("Dependabot") and §Deploy (the python tag; the registry `HEAD`);
  spec 01 §Normalize; `README.md` and `CONTRIBUTING.md` (uv 0.12.22+); `deploy/README.md` and the
  `api.Dockerfile` comment; the `html.py` docstring.
- Test or hook added? — `backend/tests/unit/test_python_pin.py` (pins agree; the interpreter has the fix) and
  `test_malformed_markup_parses_in_linear_time`, `test_text_is_read_as_on_3_12_9`,
  `test_an_unclosed_raw_text_tag_does_not_swallow_the_rows_after_it` and
  `test_the_readings_left_to_the_pinned_parser` in `backend/tests/unit/ingest/test_html.py`.
