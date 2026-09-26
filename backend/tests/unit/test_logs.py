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
