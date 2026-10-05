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
  through `logs.reason_of` (and its frames through `logs.frames`). A failure that stands for another (`raise … from e`) logs the cause's
  type, frames and reason too (`cause`, `cause_frames`, `cause_reason`).
- **A state, not a stream.** A condition that persists (a full record store, an unreadable index
  directory) logs once when it starts and once when it ends (`records_store_full` /
  `records_store_recovered`, `index_list_failed` / `index_list_recovered`, `record_saves_throttled` /
  `record_saves_recovered`), never once per request that meets it. The flip of the state and its line happen
  under one lock, so two threads meeting the change log it once.

## Levels mean something
| Level | Use for | Example |
|---|---|---|
| `ERROR` | Something failed and a person must act; the operation did not complete | a replay `mismatch` (guarantee 4 broken), a crawl aborted |
| `WARNING` | Degraded but continuing; worth a look | a 429 back-off, a listing's or crawl's records with `track=unknown` (counted in one line, never one per record) |
| `INFO` | One line per **meaningful unit of work** | index built, snapshot written, crawl finished (with counts), one access line per request |
| `DEBUG` | Detail for development; off by default, never required to diagnose production | per-page fetches, per-record classification, a record-level anomaly (counted at WARNING) |

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

## Crawl lines (TASK-116)
- **Start, heartbeats, end** at INFO. OpenReview (API v1 and v2 alike): `openreview_crawl_started`,
  `openreview_crawl_progress`, `openreview_crawl_finished`, each with `api`, `venue`, `year`, the counts
  processed so far, `requests` and `cached` (the finished line also counts `title_control_characters`, the
  records whose title lost a control character: decision-036, never an attention count); a heartbeat is due at most every 30 s (`common.Heartbeat` on the
  HTTP client's monotonic clock, so a test's fake clock drives it). The proceedings miners:
  `neurips_listing_started` / `_progress` / `_mined` and `pmlr_volume_started` / `_progress` / `_mined`, with the
  year or volume and `done` / `of`; their heartbeat is due at most every `PROGRESS_SECONDS` (30 s) of
  `time.monotonic`, checked after each record built. Never a line per item.
- **Record-level anomalies are DEBUG** (`openreview_unknown_track`, `openreview_v1_unmapped`,
  `openreview_v1_conflict`, `openreview_v1_twin_outcome`, `openreview_v1_duplicate`, `openreview_duplicate_submission`, `openreview_note_skipped`, `openreview_presentation_unmapped`, `openreview_title_control_characters` (forum and count, never the title), `neurips_record_invalid`,
  `pmlr_record_invalid`, and per cache entry `openreview_cache_incompatible`, a purged pre-projection entry,
  which a crawl reports as `cache_incompatible`). Each listing or crawl logs **at most one aggregate WARNING**
  with the counts
  (`listing_attention`, `openreview_crawl_attention`); listing-level conditions (`listing_count_mismatch`,
  `listing_see_also_unfollowed`) keep their own line.
- **HTTP policy events are constants** (`http.PolicyEvents`: `crawl_retry_wait` / `openreview_retry_wait`
  WARNING, `*_budget_wait` INFO, `*_cache_expired` INFO), selected by the source's `Policy`, never built from
  a prefix; a test walks every crawler log call and refuses an f-string or concatenated event.
- **A refusal says where and what to do**, safely: an OpenReview projection refusal names the canonical
  request (`GET <url>`, the cache key), never response data or credentials; a proceedings page past the HTML
  parser's bounds (`html_budget`) names its URL, `--refresh` and its cache entry.

