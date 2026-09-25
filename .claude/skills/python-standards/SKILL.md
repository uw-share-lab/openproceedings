---
name: python-standards
description: The backend Python standard for openproceedings — Python 3.12 with the root uv workspace, ruff + ruff-format (configured once in the root pyproject.toml, applied by the autofix hook and make fmt/lint), mypy --strict, pydantic v2 models as contracts, pure functions in query/ and engine/, no module-level mutable state, typed exceptions mapped to Diagnostics in the diagnostics.py registry, and logging per logging-standards. Use when writing or reviewing any code under backend/, adding a dependency, or fixing a lint/type failure in CI.
---

# Python standards (backend/)

## Toolchain — uv workspace only
- The root `pyproject.toml` is the **uv workspace root** (dev group: ruff, mypy); `backend/` joins as a
  member in M1. One `uv.lock`, at the root.
- `uv sync` **at the repo root** to install every member and the dev tools into one `.venv`; `uv run <cmd>`
  to run (`uv run pytest`, `uv run op search …`); `uv add <pkg>` (in the member) / `uv add --dev <pkg>` to
  add deps. Never `pip install` into the workspace, never a hand-edited lock. `uv.lock` is committed and a
  lockfile or `pyproject.toml` change routes to `security-reviewer` and `qa-auditor`.
- Python **3.12**. Use `type X = …` aliases, `StrEnum`, `match` where it clarifies AST dispatch.
- Ruff's configuration lives **only** in the root `pyproject.toml`; members inherit it. No per-package
  ruff sections without a recorded decision (`.claude/skills/autolint/SKILL.md`).
- `autofix.sh` (PostToolUse) runs `ruff format` and `ruff check --fix` on each file as it's edited and
  reports what remains. `make fmt` fixes the whole repo.
- CI `lint` runs `make lint`: `ruff format --check`, `ruff check`, and `mypy --strict backend/src` (once it
  exists). Run `make lint` locally before committing; `.githooks/pre-push` runs it too.

## Typing
- `mypy --strict` with no blanket ignores. A `# type: ignore[code]` needs the specific code and a comment
  saying why (usually an untyped third-party API such as `tantivy`; wrap it once in a typed adapter inside
  `engine/tantivy_engine.py` rather than scattering ignores).
- No `Any` in public signatures. Prefer `Sequence`/`Mapping` for parameters, concrete types for returns.
- `frozenset[str]` for ID sets (`match_ids`) — sets are the unit of correctness here.

## pydantic v2
- Models in `api/` and the record schema (`PaperRecord`) are the contract; OpenAPI and the TS types are
  generated from them. Changing a field is an API change (`api-contract-reviewer`).
- v2 API only: `model_validate`, `model_dump`, `model_config = ConfigDict(frozen=True, extra="forbid")`,
  `Field(...)`, `@field_validator`. No v1 `parse_obj`, `.dict()`, `class Config`.
- AST nodes are a discriminated union (`Field(discriminator="kind")`), frozen, hashable.

## Purity and state
- `query/` and `engine/` are **pure**: no network, no clock, no environment reads, no randomness. Inputs in,
  values out. That is what makes `parse(canonical).canonical == canonical` and determinism testable.
- No module-level mutable state: no global index, cache dict or config singleton. The API loads the index
  once at startup into app state and passes the `Engine` in; the CLI builds it explicitly. Hot-swap is an
  atomic pointer swap on app state (spec 04).
- Constants that affect results (`TOKENIZER_VERSION`, `SCHEMA_VERSION`, ranking params) are defined once and
  folded into `index_version` (03 §Versioning).
- Ingestion I/O stays in `ingest/sources/`; everything downstream of the cache is a pure transform.

## Errors
- A typed hierarchy per area (e.g. `QueryError`, `IngestError`, `EngineError`; never names that shadow
  builtins such as `IndexError`), each carrying a code from the registry in
  `backend/src/openproceedings/diagnostics.py` (`error-diagnostics`).
- User-facing problems are **values** (`Diagnostic` in `ParseResult.errors`), not exceptions: the parser
  never raises on bad input.
- Never bare `except:` or `except Exception: pass`. Catch the narrowest type, add context, re-raise or
  convert to a Diagnostic. A swallowed error in ingestion becomes a silent coverage gap.
- Unknown values stay `unknown` and are logged; never guessed (01 §Error handling).

## Logging
Follow `.claude/skills/logging-standards/SKILL.md`. In short: stdlib `logging` with one JSON formatter,
configured **only** in `backend/src/openproceedings/logs.py` (called by `cli.py` and API startup; library
code never configures logging); `log = logging.getLogger(__name__)` per module; `event` constants with
structured fields; one INFO line per unit of work, no per-record INFO. **Never log raw query text by
default** (unpublished review designs), abstracts, credentials or personal data. No `print` outside
`cli.py` user output. `observability-reviewer` checks every `backend/src/**` diff.

## Style
Small functions, docstrings on public functions stating the invariant they keep, no clever
metaprogramming in matching code. `ReferenceEngine` in particular must stay obviously correct — readable
beats fast there.
