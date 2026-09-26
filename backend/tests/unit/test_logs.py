"""JSON logging per the logging-standards skill: one object per line, event constants, structured fields,
redaction of query text and secrets, bound request context."""

import io
import json
import logging

import pytest
from openproceedings import logs


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
