"""The OpenAPI document as a committed, deterministic snapshot (spec 04 §Conventions, api-contract skill).

`op openapi` prints `render()`; `make openapi` writes it to `SNAPSHOT` and regenerates
`frontend/src/api/schema.ts` from it; `backend/tests/contract/test_openapi_snapshot.py` fails when the
live document differs from the committed file, so every contract change shows up in the PR diff.

The document is built from `create_app` without running its lifespan, so no index is loaded and nothing
under `data_dir` is read. It carries no timestamp and no server URL, and keys are sorted, so the same code
always renders the same bytes.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn, get_args

from fastapi import FastAPI
from fastapi.routing import APIRoute

from openproceedings.api.errors import ErrorCode, ErrorEnvelope
from openproceedings.api.models import ChangedInput, CompareReason, MatchedBy, NotComparedReason
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.ingest.dedup import Origin
from openproceedings.ingest.record import ClaimField, Presentation, Source
from openproceedings.query.ast import FilterField, TextField
from openproceedings.query.clauses import CLAUSE_REASONS
from openproceedings.search import NotCounted
from openproceedings.vocab import Status, Track, Venue

# repo-relative; the snapshot sits with the contract tests that pin it
SNAPSHOT = Path("backend/tests/contract/openapi.json")
REGENERATE = "make openapi"  # the one command that rewrites the snapshot and frontend/src/api/schema.ts

API_VERSION = "v1"  # `info.version`: the contract's version (the path's), not the package's


def response_header(description: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """An OpenAPI response header object."""
    return {"description": description, "schema": schema or {"type": "string"}}


# Every non-2xx answer is the one error envelope (`api/errors.py`), a 422 included. Declaring it as the
# `default` response also replaces FastAPI's `HTTPValidationError` 422, which this app never sends. The
# statuses that carry a header of their own are declared too, so the header is in the contract: 405 and 429
# on every rate-limited route, and 503 on the routes that run a query (`BUSY`, declared per route).
METHOD_NOT_ALLOWED: dict[int | str, dict[str, Any]] = {
    405: {
        "model": ErrorEnvelope,
        "description": "API_METHOD_NOT_ALLOWED: the endpoint exists, but not for this method",
        "headers": {
            "Allow": response_header("The methods this endpoint takes, comma-separated (RFC 9110 §10.2.1)")
        },
    }
}
RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorEnvelope,
        "description": (
            "API_RATE_LIMITED: this client's token bucket or its network's (IPv4 /24, IPv6 /48) can't pay "
            "for the request, a query's position-verified clauses included; or, on POST /records, the "
            "save ceiling of this client's network or of the whole instance is reached"
        ),
        "headers": {
            "Retry-After": response_header(
                "Whole seconds until the request would be allowed", {"type": "integer", "minimum": 1}
            )
        },
    }
}
BUSY: dict[int | str, dict[str, Any]] = {
    503: {
        "model": ErrorEnvelope,
        "description": (
            "API_BUSY (with Retry-After): the query needs a slow position check and every verification slot "
            "is taken, or another index version's open (a pinned index_version or record) outlasted the wait "
            "this instance allows; or API_INDEX_NOT_LOADED (no index loaded yet), or on POST /records "
            "API_RECORDS_STORE_FULL (neither sends Retry-After)"
        ),
        "headers": {
            "Retry-After": response_header(
                "Sent with API_BUSY: whole seconds to wait before retrying", {"type": "integer", "minimum": 1}
            )
        },
    }
}
# `POST /compare` (TASK-177): its 503 is also a taken comparison slot, a match table still being built, or a
# comparison past its time; its other statuses are declared so a client can tell them apart by status alone
COMPARE_REFUSALS: dict[int | str, dict[str, Any]] = {
    403: {
        "model": ErrorEnvelope,
        "description": "API_COMPARE_DISABLED: this instance's operator has not turned comparisons on "
        "(`GET /meta` `limits.compare` is null), or the instance offers them to its local user only (on by "
        "`op serve`'s loopback default) and the request came through a proxy or from a page not on that "
        "machine (a non-loopback `Origin`)",
    },
    408: {
        "model": ErrorEnvelope,
        "description": "API_UPLOAD_TIMEOUT: the file didn't arrive within the time one upload gets",
    },
    413: {
        "model": ErrorEnvelope,
        "description": "API_BODY_TOO_LARGE (the file's bytes, refused as they arrive) or API_RIS_TOO_LARGE "
        "(its records, its lines, or one line's length): over a cap of `GET /meta` `limits.compare`, refused "
        "whole, never cut",
    },
    415: {
        "model": ErrorEnvelope,
        "description": "API_UNSUPPORTED_MEDIA_TYPE: the body is not declared "
        "`application/x-research-info-systems` (a form or multipart upload is not read), or has a "
        "`Content-Encoding`",
    },
    422: {
        "model": ErrorEnvelope,
        "description": "API_RIS_INVALID: the file is not UTF-8 RIS (no record, content before the first one, "
        "carriage-return-only lines); API_COMPARE_TOO_COSTLY: the result holds more papers the file doesn't "
        "than `limits.compare.max_results`, a phrase or NEAR has too many inflected spellings, or the answer "
        "would pass `limits.compare.max_response_bytes`; or the query's own refusals, as on /search",
    },
    429: {
        "model": ErrorEnvelope,
        "description": (
            "API_RATE_LIMITED: this client's token bucket or its network's can't pay for the request (as on "
            "every route); or this client's network (IPv4 /24, IPv6 /48) is running a comparison, or ran one "
            "less than its pause ago (decision-035: `compare_cooldown_factor` times the slot time it used; "
            "none on a local instance). Refused before the file is read"
        ),
        "headers": {
            "Retry-After": response_header(
                "Whole seconds until the request would be allowed", {"type": "integer", "minimum": 1}
            )
        },
    },
    503: {
        "model": ErrorEnvelope,
        "description": (
            "API_BUSY (with Retry-After): every comparison slot is taken (refused before the file is read), "
            "the served index's comparison table is still being built (Retry-After: the build's expected time "
            "left), or the query needs a slow position check and every verification slot is taken; API_BUSY "
            "without Retry-After: the comparison ran past the time this instance gives one (the same request "
            "would run as long again), or the table could not be built, until the operator reloads the index "
            "(`limits.compare` is then null); or API_INDEX_NOT_LOADED (no index loaded yet; no Retry-After)"
        ),
        "headers": {
            "Retry-After": response_header(
                "Sent with API_BUSY: whole seconds to wait before retrying", {"type": "integer", "minimum": 1}
            )
        },
    },
}
DEFAULT_ERROR: dict[int | str, dict[str, Any]] = {
    "default": {"model": ErrorEnvelope, "description": "Error (spec 04 §Error handling)"}
}
ERROR_RESPONSES = {**DEFAULT_ERROR, **METHOD_NOT_ALLOWED, **RATE_LIMITED}
HEALTH_RESPONSES = {**DEFAULT_ERROR, **METHOD_NOT_ALLOWED}  # `/healthz` is never rate-limited

# Enums in responses a client must treat as open: a new value may appear within /api/v1 (a venue, a track,
# an error code, …), so a client handles one it doesn't know. Every other enum is closed: a new value in it
# is a breaking change (spec 04 §Conventions, decision-009). `test_contract_v1.py` fails on an enum
# of the document that is in neither table, so a new one is classified when it is added.
OPEN_ENUMS: dict[str, frozenset[str]] = {
    "venue": frozenset(get_args(Venue)),
    "track": frozenset(get_args(Track)),
    "status": frozenset(get_args(Status)),
    "presentation": frozenset(get_args(Presentation)),
    "claim source": frozenset(get_args(Source)),
    "abstract origin": frozenset(get_args(Origin)),  # TASK-134: the site an abstract came from
    "claim field": frozenset(get_args(ClaimField)),
    "text field": frozenset(get_args(TextField)),
    "filter field": frozenset(get_args(FilterField)),
    "diagnostic code": frozenset(DiagnosticCode),
    "error code": frozenset(ErrorCode),
    "changed input": frozenset(get_args(ChangedInput.model_fields["input"].annotation)),
    "clause reason": frozenset(CLAUSE_REASONS),  # why /parse can't toggle a filter clause (decision-011)
    "groups not counted": frozenset(get_args(NotCounted)),  # why /search has no group counts (TASK-176)
    # `POST /compare` (TASK-177): the comparison core's own vocabularies, which a later class or rule extends
    "match rule": frozenset(get_args(MatchedBy)),
    "compare reason": frozenset(get_args(CompareReason)),
    "not compared reason": frozenset(get_args(NotComparedReason)),
}
CLOSED_ENUMS: dict[str, frozenset[str]] = {
    "mode": frozenset({"native", "scholar"}),
    "sort": frozenset({"relevance", "year_desc", "year_asc", "title"}),
    "export format": frozenset({"ris", "csv", "bibtex", "jsonl"}),
    "replay status": frozenset({"reproduced", "drifted", "mismatch"}),
    "drift kind": frozenset({"corpus", "method"}),
    "wildcard op": frozenset({"*", "$"}),
    "include": frozenset({"ids"}),
    # `X-Abstract-Source` on an export's 200 (decision-021; `api/export.py::ABSTRACT_SOURCE_STATES`)
    "abstract source state": frozenset({"attributed", "unavailable"}),
}
OPEN_NOTE = "Open set: new values may be added within /api/v1; handle a value you don't know."


def operation_id(route: APIRoute) -> str:
    """The handler's name, `verb_noun` (`search`, `parse_query`, `get_paper`, `create_record`), so generated
    client types read well. FastAPI's default appends the path and the first method of the route's set,
    which follows PYTHONHASHSEED for a GET+HEAD route. Names must be unique across routers: the snapshot test
    checks."""
    return route.name


def enum_schemas(node: Any) -> Iterator[dict[str, Any]]:
    """Every schema object in `node` (an OpenAPI document or part of one) that has an `enum`."""
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            yield node
        for value in node.values():
            yield from enum_schemas(value)
    elif isinstance(node, list):
        for value in node:
            yield from enum_schemas(value)


def unclassified_enums(document: dict[str, Any]) -> list[tuple[str, ...]]:
    """The value sets of the document's enums that are in neither OPEN_ENUMS nor CLOSED_ENUMS."""
    known = {*OPEN_ENUMS.values(), *CLOSED_ENUMS.values()}
    return sorted(
        {tuple(sorted(s["enum"])) for s in enum_schemas(document)} - {tuple(sorted(k)) for k in known}
    )


