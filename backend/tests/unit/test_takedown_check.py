"""`op takedown check`'s verdicts (TASK-136 AC8, decision-022), one per way an instance can serve a listed abstract
or stop being checkable, against a fake API: each case breaks one thing and expects exactly its problem. The
real routes are checked end to end in `tests/contract/test_takedowns.py`."""

from __future__ import annotations

import csv
import http.server
import io
import json
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from openproceedings import takedown_check
from openproceedings.export import CSV_COLUMNS, TAKEDOWN, WITHHELD

RID = "op:iclr:2024:Abcd1234"
TWIN = "op:iclr:2024:Efgh5678"  # a second listed paper of the same venue-year
V = "abcdef123456"
AUTHORS = ["Ada Okafor", "Lin Wei"]


@dataclass
class FakeApi:
    """One served index `V` holding the listed papers, each withheld as it should be; flip a field to break it."""

    ids: tuple[str, ...] = (RID,)
    abstract: str | None = None  # on /papers
    claim: bool = False  # an abstract claim left on /papers
    marker: bool = True  # /papers abstract_withheld
    matched: bool = True  # /papers?q=
    lit_spans: list[list[int]] = field(default_factory=list)
    hit: dict[str, Any] | None = None  # overrides of the /search hit
    no_hit: bool = False
    search_status: int = 200
    export_status: dict[str, int] = field(default_factory=dict)
    drop_from: str | None = None  # a format whose export leaves the paper out
    sentence: str = TAKEDOWN
    reason: str = "takedown"
    export_abstract: str | None = None
    # records of the title-only export beyond the listed ones: (id, authors, abstract) (TASK-067)
    others: tuple[tuple[str, list[str], str | None], ...] = ()
    titles: dict[str, str] = field(default_factory=dict)  # /papers titles by id (default "Calibrated Trust")
    paper_status: dict[str, int] = field(default_factory=dict)  # /papers answers other than 200/404, by id
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def fetch(self, path: str, params: Mapping[str, str]) -> tuple[int, str]:
        self.calls.append((path, dict(params)))
        if path.endswith("/meta"):
            return 200, json.dumps({"index_versions": [V]})
        if path.startswith("/api/v1/papers/"):
            rid = path.rsplit("/", 1)[1]
            if "q" in params:
                return 200, json.dumps(
                    {"matched": self.matched, "highlights": {"title": [], "abstract": self.lit_spans}}
                )
            provenance = [{"field": "title"}, *([{"field": "abstract"}] if self.claim else [])]
            if rid in self.paper_status:
                return self.paper_status[rid], "{}"
            if rid not in self.ids and rid not in self.titles:
                return 404, "{}"
            paper = {
                "id": rid,
                "title": self.titles.get(rid, "Calibrated Trust"),
                "authors": AUTHORS,
                "abstract": self.abstract,
                "provenance": provenance,
            }
            return 200, json.dumps({"index_version": V, "paper": paper, "abstract_withheld": self.marker})
        if path.endswith("/search"):
            hits = [] if self.no_hit else [
                {"id": i, "abstract": None, "highlights": {"title": [[0, 3]], "abstract": []},
                 "abstract_source": None, "abstract_withheld": True, **(self.hit or {})}
                for i in self.ids
            ]  # fmt: skip
            return self.search_status, json.dumps({"hits": hits})
        fmt = params["format"]
        if fmt in self.export_status:
            return self.export_status[fmt], "{}"
        if "venue:" not in params["q"]:  # the title in every venue and year: the paper under other ids
            assert fmt == "jsonl"
            rows = [(i, AUTHORS, None, True) for i in self.ids]
            rows += [(i, authors, abstract, abstract is None) for i, authors, abstract in self.others]
            return 200, "".join(
                json.dumps({"id": i, "title": "Calibrated Trust", "authors": a, "abstract": ab,
                            "abstract_withheld": w, "abstract_withheld_reason": "takedown" if w else None}) + "\n"
                for i, a, ab, w in rows
            )  # fmt: skip
        ids = [i for i in self.ids if fmt != self.drop_from]
        return 200, "".join(self.entry(fmt, i) for i in ids) if fmt != "csv" else self.csv(ids)

    def entry(self, fmt: str, rid: str) -> str:
        if fmt == "jsonl":
            obj = {"id": rid, "title": "Calibrated Trust", "authors": AUTHORS, "abstract": self.export_abstract,
                   "abstract_withheld": True,
                   "abstract_withheld_reason": self.reason}  # fmt: skip
            return json.dumps(obj) + "\n"
        if fmt == "ris":
            ab = f"AB  - {self.export_abstract}\n" if self.export_abstract else ""
            return f"TY  - CPAPER\nTI  - T\n{ab}ID  - {rid}\nN1  - {self.sentence}\nN1  - openproceedings {V}\nER  - \n\n"
        ab = f"  abstract = {{{self.export_abstract}}},\n" if self.export_abstract else ""
        return (f"@inproceedings{{k,\n  title = {{T}},\n{ab}  abstract_withheld = {{{self.sentence}}},\n"
                f"  note = {{openproceedings {V}}},\n  openproceedings_id = {{{rid}}}\n}}\n\n")  # fmt: skip

    def csv(self, ids: list[str]) -> str:
        out = io.StringIO()
        w = csv.DictWriter(out, CSV_COLUMNS, lineterminator="\r\n", restval="")
        w.writeheader()
        for rid in ids:
            w.writerow({"id": rid, "abstract": self.export_abstract or "", "abstract_withheld": "true",
                        "abstract_withheld_reason": self.reason})  # fmt: skip
        return "﻿" + out.getvalue()


