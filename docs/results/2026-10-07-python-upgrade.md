# Python 3.12.9 → 3.12.15: ingest output and index bytes (TASK-208)

The upgrade fixes CVE-2025-6069 (quadratic time in `html.parser.HTMLParser`, CPython issue #135462). These runs
check that it changes no record and no index, and measure where the new parser reads malformed markup
differently. Machine: Apple M1 Pro, macOS 15 (Darwin 24.6). Interpreters: Homebrew CPython 3.12.9 and uv's
CPython 3.12.15 (python-build-standalone 20261001), each with this branch's locked environment (`uv sync
--locked`). "Old code" is `ingest/sources/html.py` at `dc05f6de` (origin/dev); "new code" is this branch's.
The commands use [the committed script](2026-10-07-python-upgrade-check.py); no query text or abstracts are
recorded here.

| Check | Result |
| --- | --- |
| Crawl cache replayed (`crawl.replay_all`, 55,292 cached files, all seven sources) | 168,181 records under each |
| Old code on 3.12.9 vs new code on 3.12.15 (also old code on 3.12.15) | byte-identical (`cmp`; sha256 `d0cdab2d30420654…`) |
| `tests.deploy.fixture_data` under each interpreter | the same three `index_version`s: `1124992660a9`, `6f8ef960d9bd`, `924b0d2c95bf` |
| `op index build --snapshot small` under each | `6f8ef960d9bd` both; every segment file's sha256 equal; only Tantivy's random segment names, `meta.json`, `.managed.json` and `manifest.json` (`built_at`, `build_ms`, the names) differ |
| Fuzz, 200,000 seeded malformed strings (seed 7), new code on 3.12.9 vs old code on 3.12.9 | 0 differ (`text_of`, `node_text(parse(…))`, `metas`) |
| The same, old code on 3.12.15 vs old code on 3.12.9 | 121,156 differ (61 %) |
| The same, new code on 3.12.15 vs old code on 3.12.9 | 39,845 differ (20 %): 39,816 involve a `<!` construct (comment, `<![CDATA[`, declaration, `--!>`), 1 a `</script>`, 1 a `<?` |
| CPython's regression inputs (n = 20,000), all four entry points, new code on 3.12.15 | 0.08 s; the two inputs whose tail holds a `>` (`<!--x>` repeated) cost 0.14 s at n = 3,000 on 3.12.9 and grow with n² |

What the new code keeps as 3.12.9 had it: an unterminated tail with no `>` stays text (`_feed_all`; 3.12.12+'s
`close` drops it), and only `script` and `style` bodies are raw text (`_RawTextParser`; 3.12.12+ adds `title`,
`textarea`, `xmp`, `iframe`, `noembed`, `noframes` and `plaintext`). The fuzz's atoms include those tags. What
still differs is left to the pinned parser and listed in spec 08 §Monorepo layout ("Python pin"); today's cache
meets none of it.

To reproduce, clone the cache (`cp -cR data/cache <scratch>/cache`: an APFS clone, so `data/` is only read) and
build one environment per interpreter (`UV_PROJECT_ENVIRONMENT=<scratch>/venv-3129 uv sync --locked --python
/opt/homebrew/bin/python3.12`, and the same with `--python 3.12.15`). Then, from `<scratch>`, with each
environment's `python -I`:

```sh
python -I 2026-10-07-python-upgrade-check.py replay cache rec-<interpreter>.jsonl
python -I 2026-10-07-python-upgrade-check.py fuzz <old or new html.py> fuzz-<code>-<interpreter>.jsonl 7 200000
cmp rec-3129.jsonl rec-31215.jsonl
PYTHONPATH=backend python -m tests.deploy.fixture_data <empty dir>   # from the repository root
op --data-dir <that dir> index build --snapshot small --out <out dir>
```

The old `html.py` is `git show dc05f6de:backend/src/openproceedings/ingest/sources/html.py`.
