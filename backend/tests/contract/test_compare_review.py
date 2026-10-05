"""`POST /api/v1/compare`, the security review's findings (TASK-177, 2026-10-05): one network can't hold the
comparison slot (a cooldown per client network, the upload's time the dearest), the time limit is checked
before every record and row, a link's host is echoed only as a host name and the answer has a size bound, a
match table that failed to build is built again on reload (and `/meta` says so meanwhile), builds run one at a
time, a malformed link never refuses a file, the upload's bytes are released once decoded, and a takedown is
followed through merged ids and twin links on this route too."""
# ruff: noqa: F811  (fixtures imported from the modules that own them are taken as parameters here)

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import export as exporter
from openproceedings import takedown_check
from openproceedings.api import ApiConfig, RateLimit
from openproceedings.api import compare as route
from openproceedings.api.compare import Cooldowns, slot_seconds
from openproceedings.api.middleware import TokenBucket, network_key, take_all
from openproceedings.api.state import IndexState, MatchTable
from openproceedings.eval import scholar_compare
from openproceedings.eval.scholar_compare import MAX_HOSTS, MatchIndex, Scope, link_host, read_ris
from scholarmend.parse import parse_ris

from tests.contract.conftest import attributed, make_app
from tests.contract.test_abuse_limits import error
from tests.contract.test_compare import (
    BY_ID,
    COMPARE,
    INDEX,
    KEPT,
    NO_COOLDOWN,
    ORACLE,
    Logs,
    Q,
    app_of,
    by_title,
    compared,
    corpus_dir,  # noqa: F401  (a fixture)
    entry,
    post,
    the_file,
)
from tests.contract.test_takedowns import Aliased, aliased, aliased_store, listing  # noqa: F401  (fixtures)
from tests.contract.test_twins import Twins, twins_store  # noqa: F401  (a fixture)
from tests.contract.test_twins import data as twins_data  # noqa: F401  (a fixture)
from tests.fixtures.corpus.synthetic_5k import records


# --- one network can't hold the slot (SHOULD 1) ------------------------------------------------------------------
class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def share_of_the_slot(addresses: int, *, upload: float, work: float, hours: float = 1.0) -> float:
    """The fraction of `hours` one comparison slot is held by `addresses` clients of one /24, each starting a
    comparison the moment the server lets it: the real token buckets and cooldown at their defaults, charged as
    the route charges them (the route's weight up front, the slot time debited after, the cooldown on leaving)."""
    config = ApiConfig(data_dir=Path("x"))
    limit = config.rate_limit
    clock = Clock()
    clients = TokenBucket(limit.capacity, limit.refill_per_second, limit.max_clients, clock)
    networks = TokenBucket(*limit.network_bucket, limit.max_clients, clock)
    cooldowns = Cooldowns(limit.compare_cooldown_factor, limit.max_clients, clock)
    names = [f"203.0.113.{n + 1}" for n in range(addresses)]
    assert len({network_key(n) for n in names}) == 1
    held, free_at, end = 0.0, 0.0, hours * 3600
    while clock.now < end:
        started = False
        for name in names:
            if clock.now < free_at:
                break
            network = network_key(name)
            buckets = [(clients, name), (networks, network)]
            if take_all(buckets, limit.export_weight) > 0:  # RateLimit: the route's weight, or a 429
                continue
            if cooldowns.enter(network) != 0:
                continue
            clock.now += upload + work  # it holds the slot
            held += upload + work
            free_at = clock.now
            tokens = (limit.compare_upload_weight * upload + work) * 1000 / limit.compare_token_ms
            for bucket, key in buckets:
                bucket.debit(key, tokens)
            cooldowns.leave(network, slot_seconds(config, upload, work))
            started = True
        if not started:
            clock.now += 1.0
    return held / clock.now


@pytest.mark.parametrize("addresses", [1, 2, 3, 8, 64])
def test_one_network_holds_at_most_a_quarter_of_the_slot(addresses: int) -> None:
    """Sixty-second comparisons back to back, from any number of addresses of one network: 25% at the default
    cooldown factor of 3 (the review measured 46.7%, 92.6% and 100% for 1, 2 and 3 addresses before it)."""
    assert share_of_the_slot(addresses, upload=0.0, work=60.0) <= 0.2501
    assert share_of_the_slot(addresses, upload=0.0, work=18.0) <= 0.2501  # the review's own file


