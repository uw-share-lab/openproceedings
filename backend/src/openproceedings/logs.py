"""Logging configuration: the only place logging is configured (logging-standards skill).

One JSON object per line (`ts`, `level`, `logger`, `event`, then fields). `event` is a snake_case constant;
variable data goes in `extra=` fields, never into the message. A `text` format exists for reading logs
locally; JSON is the default everywhere.

Privacy (Must, logging-standards §Privacy):
- query text (`q`, `query`, `input`, `canonical`, `identification_query`) is redacted unless
  `log_query_text=True`, which is for a local dev instance only;
- abstracts, author lists, request bodies/headers/cookies and anything secret-shaped (a key STARTING or ENDING with
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
import errno
import json
import logging
import re
import sys
import time
import traceback
import types
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import IO

ROOT = "openproceedings"
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
FORMATS = ("json", "text")
CORE_KEYS = frozenset({"ts", "level", "logger", "event", "exc", "stack"})
QUERY_FIELDS = frozenset({"q", "query", "input", "canonical", "identification_query"})
ALWAYS_REDACTED = frozenset(
    {"abstract", "abstracts", "authors", "body", "headers", "cookies", "set_cookie", "authorization"}
)
# A key is secret-shaped when it ENDS in one of these (case-insensitive): `access_token`, `apiKey`,
# `openreview_password`, `client_secret`, `x_auth`. A suffix, not a substring, so ordinary fields that merely
# contain the word stay visible: `tokenizer_version`, `token_count`, `author_count` (task-009 review).
SECRET_SUFFIXES = (
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "auth",
    "cookie",
    "credential",
    "credentials",
    "private_key",
    "bearer",
)
# ... or STARTS with one of these: `password_hash`, `secret_key`, `auth_header`, `bearer_token`,
# `credential_id`, `token_value`. `auth_` (with the underscore) spares `author_count` / `authority`.
SECRET_PREFIXES = ("password", "passwd", "secret", "auth_", "bearer", "credential", "token_")
# Ordinary counters the logging standard asks for, spared from the prefix rule.
NOT_SECRET = frozenset({"token_count", "tokens", "token_total"})
REDACTED = "[redacted]"

# What scrub redacts: in each pattern the `v` group is the secret, replaced by REDACTED, the rest kept as written.
# Every pattern is tried once per run it starts (a lookbehind, or a literal start), takes its runs possessively
# and checks a secret word with a lookahead, so scrub is linear in its text (TASK-275): tried at every character
# of a long run, a pattern read the rest of the run each time, and a lazy scan for the word re-read the rest of a
# name once per place the word appears in it.
_WORDS = "token|key|secret|password|passwd|auth|sig|signature"
_NAME = r"[a-z0-9_.%-]"  # a parameter name's characters (`X-Amz-Signature`, `api%5Fkey`, `client.secret`)
_ENC_NAME = r"(?:[a-z0-9_.-]|%5F|%2D|%2E)"  # the same, percent-encoded
_SCRUBS = (
    # userinfo (`user:pass@`). A scheme starts at its run's first letter, after the run's digits and `+.-`, so
    # `1a://user@` and `.a://user@` lose their userinfo (a lookbehind alone would leave them).
    re.compile(r"(?<![a-zA-Z0-9+.-])[0-9+.-]*+[a-zA-Z][a-zA-Z0-9+.-]*+://(?P<v>[^/\s@]+)@"),
    # the same, percent-encoded in a value (`?next=https%3A%2F%2Fu%3Ap%40h`, TASK-283)
    re.compile(
        r"(?<![a-z0-9+.%-])[0-9+.-]*+[a-z][a-z0-9+.-]*+%3A%2F%2F(?P<v>(?:[^%/\s@]|%(?!2F|40)[0-9a-f]{2})++)%40",
        re.IGNORECASE,
    ),
    # a parameter whose name holds a secret word, wherever its name starts (`?access_token=`, `#access_token=`,
    # `;token=`, a bare `token=`, TASK-283); prose such as `monkey=1` loses its value too
    re.compile(rf"(?<!{_NAME})(?={_NAME}*(?:{_WORDS})){_NAME}*+=(?P<v>[^&\s#]*)", re.IGNORECASE),
    # the same, percent-encoded in a value (`?next=https%3A%2F%2Fh%2F%3Ftoken%3Dabc`, TASK-283)
    re.compile(
        rf"(?:%3F|%26|%23|%3B)(?={_ENC_NAME}*(?:{_WORDS})){_ENC_NAME}*+%3D"
        r"(?P<v>(?:[a-z0-9_.~+-]|%(?!26|23)[0-9a-f]{2})*+)",
        re.IGNORECASE,
    ),
    # a quoted key holding a secret word and its quoted value (`{"access_token": "abc"}`, a dict's repr, TASK-283)
    re.compile(
        rf"(?P<q>[\"'])(?={_NAME}*(?:{_WORDS})){_NAME}*+(?P=q)\s*+:\s*+(?P=q)"
        r"(?P<v>(?:(?!(?P=q))[^\\]|\\[\s\S])*+)(?P=q)",
        re.IGNORECASE,
    ),
    # `Authorization: Bearer …` quoted in exception text: the word after a whole-word `bearer` and whitespace that
    # is no line break; an escape inside it (`\/`, JSON) is part of it, an escaped quote ends it
    re.compile(
        r"\bbearer[^\S\n\r\v\f\x1c-\x1e\x85\u2028\u2029]++(?P<v>(?:[^\s\"',;\\]|\\[^\s\"'\\])++)",
        re.IGNORECASE,
    ),
)


# Attributes every LogRecord has; anything else on a record came from `extra=` or `bind()`.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}
_context: contextvars.ContextVar[Mapping[str, object]] = contextvars.ContextVar(
    "op_log_context", default=types.MappingProxyType({})
)


def elapsed_ms(started: float, clock: Callable[[], float] = time.perf_counter) -> float:
    """Milliseconds since `clock()` read `started`, to one decimal: the one form of every log line's `ms`
    field (logging-standards)."""
    return round((clock() - started) * 1000, 1)


def frames(exc: BaseException) -> list[str]:
    """`file:line function` for each frame of `exc`'s traceback: where it failed, without what it said (a
    failure line's `frames`; the message can quote input, so it is never logged)."""
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


