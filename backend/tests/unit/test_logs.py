"""JSON logging per the logging-standards skill: one object per line, event constants, structured fields,
redaction of query text and secrets, bound request context."""

import io
import json
import logging
import re
from itertools import product

import pytest
from openproceedings import logs

from tests.timing import assert_near_linear, growth


@pytest.fixture
def stream() -> io.StringIO:
    buf = io.StringIO()
    logs.configure_logging("DEBUG", "json", stream=buf)
    return buf


def lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def test_one_json_object_per_line_with_required_keys(stream: io.StringIO) -> None:
    logging.getLogger("openproceedings.x").info("index_built", extra={"index_version": "a1", "docs": 3})
    (rec,) = lines(stream)
    assert rec["event"] == "index_built"
    assert rec["level"] == "INFO"
    assert rec["logger"] == "openproceedings.x"
    assert rec["index_version"] == "a1"
    assert rec["docs"] == 3
    assert isinstance(rec["ts"], str) and rec["ts"].endswith("Z")


@pytest.mark.parametrize("field", ["q", "query", "input", "canonical", "identification_query"])
def test_query_text_is_redacted_by_default(stream: io.StringIO, field: str) -> None:
    logging.getLogger("openproceedings.api").info("request", extra={field: "trust AND benchmark"})
    (rec,) = lines(stream)
    assert rec[field] == "[redacted]"


@pytest.mark.parametrize("field", ["abstract", "password", "token", "authorization"])
def test_secrets_and_abstracts_are_always_redacted(field: str) -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "json", stream=buf, log_query_text=True)
    logging.getLogger("openproceedings.x").info("e", extra={field: "sensitive"})
    (rec,) = lines(buf)
    assert rec[field] == "[redacted]"


def test_query_text_opt_in_for_local_dev() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "json", stream=buf, log_query_text=True)
    logging.getLogger("openproceedings.x").info("request", extra={"q": "trust"})
    (rec,) = lines(buf)
    assert rec["q"] == "trust"


def test_bound_context_is_added_to_every_line(stream: io.StringIO) -> None:
    log = logging.getLogger("openproceedings.api")
    with logs.bind(request_id="r-1", index_version="v9"):
        log.info("request")
    log.info("after")
    inside, after = lines(stream)
    assert inside["request_id"] == "r-1" and inside["index_version"] == "v9"
    assert "request_id" not in after


def test_level_filters(stream: io.StringIO) -> None:
    logs.configure_logging("WARNING", "json", stream=stream)
    logging.getLogger("openproceedings.x").info("quiet")
    logging.getLogger("openproceedings.x").warning("loud")
    assert [r["event"] for r in lines(stream)] == ["loud"]


def test_reconfiguring_does_not_duplicate_lines() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "json", stream=buf)
    logs.configure_logging("INFO", "json", stream=buf)
    logging.getLogger("openproceedings.x").info("once")
    assert len(lines(buf)) == 1


def test_exception_info_is_included(stream: io.StringIO) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("openproceedings.x").error("crawl_failed", exc_info=True)
    (rec,) = lines(stream)
    assert "ValueError: boom" in str(rec["exc"])


def test_text_format_is_human_readable() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    logging.getLogger("openproceedings.x").info("index_built", extra={"docs": 3})
    assert "index_built" in buf.getvalue() and "docs=3" in buf.getvalue()


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(ValueError):
        logs.configure_logging("INFO", "yaml")


# --- review round 1 (observability-reviewer) ---------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "Authorization",
        "API_KEY",
        "api_key",
        "access_token",
        "refresh_token",
        "authors",
        "body",
        "headers",
        "cookies",
        "set_cookie",
        "client_secret",
        "db_password",
        "Password",
    ],
)
def test_redaction_is_case_insensitive_and_covers_secret_like_names(stream: io.StringIO, field: str) -> None:
    logging.getLogger("openproceedings.x").info("e", extra={field: "sensitive"})
    (rec,) = lines(stream)
    assert rec[field] == "[redacted]"


