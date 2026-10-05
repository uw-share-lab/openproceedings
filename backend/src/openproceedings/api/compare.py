"""`POST /api/v1/compare` (TASK-177; spec 04 §Comparing with a RIS file, spec 07 §B): a reviewer's own RIS
file against a query's result on the served index. Which of the papers they already hold does the query keep,
which does it drop, which does it add, and which are not in the index at all.

Transport only. The comparison is `eval/scholar_compare.py`, the one implementation `op eval scholar` reports
from: `read_ris` → `scope_and_match` (spec 01's merge rules) → `compare_query` (the classes, each decided by
`ReferenceEngine`). The result is exactly `engine.match_ids` of the query's effective tree, as `/search` counts
it: nothing here changes what matches (guarantee 5), and the same query, index_version and file give the same
answer.

The file (the request body, `application/x-research-info-systems`; no form, no multipart, no content encoding):

- is read into memory for this one request and dropped with it. It is never written to disk, never stored,
  never enters the index, a search record or an export, and never logged: the access line carries counts
  (`ris_bytes`, `ris_records`, `kept`, …), no title, no venue string and no file name (none is ever sent);
- is capped before it is parsed: its bytes by `middleware.BodyLimit` (413 `API_BODY_TOO_LARGE`, counted as
  they arrive), then its lines, each line's length, its title and venue lines' length and its records
  (`check_caps`, 413 `API_RIS_TOO_LARGE`). A file over a cap is refused whole, never cut;
- is read only while this request holds one of `ApiConfig.comparison_slots` (503 `API_BUSY` otherwise), so at
  most that many files are in memory, and within `compare_upload_seconds`. A refusal sent before the file was
  read discards what arrives of it for a moment first (`middleware.drain`), so the client sending it gets the
  refusal rather than a reset connection.

One request answers everything, exports included (each list as CSV text, the added papers as RIS): a
comparison is seconds of work, nothing is kept between requests, and a second request would do it all again.

Cost (decision-010's model): the route costs `export_weight` like an export, the query's position-verified
clauses are charged and bounded as on `/search` (`deps.searchable`, `deps.check_candidates`), and the time the
slot was held is debited afterwards (`middleware.RateLimit.debit_comparison`). The work is bounded by the caps,
by `compare_max_results` (422 `API_COMPARE_TOO_COSTLY`) and by `compare_max_seconds` (503 `API_BUSY`).

The handler is `async` (the one exception to fastapi-conventions §Handlers): it must take the slot before it
reads the body, which only a coroutine can order. Everything CPU-bound runs in the thread pool
(`anyio.to_thread`), as a `def` handler's would.
"""

from __future__ import annotations

import csv
import io
import re
import threading
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import Response
from starlette.requests import ClientDisconnect

from openproceedings.api.config import ApiConfig
from openproceedings.api.deps import (
    ServedDep,
    access_fields,
    annotate,
    check_candidates,
    searchable,
)
from openproceedings.api.errors import ApiError
from openproceedings.api.export import sources_of, stored_documents
from openproceedings.api.middleware import API_PREFIX, drain
from openproceedings.api.models import (
    MODE_DOC,
    Q_DOC,
    CompareCsv,
    CompareQuery,
    CompareResponse,
    CompareRow,
    NotComparedRow,
    ReasonTotals,
    versions,
)
from openproceedings.api.openapi import COMPARE_REFUSALS
from openproceedings.api.state import Served
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.protocol import Searchable
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.eval.scholar_compare import (
    _TITLE_TAGS,
    _VENUE_TAGS,
    ONLY_OP,
    ONLY_SCHOLAR,
    Dropped,
    Entry,
    MatchIndex,
    QueryRefused,
    RisRecord,
    Row,
    Scope,
    TooManyForms,
    compare_query,
    only_in_result,
    read_ris,
    result_in_scope,
    scope_and_match,
)
from openproceedings.export import Provenance, check_count, csv_cell, entries, header, utc_date
from openproceedings.ingest.caps import MAX_TITLE
from openproceedings.query.ast import Node
from openproceedings.query.parser import Mode, ParseResult
from openproceedings.search import expanded

router = APIRouter(prefix=API_PREFIX)

