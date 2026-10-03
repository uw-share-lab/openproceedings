# A workspace member synced before its source existed installs as an empty package

**Key lesson:** If `uv sync` runs while a workspace member's `src/` is still empty, the editable install records nothing and imports fail even after you add the code. Run `uv sync --reinstall-package <name>` once the package has source files.

- **Date:** 2026-09-25 · **Task:** task-009 · **Area:** tooling
- **Artifacts:** `backend/pyproject.toml`, root `pyproject.toml` (`members = ["backend"]`), `backend/src/openproceedings/{cli,logs,diagnostics}.py`

## What we set out to do
Stand up the backend package as the first uv workspace member, with the `op` CLI stubs, JSON logging and the
diagnostics registry, test-first.

## What we learned
- **Empty editable install.** I wrote the tests, then `pyproject.toml`, then ran `uv lock && uv sync` to see
  the tests fail. They did fail (correct), but even after the modules existed, `import openproceedings` still
  failed: `site-packages` had `openproceedings-0.0.0.dist-info` and no `.pth`. hatchling had built the
  editable wheel from an empty `src/openproceedings`. `uv sync --locked --reinstall-package
  openproceedings` fixed it. For TDD on a brand-new package, create the package's `__init__.py` before the
  first sync.
- **The root must depend on its members for `uv sync` to install them.** A workspace root with
  `package = false` needs `dependencies = ["openproceedings"]` plus `[tool.uv.sources] openproceedings =
  { workspace = true }`. Listing it under `members` alone doesn't install it.
- **ruff B039:** a `ContextVar` default must be immutable. `types.MappingProxyType({})` states the intent,
  even though the code never mutated the `{}`.
- `.python-version` pins 3.12. Without it, uv picked the machine's CPython 3.14, not the spec's 3.12.

## Dead ends — don't repeat these
- Don't debug "No module named openproceedings" by editing `sys.path` or `mypy_path`. Check for the
  `.pth` in `site-packages` first.

## Decisions (and what would change them)
- argparse, not click/typer, for `op`: no dependency, and mypy-strict friendly. If subcommands grow complex
  option sets in M2 (search/export), revisit in a decision record.

## Follow-ups
- [ ] task-010: normalize.py and the golden token table (next in M1).

## Propagated to
- `CONTRIBUTING.md` (Python pin, `uv run pytest`); `CLAUDE.md` layout. No skill change: `python-standards`
  already covers the workspace layout.
