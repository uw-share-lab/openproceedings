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

# scrub's two patterns as they were before TASK-275 (origin/dev at 88df9322), frozen here as the reference
_PRE275_USERINFO = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@")
_PRE275_QUERY = re.compile(
    r"(?P<k>[?&](?:[a-z0-9_]*?(?:token|key|secret|password|passwd|auth|sig|signature)[a-z0-9_]*))=[^&\s#]*",
    re.IGNORECASE,
)
_USERINFO, _QUERY = logs._SCRUBS[0], logs._SCRUBS[2]


def _strings(alphabet: str, longest: int) -> list[str]:
    return ["".join(chars) for n in range(longest + 1) for chars in product(alphabet, repeat=n)]


# every character the userinfo pattern reads: a letter, a digit, `.` for the other scheme punctuation, `:/@`, a
# space, and `#`; no other pattern can match these strings (no secret word, quote, `%` or `bearer`)
def test_userinfo_is_redacted_as_before_on_every_short_string() -> None:
    """Every string up to 6 characters (299,593): the same text out. A difference first shown at 7 characters
    (`.a://b@`, a scheme after punctuation) is a named example. Once, not in CI: the pattern alone over every
    string up to 7 (2.4M) showed no difference."""
    for text in _strings("a1.:/@ #", 6):
        assert logs.scrub(text) == _PRE275_USERINFO.sub(r"\g<scheme>[redacted]@", text), text


def _redacted(spans: list[tuple[int, int]]) -> set[int]:
    return {i for a, b in spans for i in range(a, b)}