@contextlib.contextmanager
def bind(**fields: object) -> Iterator[None]:
    """Add `fields` to every log line emitted inside the block (per task/request, via contextvars)."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def _redact(m: re.Match[str]) -> str:
    whole, start = m.group(0), m.start()
    a, b = m.span("v")
    return whole[: a - start] + REDACTED + whole[b - start :]


def scrub(text: str) -> str:
    """Remove credentials from `text`: URL userinfo (`user:pass@`), secret-looking parameters and quoted keys, bearer
    tokens, as written or percent-encoded in a value (`_SCRUBS`)."""
    for pattern in _SCRUBS:
        text = pattern.sub(_redact, text)
    return text


def _sensitive(key: str, log_query_text: bool) -> bool:
    k = key.lower()
    if k in NOT_SECRET:
        return False
    if k in ALWAYS_REDACTED or k.endswith(SECRET_SUFFIXES) or k.startswith(SECRET_PREFIXES):
        return True
    return k in QUERY_FIELDS and not log_query_text


def _put(out: dict[str, object], last: dict[str, int], name: str, value: object) -> None:
    """`out[name] = value`, or under `name#2`, `name#3`, … when two keys scrub to the same name, so neither is lost;
    `last` holds each name's last suffix, so many keys that collide cost linear time, not a walk from `#2` each."""
    key, n = name, last.get(name, 1)
    while key in out:
        n += 1
        key = f"{name}#{n}"
    last[name] = n
    out[key] = value


def _clean(value: object, log_query_text: bool) -> object:
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        last: dict[str, int] = {}
        for k, v in value.items():  # `_sensitive` reads the key as given, before its scrub
            cleaned = REDACTED if _sensitive(str(k), log_query_text) else _clean(v, log_query_text)
            _put(out, last, scrub(str(k)), cleaned)
        return out
    if isinstance(value, list | tuple | set | frozenset):
        return [_clean(v, log_query_text) for v in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    # Everything else is logged via str(), so scrub that: an exception or an httpx.URL can carry credentials.
    # Keys are scrubbed too (above and in `_fields`): `extra={url: …}` would log its URL as a key.
    return scrub(value if isinstance(value, str) else str(value))


def _fields(record: logging.LogRecord, log_query_text: bool) -> dict[str, object]:
    raw: dict[str, object] = dict(_context.get())
    raw.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
    out: dict[str, object] = {}
    last: dict[str, int] = {}
    for key, value in raw.items():
        # a field can never overwrite the line's shape, and a key that is a URL loses its credentials
        name = f"field_{key}" if key in CORE_KEYS else scrub(key)
        _put(out, last, name, REDACTED if _sensitive(key, log_query_text) else _clean(value, log_query_text))
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
            "event": scrub(
                record.getMessage()
            ),  # backstop: %-formatted variable data is banned, but never leaks
        }
        line.update(self._extras(record))
        return json.dumps(line, default=str, ensure_ascii=False).translate(_LINE_BREAKS)


