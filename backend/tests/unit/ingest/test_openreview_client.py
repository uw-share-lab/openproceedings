"""The OpenReview client (openreview-api skill): auth, the HTML challenge, rate limits and retries on a fake
clock, the cache, and never leaking a credential. Recorded fixtures only; no network."""

from __future__ import annotations

import http.server
import json
import logging
import threading
from collections.abc import Iterator
from email.utils import format_datetime
from pathlib import Path

import pytest
from openproceedings.ingest.sources.http import (
    CacheError,
    Request,
    Response,
    TransportError,
    urllib_transport,
)
from openproceedings.ingest.sources.http import CacheMiss as OpenReviewCacheMiss
from openproceedings.ingest.sources.http import HTTPRefused as OpenReviewHTTPError
from openproceedings.ingest.sources.http import RetriesExhausted as OpenReviewRetriesExhausted
from openproceedings.ingest.sources.openreview_client import (
    API_V1,
    Credentials,
    OpenReviewAuthError,
    OpenReviewClient,
    OpenReviewPublicDataError,
    credentials,
    read_dotenv,
)

from tests.unit.ingest.openreview_fakes import (
    BUDGET,
    EPOCH,
    JSON,
    PASSWORD,
    TOKEN,
    USERNAME,
    FakeClock,
    FakeOpenReview,
    json_response,
    response,
)

CREDS = Credentials(USERNAME, PASSWORD)
PARAMS = {"content.venueid": "ICLR.cc/2024/Conference", "limit": 1}
OK = {"notes": []}


def client(
    tmp_path: Path, server: FakeOpenReview, clock: FakeClock | None = None, **kw: object
) -> OpenReviewClient:
    return OpenReviewClient(tmp_path / "http", credentials=kw.pop("credentials", CREDS), transport=server,  # type: ignore[arg-type]
                            clock=clock or FakeClock(), jitter=lambda: 0.0, **kw)  # type: ignore[arg-type]  # fmt: skip


def answering(*responses: Response) -> FakeOpenReview:
    """A server whose GETs get `responses` in turn (the last one repeats)."""
    queue = list(responses)

    def next_one(_: Request) -> Response:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return FakeOpenReview(override=next_one)


# --- auth ------------------------------------------------------------------------------------------------------


def test_an_html_challenge_is_an_auth_failure_after_one_fresh_login(tmp_path: Path) -> None:
    server = answering(response("errors/anonymous-challenge.json"))  # HTTP 200, text/html
    c = client(tmp_path, server)
    with pytest.raises(OpenReviewAuthError, match="HTML page"):
        c.get("/notes", PARAMS)
    assert [x.method for x in server.calls] == ["POST", "GET", "POST", "GET"]
    assert not list((tmp_path / "http").rglob("*.json"))  # never cached as an empty page


