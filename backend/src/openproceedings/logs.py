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
- credentials are scrubbed from every string value, key, and exception and stack text (`scrub`: URL userinfo,
  secret parameters and quoted keys, bearer tokens, as written or percent-encoded), so an HTTP-client error can
  never carry an OpenReview password into a log.

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

# What scrub redacts: in each pattern the `v` group is a secret. Every pattern reads the text as given, and the
# union of their `v` spans is redacted at once, so no pattern can rewrite text another needs (a parameter's value
# swallowing a quoted key's closing quote; an encoded URL swallowing the `&password=` after it). Every pattern is
# tried once per run it starts (a lookbehind, or a literal start), takes its runs possessively and checks a secret
# word with a lookahead, so scrub is linear in its text (TASK-275): tried at every character of a long run, a
# pattern read the rest of the run each time, and a lazy scan for the word re-read the rest of a name once per
# place the word appears in it. Double encoding (`%253D`) is not decoded.
# (`sig` covers `signature`; the longer word is listed for the reader)
_WORDS = "token|key|secret|password|passwd|auth|sig|signature|cookie|credential|bearer"
_NAME = r"[a-z0-9_.%-]"  # a parameter name's characters (`X-Amz-Signature`, `api%5Fkey`, `client.secret`)
_ENC_NAME = r"(?:[a-z0-9_.-]|%5F|%2D|%2E)"  # the same, percent-encoded
# where an encoded name starts: after a character that is no name character, after an escape that is none, or
# after a `%` that starts no escape (`100%token%3D…`)
_ENC_START = r"(?:(?<![a-z0-9_.%-])|(?<=%[0-9a-f]{2})(?<!%5F)(?<!%2D)(?<!%2E)|(?<=%)(?![0-9a-f]{2}))"
# what separates `bearer` from its token: whitespace that is no line break, or `%20`, `%09`, a JSON `\t`, `+`
_BEARER_ONE = r"(?:[^\S\n\r\v\f\x1c-\x1e\x85\u2028\u2029]|%20|%09|\\t|\+)"
_BEARER_SEP = rf"{_BEARER_ONE}++"  # mixed too (` \tBearer`)
# where a token ends early: right before another `bearer` match (`Bearer A\nBearer SECRET`: matches don't
# overlap, so the second would never be tried). It holds exactly where that match would: after `\n`, `\r` or `\t`,
# a backslash and a non-word character (`\/`), an escape (`%0A`, also after a backslash: a token reads `\%` as
# one unit, so a start inside it would be skipped), or any other non-word character (a bare `\` or
# `%` included), then `bearer`, a separator, no second `bearer`, and a token (test_logs checks every case)
_BEARER_TOKEN = r"(?:[^\s\"',;\\]|\\[^\s\"'\\])"  # one unit of a token: a character, or an escape
_BEARER_NEXT = (
    rf"(?:\\(?:[nrt]|%[0-9a-f]{{2}}|[^\w\s\"'\\])|%[0-9a-f]{{2}}|[^\w\s\"',;])"
    rf"bearer{_BEARER_SEP}(?!bearer{_BEARER_SEP}){_BEARER_TOKEN}"
)
_QUOTED = r"(?P<{q}>[\"'])(?:(?!(?P={q}))[^\\]|\\[\s\S])*+(?P={q})"  # a quoted string, escapes inside it
_SCRUBS = types.MappingProxyType(
    {
        # userinfo (`user:pass@`). A scheme starts at its run's first letter, after the run's digits and `+.-`, so
        # `1a://user@` and `.a://user@` lose their userinfo (a lookbehind alone would leave them).
        "userinfo": re.compile(r"(?<![a-zA-Z0-9+.-])[0-9+.-]*+[a-zA-Z][a-zA-Z0-9+.-]*+://(?P<v>[^/\s@]+)@"),
        # the same, percent-encoded in a value (`?next=https%3A%2F%2Fu%3Ap%40h`, TASK-283), also right after
        # another escape (`%22https%3A…`); a password may hold raw `'` (encodeURIComponent leaves it), and a
        # `&password=` the span runs into is a secret of its own, so the union loses nothing
        "encoded_userinfo": re.compile(
            r"(?:(?<![a-z0-9+.%-])|(?<=%[0-9a-f]{2}))[0-9+.-]*+[a-z][a-z0-9+.-]*+%3A%2F%2F"
            r"(?P<v>(?:[^%/\s@]|%(?!2F|40)[0-9a-f]{2})++)%40",
            re.IGNORECASE,
        ),
        # a parameter whose name holds a secret word, wherever its name starts (`?access_token=`,
        # `#access_token=`, `;token=`, a bare `token=`, TASK-283), its value a quoted string whole (`token='a b'`)
        # and/or up to `&`, whitespace or `#`, a URL's userinfo inside it whole (`token=a://x#y@z`: origin/dev's
        # userinfo pass took the `#` out first, so its value ran on); prose such as `monkey=1`, and a traceback's
        # `key=lambda`, lose their value too; a value quoted with JSON-escaped quotes (`\"a b\"`) ends at its
        # first whitespace
        "parameter": re.compile(
            rf"(?<!{_NAME})(?={_NAME}*(?:{_WORDS})){_NAME}*+=(?P<v>(?:{_QUOTED.format(q='pq')})?+(?:(?<=://)[^/\s@]++@|[^&\s#])*+)",
            re.IGNORECASE,
        ),
        # the same, percent-encoded in a value (`?next=https%3A%2F%2Fh%2F%3Ftoken%3Dabc`, `?state=token%3Dabc`)
        "encoded_parameter": re.compile(
            rf"{_ENC_START}(?={_ENC_NAME}*(?:{_WORDS})){_ENC_NAME}*+%3D"
            r"(?P<v>(?:[^%&\s#\"']|%(?!26|23)[0-9a-f]{2})*+)",
            re.IGNORECASE,
        ),
        # a quoted key holding a secret word and its quoted value, either quote (`{"access_token": "abc"}`, a
        # dict's repr, a bytes value `b'abc'`, TASK-283)
        # (all in a lookahead, so a match may start inside an earlier one's value: `{'note': "'token': '",
        # 'password': 'x'}` would otherwise hide the real key behind the false one)
        "quoted": re.compile(
            rf"(?=(?P<q>[\"'])(?={_NAME}*(?:{_WORDS})){_NAME}*+(?P=q)\s*+:\s*+b?(?P<q2>[\"'])"
            r"(?P<v>(?:(?!(?P=q2))[^\\]|\\[\s\S])*+)(?P=q2))",
            re.IGNORECASE,
        ),
        # `Authorization: Bearer …` quoted in exception text: the word after a whole-word `bearer` (or one right
        # after a percent escape or a JSON `\n`/`\r`/`\t`: `%3A%20Bearer`, `\tBearer`) and a separator; never a
        # second `bearer` (`Bearer Bearer x`, a client that stored the prefix with its token); an escape inside it
        # (`\/`, JSON) is part of it, an escaped quote ends it
        "bearer": re.compile(
            rf"(?:(?<!\w)|(?<=%[0-9a-f]{{2}})|(?<=\\[nrt]))bearer{_BEARER_SEP}(?!bearer{_BEARER_SEP})"
            rf"(?P<v>(?:(?!{_BEARER_NEXT}){_BEARER_TOKEN})++)",
            re.IGNORECASE,
        ),
    }
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


# origin/dev's query pattern before TASK-275, its words and all, made linear (the same matches: tests/unit/
# test_logs.py compares it with the original over every short string):
# `secret_spans` replays origin/dev's two passes with it, so scrub redacts everything origin/dev did whatever the
# new patterns miss (a userinfo pass that took a `#` out of a value before this one read it, round 7).
_LEGACY_QUERY = re.compile(
    r"[?&](?=[a-z0-9_]*(?:token|key|secret|password|passwd|auth|sig|signature))[a-z0-9_]*+=(?P<v>[^&\s#]*)",
    re.IGNORECASE,
)


def _legacy_spans(text: str) -> Iterator[tuple[int, int]]:
    """origin/dev's query secrets in `text`, read after its userinfo pass (whose own secrets `_SCRUBS["userinfo"]`
    finds alike): each userinfo replaced by as many NULs (like `[redacted]`, a NUL is no name character and no
    delimiter to the query pattern), so positions survive."""
    hidden = _SCRUBS["userinfo"].sub(
        lambda m: m.group(0)[: m.start("v") - m.start()] + "\0" * len(m.group("v")) + "@", text
    )
    yield from (m.span("v") for m in _LEGACY_QUERY.finditer(hidden))


def secret_spans(text: str) -> list[tuple[int, int]]:
    """The spans of `text` scrub redacts: every `_SCRUBS` pattern's `v` spans over `text` as given, and
    origin/dev's (`_legacy_spans`), sorted, and merged where they overlap or touch. An empty span is an empty
    secret (`?token=`), redacted as an insertion."""
    spans = [m.span("v") for pattern in _SCRUBS.values() for m in pattern.finditer(text)]
    merged: list[tuple[int, int]] = []
    for a, b in sorted([*spans, *_legacy_spans(text)]):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def scrub(text: str) -> str:
    """Remove credentials from `text`: URL userinfo (`user:pass@`), secret-looking parameters and quoted keys, bearer
    tokens, as written or percent-encoded in a value (`_SCRUBS`), each secret replaced by REDACTED."""
    out, at = [], 0
    for a, b in secret_spans(text):
        out += [text[at:a], REDACTED]
        at = b
    return "".join([*out, text[at:]])


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
