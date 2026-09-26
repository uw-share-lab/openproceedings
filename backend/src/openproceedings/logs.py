"""Logging configuration: the only place logging is configured (logging-standards skill).

One JSON object per line (`ts`, `level`, `logger`, `event`, then fields). `event` is a snake_case constant;
variable data goes in `extra=` fields, never into the message. A `text` format exists for reading logs
locally; JSON is the default everywhere.

Privacy (Must, logging-standards §Privacy):
- query text (`q`, `query`, `input`, `canonical`, `identification_query`) is redacted unless
  `log_query_text=True`, which is for a local dev instance only;
- abstracts, author lists, request bodies/headers/cookies and anything secret-shaped (a key containing
  `password`, `token`, `secret`, `api_key`/`apikey`, `auth`, `cookie`, `credential`) are always redacted;
- key matching is case-insensitive and reaches into nested dicts and lists;
- credentials are scrubbed from URLs and from exception text (`user:pass@`, `?token=…`), so an HTTP-client
  error can never carry an OpenReview password into a log.

Request-scoped fields are added with `bind(...)` (contextvars): they follow asyncio tasks and anyio
`to_thread` workers, but NOT raw `threading.Thread` / `ThreadPoolExecutor` workers — bind inside those.
"""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import logging
import re
import sys
import types
from collections.abc import Iterator, Mapping
from typing import IO

ROOT = "openproceedings"
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
FORMATS = ("json", "text")
CORE_KEYS = frozenset({"ts", "level", "logger", "event", "exc", "stack"})
QUERY_FIELDS = frozenset({"q", "query", "input", "canonical", "identification_query"})
ALWAYS_REDACTED = frozenset(
    {"abstract", "abstracts", "authors", "body", "headers", "cookies", "set_cookie", "authorization"}
)
SECRET_PARTS = ("password", "passwd", "token", "secret", "api_key", "apikey", "auth", "cookie", "credential")
REDACTED = "[redacted]"

_URL_USERINFO = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@")
_SECRET_QUERY = re.compile(
    r"(?P<k>[?&](?:[a-z0-9_]*?(?:token|key|secret|password|passwd|auth|sig|signature)[a-z0-9_]*))=[^&\s#]*",
    re.IGNORECASE,
)

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


def scrub(text: str) -> str:
    """Remove credentials from any URLs in `text`: userinfo (`user:pass@`) and secret-looking query params."""
    text = _URL_USERINFO.sub(r"\g<scheme>" + REDACTED + "@", text)
    return _SECRET_QUERY.sub(r"\g<k>=" + REDACTED, text)


def _sensitive(key: str, log_query_text: bool) -> bool:
    k = key.lower()
    if k in ALWAYS_REDACTED or any(part in k for part in SECRET_PARTS):
        return True
    return k in QUERY_FIELDS and not log_query_text


def _clean(value: object, log_query_text: bool) -> object:
    if isinstance(value, Mapping):
        return {
            str(k): (REDACTED if _sensitive(str(k), log_query_text) else _clean(v, log_query_text))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [_clean(v, log_query_text) for v in value]
    if isinstance(value, str):
        return scrub(value)
    return value


def _fields(record: logging.LogRecord, log_query_text: bool) -> dict[str, object]:
    raw: dict[str, object] = dict(_context.get())
    raw.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
    out: dict[str, object] = {}
    for key, value in raw.items():
        name = f"field_{key}" if key in CORE_KEYS else key  # a field can never overwrite the line's shape
        out[name] = REDACTED if _sensitive(key, log_query_text) else _clean(value, log_query_text)
    return out


class _Formatter(logging.Formatter):
    def __init__(self, log_query_text: bool) -> None:
        super().__init__()
        self._log_query_text = log_query_text

    def _extras(self, record: logging.LogRecord) -> dict[str, object]:
        fields = _fields(record, self._log_query_text)
        if record.exc_info:
            fields["exc"] = scrub(self.formatException(record.exc_info))
        if record.stack_info:
            fields["stack"] = scrub(self.formatStack(record.stack_info))
        return fields


class _JsonFormatter(_Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = dt.datetime.fromtimestamp(record.created, tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        line: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        line.update(self._extras(record))
        return json.dumps(line, default=str, ensure_ascii=False)


class _TextFormatter(_Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Values are JSON-encoded, so a newline inside a value can never start a forged log line.
        parts = [
            f"{k}={json.dumps(v, default=str, ensure_ascii=False)}" for k, v in self._extras(record).items()
        ]
        return f"{record.levelname:<7} {record.name}: {record.getMessage()}" + (
            "  " + " ".join(parts) if parts else ""
        )


def configure_logging(
    level: str = "INFO", fmt: str = "json", *, stream: IO[str] | None = None, log_query_text: bool = False
) -> None:
    """Configure the `openproceedings` logger. Idempotent: closes and replaces any handler a previous call
    installed. Library loggers (uvicorn, httpx) are routed by the API startup (task-034), not here."""
    if level.upper() not in LEVELS:
        raise ValueError(f"unknown log level {level!r}; use one of {', '.join(LEVELS)}")
    formatters: dict[str, type[_Formatter]] = {"json": _JsonFormatter, "text": _TextFormatter}
    if fmt not in formatters:
        raise ValueError(f"unknown log format {fmt!r}; use one of {', '.join(FORMATS)}")
    logger = logging.getLogger(ROOT)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(formatters[fmt](log_query_text))
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