def problems(api: FakeApi) -> list[str]:
    return sorted(takedown_check.check(api.fetch, frozenset(api.ids)).problems)


def test_an_instance_that_withholds_everything_passes_with_one_export_per_format() -> None:
    api = FakeApi(ids=(RID, TWIN))
    report = takedown_check.check(api.fetch, frozenset(api.ids))
    assert report.problems == () and report.index_versions == (V,)
    # the two ids share a venue-year: one export per format, not per id; then one of each title (TASK-067)
    assert report.exports == 4 + 2


def test_the_paper_served_under_another_id_is_a_problem_and_another_paper_is_not() -> None:
    """TASK-067: an id the paper had before a rekey, or a merged-away duplicate, serving the abstract; a
    different paper with the same title (other authors), or the paper under another id withheld, is fine."""
    old = "op:iclr:2023:Abcd1234"
    api = FakeApi(others=((old, AUTHORS, "Leaked."), ("op:iclr:2024:Zzzz9999", ["B. Other"], "Its own.")))
    assert problems(api) == [
        f"{old}: the jsonl export of index {V} serves the abstract of {RID}'s paper under this id; list it too"
    ]
    assert problems(FakeApi(others=((old, AUTHORS, None),))) == []


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        ({"abstract": "Leaked."}, f"{RID}: /papers on index {V} serves its abstract or an abstract claim"),
        ({"claim": True}, f"{RID}: /papers on index {V} serves its abstract or an abstract claim"),
        ({"marker": False}, f"{RID}: /papers on index {V} doesn't mark the abstract withheld"),
        ({"matched": False}, f"{RID}: /papers?q= by its title answered 200 or didn't match it; check it by hand"),
        ({"lit_spans": [[0, 4]]}, f"{RID}: /papers?q= on index {V} highlights the withheld abstract"),
        ({"hit": {"abstract": "Leaked."}}, f"{RID}: its /search hit on index {V} serves the abstract, its spans or its source"),
        ({"hit": {"highlights": {"title": [], "abstract": [[0, 4]]}}}, f"{RID}: its /search hit on index {V} serves the abstract, its spans or its source"),
        ({"hit": {"abstract_source": {"source": "ris"}}}, f"{RID}: its /search hit on index {V} serves the abstract, its spans or its source"),
        ({"hit": {"abstract_withheld": False}}, f"{RID}: its /search hit on index {V} doesn't mark the abstract withheld"),
        ({"no_hit": True}, f"{RID}: /search by its title didn't return it; check /search by hand"),
        ({"search_status": 500}, f"{RID}: /search for it answered 500"),
    ],
)  # fmt: skip
def test_each_served_index_leak_is_its_own_problem(broken: dict[str, Any], problem: str) -> None:
    assert problems(FakeApi(**broken)) == [problem]


@pytest.mark.parametrize("fmt", ["ris", "bibtex", "csv", "jsonl"])
def test_an_export_that_serves_the_abstract_is_a_problem(fmt: str) -> None:
    api = FakeApi()
    real = api.fetch

    def leaky(path: str, params: Mapping[str, str]) -> tuple[int, str]:
        if params.get("format") == fmt:
            api.export_abstract = "Leaked text."
            try:
                return real(path, params)
            finally:
                api.export_abstract = None
        return real(path, params)

    got = sorted(takedown_check.check(leaky, frozenset({RID})).problems)
    assert got == [f"{RID}: the {fmt} export of index {V} serves its abstract"]