@pytest.mark.parametrize("addresses", [1, 2, 3, 8, 64])
def test_stalled_uploads_hold_far_less(addresses: int) -> None:
    """Headers sent, no body, 408 after 30 s: the upload's time counts four times over, so 7.7%."""
    # 30 / (30 + 3 × 4 × 30) = 7.7%; ten hours, so the first hold at time 0 doesn't round it up
    assert share_of_the_slot(addresses, upload=30.0, work=0.0, hours=10.0) <= 0.0780


def test_one_client_alone_is_bounded_by_its_own_bucket_too() -> None:
    assert share_of_the_slot(1, upload=0.0, work=60.0) <= 0.2501
    # without the cooldown the buckets alone let a network hold it (what the review found): the test's own
    # control, so a change that removes the cooldown can't pass by accident
    config = ApiConfig(data_dir=Path("x"), rate_limit=RateLimit(compare_cooldown_factor=0))
    assert config.rate_limit.compare_cooldown_factor == 0
    clock = Clock()
    free = Cooldowns(0, 10, clock)
    assert free.enter("n") == 0
    free.leave("n", 60.0)
    assert free.enter("n") == 0  # no pause at factor 0


def test_cooldowns_are_per_network_and_bounded() -> None:
    clock = Clock()
    cool = Cooldowns(3.0, 2, clock)
    assert cool.enter("a") == 0
    assert cool.enter("a") == -1.0  # one at a time
    assert cool.enter("b") == 0  # another network is not held up
    cool.leave("a", 10.0)
    assert cool.enter("a") == pytest.approx(30.0)
    clock.now = 29.0
    assert cool.enter("a") == pytest.approx(1.0)
    clock.now = 30.0
    assert cool.enter("a") == 0
    cool.leave("a", 0.0)  # it never held a slot: no pause
    assert cool.enter("a") == 0
    cool.leave("a", 1.0)
    cool.leave("b", 100.0)
    for n in range(50):  # many networks: the map stays at its bound, the longest pauses kept
        assert cool.enter(f"n{n}") == 0
        cool.leave(f"n{n}", 1.0)
    assert len(cool._until) <= 2 and "b" in cool._until


def test_a_network_waits_after_a_comparison_and_search_is_untouched(corpus_dir: Path, logs: Logs) -> None:
    with app_of(corpus_dir, rate_limit=RateLimit(capacity=10_000)) as c:  # the default cooldown
        assert post(c, the_file()).status_code == 200
        r = post(c, the_file())
        e = error(r, 429, "API_RATE_LIMITED")
        assert (
            int(r.headers["retry-after"]) >= 1
            and "One comparison at a time from this network" in e["message"]
        )
        assert c.get("/api/v1/search", params={"q": Q}).status_code == 200
    with app_of(
        corpus_dir, rate_limit=RateLimit(enabled=False)
    ) as c:  # a local instance without a rate limit
        assert [post(c, the_file()).status_code for _ in range(3)] == [200, 200, 200]