RIS_MEDIA = "application/x-research-info-systems"
# every indexed venue, every year: a limit on years or venues is part of the query (guarantee 3), so both sides
# are scoped by what the reviewer wrote and nothing else
SCOPE = Scope()
# how the core's row keys name the file (`file#<n>`): a constant, since the request carries no file name
NAME = "file"
# lines one record may have on average: a file of the record cap's worth of records has at most this many
# times as many lines, so a body of millions of one-tag lines is refused before any is parsed into a field
MAX_LINES_PER_RECORD = 64
_RECORD_START = re.compile(r"(?m)^TY  - ")  # scholarmend's own record boundary
_SHORT_TAGS = frozenset(
    (*_TITLE_TAGS, *_VENUE_TAGS)
)  # the lines normalized for matching: capped like a title
CSV_COLUMNS = (
    "list",
    "ris_record",
    "copies",
    "id",
    "title",
    "venue",
    "year",
    "matched_by",
    "reason",
    "detail",
    "needs_review",
    "record_source",
    "fails_filters",
    "abstract_withheld",
    "index_version",
    "canonical_hash",
)
_wall = time.monotonic  # module names, so a test can move them
_cpu = time.thread_time


@dataclass(frozen=True)
class Comparisons:
    """What the app holds for `POST /compare`: the slots (a comparison takes one before it reads its file)."""

    slots: threading.BoundedSemaphore


def install(app: FastAPI, config: ApiConfig) -> None:
    app.state.comparisons = Comparisons(threading.BoundedSemaphore(config.comparison_slots))


def _closing(code: DiagnosticCode, message: str, **headers: str) -> ApiError:
    """A refusal sent while the body may be unread: the connection is closed after it."""
    return ApiError(code, message, headers={"Connection": "close", **headers})


def _busy(message: str, retry: int) -> ApiError:
    return _closing(
        DiagnosticCode.API_BUSY, f"{message} Try again in {retry} s.", **{"Retry-After": str(retry)}
    )


def check_media(request: Request) -> None:
    """415 `API_UNSUPPORTED_MEDIA_TYPE` unless the body is declared as plain RIS: `Content-Type:
    application/x-research-info-systems` (a `charset`, if given, must be UTF-8) and no `Content-Encoding`. A
    form (`multipart/form-data`, urlencoded) is refused, so no multipart parser ever runs and nothing is
    spooled to disk; a compressed body is refused, so nothing is ever decompressed."""
    kind, _, params = request.headers.get("content-type", "").partition(";")
    charsets = [
        value.strip().strip('"').lower()
        for name, _, value in (p.partition("=") for p in params.split(";"))
        if name.strip().lower() == "charset"
    ]
    if kind.strip().lower() != RIS_MEDIA or any(c not in ("utf-8", "utf8") for c in charsets):
        raise _closing(
            DiagnosticCode.API_UNSUPPORTED_MEDIA_TYPE,
            f"Send the RIS file itself as the request body, with `Content-Type: {RIS_MEDIA}` (UTF-8). A form "
            "upload (multipart) or any other type is not read.",
        )
    if request.headers.get("content-encoding", "identity").strip().lower() != "identity":
        raise _closing(
            DiagnosticCode.API_UNSUPPORTED_MEDIA_TYPE,
            "Send the RIS file uncompressed: a body with a `Content-Encoding` is not read.",
        )


def _too_large(message: str) -> ApiError:
    return ApiError(DiagnosticCode.API_RIS_TOO_LARGE, message)


def _invalid(message: str) -> ApiError:
    return ApiError(DiagnosticCode.API_RIS_INVALID, message)


def decode(body: bytes | bytearray) -> str:
    """The file's text: strict UTF-8, a leading BOM dropped (Scholar exports begin with one). 422
    `API_RIS_INVALID` otherwise; the message never quotes the bytes."""
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _invalid(
            "The file is not UTF-8 text. Export it again as RIS in UTF-8 (the default of Publish or Perish, "
            "Zotero and EndNote)."
        ) from None