def test_an_export_that_doesnt_say_takedown_is_a_problem_in_every_format() -> None:
    assert problems(FakeApi(sentence=WITHHELD, reason="source_unavailable")) == sorted(
        f"{RID}: the {fmt} export of index {V} doesn't say a takedown withheld it" for fmt in ("bibtex", "csv", "jsonl", "ris")
    )  # fmt: skip


def test_a_format_that_no_longer_holds_the_paper_is_a_problem_not_a_pass() -> None:
    assert problems(FakeApi(drop_from="bibtex")) == [
        f"{RID}: the bibtex export of index {V} doesn't hold it, though its csv export does (can this check still read bibtex?)"
    ]


def test_a_failed_export_is_reported_once() -> None:
    assert problems(FakeApi(export_status={"ris": 500})) == [f"{RID}: export ris of index {V} answered 500"]


def test_a_paper_no_loaded_version_holds_is_a_problem() -> None:
    api = FakeApi(ids=())

    def absent(path: str, params: Mapping[str, str]) -> tuple[int, str]:
        return (404, "{}") if path.startswith("/api/v1/papers/") else api.fetch(path, params)

    got = takedown_check.check(absent, frozenset({RID})).problems
    assert got == (f"{RID}: no index this instance loads holds it; check the id on the list",)


def test_meta_failing_stops_the_check() -> None:
    report = takedown_check.check(lambda path, params: (503, "{}"), frozenset({RID}))
    assert report.problems == ("GET /meta answered 503: is the API up and serving an index?",)


def test_the_title_query_takes_at_most_its_cap_of_words() -> None:
    title = " ".join(f"w{i}" for i in range(30))
    q = takedown_check.title_query(title, RID)
    assert q is not None and q.startswith(
        'title:"' + " ".join(f"w{i}" for i in range(takedown_check.MAX_TITLE_WORDS)) + '"'
    )


class _Redirecting(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:1/elsewhere")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def redirecting() -> Iterator[str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Redirecting)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_the_http_client_follows_no_redirect(redirecting: str) -> None:
    status, _body = takedown_check.http(redirecting, timeout=10)(f"{takedown_check.API}/meta", {})
    assert status == 302


class _Busy(http.server.BaseHTTPRequestHandler):
    """429 with `Retry-After: 0` for the first `busy` requests, then 200."""

    busy = 1
    seen = 0

    def do_GET(self) -> None:
        type(self).seen += 1
        if type(self).seen <= type(self).busy:
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        body = b'{"index_versions": []}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.mark.parametrize(("busy", "retries", "status", "seen"), [(1, 5, 200, 2), (9, 1, 429, 2)])
def test_the_http_client_waits_out_a_429_up_to_its_retries(
    busy: int, retries: int, status: int, seen: int
) -> None:
    handler = type("Busy", (_Busy,), {"busy": busy, "seen": 0})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fetch = takedown_check.http(
            f"http://127.0.0.1:{server.server_address[1]}", retries=retries, timeout=10
        )
        got, _body = fetch(f"{takedown_check.API}/meta", {})
    finally:
        server.shutdown()
    assert (got, handler.seen) == (status, seen)


def test_a_merge_that_withholds_another_paper_is_a_problem() -> None:
    """TASK-067 review: the check also looks the other way. An id a snapshot's merges.csv links to a listed
    paper is withheld as that paper; if the served index gives it another title, the merge (and so the
    withholding) is suspect, and the check names it."""
    other, same, gone = "op:iclr:2024:Other9999", "op:iclr:2024:Twin00001", "op:iclr:2024:Merged0001"
    api = FakeApi(titles={other: "Something Else Entirely", same: "Calibrated trust"})
    merges = ((RID, other), (same, RID), (RID, gone))  # `gone`: merged away, the served index 404s it
    report = takedown_check.check(api.fetch, frozenset(api.ids), merges)
    assert report.problems == (
        f"{other}: withheld as {RID}'s paper (a snapshot's merges.csv links them), but its title differs; "
        "check that merge",
    )


def test_a_merged_id_the_api_wont_answer_for_is_a_problem() -> None:
    other = "op:iclr:2024:Other9999"
    report = takedown_check.check(FakeApi(paper_status={other: 500}).fetch, frozenset({RID}), ((RID, other),))
    assert report.problems == (f"{other}: GET /papers answered 500",)
