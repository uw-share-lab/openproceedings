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
  **snake_case constant** (`crawl_page_fetched`, `index_built`), not a sentence. Variable data goes in
  fields: `log.info("index_built", extra={"index_version": v, "docs": n, "secs": t})`. Never build it
  into the message with an f-string.

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
  bodies. Never log IPs beyond what the rate limiter needs in memory.
- Exceptions from HTTP clients can carry URLs with credentials or tokens. `logs.py` scrubs `user:pass@` and
  secret-looking query parameters (`token`, `key`, `secret`, `password`, `auth`, `sig`) from every string
  value and from exception and stack text, and redacts secret-shaped keys case-insensitively at any depth.
  That is a backstop, not permission: still never pass credentials to a log call.

## API access line (INFO, exactly one per request)
`request` event with: `request_id`, `method`, `route` (the template, e.g. `/api/v1/papers/{id}`, not the
concrete path), `status`, `ms`, `index_version`, `canonical_hash` (search/export), `total`. Health checks
log at DEBUG.

## Review checklist (`observability-reviewer`)
1. Does every new failure path produce exactly one log at the right level?
2. Is anything logged per record, per term or per page at INFO or above?
3. Could any field contain query text, an abstract, a credential or personal data?
4. Are messages `event` constants with structured fields, not f-string sentences?
5. Is `logging` configured anywhere other than `logs.py`, or is `print` used for diagnostics?
6. Are expected conditions (a 404 for an unknown paper id, a parse error) being logged as ERROR? A user's
   parse error is not a server error. It's DEBUG at most.
