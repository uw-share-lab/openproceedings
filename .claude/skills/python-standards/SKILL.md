---
name: python-standards
description: The backend Python standard for openproceedings — Python 3.12 with uv, ruff + ruff-format, mypy --strict, pydantic v2 models as contracts, pure functions in query/ and engine/, no module-level mutable state, typed exceptions mapped to Diagnostics, and logging rules. Use when writing or reviewing any code under backend/, adding a dependency, or fixing a lint/type failure in CI.
---

# Python standards (backend/)

## Toolchain — uv only
- `uv sync` to install; `uv run <cmd>` to run (`uv run pytest`, `uv run op search …`); `uv add <pkg>` /
  `uv add --dev <pkg>` to add deps. Never `pip install`, never a hand-edited lock. `uv.lock` is committed
  and a lockfile change routes to `security-reviewer`.
- Python **3.12**. Use `type X = …` aliases, `StrEnum`, `match` where it clarifies AST dispatch.
- CI `lint` runs: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict backend/src`.
  Run all three locally before committing.

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
  builtins such as `IndexError`), each carrying a code from the registry (`error-diagnostics`).
- User-facing problems are **values** (`Diagnostic` in `ParseResult.errors`), not exceptions: the parser
  never raises on bad input.
- Never bare `except:` or `except Exception: pass`. Catch the narrowest type, add context, re-raise or
  convert to a Diagnostic. A swallowed error in ingestion becomes a silent coverage gap.
- Unknown values stay `unknown` and are logged; never guessed (01 §Error handling).

## Logging
Structured JSON via the stdlib `logging` with a JSON formatter; fields: request id, canonical hash,
latency, total. **Never log raw query text by default** (unpublished review designs). No `print` outside
`cli.py`.

## Style
Small functions, docstrings on public functions stating the invariant they keep, no clever
metaprogramming in matching code. `ReferenceEngine` in particular must stay obviously correct — readable
beats fast there.