def mark_open_enums(document: dict[str, Any]) -> None:
    """Say on every open enum's schema that it is open (the description a generated client shows)."""
    open_sets = set(OPEN_ENUMS.values())
    for schema in enum_schemas(document):
        if frozenset(schema["enum"]) in open_sets and OPEN_NOTE not in schema.get("description", ""):
            schema["description"] = " ".join(filter(None, (schema.get("description"), OPEN_NOTE)))


REF = "#/components/schemas/"


def refs(node: Any) -> Iterator[str]:
    """The component schema names `node` refers to (`$ref` anywhere inside it)."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(REF):
            yield ref.removeprefix(REF)
        for value in node.values():
            yield from refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from refs(value)


def request_schemas(document: dict[str, Any]) -> set[str]:
    """The component schemas a request body names (`ParseRequest`, `RecordRequest`), and every schema they
    refer to, however deeply: a model nested in a request body is refused whole by the server, so it stays
    closed too."""
    schemas = document.get("components", {}).get("schemas", {})
    todo = [
        name
        for item in document.get("paths", {}).values()
        for op in item.values()
        if isinstance(op, dict)
        for name in refs(op.get("requestBody", {}))
    ]
    names: set[str] = set()
    while todo:
        name = todo.pop()
        if name not in names:
            names.add(name)
            todo.extend(refs(schemas.get(name, {})))
    return names


def open_response_objects(document: dict[str, Any]) -> None:
    """Drop `additionalProperties: false` from every schema but a request body's. The server never sends an
    unknown key (`extra="forbid"` holds it to that), but adding a response field is non-breaking within
    /api/v1 (spec 04 §Conventions: clients ignore unknown keys), so the document must not tell a generated
    client to reject one. A request body stays closed: the server refuses a key it doesn't know."""
    requests = request_schemas(document)

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("additionalProperties") is False:
                del node["additionalProperties"]
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    for name, schema in document.get("components", {}).get("schemas", {}).items():
        if name not in requests:
            strip(schema)