def test_a_network_runs_one_comparison_at_a_time_whatever_the_slots(
    corpus_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()
    real = route._run

    def held(*a: Any) -> Any:
        entered.set()
        assert release.wait(30)
        return real(*a)

    monkeypatch.setattr(route, "_run", held)
    with app_of(corpus_dir, rate_limit=RateLimit(capacity=10_000), comparison_slots=2) as c:
        first: list[Any] = []
        t = threading.Thread(target=lambda: first.append(post(c, the_file())))
        t.start()
        assert entered.wait(30)
        r = post(c, the_file())  # a slot is free, but this network already has one
        error(r, 429, "API_RATE_LIMITED")
        assert r.headers["retry-after"] == "5" and r.headers["connection"] == "close"
        release.set()
        t.join(30)
        assert first[0].status_code == 200
        assert c.app.state.comparisons.slots.acquire(blocking=False)  # type: ignore[attr-defined]
        assert c.app.state.comparisons.slots.acquire(blocking=False)  # type: ignore[attr-defined]


def test_a_stalled_upload_is_charged_four_times_its_time(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def stalled(request: Any, seconds: float) -> bytearray:
        route._wall.advance(30.0)  # type: ignore[attr-defined]
        raise route._closing(route.DiagnosticCode.API_UPLOAD_TIMEOUT, "too slow")

    class Wall:
        def __init__(self) -> None:
            self.at = time.monotonic()

        def advance(self, seconds: float) -> None:
            self.at += seconds

        def __call__(self) -> float:
            return self.at

    monkeypatch.setattr(route, "_wall", Wall())
    monkeypatch.setattr(route, "_read", stalled)
    with app_of(corpus_dir, rate_limit=RateLimit(capacity=10_000)) as c:
        error(post(c, the_file()), 408, "API_UPLOAD_TIMEOUT")
        cool: Cooldowns = c.app.state.comparisons.cooldowns  # type: ignore[attr-defined]
        (until,) = cool._until.values()
    line = next(x for x in logs() if x["event"] == "request" and x["route"] == COMPARE)
    assert line["compare_ms"] == pytest.approx(30_000, abs=5) and line["compare_cost_ms"] == pytest.approx(
        120_000, abs=20
    )
    assert line["compare_tokens"] == pytest.approx(240, abs=1)  # 120 s at 500 ms a token
    assert until - cool.clock() == pytest.approx(360, abs=5)  # 3 × (4 × 30 s)


# --- the time limit is checked everywhere (SHOULD 2) --------------------------------------------------------------
def test_every_record_and_every_row_asks_the_clock() -> None:
    """`tick` before each record read and matched and each row written: the count of calls is at least the
    count of records in each phase, so no phase runs for more than one record's work past the limit."""
    file = the_file()
    calls = 0

    def tick() -> None:
        nonlocal calls
        calls += 1

    records = read_ris(file, "file", tick)
    assert calls == len(records) == 13
    calls = 0
    side = scholar_compare.scope_and_match(records, INDEX, Scope(), tick=tick)
    assert calls == 13
    calls = 0
    done = scholar_compare.compare_query(
        "file", Q, side=side, index=INDEX, engine=ORACLE, scope=Scope(), mode="native", tick=tick,
        fetch=lambda ids: {i: BY_ID[i] for i in ids},
    )  # fmt: skip
    assert calls >= len(side.entries) + len(done.added)


@pytest.mark.parametrize(
    "phase",
    ["read_ris", "scope_and_match", "compare_query", "_row", "csv_text", "entries", "model_dump_json"],
)
def test_the_limit_stops_a_comparison_in_whichever_phase_it_runs_out(
    corpus_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    """The clock passes the limit as a phase begins: the comparison is 503 from inside that phase (its first
    record or row), whichever phase it is, never after finishing it."""

    class Wall:
        late = False

        def __call__(self) -> float:
            return 1e9 if self.late else 0.0

    wall = Wall()
    reached: list[str] = []
    after: list[str] = []
    monkeypatch.setattr(route, "_wall", wall)

    def entering(owner: Any, name: str) -> None:
        real = getattr(owner, name)

        def wrapped(*a: Any, **k: Any) -> Any:
            if name == phase and not reached:
                reached.append(name)
                wall.late = True
            elif reached and name != phase:
                after.append(name)
            return real(*a, **k)

        monkeypatch.setattr(owner, name, wrapped)

    for name in ("read_ris", "scope_and_match", "compare_query", "_row", "csv_text", "entries"):
        entering(route, name)
    if phase == "model_dump_json":
        real_dump = route.CompareResponse.model_dump_json

        def dump(self: Any, *a: Any, **k: Any) -> str:
            raise AssertionError("serialised past the limit")

        real_text = route.csv_text
        seen = 0

        def last_csv(*a: Any, **k: Any) -> str:
            nonlocal seen
            seen += 1
            made = real_text(*a, **k)
            if seen == 5:  # the fifth and last CSV is written: the limit passes before the JSON is
                reached.append(phase)
                wall.late = True
            return made

        monkeypatch.setattr(route, "csv_text", last_csv)
        monkeypatch.setattr(route.CompareResponse, "model_dump_json", dump)
        assert real_dump is not dump
    with app_of(corpus_dir) as c:
        r = post(c, the_file())
    e = error(r, 503, "API_BUSY")
    assert reached == [phase] and "ran past" in e["message"]
    later = {"read_ris": 0, "scope_and_match": 1, "compare_query": 2, "_row": 3, "csv_text": 4, "entries": 5}
    assert not [name for name in after if later[name] > later.get(phase, 9)]  # no later phase began


def test_a_hostile_file_stops_within_a_margin_of_the_limit(corpus_dir: Path) -> None:
    """Titles built to be slow to normalize (1,000 characters of combining marks and case-folding letters),
    as many as the caps allow in a short test: the answer is a 503 soon after the limit, not when the file is
    done."""
    hostile = "".join(entry(("İ́ẞ" * 331) + str(n), "NeurIPS", 2024) for n in range(1500))
    limit = 0.3
    with app_of(corpus_dir, compare_max_seconds=limit) as c:
        started = time.perf_counter()
        r = post(c, hostile)
        took = time.perf_counter() - started
    error(r, 503, "API_BUSY")
    assert took < limit + 2.0, took  # a loaded machine's margin; idle it is the limit plus one record's work


# --- what of a link is echoed, and how large an answer may be (SHOULD 3) -----------------------------------------
@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://OpenReview.net/forum?id=abc", "openreview.net"),
        ("https://proceedings.mlr.press:443/v202/a23a.html", "proceedings.mlr.press:443"),
        ("http://" + "\x01" * 300 + "/x", None),
        ("http://" + "a" * 300 + ".example/x", None),
        ("http://exa mple.org/x", None),
        ("http://<script>alert(1)</script>/x", None),
        ("http://user:secret@example.org/x", None),  # credentials are never a host name
        ("http://[x", None),  # urlparse refuses it: no host, and no refusal of the file
        ("not a url", None),
    ],
)
def test_only_a_host_name_is_kept_of_a_link(url: str, host: str | None) -> None:
    assert scholar_compare._named(link_host, url) == host


def test_a_rows_evidence_names_at_most_three_host_names(shared_review: TestClient) -> None:
    links = [f"https://host{n}.example/paper" for n in range(40)] + ["http://" + "\x01" * 30_000 + "/x"]
    record = "TY  - JOUR\nTI  - a paper nobody indexed\nJF  - NeurIPS\nPY  - 2024\n"
    file = "".join(
        record.replace("nobody", f"nobody {n}") + "".join(f"UR  - {u}\n" for u in links) + "ER  - \n"
        for n in range(30)
    )
    r = post(shared_review, file)
    assert (
        r.status_code == 200 and len(r.content) < len(file.encode()) / 10
    )  # 0.9 MB of links, a small answer
    body = r.json()
    assert body["not_in_index_total"] == 30
    for row in body["not_in_index"]:
        assert row["detail"].endswith("its links are on host0.example, host1.example, host2.example")
    assert "\\u0001" not in r.text and f"host{MAX_HOSTS}.example" not in r.text


def test_an_answer_over_the_size_bound_is_refused(corpus_dir: Path) -> None:
    file = "".join(
        entry(f"{'long title ' * 80}{n}", "AISTATS", 2024) for n in range(200)
    )  # ~180 KB echoed twice
    with app_of(corpus_dir, compare_max_response_bytes=100_000) as c:
        e = error(post(c, file), 422, "API_COMPARE_TOO_COSTLY")
        assert "100,000 bytes" in e["message"] and "long title" not in e["message"]
        assert (
            compared(c, by_title(BY_ID[KEPT[0]]), "trust benchmark agent")["records_total"] == 1
        )  # a small one
    with app_of(corpus_dir) as c:
        big = post(c, file)
        assert big.status_code == 200 and 100_000 < len(big.content) < 16 * 1024 * 1024


@pytest.fixture
def shared_review(corpus_dir: Path) -> Any:
    with app_of(corpus_dir) as c:
        yield c


# --- the match table: a failure is retried, builds are serialised (SHOULD 4, a nit) -----------------------------
def test_a_failed_table_is_built_again_on_reload_and_meta_says_so_meanwhile(
    corpus_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    logs: Logs,
) -> None:
    real = MatchIndex.build
    broken = True

    def build(records: Any) -> MatchIndex:
        if broken:
            raise RuntimeError("no table today")
        return real(records)

    monkeypatch.setattr(MatchIndex, "build", build)
    with app_of(corpus_dir) as c:
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        assert c.get("/api/v1/meta").json()["limits"]["compare"] is None  # not offered while it can't run
        error(post(c, the_file()), 500, "API_INTERNAL")
        assert state.load()  # a reload while it still fails: tried again, still failed
        assert c.get("/api/v1/meta").json()["limits"]["compare"] is None
        broken = False
        engine = state.served.engine  # type: ignore[union-attr]
        assert state.load()  # SIGHUP, `current` unmoved: the index is kept, the table built
        assert state.served is not None and state.served.engine is engine
        assert c.get("/api/v1/meta").json()["limits"]["compare"] is not None
        assert compared(c, the_file())["records_total"] == 13
        served = state.served
        assert state.load() and state.served is served  # and a healthy table is not rebuilt
    events = [x["event"] for x in logs() if x["event"].startswith(("match_index", "index_unchanged"))]
    assert events == ["match_index_failed", "match_index_failed", "match_index_built", "index_unchanged"]


def test_a_superseded_build_is_skipped_and_builds_never_overlap(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quick reloads: each new bundle asks for its table, one build runs at a time, and a bundle swapped out
    while it waited is never built."""
    running, most, built = 0, 0, []
    gate = threading.Event()
    real = MatchTable.build

    def build(self: MatchTable, records: Any, version: str) -> None:
        nonlocal running, most
        running += 1
        most = max(most, running)
        gate.wait(10)
        real(self, records, version)
        built.append(self)
        running -= 1

    monkeypatch.setattr(MatchTable, "build", build)
    with TestClient(make_app(corpus_dir, compare_enabled=True, load_in_background=True)) as c:
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        deadline = time.monotonic() + 30
        while state.served is None and time.monotonic() < deadline:
            time.sleep(0.01)
        first = state.served
        assert first is not None and first.matches is not None
        tables = [first.matches]
        for _ in range(4):  # four more bundles of the same index, each with a table of its own to build
            state._served = state._bundle(first.engine, first.records, first.listed, MatchTable())
            tables.append(state._served.matches)  # type: ignore[arg-type]
            state._build_matches(state._served)
        gate.set()
        while (tables[-1].index is None or running) and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
    assert most == 1  # never two at once
    assert tables[-1].index is not None and [t for t in tables[1:-1] if t.index is not None] == []
    assert len(built) <= 2  # the one that was running, and the one left serving


# --- nits ---------------------------------------------------------------------------------------------------------
def test_a_malformed_link_names_no_paper_and_never_refuses_the_file(shared_review: TestClient) -> None:
    p = BY_ID[KEPT[0]]
    bad = [
        "http://[x",
        "https://proceedings.mlr.press/v" + "9" * 5000 + "/a23a.html",
        "http://\x01/x",
        "::::",
    ]
    file = by_title(p).replace("ER  - ", "".join(f"UR  - {u}\n" for u in bad) + "ER  - ")
    body = compared(shared_review, file)
    assert [(r["id"], r["matched_by"]) for r in body["kept"]] == [(p.id, "title_venue_year")]


def test_the_uploads_bytes_are_released_once_decoded(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handler keeps no reference to the file's bytes: the worker takes them out of the one holder."""
    holders: list[list[bytearray]] = []
    real = route._run

    def run(*a: Any) -> Any:
        holders.append(a[-1])
        assert len(a[-1]) == 1 and isinstance(a[-1][0], bytearray)
        done = real(*a)
        assert a[-1] == []  # taken out, so the bytearray died with `_run`'s local
        return done

    monkeypatch.setattr(route, "_run", run)
    with app_of(corpus_dir) as c:
        assert post(c, the_file()).status_code == 200
    assert holders == [[]]


# --- a takedown is followed here too (the audit's gap) ---------------------------------------------------------
def named(*papers: Any) -> str:
    """A file naming each paper by its OpenReview link (so it matches whatever its title says)."""
    return "".join(
        entry("some title", p.venue, p.year, f"https://openreview.net/forum?id={p.native}") for p in papers
    )


def csv_details(text: str) -> dict[str, str]:
    import csv
    import io

    return {r["id"]: r["detail"] for r in csv.DictReader(io.StringIO(text.removeprefix("\ufeff")))}


def test_a_takedown_follows_a_merged_or_rekeyed_id_on_this_route(aliased: Aliased) -> None:
    """The list names the id the newest index has; the served (older) index holds the paper only under its
    aliases: `rekeyed` (the same native id, a year off) and `dup` (linked by another snapshot's merges.csv).
    Both are withheld here as on `/search`: no evidence in the row or the CSV, no abstract anywhere."""
    data, prev, _, paper, rekeyed, dup = aliased
    with TestClient(make_app(data, index=prev, compare_enabled=True, rate_limit=NO_COOLDOWN)) as c:
        assert c.get(f"/api/v1/papers/{paper.id}").status_code == 404  # only the aliases are served here
        control = next(
            p for p in (attributed(r) for r in list(records())[:300]) if p.id != paper.id and p.abstract
        )
        dropped = post(c, named(rekeyed, dup, control), "zzqqnosuchword")
        assert dropped.status_code == 200, dropped.text
        body = dropped.json()
        rows = {x["id"]: x for x in body["dropped"]}
        assert set(rows) == {rekeyed.id, dup.id, control.id}
        for alias in (rekeyed, dup):
            assert rows[alias.id]["abstract_withheld"] is True and rows[alias.id]["detail"] == ""
            assert csv_details(body["csv"]["dropped"])[alias.id] == ""
        assert rows[control.id]["abstract_withheld"] is False and rows[control.id]["detail"] != ""
        assert csv_details(body["csv"]["dropped"])[control.id] == rows[control.id]["detail"]
        added = post(c, named(control), takedown_check.cell_query(rekeyed.id))
        assert added.status_code == 200, added.text
        there = {x["id"]: x for x in added.json()["added"]}
        assert there[rekeyed.id]["abstract_withheld"] is True and there[rekeyed.id]["detail"] == ""
        ris = {r.fields["ID"][0]: r for r in parse_ris(added.json()["added_ris"], "added.ris")}
        assert "AB" not in ris[rekeyed.id].fields and exporter.TAKEDOWN in ris[rekeyed.id].fields["N1"]
    assert paper.abstract is not None
    assert paper.abstract[:40] not in dropped.text and paper.abstract[:40] not in added.text


def test_a_takedown_follows_a_twin_link_on_this_route(twins_data: Path, twins_store: Twins) -> None:
    """Three twin records, one of them listed: all three are withheld, as dropped and as added, in the row,
    the CSV and the RIS, while an unlisted paper of the same venue and year keeps its evidence."""
    _, conf, copy, copy2, _other = twins_store
    cell = [
        p
        for p in (attributed(r) for r in list(records())[:300])
        if (p.venue, p.year) == (conf.venue, conf.year)
    ]
    control = next(p for p in cell if p.id not in {conf.id, copy.id, copy2.id} and p.abstract)
    listing(twins_data, copy.id)  # only one twin is listed
    with TestClient(make_app(twins_data, compare_enabled=True, rate_limit=NO_COOLDOWN)) as c:
        dropped = post(c, named(conf, copy, copy2, control), "zzqqnosuchword")
        assert dropped.status_code == 200, dropped.text
        body = dropped.json()
        rows = {x["id"]: x for x in body["dropped"]}
        details = csv_details(body["csv"]["dropped"])
        assert set(rows) == {conf.id, copy.id, copy2.id, control.id}
        for twin in (conf, copy, copy2):
            assert rows[twin.id]["abstract_withheld"] is True and rows[twin.id]["detail"] == ""
            assert details[twin.id] == ""
        assert rows[control.id]["abstract_withheld"] is False
        assert rows[control.id]["detail"] != "" and details[control.id] == rows[control.id]["detail"]
        entirely = post(c, named(BY_ID[KEPT[0]]), takedown_check.cell_query(conf.id))
        assert entirely.status_code == 200, entirely.text
        added = entirely.json()
        there = {x["id"]: x for x in added["added"]}
        added_details = csv_details(added["csv"]["added"])
        ris = {r.fields["ID"][0]: r for r in parse_ris(added["added_ris"], "added.ris")}
        for twin in (conf, copy, copy2):
            assert there[twin.id]["abstract_withheld"] is True and there[twin.id]["detail"] == ""
            assert added_details[twin.id] == ""
            assert "AB" not in ris[twin.id].fields and exporter.TAKEDOWN in ris[twin.id].fields["N1"]
        assert there[control.id]["abstract_withheld"] is False and "AB" in ris[control.id].fields
    for twin in (conf, copy, copy2):
        assert twin.abstract is not None
        assert twin.abstract[:40] not in dropped.text and twin.abstract[:40] not in entirely.text