# `?&=` and `sig` (a secret word whose letters are also name characters), `#`, which ends a value and now starts a
# name, and a space. Since TASK-275 a name starts after any character that is not a name character, so the
# query pattern redacts more than it did (a bare `sig=`); it must still redact every character it did.
def test_every_query_value_redacted_before_is_redacted_on_every_short_string() -> None:
    """Every string up to 6 characters (299,593): each character the old pattern redacted falls in a value the
    new one redacts, and a value it redacted empty (`?sig=`) is still matched."""
    for text in _strings("?&=sig #", 6):
        old = [(m.end("k") + 1, m.end()) for m in _PRE275_QUERY.finditer(text)]
        new = [m.span("v") for m in _QUERY.finditer(text)]
        assert _redacted(old) <= _redacted(new), text
        assert {b for a, b in old if a == b} <= {b for a, b in new}, text


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
        ('{"authorization": "bearer ab"}', '{"authorization": "[redacted]"}'),  # `auth` in the key: all of it
        ('{"h": "bearer ab"}', '{"h": "bearer [redacted]"}'),
        ("a bearer of news", "a bearer [redacted] news"),  # a backstop: an ordinary `bearer` loses a word
        ("a forbearer of x", "a forbearer of x"),  # `bearer` only as a whole word
        ('\\"Bearer ab\\"', '\\"Bearer [redacted]\\"'),  # JSON-escaped: the escape stays
        ("Bearer\u00a0ab", "Bearer\u00a0[redacted]"),  # any whitespace that is no line break
        ("Bearer\nab", "Bearer\nab"),
        ("Bearer\u2028ab", "Bearer\u2028ab"),
        ("Bearer\x85ab", "Bearer\x85ab"),
        ("Bearer\vab", "Bearer\vab"),
        ("Bearer\fab", "Bearer\fab"),
        ("Bearer\x1dab", "Bearer\x1dab"),
        (
            '{"h": "Bearer ab\\/cd+ef=="}',
            '{"h": "Bearer [redacted]"}',
        ),  # an escape inside the token is the token
        ("Bearer ab\\u002Fcd", "Bearer [redacted]"),
        # TASK-283: a bare parameter, wherever its name starts
        ("access_token=abc page=2", "access_token=[redacted] page=2"),
        ("retry with token=abc", "retry with token=[redacted]"),
        ("page=2 count=3 size=4", "page=2 count=3 size=4"),  # no secret word: untouched
        ("monkey=1", "monkey=[redacted]"),  # a backstop: a word inside a name counts, as `?designer=` did
        # TASK-283: percent-encoded in a value (a redirect target)
        (
            "https://h/x?next=https%3A%2F%2Fh%2F%3Ftoken%3Dabc%26p%3D1",
            "https://h/x?next=https%3A%2F%2Fh%2F%3Ftoken%3D[redacted]%26p%3D1",
        ),
        ("?next=%2F%3Fa%3D1%26API%5FKEY%3Dz%23f", "?next=%2F%3Fa%3D1%26API%5FKEY%3D[redacted]%23f"),
        ("?next=https%3A%2F%2Fu%3Ap%40h%2Fz", "?next=https%3A%2F%2F[redacted]%40h%2Fz"),
        ("?n=%22https%3A%2F%2Fu%3Ap%40h", "?n=%22https%3A%2F%2F[redacted]%40h"),  # right after another escape
        (
            "?n=%2Chttps%3A%2F%2Fu%40h %20ftp%3A%2F%2Fv%40g",
            "?n=%2Chttps%3A%2F%2F[redacted]%40h %20ftp%3A%2F%2F[redacted]%40g",
        ),
        ("?n=%2F%3Ftoken%3Dab!c*d(e)/f:g&x=1", "?n=%2F%3Ftoken%3D[redacted]&x=1"),  # every value character
        ('{"u": "%2F%3Ftoken%3Dab", "x": 1}', '{"u": "%2F%3Ftoken%3D[redacted]", "x": 1}'),  # a quote ends it
        (
            "?r=%2Fcb%23access_token%3Dab%26x%3D1",
            "?r=%2Fcb%23access_token%3D[redacted]%26x%3D1",
        ),  # `#`, encoded
        ("?r=%2Fx%3Ba%3D1%3Btoken%3Dab", "?r=%2Fx%3Ba%3D1%3Btoken%3D[redacted]"),  # `;`, encoded
        ("?next=%2F%3Fpage%3D2", "?next=%2F%3Fpage%3D2"),
        # TASK-283: a quoted key and its quoted value (JSON, a dict's repr)
        ('{"access_token": "abc", "n": 1}', '{"access_token": "[redacted]", "n": 1}'),
        ("{'client_secret': 'a\\'b', 'x': 'y'}", "{'client_secret': '[redacted]', 'x': 'y'}"),
        ('{"token":"a\\"b"}', '{"token":"[redacted]"}'),  # an escaped quote stays inside the value
        ('{"token": \'ab"c\'}', "{\"token\": '[redacted]'}"),  # the value's own quote
        ("{'token': b'ab'}", "{'token': b'[redacted]'}"),  # a bytes value
        ('{"tokens": 3, "page": "2"}', '{"tokens": 3, "page": "2"}'),  # a value that is not quoted is left
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
        lambda n: "bearer " + "\\" * n,
        lambda n: "a=" * (n // 2),  # TASK-283: a name may start at every other character
        lambda n: "token" * (n // 5),
        lambda n: "%3Ftoken" * (n // 8),
        lambda n: "%3F" + "%5F" * (n // 3),
        lambda n: "%3Ftoken%3D" + "%41" * (n // 3),
        lambda n: "a%3A%2F%2F" * (n // 10),
        lambda n: "https%3A%2F%2F" + "u" * n,
        lambda n: "'token':'" * (n // 9),
        lambda n: '"' * n,
        lambda n: "'" + "a" * n,
        lambda n: "'token': '" + "\\a" * (n // 2),
        lambda n: ('"token": "' + "a" * 50) * (n // 60),
        lambda n: "%22h%3A" * (n // 7),  # an encoded scheme tried after every escape
        lambda n: "%3Ftoken%3D" + "!" * n,
        lambda n: "'token': b'" * (n // 11),
        lambda n: '"token": \'' + "a" * n,
    ],
)
def test_scrub_is_linear_on_a_long_run(build: object) -> None:
    """About 20k characters took 97-760 ms before TASK-275 by shape (292 ms on a run of letters, 758 ms on
    `?` + `token` x 4,000), 16 times 5k's: crawled text reaching a log line. The `-.%`, `#` and `bearer` shapes
    guard what TASK-275 added (the old patterns didn't read them), the rest what TASK-283 added."""
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


def test_a_real_suffixed_key_is_kept_when_keys_collide_after_it() -> None:
    out = logs._clean(
        {"https://[redacted]@h#2": "real", "https://a@h": 1, "https://b@h": 2}, log_query_text=False
    )
    assert out == {"https://[redacted]@h#2": "real", "https://[redacted]@h": 1, "https://[redacted]@h#3": 2}


@pytest.mark.parametrize("brk", ["\x85", "\u2028", "\u2029"])
def test_a_json_line_is_one_line_to_any_reader(stream: io.StringIO, brk: str) -> None:
    """json.dumps leaves these as they are; escaped, `str.splitlines` keeps the line whole and it parses the same."""
    logging.getLogger("openproceedings.x").info(f"e{brk}", extra={f"k{brk}": f"v{brk}"})
    (line,) = stream.getvalue().splitlines()
    rec = json.loads(line)
    assert rec["event"] == f"e{brk}" and rec[f"k{brk}"] == f"v{brk}"


@pytest.mark.parametrize("ctl", ["\x1b[2K", "\x08", "\x00", "\x7f", "\x9b", "\t"])
def test_text_format_escapes_control_characters(ctl: str) -> None:
    """ESC, backspace and the other C0/C1 controls, in the message or a value, never reach the terminal raw."""
    buf = io.StringIO()
    logs.configure_logging("INFO", "text", stream=buf)
    logging.getLogger("openproceedings.x").info("e %s", f"m{ctl}", extra={"k": f"v{ctl}"})
    out = buf.getvalue().rstrip("\n")
    assert not any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in out), repr(out)
