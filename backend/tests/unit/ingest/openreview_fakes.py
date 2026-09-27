"""Test doubles for the OpenReview crawler: a fake clock, and a fake api2 server built from the recorded,
scrubbed fixtures under `fixtures/http/openreview/v2/` (TASK-002), and a fake api1 from `v1/` (TASK-051). No network: the client's transport is
swapped for these (and conftest refuses any real connection anyway).

Where a test needs more notes than a fixture holds (pagination), `clone` copies a recorded note and changes
only its id, forum and number; where it needs a group the fixtures lack, `group_doc` copies the recorded
`ICLR.cc/2025/Conference` group and renames it. Every shape is a recorded one.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from openproceedings.ingest.sources.http import Request, Response

FIXTURES = Path(__file__).parents[2] / "fixtures" / "http" / "openreview" / "v2"
USERNAME = "someone@example.org"
PASSWORD = "pw-DO-NOT-LOG-7f3a"
TOKEN = "tok-DO-NOT-LOG-91c2"
EPOCH = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
JSON = {"content-type": "application/json; charset=utf-8"}
BUDGET = {**JSON, "ratelimit-policy": "500;w=3600", "ratelimit-remaining": "271", "ratelimit-reset": "2261",
          "x-ratelimit-reset": "1790543172"}  # fmt: skip


def recorded(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def response(name: str) -> Response:
    """A recorded exchange's response, as the transport would return it."""
    r = recorded(name)["response"]
    body = json.dumps(r["json"]) if "json" in r else r["text"]
    return Response(r["status"], {k.lower(): v for k, v in r["headers"].items()}, body.encode("utf-8"))


def recorded_note(name: str) -> dict[str, Any]:
    [note] = recorded(name)["response"]["json"]["notes"]
    note_copy: dict[str, Any] = copy.deepcopy(note)
    return note_copy


def clone(note: Mapping[str, Any], nid: str, number: int, venueid: str | None = None) -> dict[str, Any]:
    out = copy.deepcopy(dict(note))
    out["id"] = out["forum"] = nid
    out["number"] = number
    if venueid is not None:
        out["content"]["venueid"] = {"value": venueid}
    return out


def group_doc(gid: str, *, domain: str | None = None, venue_ids: bool = True) -> dict[str, Any]:
    """The recorded ICLR 2025 Conference group, renamed to `gid` (its venueids renamed with it)."""
    group: dict[str, Any] = copy.deepcopy(
        recorded("iclr-2025/group-conference.json")["response"]["json"]["groups"][0]
    )
    text = json.dumps(group).replace("ICLR.cc/2025/Conference", gid)
    out: dict[str, Any] = json.loads(text)
    out["domain"] = gid if domain is None else domain
    if not venue_ids:
        out["content"] = {k: v for k, v in out["content"].items() if not k.endswith("_venue_id")}
    return out


def json_response(data: object, status: int = 200, headers: Mapping[str, str] | None = None) -> Response:
    return Response(status, dict(headers or BUDGET), json.dumps(data).encode("utf-8"))