def test_nested_values_are_redacted(stream: io.StringIO) -> None:
    extra = {"params": {"query": "trust", "page": 2, "inner": [{"token": "t"}]}}
    logging.getLogger("openproceedings.x").info("e", extra=extra)
    (rec,) = lines(stream)
    assert rec["params"] == {"query": "[redacted]", "page": 2, "inner": [{"token": "[redacted]"}]}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://u:p@api2.openreview.net/notes", "https://[redacted]@api2.openreview.net/notes"),
        ("https://h/x?token=abc&page=2", "https://h/x?token=[redacted]&page=2"),
        ("https://h/x?api_key=abc", "https://h/x?api_key=[redacted]"),
        ("https://h/x?page=2", "https://h/x?page=2"),
    ],
)
def test_urls_keep_their_shape_but_lose_credentials(stream: io.StringIO, value: str, expected: str) -> None:
    logging.getLogger("openproceedings.x").info("crawl_page_fetched", extra={"url": value})
    (rec,) = lines(stream)
    assert rec["url"] == expected


@pytest.mark.parametrize("key", ["event", "level", "logger", "ts", "exc"])
def test_fields_cannot_overwrite_core_keys(stream: io.StringIO, key: str) -> None:
    with logs.bind(**{key: "bound"}):
        logging.getLogger("openproceedings.x").info("real_event", extra={key: "clobber"})
    (rec,) = lines(stream)
    assert rec["event"] == "real_event"
    assert rec["level"] == "INFO"
    assert rec["logger"] == "openproceedings.x"
    assert rec[f"field_{key}"] == "clobber"


def test_exception_text_is_scrubbed_of_credentials(stream: io.StringIO) -> None:
    try:
        raise ConnectionError("GET https://u:secret@api2.openreview.net/notes?token=abc failed")
    except ConnectionError:
        logging.getLogger("openproceedings.x").error("crawl_failed", exc_info=True)
    (rec,) = lines(stream)
    assert "secret" not in str(rec["exc"]) and "abc" not in str(rec["exc"])


def test_stack_info_is_rendered(stream: io.StringIO) -> None:
    logging.getLogger("openproceedings.x").warning("odd", stack_info=True)
    (rec,) = lines(stream)
    assert "Stack (most recent call last)" in str(rec["stack"])


def test_text_format_escapes_values_so_a_newline_cannot_fake_a_line() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    logging.getLogger("openproceedings.x").info("e", extra={"note": "a\nINFO forged"})
    assert len(buf.getvalue().strip().splitlines()) == 1


def test_text_format_includes_exception_text() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("openproceedings.x").error("crawl_failed", exc_info=True)
    assert "ValueError: boom" in buf.getvalue()


def test_unknown_level_is_rejected_by_configure() -> None:
    with pytest.raises(ValueError):
        logs.configure_logging("VERBOSE", "json")


class _Url:
    def __str__(self) -> str:
        return "https://u:p@host/?api_key=zz"


@pytest.mark.parametrize("value", [_Url(), ValueError("https://u:p@h/x?token=t")])
def test_non_string_values_are_scrubbed_via_their_str(stream: io.StringIO, value: object) -> None:
    logging.getLogger("openproceedings.x").info("fetch_failed", extra={"target": value})
    (rec,) = lines(stream)
    assert (
        "u:p@" not in str(rec["target"]) and "zz" not in str(rec["target"]) and "=t" not in str(rec["target"])
    )


def test_numbers_and_bools_pass_through_unchanged(stream: io.StringIO) -> None:
    logging.getLogger("openproceedings.x").info("e", extra={"docs": 3, "ok": True, "secs": 1.5, "none": None})
    (rec,) = lines(stream)
    assert (rec["docs"], rec["ok"], rec["secs"], rec["none"]) == (3, True, 1.5, None)


