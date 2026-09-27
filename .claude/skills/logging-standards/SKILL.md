---
name: logging-standards
description: The openproceedings logging standard — stdlib logging with one JSON formatter configured once at the entry point, one module logger per file, what each level means, one access line per API request, summarised (not per-record) crawl and build progress, the privacy rules (no raw query text by default, no abstracts, no credentials, no personal data), and the review checklist for noisy, missing or leaky logs. Use when adding or changing any log call, configuring logging in the CLI or API, or reviewing a backend/src/** diff.
---

# Logging standard

The goal is logs you can **read at 2 a.m. and grep in a year**: few lines, all of them structured, with
nothing private in them. A log is not a debugger, a progress bar or a data dump.

## Setup (once, at the entry point)
- Python stdlib `logging` only. `configure_logging(level, fmt)` lives in
  `backend/src/openproceedings/logs.py` and is called **only** by `cli.py` and the API's startup. Library
  code never calls `basicConfig`, never adds handlers, never sets levels.
- Every module: `log = logging.getLogger(__name__)`. No `print()` outside CLI user output, and CLI output
  that's meant for the user (results, tables) goes to stdout, not through logging.
- Format: one JSON object per line (`ts`, `level`, `logger`, `event`, then fields). `op --log-format text`
  renders the same fields as one readable line (values JSON-escaped) for local reading only; JSON is the
  default and the only format anything collects. A field named like a core key is emitted as
  `field_<key>`, so it can never overwrite the line's shape. `event` is a short
  **snake_case constant** (`crawl_page_fetched`, `index_built`), not a sentence, named `<noun>_<verb>`
  (`pinned_index_opened`, `index_load_failed`, `records_store_full`). Variable data goes in
  fields: `log.info("index_built", extra={"index_version": v, "docs": n, "secs": t})`. Never build it
  into the message with an f-string.
- **Durations are `ms`**, milliseconds to one decimal, from `logs.elapsed_ms(started)`: one form in every
  line (a float), never a hand-rolled `round(...)`.
- **Why, as a constant.** A failure line carries `error` (the type) and, when there is one, a `reason`
  constant, never the message (messages name paths): an exception's own `reason` (`SnapshotError`,
  `IndexBuildError`, `IndexSelectionError`, `IndexUnservable`) or an OSError's errno name (`ENOENT`),
  through `api.errors.reason_of`. A failure that stands for another (`raise … from e`) logs the cause's
  type, frames and reason too (`cause`, `cause_frames`, `cause_reason`).
- **A state, not a stream.** A condition that persists (a full record store, an unreadable index
  directory) logs once when it starts and once when it ends (`records_store_full` /
  `records_store_recovered`, `index_list_failed` / `index_list_recovered`), never once per request that
  meets it.

## Levels mean something
| Level | Use for | Example |
|---|---|---|
| `ERROR` | Something failed and a person must act; the operation did not complete | a replay `mismatch` (guarantee 4 broken), a crawl aborted |
| `WARNING` | Degraded but continuing; worth a look | a 429 back-off, a record with `track=unknown`, a missing abstract (counted, not listed) |
| `INFO` | One line per **meaningful unit of work** | index built, snapshot written, crawl finished (with counts), one access line per request |
| `DEBUG` | Detail for development; off by default, never required to diagnose production | per-page fetches, per-record classification |

## Volume rules (what the reviewer checks first)
- **No per-record INFO.** Crawls, dedup and index builds log a start line, periodic summaries (at most every
  30 s or every 10k items), and an end line with counts. Per-item detail is DEBUG.
- **No logging inside hot loops** of `query/` or `engine/`. Search latency is budgeted (spec 03); a log call
  per term is a performance bug.
- **Log once, where it's handled.** Don't log and then re-raise. The layer that handles the exception logs
  it (with `exc_info` for ERROR). Everyone else just raises.
- **No duplicate context.** Request ID, `index_version` and route come from the logging context (a
  `contextvars` filter), so you don't repeat them at every call site.

## Privacy rules (Must)
- **Query text is not logged by default** (spec 04). Log `canonical_hash`, token count and total. The config
  flag `log_query_text=false` can be switched on only on a local dev instance.
- Never log abstracts, author lists, OpenReview credentials, tokens, cookies, `.env` values, or request
  bodies. Never log `Diagnostic.message` or `OpenProceedingsError.message`: they quote user input. Log
  the `code` (a `UserInputError` at DEBUG, an `InternalError` at ERROR with the traceback). Never log IPs beyond what the rate limiter needs in memory.
- Exceptions from HTTP clients can carry URLs with credentials or tokens. `logs.py` scrubs `user:pass@` and
  secret-looking query parameters (`token`, `key`, `secret`, `password`, `auth`, `sig`) from every string
  value and from exception and stack text, and redacts secret-shaped keys (starting or ending with a secret word: `password…`, `…_token`, `auth_…`,
  `secret…`, `bearer…`, `…api_key`) case-insensitively at any depth, while ordinary fields like
  `tokenizer_version`, `token_count` and `author_count` stay visible.
  That is a backstop, not permission: still never pass credentials to a log call.

## API access line (INFO, exactly one per request)
`request` event with: `request_id`, `method`, `route` (the template, e.g. `/api/v1/papers/{id}`, not the
concrete path), `status`, `ms`, `index_version`, `canonical_hash` (search/export), `total`. Health checks
log at DEBUG. An unexpected failure is one `request_failed` ERROR line beside it: `code`, `error`, `frames`,
and for a wrapped one `cause`, `cause_frames` (where it really failed: Starlette wraps an error its handler
catches after a stream started in a RuntimeError whose frames stop at the handler) and `cause_reason`. `status` is what the client was sent. If a handler fails after the response started (a
stream cut short), the line adds `aborted: true`, beside that failure's one `request_failed` ERROR line;
uvicorn then also logs `ASGI callable returned without completing response.` at ERROR (it closes the
connection), which is expected there and carries no request data. If the response started and never sent
its final body message with nothing having failed, the client hung up mid-stream: the line adds
`client_disconnected: true` and nothing is logged above INFO. Each key is absent otherwise.

## CLI search line (INFO, at most one per `op search` / `op export`)
`search_run` event with: `command`, `mode`, `engine`, `index_version`, `canonical_hash`, `total`, `ms`: the
access line's privacy-safe fields, never the query. Diagnostics (parse errors, warnings, translations) are
user output on stderr, not log lines, because they quote the query (task-030).

A refusal is one `cli_refused` line (`command`, `error` type, `code` if it has one; never the message),
at the level of its kind: DEBUG for the user's own input (`UserInputError`: a bad query, a bad argument),
ERROR with the traceback for an `InternalError`, ERROR without it for a broken guarantee (`ParityError`,
whose message quotes corpus tokens), WARNING for any other refusal (a snapshot, an index, a file). An
exception nothing anticipated is one `cli_failed` ERROR line with the traceback; a traceback's last line is
the exception's message, which can quote input, so the API (task-034) logs frames and type, not the
message. Long jobs say they're alive: `index_build_started`, `index_build_progress` every 10k documents,
`index_built`; `index_parity_ok` when a parity check passes.

## Review checklist (`observability-reviewer`)
1. Does every new failure path produce exactly one log at the right level?
2. Is anything logged per record, per term or per page at INFO or above?
3. Could any field contain query text, an abstract, a credential or personal data?
4. Are messages `event` constants with structured fields, not f-string sentences?
5. Is `logging` configured anywhere other than `logs.py`, or is `print` used for diagnostics?
6. Are expected conditions (a 404 for an unknown paper id, a parse error) being logged as ERROR? A user's
   parse error is not a server error. It's DEBUG at most.