def check_caps(text: str, *, max_records: int, max_line_chars: int, max_title_chars: int = MAX_TITLE) -> int:
    """The number of records `text` holds, once it is within every cap; 413 `API_RIS_TOO_LARGE` for a file over
    one, before anything is parsed into fields. In order, each a single pass that allocates nothing per line:
    the lines (at most `MAX_LINES_PER_RECORD` × `max_records`), each line's length (`max_line_chars`; a title
    or venue line's value `max_title_chars`, since those are normalized for matching), then the records."""
    if "\n" not in text and "\r" in text:  # the parser reads `\n` and `\r\n`; this would be one endless line
        raise _invalid(
            "The file's lines end with a carriage return only, which is not read. Save it with LF or CRLF line "
            "endings."
        )
    max_lines = MAX_LINES_PER_RECORD * max_records
    if text.count("\n") > max_lines:
        raise _too_large(
            f"The file has more than {max_lines:,} lines, the most this instance reads in one comparison "
            f"({max_records:,} records). Split it into several files."
        )
    start, line = 0, 1
    while start < len(text):
        end = text.find("\n", start)
        if end < 0:
            end = len(text)
        if end - start > max_line_chars:
            raise _too_large(
                f"Line {line:,} of the file is over {max_line_chars:,} characters, the longest line this "
                "instance reads. Leave the abstracts out: only titles, venues, years and links are compared."
            )
        if end - start > max_title_chars + 6 and text.startswith("  - ", start + 2):
            tag = text[start : start + 2]
            if tag in _SHORT_TAGS and len(text[start + 6 : end].strip()) > max_title_chars:
                raise _too_large(
                    f"Line {line:,} of the file is a title or venue over {max_title_chars:,} characters, "
                    "longer than any the index holds, so it can't be compared. Remove or shorten that record."
                )
        start, line = end + 1, line + 1
    records = sum(1 for _ in _RECORD_START.finditer(text))
    if records > max_records:
        raise _too_large(
            f"The file holds {records:,} records; this instance compares at most {max_records:,} in one "
            "request. Split it into several files."
        )
    return records


def parse_file(text: str) -> list[RisRecord]:
    """`read_ris` of the file's text; 422 `API_RIS_INVALID` for a text that holds no record (the parser's own
    refusals name the file and its size, so the message here is ours)."""
    try:
        records = read_ris(text, NAME)
    except ValueError:
        raise _invalid(
            "The file is not RIS as this instance reads it: it must start with a record (a `TY  - ` line), "
            "with nothing before the first one."
        ) from None
    if not records:
        raise _invalid("The file holds no RIS record (no `TY  - ` line).")
    return records


class _OneSearch:
    """The request's engine as the comparison core sees it: one `match_ids` per tree, however often it is
    asked (the route counts the result before the core compares it; the search runs once)."""

    def __init__(self, engine: TantivyEngine) -> None:
        self.index_version = engine.index_version
        self.tokenizer_version = engine.tokenizer_version
        self._engine = engine
        self._found: dict[str, frozenset[str]] = {}

    def match_ids(self, ast: Node) -> frozenset[str]:
        key = ast.model_dump_json()
        if key not in self._found:
            self._found[key] = self._engine.match_ids(ast)
        return self._found[key]


def _number(key: str) -> int:
    return int(key.rpartition("#")[2])


def _source(independent: bool | None) -> str:
    return "" if independent is None else "crawled" if independent else "ris_only"


def csv_text(rows: Iterable[Iterable[object]]) -> str:
    """A CSV file's text: the BOM (so a spreadsheet reads UTF-8), the header row, then `rows`, every cell
    through `export.csv_cell` (titles come from anyone: no cell starts a formula)."""
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(csv_cell(c) for c in row)
    return out.getvalue()


def _csv_row(name: str, r: CompareRow, index_version: str, canonical_hash: str) -> tuple[object, ...]:
    return (
        name,
        r.ris_record,
        r.copies or None,
        r.id,
        r.title,
        r.venue,
        r.year,
        r.matched_by,
        r.reason,
        r.detail,
        "" if r.settled else "true",
        _source(r.independent),
        "true" if r.fails_filters else "false",
        "true" if r.abstract_withheld else "false",
        index_version,
        canonical_hash,
    )


def _left_out_csv(r: NotComparedRow, index_version: str, canonical_hash: str) -> tuple[object, ...]:
    """A `not_compared` row in the lists' columns: its reason under `reason`, no index record's cells."""
    cells: dict[str, object] = {
        "list": "not_compared",
        "ris_record": r.ris_record,
        "title": r.title,
        "venue": r.venue,
        "year": r.year,
        "reason": r.reason,
        "index_version": index_version,
        "canonical_hash": canonical_hash,
    }
    return tuple(cells.get(c) for c in CSV_COLUMNS)