def test_the_message_itself_is_scrubbed_as_a_backstop(stream: io.StringIO) -> None:
    logging.getLogger("openproceedings.x").info(
        "fetch_failed %s", "https://u:p@h"
    )  # banned style; still safe
    (rec,) = lines(stream)
    assert "u:p@" not in str(rec["event"])


@pytest.mark.parametrize(
    "field",
    [
        "tokenizer_version",
        "token_count",
        "author_count",
        "index_version",
        "canonical_hash",
        "authority_score",
    ],
)
def test_ordinary_fields_that_merely_contain_a_secret_word_are_not_redacted(
    stream: io.StringIO, field: str
) -> None:
    logging.getLogger("openproceedings.x").info("index_built", extra={field: "v"})
    (rec,) = lines(stream)
    assert rec[field] == "v"


@pytest.mark.parametrize("field", ["accessToken", "openreview_password", "client_secret", "x_auth", "apiKey"])
def test_secret_suffixes_in_any_case_are_redacted(stream: io.StringIO, field: str) -> None:
    logging.getLogger("openproceedings.x").info("e", extra={field: "s"})
    (rec,) = lines(stream)
    assert rec[field] == "[redacted]"


@pytest.mark.parametrize(
    "field",
    [
        "password_hash",
        "passwd_old",
        "secret_key",
        "auth_header",
        "bearer",
        "Bearer_Token",
        "credential_id",
        "token_value",
    ],
)
def test_secret_prefixes_are_redacted(stream: io.StringIO, field: str) -> None:
    logging.getLogger("openproceedings.x").info("e", extra={field: "s"})
    (rec,) = lines(stream)
    assert rec[field] == "[redacted]"


@pytest.mark.parametrize("field", ["tokenizer_version", "token_count", "author_count", "authority_score"])
def test_prefix_rule_still_spares_ordinary_fields(stream: io.StringIO, field: str) -> None:
    # `token_count` is the one deliberate carve-out from the token_ prefix: counts are what the standard asks for.
    logging.getLogger("openproceedings.x").info("e", extra={field: "v"})
    (rec,) = lines(stream)
    assert rec[field] == "v"


# --- scrub in linear time (TASK-275) ---------------------------------------------------------------------------

# the patterns as they were before TASK-275; the userinfo one with an empty `pre` group, which matches nothing, so
# today's `scrub` (whose replacement names `pre`) runs on them unchanged
_PRE275 = {
    "_URL_USERINFO": re.compile(r"(?P<pre>)(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@"),
    "_SECRET_QUERY": re.compile(
        r"(?P<k>[?&](?:[a-z0-9_]*?(?:token|key|secret|password|passwd|auth|sig|signature)[a-z0-9_]*))=[^&\s#]*",
        re.IGNORECASE,
    ),
}


def _scrubbed(texts: list[str], patterns: dict[str, re.Pattern[str]] | None = None) -> list[str]:
    """`logs.scrub` of each text, with `patterns` put on `logs` for the calls when given."""
    saved = {name: getattr(logs, name) for name in patterns or {}}
    try:
        for name, pattern in (patterns or {}).items():
            setattr(logs, name, pattern)
        return [logs.scrub(t) for t in texts]
    finally:
        for name, pattern in saved.items():
            setattr(logs, name, pattern)