class FakeClock:
    """Monotonic time that only moves when something sleeps; `now` follows it from EPOCH."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def now(self) -> datetime:
        return EPOCH + timedelta(seconds=self.t)


class FakeOpenReview:
    """A fake api2: `/login`, `/groups?parent=` and `/groups?id=`, and `/notes?content.venueid=` with
    `limit`/`offset` paging and `count` only when `offset` is sent (as the live API does). `override(url)`
    may answer any GET first (a 429, a 503, an HTML page)."""

    def __init__(
        self,
        children: Mapping[str, list[str]] | None = None,
        groups: Mapping[str, dict[str, Any]] | None = None,
        notes: Mapping[str, list[dict[str, Any]]] | None = None,
        override: Callable[[Request], Response | None] | None = None,
    ) -> None:
        self.children = dict(children or {})
        self.groups = dict(groups or {})
        self.notes = dict(notes or {})
        self.override = override
        self.calls: list[Request] = []
        self.count_bias = 0  # added to `count` (a listing that changed under a resumed crawl)
        self.ignore_offset = False

    def gets(self) -> list[str]:
        return [c.url for c in self.calls if c.method == "GET"]

    def logins(self) -> int:
        return sum(c.method == "POST" for c in self.calls)

    def __call__(self, request: Request, timeout: float = 60.0) -> Response:
        self.calls.append(request)
        parts = urlsplit(request.url)
        assert parts.hostname == "api2.openreview.net"
        if request.method == "POST":
            assert parts.path == "/login"
            body = json.loads(request.body or b"{}")
            if (body.get("id"), body.get("password")) != (USERNAME, PASSWORD):
                return json_response(
                    {"name": "LoginError", "message": "Invalid username or password"}, 400, JSON
                )
            return json_response({"token": TOKEN}, headers=JSON)
        if self.override is not None and (answer := self.override(request)) is not None:
            return answer
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return response("errors/anonymous-challenge.json")
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        limit, offset = int(q.get("limit", 1000)), int(q.get("offset", 0))
        start = 0 if self.ignore_offset else offset
        if parts.path == "/groups" and "parent" in q:
            rows = [{"id": g} for g in self.children.get(q["parent"], [])]
            return json_response({"groups": rows[start : start + limit], "count": len(rows)})
        if parts.path == "/groups" and "id" in q:
            doc = self.groups.get(q["id"])
            return json_response({"groups": [doc] if doc else [], "count": 1 if doc else 0})
        if parts.path == "/notes":
            listed = self.notes.get(q["content.venueid"], [])
            page: dict[str, Any] = {"notes": listed[start : start + limit]}
            if "offset" in q:
                page["count"] = len(listed) + self.count_bias
            return json_response(page)
        raise AssertionError(f"unexpected request {request.url}")


# --- API v1 (TASK-051) --------------------------------------------------------------------------------------

FIXTURES_V1 = FIXTURES.parent / "v1"


def recorded_v1(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES_V1 / name).read_text(encoding="utf-8"))
    return data


def v1_notes(name: str) -> list[dict[str, Any]]:
    """Every note of a recorded v1 response (a listing, a note by id, or a forum), deep-copied."""
    notes: list[dict[str, Any]] = copy.deepcopy(recorded_v1(name)["response"]["json"]["notes"])
    return notes


def v1_note(name: str) -> dict[str, Any]:
    """The submission note of a recorded v1 response (`id == forum`; a forum listing is not ordered)."""
    [note] = [n for n in v1_notes(name) if n["id"] == n["forum"]]
    return note


def v1_clone(note: Mapping[str, Any], nid: str, number: int | None = None, **content: Any) -> dict[str, Any]:
    """A recorded v1 note with another id (and forum), optionally another number and content values
    (`None` deletes a key)."""
    out = copy.deepcopy(dict(note))
    out["id"] = out["forum"] = nid
    if number is not None:
        out["number"] = number
    for key, value in content.items():
        if value is None:
            out["content"].pop(key, None)
        else:
            out["content"][key] = value
    return out


class FakeOpenReviewV1:
    """A fake api1 (`/notes?invitation=` and `/notes?forum=`, with `limit`/`offset` and `count` on every
    page, as v1 sends it) plus api2's `/login`, where a v1 client logs in. `override(url)` may answer any
    GET first."""

    def __init__(
        self,
        listings: Mapping[str, list[dict[str, Any]]] | None = None,
        forums: Mapping[str, list[dict[str, Any]]] | None = None,
        override: Callable[[Request], Response | None] | None = None,
    ) -> None:
        self.listings = dict(listings or {})
        self.forums = dict(forums or {})
        self.override = override
        self.calls: list[Request] = []
        self.count_bias = 0

    def gets(self) -> list[str]:
        return [c.url for c in self.calls if c.method == "GET"]

    def logins(self) -> int:
        return sum(c.method == "POST" for c in self.calls)

    def __call__(self, request: Request, timeout: float = 60.0) -> Response:
        self.calls.append(request)
        parts = urlsplit(request.url)
        if request.method == "POST":
            assert (parts.hostname, parts.path) == ("api2.openreview.net", "/login")
            body = json.loads(request.body or b"{}")
            if (body.get("id"), body.get("password")) != (USERNAME, PASSWORD):
                return json_response(
                    {"name": "LoginError", "message": "Invalid username or password"}, 400, JSON
                )
            return json_response({"token": TOKEN}, headers=JSON)
        assert parts.hostname == "api.openreview.net" and parts.path == "/notes"
        if self.override is not None and (answer := self.override(request)) is not None:
            return answer
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return response("errors/anonymous-challenge.json")
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        limit, offset = int(q.get("limit", 1000)), int(q.get("offset", 0))
        if "invitation" in q:
            listed = self.listings.get(q["invitation"], [])
        elif "forum" in q:
            listed = self.forums.get(q["forum"], [])
        else:
            raise AssertionError(f"unexpected request {request.url}")
        page = {"notes": listed[offset : offset + limit], "count": len(listed) + self.count_bias}
        return json_response(page, headers=JSON)  # authenticated api1 sends no rate-limit headers
