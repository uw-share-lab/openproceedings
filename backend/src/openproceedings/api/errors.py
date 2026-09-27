"""The one error envelope, `{"error": {"code", "message", "diagnostics"?}}` (spec 04 §Error handling).

Every refusal goes through `error_response`. FastAPI's own `RequestValidationError` and `HTTPException`
handlers (which answer `{"detail": …}`) are replaced, so the contract has one error shape. Statuses come
from the registry (`diagnostics.http_status`), never from a call site.

Logging (logging-standards): a refusal of the client's own request is DEBUG with its code; an internal
failure is one ERROR line with the exception's type and frames, never its message or a formatted
traceback, whose last line is the message and can quote the query (task-034 notes).
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from openproceedings.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    InternalError,
    OpenProceedingsError,
    http_status,
)

log = logging.getLogger(__name__)
ACCESS = "openproceedings.access"  # scope key: the request's access-line fields (api/middleware.py)


class ErrorBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: DiagnosticCode
    message: str
    diagnostics: list[Diagnostic] | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    error: ErrorBody


class ApiError(Exception):
    """A refusal with a registry code; its status is the code's (spec 04). `message` is for the client and
    may quote its input, so it is never logged."""

    def __init__(
        self,
        code: DiagnosticCode,
        message: str,
        *,
        diagnostics: Sequence[Diagnostic] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        status = http_status(code)
        if status is None:
            raise ValueError(f"{code} is not an HTTP error code")
        super().__init__(code, message)
        self.code = code
        self.message = message
        self.status = status
        self.diagnostics = list(diagnostics) if diagnostics is not None else None
        self.headers = dict(headers or {})


def error_response(
    code: DiagnosticCode,
    message: str,
    *,
    diagnostics: Sequence[Diagnostic] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    status = http_status(code)
    if status is None:
        raise ValueError(f"{code} is not an HTTP error code")
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code, message=message, diagnostics=list(diagnostics) if diagnostics is not None else None
        )
    )
    content = body.model_dump(mode="json")
    if diagnostics is None:
        del content["error"]["diagnostics"]  # absent, not null; a diagnostic's own null span stays
    return JSONResponse(content, status_code=status, headers=headers)


def frames(exc: BaseException) -> list[str]:
    """`file:line function` for each frame of `exc`'s traceback: where it failed, without what it said."""
    return [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in traceback.extract_tb(exc.__traceback__)]


def request_id(scope: Mapping[str, object]) -> str:
    fields = scope.get(ACCESS)
    return str(fields.get("request_id", "")) if isinstance(fields, dict) else ""


def internal_error(scope: Mapping[str, object], exc: BaseException) -> JSONResponse:
    """Log an unexpected failure once (ERROR: type and frames, never the message) and answer 500
    `API_INTERNAL` naming the request id, so a report can be matched to the log line."""
    cause = exc.__cause__ or exc.__context__
    log.error(
        "request_failed",
        extra={
            "code": str(DiagnosticCode.API_INTERNAL),
            "error": type(exc).__name__,
            "cause": type(cause).__name__ if cause is not None else None,
            "frames": frames(exc),
        },
    )
    rid = request_id(scope)
    return error_response(
        DiagnosticCode.API_INTERNAL,
        f"Something went wrong on our side (request {rid}). Please report it with this id.",
    )


def _refused(code: DiagnosticCode | str) -> None:
    log.debug("request_refused", extra={"code": str(code)})  # the client's own request: DEBUG at most


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    _refused(exc.code)
    return error_response(exc.code, exc.message, diagnostics=exc.diagnostics, headers=exc.headers)


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    """A malformed parameter or body: 422 `API_BAD_PARAM`, naming each bad location and what is wrong
    (pydantic's own text). The offending *value* is left out, but a location can name a key the client
    sent (an unexpected body key). The message goes to that client only; the log gets the code alone."""
    assert isinstance(exc, RequestValidationError)
    problems = [
        f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', 'invalid')}" for e in exc.errors()
    ]
    _refused(DiagnosticCode.API_BAD_PARAM)
    return error_response(
        DiagnosticCode.API_BAD_PARAM, "Check the request's parameters — " + "; ".join(problems) + "."
    )


async def _http(request: Request, exc: Exception) -> JSONResponse:
    """Starlette's routing refusals: no such endpoint (404) or another method (405, with `Allow`)."""
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        _refused(DiagnosticCode.API_NOT_FOUND)
        return error_response(
            DiagnosticCode.API_NOT_FOUND, "There is no such endpoint; the API lives under /api/v1."
        )
    if exc.status_code == 405:
        _refused(DiagnosticCode.API_METHOD_NOT_ALLOWED)
        allow = (exc.headers or {}).get("Allow", "")
        return error_response(
            DiagnosticCode.API_METHOD_NOT_ALLOWED,
            f"This endpoint doesn't take that method; use {allow or 'another'}.",
            headers={"Allow": allow} if allow else None,
        )
    if 400 <= exc.status_code < 500:  # nothing of ours raises one, but a 4xx is the client's, never a 500
        _refused(DiagnosticCode.API_BAD_PARAM)
        return error_response(DiagnosticCode.API_BAD_PARAM, "The request can't be served as sent.")
    return internal_error(request.scope, exc)


QUERY_CODES = ("PARSE_", "FIELD_", "WILDCARD_")  # spec 04 row 1: these refusals carry diagnostics


async def _openproceedings(request: Request, exc: Exception) -> JSONResponse:
    """A typed failure from the shared functions: a user-input one is refused with its own code (e.g. 422
    `WILDCARD_TOO_MANY_EXPANSIONS`), and a query refusal carries its diagnostics: the located ones a
    `search.QueryRefused` holds, else one without a span; an internal one, or one without an HTTP status,
    is a 500."""
    assert isinstance(exc, OpenProceedingsError)
    if isinstance(exc, InternalError) or http_status(exc.code) is None:
        return internal_error(request.scope, exc)
    _refused(exc.code)
    diagnostics: list[Diagnostic] | None = None
    if str(exc.code).startswith(QUERY_CODES):
        located = getattr(exc, "diagnostics", None)
        diagnostics = (
            list(located) if located else [Diagnostic(code=exc.code, message=exc.message, span=None)]
        )
    return error_response(exc.code, exc.message, diagnostics=diagnostics)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(OpenProceedingsError, _openproceedings)