## API access line (INFO, exactly one per request)
Index loads (`api/state.py`): `index_loaded` / `index_swapped` carry `abstracts_withheld` (how many ids the
takedown list names; never the ids), `takedowns_not_in_index` (how many of them the index doesn't hold under that id), `takedowns_followed` (how
many ids it withholds as a listed paper under another id, TASK-067) and
`takedowns_list` (`present`/`absent`, whether the file exists), and
a SIGHUP that finds the same index but another list, or whose new index fails while its new list parsed, logs
`takedowns_reloaded` (INFO, the same counts; `takedowns_reload_failed` ERROR with `index_version`, `error`,
`ms` and any `reason`, if even that fails); a list that doesn't parse, can't be read, or is missing while
it is required (`op serve` off loopback or behind a trusted proxy), a list is applied, or any snapshot on disk
withheld abstracts, is `index_load_failed` with `reason` `takedowns_invalid`, `takedowns_unreadable` or
`takedowns_missing`. A snapshot whose merges.csv doesn't match its manifest is one ERROR
`takedown_merges_unavailable` per damaged snapshot (`snapshot`, its directory name; `error`; `reason`), and the
list applies without that snapshot's merges (in the API and `op export`). Likewise `op export` of another index than `current` logs one ERROR `takedown_twins_unavailable` (`error`; `reason`; `index`, the current index's name) when the current index's snapshot can't be read: the list then follows only the exported snapshot's twin links (TASK-163).
A 503 `API_BUSY` from the bounded pinned-open wait puts `busy: pinned_open` on the access line (TASK-067). On
`POST /compare` (TASK-177) `busy` names the capacity that refused it: `match_index_building` and
`compare_slots` on a 503 with `Retry-After`; `match_index_failed` (retrying won't help until the index is
reloaded) and `compare_deadline` (the client offers Retry at once and never retries it by itself) on a 503
without one; `compare_running` and `compare_cooldown` on the network's 429. A loopback-default instance
refusing a proxied request puts `compare_refused: proxied` on its 403 (spec 04 §Logging, the access line's
`busy`, is the full list). `abstracts_withheld` means three counts,
each named by its event: the list's size on a load, the records a build withheld on `snapshot_built`, the
records of the body on an export's access line (the build's JSON gives the ids themselves, `withheld_ids`). `snapshot_built` / `snapshot_exists` carry
`abstracts_withheld`, `takedowns_followed`, `takedowns_unmatched` and `takedowns_twins` counts, and `trimmed`: how many records
the ingest caps trimmed (decision-026), never their ids. When it is non-zero the build also logs one WARNING
`snapshot_trimmed` with the count. An export's access line carries
`abstracts_withheld` (its `X-Abstracts-Withheld`). `op takedown check` logs one `takedown_checked` (INFO, WARNING when
it found problems) with `listed`, `index_versions` and `problems` counts: never an id's text or a requester.