# every character each pattern reads: a letter, a digit, `.` for the other scheme punctuation, `:/@`, a space,
# and `#`, which ends a query value; `?&=` and `sig` (a secret word whose letters are also name characters), a
# space and `,`, which no pattern reads here (`bearer` can't form without a `b`). Since TASK-275 `-.%` are name characters and `#;` start a name too,
# so they are left out of the query alphabet: what they add is only more redaction (examples below).
@pytest.mark.parametrize("alphabet", ["a1.:/@ #", "?&=sig ,"])
def test_scrub_gives_what_it_gave_before_on_every_short_string(alphabet: str) -> None:
    """Every string up to 6 characters (299,593 per alphabet): the same text out, so a log line reads as
    before. A difference first shown at 7 characters (`.a://b@`, a scheme after punctuation) is a named example.
    Once, not in CI: each pattern alone over every string up to 7 characters (userinfo over `a1.:/@ #`, 2.4M;
    the query over `?&=sigx #`, 5.4M) showed no difference."""
    texts = ["".join(chars) for n in range(7) for chars in product(alphabet, repeat=n)]
    before = _scrubbed(texts, _PRE275)
    for text, now, then in zip(texts, _scrubbed(texts), before, strict=True):
        assert now == then, text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1a://u:p@h", "1a://[redacted]@h"),  # a scheme after digits still loses its userinfo
        ("x+1a://u@h", "x+1a://[redacted]@h"),
        (".a://u@h", ".a://[redacted]@h"),  # past the exhaustive length: the gap first shows at 7 (`.a://b@`)
        ("-a://u@h", "-a://[redacted]@h"),
        ("+a://u@h", "+a://[redacted]@h"),
        ("see https://u@h and ftp://v@g", "see https://[redacted]@h and ftp://[redacted]@g"),
        ("https://h/x?an_Auth_code=1&sig=2", "https://h/x?an_Auth_code=[redacted]&sig=[redacted]"),
        (
            "?\u017fig=1",
            "?\u017fig=[redacted]",
        ),  # long s folds to `s` under IGNORECASE, in the word and the name
        ("?\u212aey=1", "?\u212aey=[redacted]"),  # Kelvin sign folds to `k`
        ("https://s3/x?X-Amz-Signature=ab&p=1", "https://s3/x?X-Amz-Signature=[redacted]&p=1"),
        ("https://h/x?api-key=ab", "https://h/x?api-key=[redacted]"),
        ("https://h/x?api%5Fkey=ab", "https://h/x?api%5Fkey=[redacted]"),
        ("https://h/x?auth.v2=ab", "https://h/x?auth.v2=[redacted]"),
        ("https://h/x?client.secret=ab", "https://h/x?client.secret=[redacted]"),  # the word after a `.`
        ("https://h/x?sig=a#b", "https://h/x?sig=[redacted]#b"),  # `#` ends a value
        ("https://h/cb#access_token=ab&x=1", "https://h/cb#access_token=[redacted]&x=1"),  # a fragment
        ("https://h/x?a=1;token=2", "https://h/x?a=1;token=[redacted]"),
        ("Authorization: Bearer ab.c-d", "Authorization: Bearer [redacted]"),
        ('{"authorization": "bearer ab"}', '{"authorization": "bearer [redacted]"}'),
        ("a bearer of news", "a bearer [redacted] news"),  # a backstop: an ordinary `bearer` loses a word
        ("a forbearer of x", "a forbearer of x"),  # `bearer` only as a whole word
        ('\\"Bearer ab\\"', '\\"Bearer [redacted]\\"'),  # JSON-escaped: the escape stays
        ("Bearer\u00a0ab", "Bearer\u00a0[redacted]"),  # any whitespace but a line break
        ("Bearer\nab", "Bearer\nab"),
        (
            "https://h/x?designer=1",
            "https://h/x?designer=[redacted]",
        ),  # `sig` anywhere in the name, as before
    ],
)
def test_scrub_examples(value: str, expected: str) -> None:
    assert logs.scrub(value) == expected


