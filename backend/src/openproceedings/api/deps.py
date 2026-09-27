"""What every route shares: the one engine of a request, the query-length cap, the parse, and the
privacy-safe fields a route adds to its access line.

    @router.get("/search")
    def search(request: Request, engine: EngineDep, q: str, ...) -> SearchResponse:
        result = searchable(request, q, mode)    # PARSE_TOO_LONG before parsing; 422 if it doesn't parse;
                                                 # canonical_hash, token count, codes on the line, never q
        found = run(engine, result, ...)         # openproceedings.search, as `op search` runs it
        annotate(request, total=found.total)

`current_served` reads `IndexState.served` once; FastAPI caches a dependency per request, so every use of
`ServedDep` and `EngineDep` in one request is the same bundle and engine (hits, total, facets and excluded from one index_version).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from openproceedings.api.errors import ACCESS, ApiError
from openproceedings.api.middleware import charge
from openproceedings.api.state import Served
from openproceedings.diagnostics import Diagnostic, DiagnosticCode, clip
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import And, Near, Node, Not, Or, Phrase, Term, Wildcard
from openproceedings.query.parser import Mode, ParseResult, parse, too_long

if TYPE_CHECKING:
    from openproceedings.api.state import IndexState

MAX_LOGGED_CODES = 10  # distinct diagnostic codes on one access line; more are counted, not listed
MAX_NAMED_PARAMS = 5  # unknown or repeated parameters a refusal names; more are counted
# a route's query parameter names are cached on the route itself (it lives and dies with them): a global
# map keyed by `id(route)` handed a new app's route the names of a collected one that had its id (M3a round 2)
DECLARED_ATTR = "_openproceedings_declared_query"


def _query_names(dependant: Dependant) -> set[str]:
    names = {p.alias for p in dependant.query_params}
    for sub in dependant.dependencies:
        names |= _query_names(sub)
    return names


def declared_query(route: APIRoute) -> frozenset[str]:
    """The query parameter names `route` declares (aliases, e.g. `/export`'s `format`), its dependencies'
    included."""
    names: frozenset[str] | None = route.__dict__.get(DECLARED_ATTR)
    if names is None:
        names = frozenset(_query_names(route.dependant))
        setattr(route, DECLARED_ATTR, names)
    return names


async def strict_query(request: Request) -> None:
    """422 `API_BAD_PARAM` for a query parameter the route doesn't declare (`/search?limt=5` would otherwise
    be answered as if `limit` were the default) or one given more than once (`?q=a&q=b`: which one ran?).
    Every route has it (`create_app`'s app-wide dependency); it runs before the route's own parameters are
    read, on the event loop (`async`: it does no I/O, so it needs no worker thread). The message names the parameters (the client's own keys, clipped); the log gets the code only."""
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return
    allowed = declared_query(route)
    counts: dict[str, int] = {}
    for key, _value in request.query_params.multi_items():
        counts[key] = counts.get(key, 0) + 1
    unknown = sorted(k for k in counts if k not in allowed)
    repeated = sorted(k for k, n in counts.items() if k in allowed and n > 1)
    problems = [
        *(f"unknown parameter `{clip(k, 30)}`" for k in unknown),
        *(f"`{k}` given more than once" for k in repeated),
    ]
    if problems:
        shown = problems[:MAX_NAMED_PARAMS] + (
            [f"{len(problems) - MAX_NAMED_PARAMS} more"] if len(problems) > MAX_NAMED_PARAMS else []
        )
        expected = ", ".join(f"`{n}`" for n in sorted(allowed)) or "none"
        raise ApiError(
            DiagnosticCode.API_BAD_PARAM,
            f"Check the request's parameters — {'; '.join(shown)}. This endpoint takes: {expected}.",
        )


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
    """`parse(q, mode)`, annotated on the access line: a report, never a refusal (`POST /parse`). `parse`
    checks the length cap first, in O(1), so an over-long query is `errors=[PARSE_TOO_LONG]`, never lexed."""
    result = parse(q, mode)
    annotate_parse(request, result)
    return result


def searchable(request: Request, q: str, mode: Mode) -> ParseResult:
    """`parsed`, refusing a query that doesn't parse: 422 with the first error's code and every error as a
    diagnostic, spans into `q` (spec 04 §Error handling). The engine never sees it (spec 03)."""
    result = parsed(request, checked_query(q), mode)
    if result.effective_ast is None:
        first = result.errors[0]
        raise ApiError(first.code, first.message, diagnostics=result.errors)
    charge_verified(request, result.effective_ast)  # every route that runs a query parses it here
    return result


def verified_clauses(node: Node | None) -> list[Phrase | Near]:
    """Every clause of `node` that compiles to the position-verified path, in query order: the rule of
    `engine.compile.verifies` (a phrase with a wildcard item, a NEAR that isn't two distinct terms), counted
    rather than tested. A test holds `bool(verified_clauses(n)) == verifies(n)` and the count equal to the
    compiler's own."""
    match node:
        case Phrase() if not all(isinstance(i, Term) for i in node.items):
            return [node]
        case Near() if not (
            isinstance(node.left, Term)
            and isinstance(node.right, Term)
            and node.left.token != node.right.token
        ):
            return [node]
        case Not():
            return verified_clauses(node.child)
        case And() | Or():
            return [clause for c in node.children for clause in verified_clauses(c)]
        case _:
            return []


def too_many_verified(clauses: Sequence[Phrase | Near], cap: int, *, located: bool = True) -> ApiError:
    """422 `API_TOO_MANY_VERIFIED_CLAUSES`: one diagnostic per verified clause, each spanning it in `q`
    (`located=False`: a replay, whose query is the record's canonical string, not the client's `q`)."""
    message = (
        f"This query has {len(clauses)} clauses that need a slow position check (a phrase with a wildcard, "
        f"or a NEAR of anything but two different words); this instance runs at most {cap} in one query. "
        "Split it into several searches, or write some of them as plain phrases."
    )
    diagnostics = (
        [
            Diagnostic(
                code=DiagnosticCode.API_TOO_MANY_VERIFIED_CLAUSES,
                message="This clause needs a slow position check.",
                span=c.span,
            )
            for c in clauses
        ]
        if located
        else [Diagnostic(code=DiagnosticCode.API_TOO_MANY_VERIFIED_CLAUSES, message=message)]
    )
    return ApiError(DiagnosticCode.API_TOO_MANY_VERIFIED_CLAUSES, message, diagnostics=diagnostics)


def charge_verified(request: Request, ast: Node | None, *, located: bool = True) -> None:
    """A query's position-verified clauses (spec 03), counted from the AST before anything compiles it: more
    than `ApiConfig.max_verified_clauses` is 422 `API_TOO_MANY_VERIFIED_CLAUSES` (each is a cold
    verification holding a slot for seconds, so one request could otherwise hold the slots for a minute);
    otherwise the query costs `verified_weight` per clause (`RateLimit.verified_charge`): the rest is charged
    now, or 429 `API_RATE_LIMITED` (spec 04 §Rate limit). Every route that runs a query calls this: through
    `searchable`, or on a replay's re-parsed canonical (`api/records.py`)."""
    clauses = verified_clauses(ast)
    if not clauses:
        return
    config = request.app.state.config
    if len(clauses) > config.max_verified_clauses:
        raise too_many_verified(clauses, config.max_verified_clauses, located=located)
    if config.rate_limit.enabled:
        charge(request.scope, config.rate_limit.verified_charge(len(clauses)))


def current_served(request: Request) -> Served:
    """The served index this request uses (engine, records, coverage), read once; 503
    `API_INDEX_NOT_LOADED` while none is loaded."""
    state: IndexState = request.app.state.index
    served = state.served
    if served is None:
        raise ApiError(
            DiagnosticCode.API_INDEX_NOT_LOADED,
            "No index is loaded yet (the service is starting, or its index failed to load). Try again shortly.",
        )
    annotate(request, index_version=served.engine.index_version)
    return served


ServedDep = Annotated[Served, Depends(current_served)]


def current_engine(served: ServedDep) -> TantivyEngine:
    """The engine of the request's one read of the served index (FastAPI caches `current_served` per request,
    so a route taking both gets one bundle)."""
    return served.engine


EngineDep = Annotated[TantivyEngine, Depends(current_engine)]