`request` event with: `request_id`, `method`, `route` (the template, e.g. `/api/v1/papers/{id}`, not the
concrete path), `status`, `ms`, `index_version`, `canonical_hash` (search/export), `total`, `abstract_source`
(export: its `X-Abstract-Source`, `unavailable` when it withheld the abstracts, decision-021), and `code` (the
error envelope's code, on every refusal and every 500; `api.errors.note_code`), and for a route that runs a
query `verified_clauses` (its position-verified clauses), `verification_candidates` (what their checks
would read, summed; absent with none) and `verify_ms` (the time it held a verification slot; absent when it
held none; added by `IndexState.verification_slot` through the `errors.current_access` context variable,
the request having no handle there). A request whose slot holds pass `slow_verification_seconds` logs one
`verification_slow` WARNING (`verify_ms`, `threshold_ms`): every other cold verification was refused
meanwhile. `verify_cpu_ms` is the verifying thread's CPU in those holds, and `verify_tokens` what that CPU
time was debited after the fact (`RateLimit`; never wall time, which other requests' load inflates). A comparison (`POST /compare`, TASK-177) adds counts only: `ris_bytes`, `ris_records`, `ris_papers`, `kept`,
`dropped`, `not_in_index`, `added`, `compare_ms` (wall time it held its slot), `compare_cost_ms` (what is
debited: the file's arrival plus the work's CPU) and `compare_tokens`. Never a title, a venue string or a file
name from the uploaded file (none is sent; a test greps every line for them). The served index's match table
logs `match_index_built` (INFO: `index_version`, `records`, `ms`) once per served index, or `match_index_failed`
(ERROR: `index_version`, `error`, `ms`, `reason` when there is one, `frames` for an unexpected type); each
comparison refused after it is a state on the access line (`busy: match_index_failed`), not another ERROR. A facet worker
that would have had to verify (a bug) logs `facet_worker_recounted` (WARNING) and the caller recounts; the group-count worker likewise, `group_worker_recounted` (TASK-176); any other failure of it is one ERROR `group_count_failed` (`groups`, `error`: the type, never the message, `frames`, and `reason` when the error has one), a late answer one WARNING `group_count_timed_out` (`groups`, `threshold_ms`: the wait it passed), and a job no counting worker took within the grace one DEBUG `group_count_busy` (`groups`: a state under load, not an alarm), the search answering without its counts either way. `/search`'s line also carries `groups` (how many concept groups the query has) and `groups_counted` (how many were counted: all or 0), two integers, never a span, and, when none were, `groups_not_counted` (why: a `search.NotCounted` constant). Health checks log at DEBUG. An unexpected failure is one `request_failed` ERROR line beside it: `code`, `error`, `frames`,
and for a wrapped one (only then: never `cause: null`) `cause`, `cause_frames` (where it really failed: Starlette wraps an error its handler
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
`index_built`; `index_parity_ok` when a parity check passes. A failed build whose `.tmp-*` staging directory
survives its removal logs `index_build_tmp_left` (WARNING, the directory's name only). `op index retire`
logs one line with `index_version`, `pinned` and the outcome: `index_retired` (INFO; WARNING with
`tmp_left: true` when its `.tmp-` directory survived), `index_retire_checked` (`--dry-run`) or
`index_retire_refused` (WARNING with its `reason`; DEBUG for a malformed name, which is left out), plus
ERROR `index_retire_restore_failed` (the `.retiring-` directory's name and errno name) when a set-aside index
can't be renamed back. That run logs two lines: the ERROR, then the `index_retire_refused` (or `cli_refused`,
or nothing for Ctrl-C) of whatever made it restore. A later retire of that version is refused with reason
`retire_cut_short` until the directory is moved back. A
`storage.sweep` that can't remove a `.tmp-` leftover logs `tmp_sweep_failed` (WARNING, its name and the
chmod's errno name) and carries on.

`op eval scholar` logs `scholar_report_started` (INFO: `index_version`, `queries`, `ris_records`) before it
reads the snapshot, then one `scholar_report_written` line (ERROR when the automation found an `our_bug`, else
INFO): `index_version`, `queries`, `ris_records`, `ris_papers` (the set's papers in scope, the name the
`/compare` access line uses), `ris_only_matches`, `our_bug`, `unresolved`, `review_rows`, `human_calls`,
`human_our_bug`, `classified`, `replaced`, `ms`. Counts only: never a query, a title, a role or a note.

## Review checklist (`observability-reviewer`)
1. Does every new failure path produce exactly one log at the right level?
2. Is anything logged per record, per term or per page at INFO or above?
3. Could any field contain query text, an abstract, a credential or personal data?
4. Are messages `event` constants with structured fields, not f-string sentences?
5. Is `logging` configured anywhere other than `logs.py`, or is `print` used for diagnostics?
6. Are expected conditions (a 404 for an unknown paper id, a parse error) being logged as ERROR? A user's
   parse error is not a server error. It's DEBUG at most.

## Framework instrumentation

FastAPI's locked `opentelemetry-api` dependency does not include an SDK or exporter; telemetry is
inactive in the shipped configuration. Adding an SDK/exporter or enabling automatic framework
instrumentation requires a separate privacy review. Framework spans can include `url.query` and
therefore raw search text; our access-log redaction does not automatically sanitize those spans.
Use the existing safe structured fields and verify span attributes before enabling export.