def test_the_recorded_challenge_is_what_an_unauthenticated_request_gets(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    req = Request(
        "GET", "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=1", {}
    )
    assert server(req).headers["content-type"].startswith("text/html")


def test_no_credentials_is_refused_before_any_request(tmp_path: Path) -> None:
    server = FakeOpenReview()
    with pytest.raises(OpenReviewAuthError, match="OPENREVIEW_USERNAME") as e:
        client(tmp_path, server, credentials=None).get("/notes", PARAMS)
    assert e.value.reason == "credentials_missing" and server.calls == []


def test_a_refused_login_names_no_credential(tmp_path: Path) -> None:
    server = FakeOpenReview()
    with pytest.raises(OpenReviewAuthError, match=r"HTTP 400, LoginError") as e:
        client(tmp_path, server, credentials=Credentials(USERNAME, "wrong-password")).get("/notes", PARAMS)
    assert USERNAME not in str(e.value) and "wrong-password" not in str(e.value)


def test_an_expired_token_logs_in_again_once(tmp_path: Path) -> None:
    server = answering(json_response({"name": "TokenExpiredError"}, 401, JSON), json_response(OK))
    entry = client(tmp_path, server).get("/notes", PARAMS)
    assert entry["json"] == OK and server.logins() == 2


def test_login_is_lazy_and_happens_once(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    c = client(tmp_path, server)
    for venueid in ("ICLR.cc/2024/Conference", "ICLR.cc/2024/Conference/Rejected_Submission"):
        c.get("/notes", {"content.venueid": venueid, "limit": 1})
    assert server.logins() == 1


def test_credentials_come_from_the_environment_then_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text('# comment\nexport OPENREVIEW_USERNAME="dot@example.org"\nOPENREVIEW_PASSWORD=dotpw\n')
    assert read_dotenv(tmp_path / "missing") == {}
    got = credentials({}, dotenv)
    assert got == Credentials("dot@example.org", "dotpw")
    assert credentials({"OPENREVIEW_PASSWORD": "envpw"}, dotenv) == Credentials("dot@example.org", "envpw")
    assert credentials({"OPENREVIEW_USERNAME": "u"}, None) is None
    assert credentials({"SCHOLARMEND_OPENREVIEW_USER": "u", "SCHOLARMEND_OPENREVIEW_PASSWORD": "p"}) is None
    assert "dotpw" not in repr(got) and "dot@example.org" not in repr(got)


# --- the cache ------------------------------------------------------------------------------------------------


def test_a_cached_response_is_never_fetched_again_and_needs_no_credentials(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    first = client(tmp_path, server).get("/notes", PARAMS)
    again = FakeOpenReview()
    warm = client(tmp_path, again, credentials=None, offline=True)
    assert warm.get("/notes", PARAMS) == first and again.calls == [] and warm.cached == 1
    # the claim time comes from the cache entry: fetched one paced second after the login
    assert first["fetched_at"] == EPOCH.replace(second=1).isoformat()
    assert first["headers"] == {k: BUDGET[k] for k in ("content-type", "ratelimit-policy", "ratelimit-remaining",
                                                        "ratelimit-reset")}  # fmt: skip


def test_private_v2_content_fields_are_removed_before_the_response_is_cached(tmp_path: Path) -> None:
    public = {
        "id": "PublicNote1",
        "forum": "PublicNote1",
        "readers": ["everyone"],
        "content": {
            "title": {"value": "Public title"},
            "private_comment": {"value": "do-not-cache", "readers": ["ICLR.cc/2026/Program_Chairs"]},
            "excluded_everyone": {"value": "also-do-not-cache", "nonreaders": ["everyone"]},
        },
    }
    entry = client(tmp_path, answering(json_response({"notes": [public], "count": 1}))).get("/notes", PARAMS)
    [note] = entry["json"]["notes"]
    assert note["content"] == {"title": {"value": "Public title"}}
    paths = list((tmp_path / "http").rglob("*.json"))
    cached = " ".join(p.read_text() for p in paths)
    assert "do-not-cache" not in cached and "also-do-not-cache" not in cached
    assert any(json.loads(p.read_text())["payload"]["public_projection"] == 1 for p in paths)


@pytest.mark.parametrize("bad_acl", ["everyone", {"everyone": True}, ["everyone", 7]])
def test_a_malformed_top_level_acl_is_refused_and_a_malformed_field_acl_is_dropped(
    tmp_path: Path, bad_acl: object
) -> None:
    note = {
        "id": "PublicNote1",
        "forum": "PublicNote1",
        "readers": ["everyone"],
        "content": {"private": {"value": "do-not-cache", "nonreaders": bad_acl}},
    }
    entry = client(tmp_path, answering(json_response({"notes": [note], "count": 1}))).get("/notes", PARAMS)
    assert entry["json"]["notes"][0]["content"] == {}
    assert "do-not-cache" not in " ".join(path.read_text() for path in (tmp_path / "http").rglob("*.json"))

    note["content"] = {}
    note["nonreaders"] = bad_acl
    with pytest.raises(OpenReviewPublicDataError, match="not world-readable"):
        client(tmp_path / "top", answering(json_response({"notes": [note], "count": 1}))).get(
            "/notes", PARAMS
        )
    assert not list((tmp_path / "top").rglob("*.json"))


@pytest.mark.parametrize("empty", [None, [], "absent"])
def test_a_null_or_empty_top_level_nonreaders_excludes_no_one(tmp_path: Path, empty: object) -> None:
    """API v1 writes `nonreaders: null` on some public notes (59 of the 161 live ICLR 2017 workshop submissions,
    2026-09-29, all with readers ["everyone"]); null excludes no one, like [] or no key (TASK-119)."""
    note: dict[str, object] = {
        "id": "PublicNote1",
        "forum": "PublicNote1",
        "readers": ["everyone"],
        "content": {},
    }
    if empty != "absent":
        note["nonreaders"] = empty
    entry = client(tmp_path, answering(json_response({"notes": [note], "count": 1}))).get("/notes", PARAMS)
    assert [n["id"] for n in entry["json"]["notes"]] == ["PublicNote1"]


@pytest.mark.parametrize(
    "acl",
    [{"readers": ["ICLR.cc/2017/pcs"], "nonreaders": None}, {"readers": None, "nonreaders": None},
     # only null means "no one excluded": other falsy non-lists stay malformed, so refused
     {"readers": ["everyone"], "nonreaders": ""}, {"readers": ["everyone"], "nonreaders": {}},
     {"readers": ["everyone"], "nonreaders": False}, {"readers": ["everyone"], "nonreaders": 0}],
)  # fmt: skip
def test_a_null_nonreaders_does_not_make_a_private_note_public(
    tmp_path: Path, acl: dict[str, object]
) -> None:
    note = {"id": "PrivateNote1", "forum": "PrivateNote1", "content": {}, **acl}
    with pytest.raises(OpenReviewPublicDataError, match="not world-readable") as refused:
        client(tmp_path, answering(json_response({"notes": [note], "count": 1}))).get("/notes", PARAMS)
    assert not list((tmp_path / "http").rglob("*.json"))
    assert "ICLR.cc/2017/pcs" not in str(refused.value)  # the ACL's shape is named, never its entries


def test_a_projection_refusal_names_the_canonical_request_and_nothing_else(tmp_path: Path) -> None:
    """TASK-116: the refusal says which request to look at (the cache key: host, path, parameters sorted),
    never the response's data, the token or a credential."""
    note = {"id": "PrivateNote1", "forum": "PrivateNote1", "readers": ["~Some_Person1"],
            "content": {"title": {"value": "do-not-show"}}}  # fmt: skip
    params = {"offset": 0, "content.venueid": "ICLR.cc/2024/Conference", "limit": 1000}
    c = client(tmp_path, answering(json_response({"notes": [note], "count": 1})))
    with pytest.raises(OpenReviewPublicDataError, match="not world-readable") as refused:
        c.get("/notes", params)
    message = str(refused.value)
    target = "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=1000&offset=0"
    assert c.url("/notes", params) == target and f"GET {target} " in message
    assert "readers list of 1 without everyone" in message  # the ACL's shape, as before
    for leak in ("~Some_Person1", "do-not-show", "PrivateNote1", TOKEN, PASSWORD, USERNAME, "Bearer"):
        assert leak not in message


@pytest.mark.parametrize(
    ("url", "data", "says"),
    [
        ("https://api2.openreview.net/profiles?id=x", {"profiles": []}, "has no public cache projection"),
        ("https://api2.openreview.net/groups?id=G", {"groups": ["not-an-object"]}, "is not an object"),
    ],
)
def test_every_projection_refusal_names_its_request(url: str, data: dict[str, object], says: str) -> None:
    from openproceedings.ingest.sources.openreview_client import _public_projection

    with pytest.raises(OpenReviewPublicDataError, match=says) as refused:
        _public_projection(url, data)
    assert f"GET {url} " in str(refused.value) and "not-an-object" not in str(refused.value)


def test_openreview_policy_events_are_fixed_constants() -> None:
    from openproceedings.ingest.sources.openreview_client import EVENTS, POLICY

    assert POLICY.events is EVENTS
    assert (EVENTS.retry_wait, EVENTS.budget_wait, EVENTS.cache_expired) == (
        "openreview_retry_wait", "openreview_budget_wait", "openreview_cache_expired",
    )  # fmt: skip


def test_the_refusal_names_the_acl_shape() -> None:
    from openproceedings.ingest.sources.openreview_client import _acl_shape

    note = {"readers": ["~Some_Person1", "everyone"], "nonreaders": None}
    assert (_acl_shape(note, "readers"), _acl_shape(note, "nonreaders")) == (
        "readers list of 2 naming everyone",
        "nonreaders null",
    )
    assert _acl_shape({"nonreaders": ""}, "nonreaders") == "nonreaders str"
    assert _acl_shape({}, "readers") == "readers absent"


def test_group_responses_are_projected_with_the_same_acl_rules(tmp_path: Path) -> None:
    group = {
        "id": "ICLR.cc/2026/Conference",
        "domain": "ICLR.cc/2026/Conference",
        "readers": ["everyone"],
        "content": {
            "submission_venue_id": {"value": "ICLR.cc/2026/Conference"},
            "chairs_only": {"value": "do-not-cache", "readers": ["ICLR.cc/2026/Program_Chairs"]},
        },
    }
    entry = client(tmp_path, answering(json_response({"groups": [group], "count": 1}))).get(
        "/groups", {"parent": "ICLR.cc/2026", "limit": 1}
    )
    [projected] = entry["json"]["groups"]
    assert projected["content"] == {"submission_venue_id": {"value": "ICLR.cc/2026/Conference"}}
    assert "do-not-cache" not in " ".join(path.read_text() for path in (tmp_path / "http").rglob("*.json"))


@pytest.mark.parametrize("base", ["https://api2.openreview.net", API_V1])
def test_a_mixed_public_private_response_is_refused_and_never_cached(tmp_path: Path, base: str) -> None:
    data = {
        "notes": [
            {"id": "PublicNote1", "readers": ["everyone"], "content": {}},
            {"id": "PrivateNote1", "readers": ["Venue/Program_Chairs"], "content": {"secret": "x"}},
        ],
        "count": 2,
    }

    def transport(request: Request, timeout: float = 60.0) -> Response:
        return (
            json_response({"token": TOKEN}, headers=JSON) if request.method == "POST" else json_response(data)
        )

    c = OpenReviewClient(
        tmp_path / "http",
        credentials=CREDS,
        base=base,
        login_base="https://api2.openreview.net",
        transport=transport,
        clock=FakeClock(),
        jitter=lambda: 0.0,
    )
    with pytest.raises(OpenReviewPublicDataError, match="not world-readable"):
        c.get("/notes", PARAMS)
    assert not list((tmp_path / "http").rglob("*.json"))


def test_an_old_unprojected_cache_is_rejected_offline_and_purged_live(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    live = client(tmp_path, server)
    url = live.url("/notes", PARAMS)
    path = live.cache.path(url)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "key": url,
                "payload": {
                    "url": url,
                    "fetched_at": EPOCH.isoformat(),
                    "headers": {},
                    "json": {"notes": []},
                },
            }
        )
    )
    with pytest.raises(CacheError, match="malformed"):
        OpenReviewClient(tmp_path / "http", credentials=None, offline=True).get("/notes", PARAMS)
    got = live.get("/notes", PARAMS)
    assert got["json"] == {"notes": []}
    assert json.loads(path.read_text())["payload"]["public_projection"] == 1


def test_a_malformed_projected_cache_is_not_silently_purged(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    live = client(tmp_path, server)
    live.get("/notes", PARAMS)
    path = live.cache.path(live.url("/notes", PARAMS))
    document = json.loads(path.read_text())
    document["payload"]["json"] = []
    path.write_text(json.dumps(document))
    with pytest.raises(CacheError, match="malformed"):
        live.get("/notes", PARAMS)
    assert path.exists() and len(server.gets()) == 1


def test_offline_refuses_a_miss_and_refresh_refetches(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={"ICLR.cc/2024/Conference": []})
    with pytest.raises(OpenReviewCacheMiss) as e:
        client(tmp_path, server, offline=True).get("/notes", PARAMS)
    assert e.value.url == "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=1"
    client(tmp_path, server).get("/notes", PARAMS)
    client(tmp_path, server, refresh=True).get("/notes", PARAMS)
    assert len(server.gets()) == 2


def test_the_base_url_must_be_an_openreview_api_host(tmp_path: Path) -> None:
    for base in ("https://evil.example", "http://api2.openreview.net", "https://api2.openreview.net/x"):
        with pytest.raises(ValueError, match="base URL"):
            OpenReviewClient(tmp_path, credentials=None, base=base)
        with pytest.raises(ValueError, match="base URL"):  # the login host too (a v1 client logs in on api2)
            OpenReviewClient(tmp_path, credentials=None, base="https://api.openreview.net", login_base=base)


# --- rate limits and retries (fake clock) -------------------------------------------------------------------


def test_429_waits_for_retry_after_seconds(tmp_path: Path) -> None:
    clock = FakeClock()
    server = answering(json_response({}, 429, {**JSON, "retry-after": "30"}), json_response(OK))
    assert client(tmp_path, server, clock).get("/notes", PARAMS)["json"] == OK
    assert 31.0 in clock.sleeps


def test_429_waits_for_an_http_date_retry_after(tmp_path: Path) -> None:
    clock = FakeClock()
    when = format_datetime(EPOCH.replace(minute=2), usegmt=True)  # two minutes after the clock's start
    server = answering(json_response({}, 429, {**JSON, "retry-after": when}), json_response(OK))
    client(tmp_path, server, clock).get("/notes", PARAMS)
    assert any(abs(s - 121.0) < 1.5 for s in clock.sleeps)


def test_429_without_retry_after_uses_ratelimit_reset_never_the_epoch_header(tmp_path: Path) -> None:
    clock = FakeClock()
    headers = {
        **BUDGET,
        "ratelimit-remaining": "0",
        "ratelimit-reset": "2261",
        "x-ratelimit-reset": "1790543172",
    }
    server = answering(json_response({}, 429, headers), json_response(OK))
    client(tmp_path, server, clock).get("/notes", PARAMS)
    assert 2262.0 in clock.sleeps and max(clock.sleeps) < 3702


def test_a_spent_budget_waits_for_the_window_to_reset(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    server = answering(
        json_response(OK, headers={**BUDGET, "ratelimit-remaining": "0", "ratelimit-reset": "600"})
    )
    with caplog.at_level(logging.INFO):
        client(tmp_path, server, clock).get("/notes", PARAMS)
    assert clock.sleeps[-1] == 601.0
    [wait] = [r for r in caplog.records if r.getMessage() == "openreview_budget_wait"]
    assert wait.__dict__["wait_s"] == 601.0


def test_a_hostile_wait_is_capped_at_about_an_hour(tmp_path: Path) -> None:
    clock = FakeClock()
    server = answering(json_response({}, 429, {**JSON, "retry-after": "999999"}), json_response(OK))
    client(tmp_path, server, clock).get("/notes", PARAMS)
    assert max(clock.sleeps) == 3701.0


def test_5xx_backs_off_exponentially_and_gives_up(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    server = answering(json_response({"name": "InternalServerError"}, 503, JSON))
    with pytest.raises(OpenReviewRetriesExhausted), caplog.at_level(logging.WARNING):
        client(tmp_path, server, clock, max_attempts=5, min_interval=0.0).get("/notes", PARAMS)
    assert clock.sleeps == [1.0, 2.0, 4.0, 8.0] and len(server.gets()) == 5
    assert [r.getMessage() for r in caplog.records].count("openreview_retry_wait") == 4


def test_jitter_is_added_to_the_backoff(tmp_path: Path) -> None:
    clock = FakeClock()
    server = answering(json_response({}, 502, JSON), json_response(OK))
    OpenReviewClient(tmp_path, credentials=CREDS, transport=server, clock=clock, min_interval=0.0,
                     jitter=lambda: 0.25).get("/notes", PARAMS)  # fmt: skip
    assert clock.sleeps == [1.25]


def test_a_truncated_json_body_and_a_network_error_are_retried(tmp_path: Path) -> None:
    calls = iter([Response(200, JSON, b'{"notes": ['), TransportError("TimeoutError"), json_response(OK)])

    def flaky(_: Request) -> Response:
        nxt = next(calls)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    assert client(tmp_path, FakeOpenReview(override=flaky)).get("/notes", PARAMS)["json"] == OK


def test_any_other_4xx_is_raised_at_once(tmp_path: Path) -> None:
    server = answering(response("errors/limit-over-1000.json"))
    with pytest.raises(OpenReviewHTTPError) as e:
        client(tmp_path, server).get("/notes", {"content.venueid": "ICLR.cc/2024/Conference", "limit": 1001})
    assert (e.value.status, e.value.name, len(server.gets())) == (400, "ValidationError", 1)
    assert "limit must be" not in str(e.value)  # the API's message isn't repeated
    not_found = answering(response("errors/v1-note-not-found.json"))
    with pytest.raises(OpenReviewHTTPError, match="404 NotFoundError"):
        client(tmp_path, not_found).get("/notes", {"id": "g1SzIRLQXMM"})


# --- secrets ----------------------------------------------------------------------------------------------------


def test_no_credential_or_token_reaches_a_log_line_an_error_or_the_cache(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = answering(json_response({}, 401, JSON), json_response({}, 429, {**JSON, "retry-after": "1"}),
                       json_response(OK))  # fmt: skip
    with caplog.at_level(logging.DEBUG):
        client(tmp_path, server).get("/notes", PARAMS)
        with pytest.raises(OpenReviewAuthError) as e:
            client(tmp_path / "2", answering(response("errors/anonymous-challenge.json"))).get(
                "/notes", PARAMS
            )
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records) + str(e.value)
    text += " ".join(p.read_text() for p in tmp_path.rglob("*.json"))
    for secret in (USERNAME, PASSWORD, TOKEN):
        assert secret not in text
    assert "Authorization" not in repr(server.calls[-1]) and TOKEN not in repr(server.calls[-1])


# --- the real transport, against a loopback server ----------------------------------------------------------


@pytest.fixture
def loopback() -> Iterator[tuple[str, list[str]]]:
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()
                return
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", hits
    server.shutdown()
    server.server_close()


def test_the_transport_never_follows_a_redirect(loopback: tuple[str, list[str]]) -> None:
    base, hits = loopback
    got = urllib_transport(Request("GET", f"{base}/redirect", {"Authorization": "Bearer x"}), timeout=5)
    assert got.status == 302 and hits == ["/redirect"]


def test_the_transport_bounds_the_body(loopback: tuple[str, list[str]]) -> None:
    base, _ = loopback
    assert (
        urllib_transport(Request("GET", f"{base}/ok", {}), timeout=5).headers["content-type"]
        == "application/json"
    )
    with pytest.raises(TransportError, match="body_too_large"):
        urllib_transport(Request("GET", f"{base}/ok", {}), timeout=5, max_body=4)


@pytest.mark.parametrize(
    "token",
    ["abc\r\nX-Evil: y", "tok en", "abc\x00", "abcé", "abc" + "a" * 4094],
    ids=["crlf", "space", "nul", "non-ascii", "too-long"],
)
def test_a_token_that_cant_be_a_header_is_refused_without_echoing_it(
    tmp_path: Path, token: str, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-067: http.client refuses a CR/LF header with a ValueError quoting the whole `Bearer <token>`, which
    reached `op`'s stderr unscrubbed; the login checks the token's shape first."""

    def server(request: Request, timeout: float = 60.0) -> Response:
        assert request.method == "POST"
        return json_response({"token": token}, headers=JSON)

    with caplog.at_level(logging.DEBUG), pytest.raises(OpenReviewAuthError) as e:
        client(tmp_path, server).get("/notes", PARAMS)  # type: ignore[arg-type]
    assert token not in str(e.value) and token not in caplog.text and "abc" not in str(e.value)


def test_the_transport_never_echoes_a_header_value_it_cant_send() -> None:
    with pytest.raises(TransportError) as e:
        urllib_transport(
            Request("GET", "http://127.0.0.1:9/x", {"Authorization": "Bearer SECRET\r\nX: y"}), 1
        )
    assert "SECRET" not in str(e.value) and e.value.__cause__ is None


def test_the_live_transport_reads_no_more_than_the_policys_body_bound(tmp_path: Path) -> None:
    from openproceedings.ingest.sources.http import Fetcher, PageCache

    fetcher = Fetcher(PageCache(tmp_path), urllib_transport, hosts=frozenset({"example.org"}))
    assert fetcher.transport.keywords == {"max_body": fetcher.policy.max_body}  # type: ignore[union-attr]