@pytest.mark.parametrize(
    "build",
    [
        lambda n: "a" * n,  # a scheme tried at every letter
        lambda n: "x a://" + "b" * n,
        lambda n: "?" + "token" * (n // 5),  # a secret word found again at every repeat
        lambda n: "a1." * (n // 3),  # a scheme tried at every third character
        lambda n: "a+" * (n // 2),  # each scheme punctuation character the lookbehind must read
        lambda n: "a-" * (n // 2),
        lambda n: "?" + "-token" * (n // 6),  # the word again after each added name character
        lambda n: "?" + ".key" * (n // 4),
        lambda n: "?" + "%sig" * (n // 4),
        lambda n: "#" * n,
        lambda n: "bearer" + " " * n,
        lambda n: "bearer " * (n // 7),
    ],
)
def test_scrub_is_linear_on_a_long_run(build: object) -> None:
    """About 20k characters took 97-760 ms before TASK-275 by shape (292 ms on a run of letters, 758 ms on
    `?` + `token` x 4,000), 16 times 5k's: crawled text reaching a log line. The `-.%`, `#` and `bearer` shapes
    guard what TASK-275 added (the old patterns didn't read them)."""
    assert_near_linear(logs.scrub, build, 5_000)  # type: ignore[arg-type]


def test_a_url_used_as_a_key_loses_its_credentials(stream: io.StringIO) -> None:
    """Keys are scrubbed at any depth, top-level `extra` keys included."""
    logging.getLogger("openproceedings.x").info(
        "e", extra={"https://u:p@h/?token=t": 1, "m": {"https://v:q@g": [{"a://w@f": 2}]}}
    )
    (rec,) = lines(stream)
    assert rec["https://[redacted]@h/?token=[redacted]"] == 1
    assert rec["m"] == {"https://[redacted]@g": [{"a://[redacted]@f": 2}]}
    assert "p@" not in json.dumps(rec) and "q@" not in json.dumps(rec)


def test_a_secret_named_url_key_is_judged_on_its_own_name(stream: io.StringIO) -> None:
    """`_sensitive` reads the key as given: its value is redacted, and its name is scrubbed."""
    logging.getLogger("openproceedings.x").info("e", extra={"m": {"https://u@h/?x=1_token": "v"}})
    (rec,) = lines(stream)
    assert rec["m"] == {"https://[redacted]@h/?x=1_token": "[redacted]"}


def test_two_keys_that_scrub_alike_are_both_kept(stream: io.StringIO) -> None:
    logging.getLogger("openproceedings.x").info(
        "e",
        extra={
            "https://a:1@h": "A",
            "https://b:2@h": "B",
            "m": {"https://a@h": 1, "https://b@h": 2, "https://[redacted]@h": 3},
        },
    )
    (rec,) = lines(stream)
    assert rec["https://[redacted]@h"] == "A" and rec["https://[redacted]@h#2"] == "B"
    assert rec["m"] == {"https://[redacted]@h": 1, "https://[redacted]@h#2": 2, "https://[redacted]@h#3": 3}


def test_text_format_escapes_a_key_so_a_newline_cannot_fake_a_line() -> None:
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    logging.getLogger("openproceedings.x").info("e", extra={"x\nINFO forged": 1, "plain_name": 2})
    out = buf.getvalue().strip()
    assert len(out.splitlines()) == 1
    assert '"x\\nINFO forged"=1' in out and " plain_name=2" in out


@pytest.mark.parametrize("brk", ["\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_text_format_escapes_every_line_break_in_keys_values_and_the_message(brk: str) -> None:
    """Every character `str.splitlines` breaks at, in a key, a value or a %-formatted message (banned, but a
    backstop), stays on one line."""
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    logging.getLogger("openproceedings.x").info("e %s", f"m{brk}INFO forged", extra={f"k{brk}x": f"v{brk}y"})
    assert len(buf.getvalue().splitlines()) == 1


def test_many_keys_that_scrub_alike_are_all_kept_in_linear_time() -> None:
    """Each name's last suffix is remembered, so n colliding keys cost n steps, not n²/2."""

    def build(n: int) -> dict[str, int]:
        return {f"https://u{i}@h": i for i in range(n)}

    out = logs._clean(build(1000), log_query_text=False)
    assert isinstance(out, dict) and len(out) == 1000 and out["https://[redacted]@h#1000"] == 999
    small, large = build(2_000), build(8_000)
    ratio, pairs = growth(lambda: logs._clean(small, False), lambda: logs._clean(large, False))
    assert ratio < 8, (ratio, pairs)
