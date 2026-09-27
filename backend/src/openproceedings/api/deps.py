"""What every route shares: the one engine of a request, the query-length cap, the parse, and the
privacy-safe fields a route adds to its access line.

    @router.get("/search")
    def search(request: Request, engine: EngineDep, q: str, ...) -> SearchResponse:
        result = searchable(request, q, mode)    # PARSE_TOO_LONG before parsing; 422 if it doesn't parse;
                                                 # canonical_hash, token count, codes on the line, never q
        found = run(engine, result, ...)         # openproceedings.search, as `op search` runs it
        annotate(request, total=found.total)

`current_engine` reads `IndexState.engine` once; FastAPI caches a dependency per request, so every use of
`EngineDep` in one request is the same object (hits, total, facets and excluded from one index_version).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from openproceedings.api.errors import ACCESS, ApiError
from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import And, Near, Node, Not, Or, Phrase, Term, Wildcard
from openproceedings.query.parser import Mode, ParseResult, parse, too_long

if TYPE_CHECKING:
    from openproceedings.api.state import IndexState

MAX_LOGGED_CODES = 10  # distinct diagnostic codes on one access line; more are counted, not listed


def access_fields(request: Request) -> dict[str, object]:
    """The mutable field dict of this request's access line (set by the access-log middleware)."""
    fields = request.scope.get(ACCESS)
    if not isinstance(fields, dict):  # an app driven without the middleware (a unit test)
        fields = request.scope[ACCESS] = {}
    return fields


def annotate(
    request: Request,
    *,
    index_version: str | None = None,
    canonical_hash: str | None = None,
    total: int | None = None,
) -> None:
    """Add privacy-safe fields to the access line. Keyword-only and typed, so no query text fits."""
    fields = access_fields(request)
    for key, value in (
        ("index_version", index_version),
        ("canonical_hash", canonical_hash),
        ("total", total),
    ):
        if value is not None:
            fields[key] = value


def _codes(diagnostics: Sequence[Diagnostic]) -> list[str]:
    codes = sorted({str(d.code) for d in diagnostics})
    return codes[:MAX_LOGGED_CODES] + (
        [f"+{len(codes) - MAX_LOGGED_CODES}"] if len(codes) > MAX_LOGGED_CODES else []
    )


def token_count(node: Node | None) -> int:
    """How many search terms a query tree holds (each term or wildcard, phrase words one by one)."""
    match node:
        case Term() | Wildcard():
            return 1
        case Phrase():
            return len(node.items)
        case Near():
            return token_count(node.left) + token_count(node.right)
        case Not():
            return token_count(node.child)
        case And() | Or():
            return sum(token_count(c) for c in node.children)
        case _:  # a filter, or no tree
            return 0


def parse_fields(result: ParseResult) -> dict[str, object]:
    """A parse, as the access line may carry it (AC5): the hash, the term count and the diagnostic codes
    (capped); never the input, the canonical or identification strings, messages or spans."""
    fields: dict[str, object] = {
        "token_count": token_count(result.ast),
        "n_errors": len(result.errors),
        "error_codes": _codes(result.errors),
        "warning_codes": _codes([*result.warnings, *result.translations]),
    }
    if result.canonical_hash is not None:
        fields["canonical_hash"] = result.canonical_hash
    return fields


def annotate_parse(request: Request, result: ParseResult) -> None:
    access_fields(request).update(parse_fields(result))


def checked_query(q: str) -> str:
    """`q` if it is within the query-length cap; otherwise 422 `PARSE_TOO_LONG` with the parser's own
    diagnostic, raised before anything reads the query (O(1): a length check)."""
    over = too_long(q)
    if over is not None:
        raise ApiError(over.code, over.message, diagnostics=[over])
    return q


def parsed(request: Request, q: str, mode: Mode) -> ParseResult:
    """`parse(q, mode)`, annotated on the access line, after the length cap (`checked_query`)."""
    result = parse(checked_query(q), mode)
    annotate_parse(request, result)
    return result


def searchable(request: Request, q: str, mode: Mode) -> ParseResult:
    """`parsed`, refusing a query that doesn't parse: 422 with the first error's code and every error as a
    diagnostic, spans into `q` (spec 04 §Error handling). The engine never sees it (spec 03)."""
    result = parsed(request, q, mode)
    if result.effective_ast is None:
        first = result.errors[0]
        raise ApiError(first.code, first.message, diagnostics=result.errors)
    return result


def current_engine(request: Request) -> TantivyEngine:
    """The engine this request uses, read once; 503 `API_INDEX_NOT_LOADED` while none is loaded."""
    state: IndexState = request.app.state.index
    engine = state.engine
    if engine is None:
        raise ApiError(
            DiagnosticCode.API_INDEX_NOT_LOADED,
            "No index is loaded yet (the service is starting, or its index failed to load). Try again shortly.",
        )
    annotate(request, index_version=engine.index_version)
    return engine


EngineDep = Annotated[TantivyEngine, Depends(current_engine)]