def integer_bounds(node: Any) -> None:
    """An integer schema's `minimum`/`maximum` as integers (pydantic emits `ge=1000` as `1000.0`)."""
    if isinstance(node, dict):
        if node.get("type") == "integer":
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                value = node.get(key)
                if isinstance(value, float) and value.is_integer():
                    node[key] = int(value)
        for value in node.values():
            integer_bounds(value)
    elif isinstance(node, list):
        for value in node:
            integer_bounds(value)


def document_head_as_get(app: FastAPI) -> None:
    """Serve the document without the HEAD operations of routes that also answer GET (`/healthz`), with
    every open enum marked as open (`mark_open_enums`), and with response objects open to new keys
    (`open_response_objects`).

    FastAPI gives every method of one route the same operationId, so a GET+HEAD route yields an invalid
    document (a repeated id, which openapi-typescript keys `operations` by). HEAD is GET without a body
    (RFC 9110 §9.3.2), so documenting the GET says everything; the route keeps answering HEAD.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            with warnings.catch_warnings():  # FastAPI's duplicate-id warning, about exactly these operations
                warnings.filterwarnings("ignore", message="Duplicate Operation ID", category=UserWarning)
                schema = generate()
            for item in schema.get("paths", {}).values():
                if "get" in item:
                    item.pop("head", None)
            mark_open_enums(schema)
            open_response_objects(schema)
            integer_bounds(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented override point


def openapi_document() -> dict[str, Any]:
    """The app's OpenAPI document. The config only has to validate: routes and models don't depend on it."""
    from openproceedings.api.app import create_app
    from openproceedings.api.config import ApiConfig

    def never(path: Path) -> NoReturn:  # the lifespan never runs here, so no index is opened
        raise AssertionError("openapi_document must not open an index")

    return create_app(ApiConfig(data_dir=Path("unused")), opener=never).openapi()


def render(document: dict[str, Any] | None = None) -> str:
    """Stable text: sorted keys, two-space indent, raw UTF-8, one trailing newline."""
    doc = openapi_document() if document is None else document
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
