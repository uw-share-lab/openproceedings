"""The one Diagnostic shape and the registry of every code (error-diagnostics skill).

Codes are `AREA_SNAKE_NAME` and stable forever once released: retire a code, never rename or reuse it.
HTTP statuses for `API_*` codes are exactly spec 04 §Error handling; `PARSE_*` errors are 422.
`API_REPLAY_MISMATCH` is a log code only: a replay mismatch is a 200 whose `status` field is `mismatch`.
Adding a code needs: an entry here, a golden test that produces it with its span, and the help table.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Strict, field_validator


class DiagnosticCode(StrEnum):
    # grammar (spec 02 §Error handling)
    PARSE_UNBALANCED_PAREN = "PARSE_UNBALANCED_PAREN"
    PARSE_EMPTY_GROUP = "PARSE_EMPTY_GROUP"
    PARSE_ALL_NEGATIVE = "PARSE_ALL_NEGATIVE"
    PARSE_UNTERMINATED_PHRASE = "PARSE_UNTERMINATED_PHRASE"
    PARSE_BAD_NEAR = "PARSE_BAD_NEAR"
    PARSE_WILDCARD_NOT_SUFFIX = "PARSE_WILDCARD_NOT_SUFFIX"
    PARSE_EXPECTED_TERM = "PARSE_EXPECTED_TERM"
    PARSE_EMPTY_TERM = "PARSE_EMPTY_TERM"
    PARSE_NESTED_FIELD = "PARSE_NESTED_FIELD"
    PARSE_TOO_DEEP = "PARSE_TOO_DEEP"
    PARSE_WILDCARD_DETACHED = "PARSE_WILDCARD_DETACHED"
    PARSE_AMBIGUOUS_MINUS = "PARSE_AMBIGUOUS_MINUS"
    PARSE_STRAY_COLON = "PARSE_STRAY_COLON"
    # wildcard expansion
    WILDCARD_STEM_TOO_SHORT = "WILDCARD_STEM_TOO_SHORT"
    WILDCARD_TOO_MANY_EXPANSIONS = "WILDCARD_TOO_MANY_EXPANSIONS"
    # fields and filters
    FIELD_UNKNOWN = "FIELD_UNKNOWN"
    FIELD_UNKNOWN_VALUE = "FIELD_UNKNOWN_VALUE"
    FIELD_RANGE_INVERTED = "FIELD_RANGE_INVERTED"
    FIELD_FILTER_SYNTAX = "FIELD_FILTER_SYNTAX"
    FIELD_COMPAT_ONLY = "FIELD_COMPAT_ONLY"
    # warnings (shown, never auto-fixed; they do not change what a query means)
    WARN_LOWERCASE_OPERATOR = "WARN_LOWERCASE_OPERATOR"
    WARN_MIXED_AND_OR = "WARN_MIXED_AND_OR"
    WARN_NESTED_FILTER = "WARN_NESTED_FILTER"
    WARN_FILTER_SCOPE = "WARN_FILTER_SCOPE"
    WARN_LOOKALIKE_OPERATOR = "WARN_LOOKALIKE_OPERATOR"
    WARN_SYMBOLS_DROPPED = "WARN_SYMBOLS_DROPPED"
    WARN_SOURCE_PARTIAL = "WARN_SOURCE_PARTIAL"
    # scholar/PoP compatibility translations
    COMPAT_SOURCE_ALIAS = "COMPAT_SOURCE_ALIAS"
    COMPAT_POP_DOLLAR = "COMPAT_POP_DOLLAR"
    COMPAT_POP_PHRASE = "COMPAT_POP_PHRASE"
    # HTTP layer (spec 04 §Error handling)
    API_BAD_PARAM = "API_BAD_PARAM"
    API_PAPER_NOT_FOUND = "API_PAPER_NOT_FOUND"
    API_RECORD_NOT_FOUND = "API_RECORD_NOT_FOUND"
    API_INDEX_VERSION_UNAVAILABLE = "API_INDEX_VERSION_UNAVAILABLE"
    API_RECORD_MISMATCH = "API_RECORD_MISMATCH"
    API_RATE_LIMITED = "API_RATE_LIMITED"
    API_INDEX_NOT_LOADED = "API_INDEX_NOT_LOADED"
    API_INTERNAL = "API_INTERNAL"
    API_REPLAY_MISMATCH = "API_REPLAY_MISMATCH"  # log code only — never an HTTP error


_API_STATUS: dict[DiagnosticCode, int] = {
    DiagnosticCode.API_BAD_PARAM: 422,
    DiagnosticCode.API_PAPER_NOT_FOUND: 404,
    DiagnosticCode.API_RECORD_NOT_FOUND: 404,
    DiagnosticCode.API_INDEX_VERSION_UNAVAILABLE: 409,
    DiagnosticCode.API_RECORD_MISMATCH: 409,
    DiagnosticCode.API_RATE_LIMITED: 429,
    DiagnosticCode.API_INDEX_NOT_LOADED: 503,
    DiagnosticCode.API_INTERNAL: 500,
}


def http_status(code: DiagnosticCode) -> int | None:
    """The HTTP status an error with this code is returned with, or None if it is never an HTTP error."""
    if code in _API_STATUS:
        return _API_STATUS[code]
    if code.startswith("PARSE_"):
        return 422
    return None


class Diagnostic(BaseModel):
    """A warning, error or translation notice about a query, with a half-open code-point span into `q`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: DiagnosticCode
    message: str
    span: tuple[Annotated[int, Strict()], Annotated[int, Strict()]] | None = None

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a diagnostic message must say what is wrong and how to fix it")
        return v

    @field_validator("span")
    @classmethod
    def _half_open(cls, v: tuple[int, int] | None) -> tuple[int, int] | None:
        if v is not None and not (0 <= v[0] <= v[1]):
            raise ValueError(f"span must be a half-open [start, end) range with 0 <= start <= end, got {v}")
        return v


class OpenProceedingsError(Exception):
    """Base for internal failures. Each carries a registry code; the API edge maps it to an error envelope."""

    def __init__(self, code: DiagnosticCode, message: str) -> None:
        super().__init__(code, message)  # both args, so the error pickles across processes
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
