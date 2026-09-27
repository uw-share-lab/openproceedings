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
from pathlib import Path
from typing import Any, NoReturn

from fastapi import FastAPI
from fastapi.routing import APIRoute

from openproceedings.api.errors import ErrorEnvelope

# repo-relative; the snapshot sits with the contract tests that pin it
SNAPSHOT = Path("backend/tests/contract/openapi.json")
REGENERATE = "make openapi"  # the one command that rewrites the snapshot and frontend/src/api/schema.ts

# Every non-2xx answer is the one error envelope (`api/errors.py`), a 422 included. Declaring it as the
# `default` response also replaces FastAPI's `HTTPValidationError` 422, which this app never sends.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {"model": ErrorEnvelope, "description": "Error (spec 04 §Error handling)"}
}


def operation_id(route: APIRoute) -> str:
    """The handler's name (`search`, `parse_query`), so generated client types read well. FastAPI's default
    appends the path and the first method of the route's set, which follows PYTHONHASHSEED for a GET+HEAD
    route. Names must be unique across routers: the snapshot test checks."""
    return route.name


def document_head_as_get(app: FastAPI) -> None:
    """Serve the document without the HEAD operations of routes that also answer GET (`/healthz`).

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