def _row(row: Row, entry: Entry | None, hidden: AbstractSet[str]) -> CompareRow:
    """The core's row as the API sends it. `entry` is the file's paper (None on an `added` row). A withheld
    record keeps its class and loses the evidence, which can name words of its abstract."""
    withheld = bool(row.op_id) and row.op_id in hidden
    return CompareRow.model_validate(
        {
            "ris_record": _number(row.scholar_key) if entry is not None else None,
            "copies": entry.copies if entry is not None else 0,
            "id": row.op_id or None,
            "title": row.title,
            "venue": row.venue or None,
            "year": row.year,
            "matched_by": (entry.match.rule or entry.match.problem) if entry is not None else None,
            "reason": row.auto_class or None,
            "detail": "" if withheld or not row.auto_class else row.auto_evidence,
            "settled": row.settled,
            "independent": row.independent,
            "fails_filters": row.fails_filters,
            "abstract_withheld": withheld,
        }
    )


def _reasons(rows: Iterable[CompareRow]) -> dict[str, int]:
    """Rows per `reason`, the reasons in the protocol's order (`ONLY_SCHOLAR`, then `ONLY_OP`'s own)."""
    found: Counter[str] = Counter(r.reason for r in rows if r.reason is not None)
    return {c: found[c] for c in dict.fromkeys((*ONLY_SCHOLAR, *ONLY_OP)) if found[c]}


def _left_out(d: Dropped) -> NotComparedRow:
    r = d.record
    return NotComparedRow.model_validate(
        {
            "ris_record": _number(r.key),
            "title": r.title,
            "venue": r.venue_raw,
            "year": r.year,
            "reason": d.reason,
        }
    )


def _admit(request: Request, served: Served, q: str, mode: Mode) -> ParseResult:
    """The query, admitted exactly as `/search` and `/export` admit it (length, parse, the verified-clause
    charge, wildcard expansion, the candidate ceiling): each refusal is theirs."""
    engine = served.engine
    result = searchable(request, q, mode, engine.tokenizer_version)
    assert result.effective_ast is not None  # searchable refuses a query that doesn't parse
    expanded(engine, result.effective_ast)  # an over-cap wildcard is a located 422 before anything runs
    check_candidates(request, engine, result.effective_ast)
    return result


def _table(served: Served, retry: int) -> MatchIndex:
    """The served index's match table (`state.MatchTable`): 503 `API_BUSY` while it is being built."""
    table = served.matches
    if table is None or table.failed:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "comparisons are on but the index has no match table"
        )
    index = table.index
    if index is None:
        raise _busy(
            "This index was loaded a moment ago and its comparison table is still being prepared.", retry
        )
    return index


async def _read(request: Request, seconds: float) -> bytearray:
    """The whole body, within `seconds` (408 `API_UPLOAD_TIMEOUT` past it, or if the client goes away).
    `BodyLimit` counts the bytes as they arrive and raises the 413 itself."""
    body = bytearray()
    try:
        with anyio.fail_after(seconds):
            async for chunk in request.stream():
                body.extend(chunk)
    except (TimeoutError, ClientDisconnect):
        raise _closing(
            DiagnosticCode.API_UPLOAD_TIMEOUT,
            f"The file didn't arrive within the {seconds:g} s this instance gives one upload. Try again on a "
            "faster connection, or with a smaller file.",
        ) from None
    return body


async def offered(request: Request) -> None:
    """403 `API_COMPARE_DISABLED` unless this instance's operator turned comparisons on. The route's first
    dependency, so an instance that doesn't offer them answers every request to the path alike (whatever its
    query, its body or the index's state; only an undeclared parameter is refused earlier, as on any route):
    it says nothing about the served index, and nothing of the query or the body is looked at."""
    config: ApiConfig = request.app.state.config
    if not config.compare_enabled:
        await drain(request.receive)  # at most `max_body_bytes` on this path while comparisons are off
        raise _closing(
            DiagnosticCode.API_COMPARE_DISABLED,
            "Comparing with a RIS file is not turned on on this instance. Run your own instance (`op "
            "serve` on your machine offers it), or use `op eval scholar`.",
        )


class _Spent:
    """What a comparison used of its slot: the wall time its file took to arrive, and the work's CPU time
    (less what `IndexState.verification_slot` already debits as `verify_cpu_ms`)."""

    upload_ms = 0.0
    cpu_ms = 0.0


