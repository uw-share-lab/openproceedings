"""Logging configuration: the only place logging is configured (logging-standards skill).

One JSON object per line (`ts`, `level`, `logger`, `event`, then fields). `event` is a snake_case constant;
variable data goes in `extra=` fields, never into the message. Query text is redacted unless
`log_query_text=True` (local development only); abstracts and secrets are always redacted. Request-scoped
fields (request id, index version) are added to every line inside `bind(...)`.
"""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import logging
import sys
import types
from collections.abc import Iterator, Mapping
from typing import IO, Any

ROOT = "openproceedings"
QUERY_FIELDS = frozenset({"q", "query", "input", "canonical", "identification_query"})
ALWAYS_REDACTED = frozenset({"abstract", "password", "token", "authorization", "cookie", "secret"})
REDACTED = "[redacted]"

# Attributes every LogRecord has; anything else on a record came from `extra=` or `bind()`.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}
_context: contextvars.ContextVar[Mapping[str, object]] = contextvars.ContextVar(
    "op_log_context", default=types.MappingProxyType({})
)


@contextlib.contextmanager
def bind(**fields: object) -> Iterator[None]:
    """Add `fields` to every log line emitted inside the block (per task/request, via contextvars)."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def _fields(record: logging.LogRecord, log_query_text: bool) -> dict[str, object]:
    out: dict[str, object] = dict(_context.get())
    out.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
    for key in out:
        if key in ALWAYS_REDACTED or (key in QUERY_FIELDS and not log_query_text):
            out[key] = REDACTED
    return out


class _JsonFormatter(logging.Formatter):
    def __init__(self, log_query_text: bool) -> None:
        super().__init__()
        self._log_query_text = log_query_text

    def format(self, record: logging.LogRecord) -> str:
        ts = dt.datetime.fromtimestamp(record.created, tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        line: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        line.update(_fields(record, self._log_query_text))
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def __init__(self, log_query_text: bool) -> None:
        super().__init__()
        self._log_query_text = log_query_text

    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(f"{k}={v}" for k, v in _fields(record, self._log_query_text).items())
        text = f"{record.levelname:<7} {record.name}: {record.getMessage()}" + (
            f" {fields}" if fields else ""
        )
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def configure_logging(
    level: str = "INFO", fmt: str = "json", *, stream: IO[str] | None = None, log_query_text: bool = False
) -> None:
    """Configure the `openproceedings` logger. Idempotent: replaces any handler a previous call installed."""
    formatters: dict[str, Any] = {"json": _JsonFormatter, "text": _TextFormatter}
    if fmt not in formatters:
        raise ValueError(f"unknown log format {fmt!r}; use one of {sorted(formatters)}")
    logger = logging.getLogger(ROOT)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(formatters[fmt](log_query_text))
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
