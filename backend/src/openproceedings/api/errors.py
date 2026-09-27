"""The one error envelope, `{"error": {"code", "message", "diagnostics"?}}` (spec 04 §Error handling).

Every refusal goes through `error_response`. FastAPI's own `RequestValidationError` and `HTTPException`
handlers (which answer `{"detail": …}`) are replaced, so the contract has one error shape. Statuses come
from the registry (`diagnostics.http_status`), never from a call site.

Logging (logging-standards): a refusal of the client's own request is DEBUG with its code; an internal
failure is one ERROR line with the exception's type and frames, never its message or a formatted
traceback, whose last line is the message and can quote the query (task-034 notes).
"""

from __future__ import annotations

import errno
import logging
import traceback
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
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

if TYPE_CHECKING:
    ErrorCode = DiagnosticCode
else:
    # The codes an error envelope can carry: the registry's codes that have an HTTP status (`PARSE_*`,
    # `FIELD_*`, `WILDCARD_*` and every `API_*` one but `API_REPLAY_MISMATCH`), as a schema of its own, so a
    # client's switch over `error.code` holds no warning or log-only code. Derived from the registry, never
    # hand-listed; a contract test compares the two.
    ErrorCode = StrEnum(
        "ErrorCode", {c.name: c.value for c in DiagnosticCode if http_status(c) is not None}, module=__name__
    )
    ErrorCode.__doc__ = "An error envelope's code (spec 04 §Error handling)."


class ErrorBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode
    message: str
    # present (non-empty) on a query refusal (`PARSE_*`, `FIELD_*`, `WILDCARD_*`,
    # `API_TOO_MANY_VERIFIED_CLAUSES`), absent otherwise; never null
    diagnostics: list[Diagnostic] | SkipJsonSchema[None] = Field(default=None)


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


def reason_of(exc: BaseException) -> str | None:
    """A constant that says why `exc` happened, never its message: its `reason` (SnapshotError,
    IndexBuildError, IndexSelectionError, IndexUnservable), or an OSError's errno name (`ENOENT`)."""
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str):
        return reason
    if isinstance(exc, OSError) and exc.errno is not None:
        return errno.errorcode.get(exc.errno, str(exc.errno))
    return None


def request_id(scope: Mapping[str, object]) -> str:
    fields = scope.get(ACCESS)
    return str(fields.get("request_id", "")) if isinstance(fields, dict) else ""


def note_code(scope: Mapping[str, object], code: DiagnosticCode | str) -> None:
    """Put an error envelope's code on the request's access line (`code`): every refusal and every 500."""
    fields = scope.get(ACCESS)
    if isinstance(fields, dict):
        fields["code"] = str(code)


def internal_error(scope: Mapping[str, object], exc: BaseException) -> JSONResponse:
    """Log an unexpected failure once (ERROR: type and frames, never the message) and answer 500
    `API_INTERNAL` naming the request id, so a report can be matched to the log line."""
    cause = exc.__cause__ or exc.__context__
    fields: dict[str, object] = {
        "code": str(DiagnosticCode.API_INTERNAL),
        "error": type(exc).__name__,
        "frames": frames(exc),
    }
    if cause is not None:  # absent, not null, when there is none
        fields["cause"] = type(cause).__name__
        # Starlette wraps an exception its handlers catch after the response started (a stream failing
        # mid-body) in a RuntimeError whose own frames stop at the handler; where it failed is the cause's
        fields["cause_frames"] = frames(cause)
        reason = reason_of(cause)
        if reason is not None:
            fields["cause_reason"] = reason
    log.error("request_failed", extra=fields)
    note_code(scope, DiagnosticCode.API_INTERNAL)
    rid = request_id(scope)
    return error_response(
        DiagnosticCode.API_INTERNAL,
        f"Something went wrong on our side (request {rid}). Please report it with this id.",
    )


def refused(scope: Mapping[str, object], code: DiagnosticCode | str) -> None:
    """A refusal of the client's own request: its code on the access line, and a DEBUG line at most."""
    note_code(scope, code)
    log.debug("request_refused", extra={"code": str(code)})


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    refused(request.scope, exc.code)
    return error_response(exc.code, exc.message, diagnostics=exc.diagnostics, headers=exc.headers)


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    """A malformed parameter or body: 422 `API_BAD_PARAM`, naming each bad location and what is wrong
    (pydantic's own text). The offending *value* is left out, but a location can name a key the client
    sent (an unexpected body key). The message goes to that client only; the log gets the code alone."""
    assert isinstance(exc, RequestValidationError)
    problems = [
        f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', 'invalid')}" for e in exc.errors()
    ]
    refused(request.scope, DiagnosticCode.API_BAD_PARAM)
    return error_response(
        DiagnosticCode.API_BAD_PARAM, "Check the request's parameters — " + "; ".join(problems) + "."
    )


async def _http(request: Request, exc: Exception) -> JSONResponse:
    """Starlette's routing refusals: no such endpoint (404) or another method (405, with `Allow`)."""
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        refused(request.scope, DiagnosticCode.API_NOT_FOUND)
        return error_response(
            DiagnosticCode.API_NOT_FOUND, "There is no such endpoint; the API lives under /api/v1."
        )
    if exc.status_code == 405:
        refused(request.scope, DiagnosticCode.API_METHOD_NOT_ALLOWED)
        allow = (exc.headers or {}).get("Allow", "")
        return error_response(
            DiagnosticCode.API_METHOD_NOT_ALLOWED,
            f"This endpoint doesn't take that method; use {allow or 'another'}.",
            headers={"Allow": allow} if allow else None,
        )
    if 400 <= exc.status_code < 500:  # nothing of ours raises one, but a 4xx is the client's, never a 500
        refused(request.scope, DiagnosticCode.API_BAD_PARAM)
        return error_response(DiagnosticCode.API_BAD_PARAM, "The request can't be served as sent.")
    return internal_error(request.scope, exc)


QUERY_CODES = ("PARSE_", "FIELD_", "WILDCARD_")  # spec 04 row 1: these refusals carry diagnostics


async def _openproceedings(request: Request, exc: Exception) -> JSONResponse:
    """A typed failure from the shared functions: a user-input one is refused with its own code (e.g. 422
    `WILDCARD_TOO_MANY_EXPANSIONS`), and a query refusal carries its diagnostics: the located ones a
    an `EngineInputError` holds (`search.run` locates them), else one without a span; an internal one, or one without an HTTP status,
    is a 500."""
    assert isinstance(exc, OpenProceedingsError)
    if isinstance(exc, InternalError) or http_status(exc.code) is None:
        return internal_error(request.scope, exc)
    refused(request.scope, exc.code)
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