@router.post(
    "/compare",
    response_model=CompareResponse,
    responses=COMPARE_REFUSALS,
    dependencies=[Depends(offered)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": "The RIS file itself, UTF-8 (a BOM is accepted): no form, no multipart, no content "
            "encoding. `GET /meta` `limits.compare` gives its caps.",
            "content": {RIS_MEDIA: {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def compare_records(
    request: Request,
    served: ServedDep,
    q: Annotated[str, Query(description=Q_DOC)],
    mode: Annotated[Mode, Query(description=MODE_DOC)] = "native",
) -> Response:
    """Compare the RIS file in the body with `q`'s result on the served index: the papers of the file the
    result keeps, the ones it drops (in the index, not in the result, each with why), the ones the index
    doesn't hold, and the papers the result adds. The file is matched to the index by spec 01's merge rules
    (a forum id, a proceedings id, else title with venue and year; never a title alone). The result is
    `/search`'s for the same `q`, `mode` and index: `total` is its `total`, and `kept_total` + `added_total`
    equal it. Each list also comes as CSV text, and the added papers as RIS, ready to save. The file is used
    for this request only: never stored, never logged, never added to the index.
    Off unless this instance's operator turned it on (403 `API_COMPARE_DISABLED`; `GET /meta`
    `limits.compare` is then null)."""
    config: ApiConfig = request.app.state.config
    gate: Comparisons = request.app.state.comparisons
    retry = config.busy_retry_seconds
    try:
        check_media(request)
        result = await anyio.to_thread.run_sync(_admit, request, served, q, mode)
        index = _table(served, retry)
        if not gate.slots.acquire(blocking=False):
            raise _busy("This instance is running as many comparisons as it can.", retry)
    except Exception:
        await drain(request.receive)  # so the refusal reaches a client still sending its file
        raise
    fields = access_fields(request)
    started = _wall()
    spent = _Spent()
    try:
        body = await _read(request, config.compare_upload_seconds)
        spent.upload_ms = (_wall() - started) * 1000
        return await anyio.to_thread.run_sync(_compare, request, served, index, result, q, mode, body, spent)
    finally:
        gate.slots.release()
        if spent.upload_ms == 0.0:  # the upload itself failed: all of the hold was the file arriving
            spent.upload_ms = (_wall() - started) * 1000
        fields["compare_ms"] = round((_wall() - started) * 1000, 1)
        fields["compare_cost_ms"] = round(spent.upload_ms + spent.cpu_ms, 1)


def _compare(
    request: Request,
    served: Served,
    index: MatchIndex,
    result: ParseResult,
    q: str,
    mode: Mode,
    body: bytearray,
    spent: _Spent,
) -> Response:
    """The work, in a worker thread: its CPU time goes to `spent` whatever happens."""
    fields = access_fields(request)
    cpu, verified = _cpu(), fields.get("verify_cpu_ms", 0.0)
    try:
        return _run(request, served, index, result, q, mode, body)
    finally:
        after = fields.get("verify_cpu_ms", 0.0)
        already = (after - verified) if isinstance(after, float) and isinstance(verified, float) else 0.0
        spent.cpu_ms = max(0.0, (_cpu() - cpu) * 1000 - already)


def _run(
    request: Request,
    served: Served,
    index: MatchIndex,
    result: ParseResult,
    q: str,
    mode: Mode,
    body: bytearray,
) -> Response:
    config: ApiConfig = request.app.state.config
    engine = served.engine
    deadline = _wall() + config.compare_max_seconds

    def tick() -> None:
        if _wall() > deadline:
            raise _busy(
                f"This comparison ran past the {config.compare_max_seconds:g} s this instance gives one: the "
                "server is busy, or the file and the query are too much to compare here in one request (a "
                "smaller file or a narrower query takes less).",
                config.busy_retry_seconds,
            )

    size = len(body)
    text = decode(body)
    del body
    check_caps(text, max_records=config.compare_max_records, max_line_chars=config.compare_max_line_chars)
    records = parse_file(text)
    del text
    annotate(request, ris_bytes=size, ris_records=len(records))
    tick()
    side = scope_and_match(records, index, SCOPE)
    tick()
    assert result.effective_ast is not None and result.canonical is not None
    assert result.canonical_hash is not None  # it parsed (`_admit`)
    once = _OneSearch(engine)
    try:
        found, in_scope = result_in_scope(once, result.effective_ast, index, SCOPE)
    except ValueError:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "the served index holds a record its match table doesn't"
        ) from None
    extra = only_in_result(in_scope, side)
    annotate(request, total=len(found), ris_papers=len(side.entries))
    if len(extra) > config.compare_max_results:
        raise ApiError(
            DiagnosticCode.API_COMPARE_TOO_COSTLY,
            f"This query's result holds {len(extra):,} papers that the file doesn't, and each would be read "
            f"and judged; this instance compares at most {config.compare_max_results:,}. Narrow the query "
            "(a `year:` or `venue:` limit, a rarer term), then compare again.",
        )
    hidden = served.withheld_in(served.records)

    def fetch(ids: AbstractSet[str]) -> Mapping[str, Searchable]:
        tick()
        return {i: r for i in ids if (r := served.records.get(i)) is not None}

    try:
        compared = compare_query(
            NAME, q, side=side, index=index, engine=once, fetch=fetch, scope=SCOPE, mode=mode, tick=tick
        )
    except TooManyForms as e:
        raise ApiError(
            DiagnosticCode.API_COMPARE_TOO_COSTLY,
            f"A phrase or NEAR of this query has {e.count:,} spellings once each word's inflected forms are "
            "tried, more than a comparison checks. Shorten that phrase, then compare again.",
        ) from None
    except (QueryRefused, ValueError):  # it parsed in `_admit`, and every compared record was just read
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "a comparison failed on a query that parsed"
        ) from None
    entries = {e.record.key: e for e in side.entries}
    lists: dict[str, list[CompareRow]] = {
        "kept": [_row(r, entries[r.scholar_key], hidden) for r in compared.kept],
        "dropped": [_row(r, entries[r.scholar_key], hidden) for r in compared.dropped],
        "not_in_index": [_row(r, entries[r.scholar_key], hidden) for r in compared.not_in_index],
        "added": [_row(r, None, hidden) for r in compared.added],
    }
    left_out = [_left_out(d) for d in side.out_of_scope]
    version, digest = engine.index_version, result.canonical_hash
    annotate(
        request,
        kept=len(lists["kept"]),
        dropped=len(lists["dropped"]),
        not_in_index=len(lists["not_in_index"]),
        added=len(lists["added"]),
    )
    response = CompareResponse(
        **versions(version, engine.tokenizer_version),
        query=CompareQuery(input=q, mode=mode, canonical=result.canonical, canonical_hash=digest),
        total=compared.total,
        records_total=side.read,
        not_compared_total=len(left_out),
        duplicates_total=side.duplicates,
        papers_total=len(side.entries),
        kept_total=len(lists["kept"]),
        dropped_total=len(lists["dropped"]),
        not_in_index_total=len(lists["not_in_index"]),
        added_total=len(lists["added"]),
        kept_ris_only_total=sum(r.independent is False for r in lists["kept"]),
        dropped_ris_only_total=sum(r.independent is False for r in lists["dropped"]),
        reason_totals=ReasonTotals(**{name: _reasons(rows) for name, rows in lists.items()}),
        **lists,
        not_compared=left_out,
        csv=CompareCsv(
            **{
                name: csv_text(_csv_row(name, r, version, digest) for r in rows)
                for name, rows in lists.items()
            },
            not_compared=csv_text(_left_out_csv(r, version, digest) for r in left_out),
        ),
        added_ris=_added_ris(request, served, extra, digest),
    )
    return Response(response.model_dump_json(), media_type="application/json")


def _added_ris(request: Request, served: Served, ids: list[str], canonical_hash: str) -> str:
    """The papers the query adds, as `GET /export` writes RIS: the same writer over the same display records,
    attributions and withheld abstracts, in id order, counted against the list. Nothing of the file is in it."""
    engine = served.engine
    sources, withheld, twins = sources_of(request, served, engine)
    provenance = Provenance(engine.index_version, canonical_hash, utc_date())
    written = list(
        entries(
            "ris", stored_documents(engine, ids), provenance, sources=sources, withheld=withheld, twins=twins
        )
    )
    check_count(len(written), len(ids))
    return header("ris") + "".join(written)