# Every character `str.splitlines` breaks a line at, as a JSON escape: json.dumps leaves U+0085, U+2028 and
# U+2029 as they are, so a reader that splits on them would cut a JSON line in two (`\u2028` is the same string).
_LINE_BREAKS = str.maketrans({c: f"\\u{ord(c):04x}" for c in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"})
# The text line escapes every control character too (C0, DEL, C1: line breaks, ESC, backspace), so no text can
# start a forged line or move the terminal's cursor; the message is not JSON-encoded.
_CONTROLS = str.maketrans({chr(c): f"\\u{c:04x}" for c in [*range(0x20), *range(0x7F, 0xA0), 0x2028, 0x2029]})


class _TextFormatter(_Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Values are JSON-encoded, and so is a key that is not a plain name; then every control character left.
        parts = [
            f"{k if k.isascii() and k.isidentifier() else json.dumps(k, ensure_ascii=False)}="
            f"{json.dumps(v, default=str, ensure_ascii=False)}"
            for k, v in self._extras(record).items()
        ]
        line = f"{record.levelname:<7} {record.name}: {scrub(record.getMessage())}" + (
            "  " + " ".join(parts) if parts else ""
        )
        return line.translate(_CONTROLS)


# The server's loggers (task-034). `uvicorn` (and `uvicorn.error` under it) goes through our handler, so its
# lines are JSON too. `uvicorn.access` is switched off: the API's own `request` line replaces it, and its
# line holds the full path with the query string, i.e. `q`. httpx/httpcore (and their httpx2 forks, the
# test client's) log every request URL at INFO, so they are pinned to WARNING (and routed like uvicorn).
SERVER_LOGGERS = ("uvicorn",)
SERVER_CHILDREN = ("uvicorn.error",)  # no handler of their own: they reach ours through `uvicorn`
SILENCED_LOGGERS = ("uvicorn.access",)
QUIET_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2")
OURS = "_openproceedings_handler"  # marks the root handler configure_logging installed


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    *,
    stream: IO[str] | None = None,
    log_query_text: bool = False,
    route_server_loggers: bool = False,
) -> None:
    """Configure the `openproceedings` logger. Idempotent: closes and replaces any handler a previous call
    installed. `route_server_loggers` (the API's startup, `op serve`) also sends uvicorn's loggers through the
    same handler, silences `uvicorn.access`, pins httpx/httpcore to WARNING (QUIET_LOGGERS above), and gives
    the root logger a JSON handler at WARNING, so any other library's warning (asyncio, fastapi) is JSON too."""
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
    if route_server_loggers:
        for name in SERVER_LOGGERS:
            server = logging.getLogger(name)
            for h in list(server.handlers):
                server.removeHandler(h)
            server.addHandler(handler)
            server.setLevel(level.upper())
            server.propagate = False
        for name in SERVER_CHILDREN:
            child = logging.getLogger(name)
            for h in list(child.handlers):
                child.removeHandler(h)
            child.setLevel(logging.NOTSET)
            child.propagate = True
        for name in SILENCED_LOGGERS:
            silenced = logging.getLogger(name)
            for h in list(silenced.handlers):
                silenced.removeHandler(h)
            silenced.propagate = False
            silenced.disabled = True
        # everything else that propagates to the root (asyncio, fastapi, starlette, …): WARNING and up, as JSON
        root = logging.getLogger()
        for h in list(root.handlers):
            if getattr(h, OURS, False):  # a previous call's; other handlers (pytest's capture) are left alone
                root.removeHandler(h)
        rooted = logging.StreamHandler(stream if stream is not None else sys.stderr)
        rooted.setFormatter(formatters[fmt](log_query_text))
        rooted.setLevel(logging.WARNING)
        setattr(rooted, OURS, True)
        root.addHandler(rooted)
        if root.level == logging.NOTSET or root.level > logging.WARNING:
            root.setLevel(logging.WARNING)
        for name in QUIET_LOGGERS:
            quiet = logging.getLogger(name)
            for h in list(quiet.handlers):
                quiet.removeHandler(h)
            quiet.addHandler(handler)
            quiet.setLevel(logging.WARNING)
            quiet.propagate = False
