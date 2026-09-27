"""What one query can make the service spend, round 3 of the M3a review gate (spec 04 §Rate limit, §Search
records; decision-010): cold verification bounded by the documents its position checks would read
(`API_QUERY_TOO_COSTLY`, located, before any is verified), a replay over either verification limit withheld
(200, `refused`, never a 422, and still exportable), the verified charge given back on `API_BUSY` and on
`API_QUERY_TOO_COSTLY`, and the access line's `verified_clauses`, `verification_candidates` and `verify_ms`
with a `verification_slow` WARNING."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.api import server as api_server
from openproceedings.api.config import ApiConfig
from openproceedings.engine.compile import verified_clauses
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse

from tests.contract.conftest import Store, make_app
from tests.contract.test_abuse_limits import VERIFIED, error
from tests.contract.test_export import ids_of
from tests.contract.test_records import mismatch_lines, save, tampered

SEARCH = "/api/v1/search"
# two position-verified clauses with candidates in the 5k fixture (`many_verified`'s have none)
TWO = ('"trust calibrat*"', '"calibrat* model"')
Logs = Callable[[], list[dict[str, Any]]]


def candidates(engine: TantivyEngine, q: str) -> int:
    ast = parse(q).effective_ast
    assert ast is not None
    return sum(n for _c, _f, n in engine.candidates(ast))


def never(*_a: Any, **_kw: Any) -> Any:
    pytest.fail("verified a clause")


# --- the candidate ceiling ---------------------------------------------------------------------------------------
def test_candidates_count_what_a_cold_verification_reads(store: Store) -> None:
    """Each (clause, field)'s count is the documents its position check reads (`Compiler.verified`'s
    candidates), in query order, one per field the clause is verified in, counted without reading one."""
    engine = TantivyEngine(store.indexes / store.big)
    ast = parse(f'{VERIFIED} OR title:"model calibrat*"').effective_ast
    assert ast is not None
    first, second = verified_clauses(ast)
    counted = engine.candidates(ast)
    assert [(c, f) for c, f, _n in counted] == [(first, "title"), (first, "abstract"), (second, "title")]
    read: list[int] = []
    original = engine.read

    def counting(query: Any, field: Any) -> Any:
        docs = list(original(query, field))
        read.append(len(docs))
        return iter(docs)

    engine.read = counting  # type: ignore[method-assign]
    engine.compile(ast)
    assert read == [n for _c, _f, n in counted] and sum(read) > 0


@pytest.mark.parametrize("route", ["search", "records", "export"])
def test_a_query_over_the_candidate_ceiling_is_a_located_422_before_any_verification(
    store: Store, route: str
) -> None:
    q = " OR ".join(TWO)
    with TestClient(make_app(store.indexes.parent)) as probe:
        need = candidates(probe.app.state.index.engine, q)  # type: ignore[attr-defined]
    assert need > 0
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=need - 1)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        engine.read = never
        r = {
            "search": lambda: c.get(SEARCH, params={"q": q}),
            "records": lambda: c.post("/api/v1/records", json={"q": q}),
            "export": lambda: c.get("/api/v1/export", params={"q": q, "format": "ris"}),
        }[route]()
        e = error(r, 422, "API_QUERY_TOO_COSTLY")
        assert f"would read {need:,} documents" in e["message"] and f"at most {need - 1:,}" in e["message"]
        assert [q[d["span"][0] : d["span"][1]] for d in e["diagnostics"]] == list(TWO)
        assert all("documents in title" in d["message"] for d in e["diagnostics"])
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=need)) as c:
        assert c.get(SEARCH, params={"q": q}).status_code == 200  # at the ceiling: served


def test_an_over_cap_wildcard_is_still_its_own_located_422(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expansions come before the candidate count, so the wildcard cap keeps its code and its span."""
    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)  # calibrat* has 2
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=1)) as c:
        e = error(c.get(SEARCH, params={"q": TWO[0]}), 422, "WILDCARD_TOO_MANY_EXPANSIONS")
    assert [d["span"] for d in e["diagnostics"]] == [[7, 16]]


def test_the_default_candidate_ceiling() -> None:
    assert ApiConfig(data_dir=Path("x")).max_verification_candidates == 300_000


# --- refunds -----------------------------------------------------------------------------------------------------
def test_a_too_costly_query_gets_its_verified_charge_back(store: Store) -> None:
    limit = RateLimit(capacity=24, refill_per_second=0.001, export_weight=10)  # 10 per clause, cap 2
    app = make_app(
        store.indexes.parent, rate_limit=limit, max_verified_clauses=2, max_verification_candidates=1
    )
    with TestClient(app) as c:
        for _ in range(3):  # 20 each without the refund: the second would be a 429
            error(c.get(SEARCH, params={"q": " OR ".join(TWO)}), 422, "API_QUERY_TOO_COSTLY")
        assert c.get(SEARCH, params={"q": "trust"}).status_code == 200  # 4 of 24 spent


def test_a_busy_query_gets_its_verified_charge_back(store: Store) -> None:
    limit = RateLimit(capacity=20, refill_per_second=0.001, export_weight=10, verified_weight=8)
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verified_clauses=2)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        read = engine.read
        entered, release = threading.Event(), threading.Event()

        def slow(*args: Any) -> Any:
            entered.set()
            assert release.wait(10)
            return read(*args)

        engine.read = slow
        try:
            with ThreadPoolExecutor(1) as pool:
                first = pool.submit(c.get, SEARCH, params={"q": VERIFIED})  # 8
                assert entered.wait(10)
                error(c.get(SEARCH, params={"q": '"calibrat* model"'}), 503, "API_BUSY")  # 16, then back to 9
                release.set()
                assert first.result(10).status_code == 200
        finally:
            engine.read = read
        assert c.get(SEARCH, params={"q": "trust"}).status_code == 200  # 10
        assert c.get(SEARCH, params={"q": VERIFIED}).status_code == 200  # 18 of 20 (without the refund, 25)


# --- a replay over a verification limit is withheld, never a 422 -------------------------------------------------
@pytest.mark.parametrize(
    ("limits", "code"),
    [
        ({"max_verified_clauses": 1}, "API_TOO_MANY_VERIFIED_CLAUSES"),
        ({"max_verification_candidates": 1}, "API_QUERY_TOO_COSTLY"),
    ],
)
def test_a_replay_over_a_limit_is_withheld_and_the_record_stays_readable_and_exportable(
    data_dir: Path, logs: Logs, limits: dict[str, int], code: str
) -> None:
    with TestClient(make_app(data_dir)) as c:
        rid = save(c, " OR ".join(TWO))
        stored = c.get(f"/api/v1/records/{rid}", params={"include": "ids"}).json()["record"]
    before = len(mismatch_lines(logs)) + len(mismatch_lines(logs, "DEBUG"))
    with TestClient(make_app(data_dir, **limits)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        engine.compile = never  # withheld: nothing compiles
        r = c.get(f"/api/v1/records/{rid}")
        assert r.status_code == 200, r.text
        replay = r.json()["replay"]
        assert (replay["status"], replay["refused"], replay["verified_clauses"]) == ("drifted", code, 2)
        assert replay["changed"] == []  # its own index, its own query version: withheld, not changed
        nulls = ("total", "excluded", "ids_hash", "ids_match", "excluded_match", "added_total", "removed_total",
                 "membership_identical")  # fmt: skip
        assert {k: replay[k] for k in nulls} == dict.fromkeys(nulls)
        diff = c.get(f"/api/v1/records/{rid}/diff")
        assert diff.status_code == 200, diff.text
        d = diff.json()
        assert (d["refused"], d["verified_clauses"], d["added"], d["removed"]) == (code, 2, [], [])
        exported = c.get("/api/v1/export", params={"record_id": rid, "format": "jsonl"})
        assert exported.status_code == 200, exported.text
        assert int(exported.headers["x-total"]) == stored["total"]
        assert ids_of("jsonl", exported.content) == stored["ids"]  # exactly the stored ids
    assert len(mismatch_lines(logs)) + len(mismatch_lines(logs, "DEBUG")) == before  # never a mismatch


def test_a_withheld_replay_whose_run_free_check_fails_is_a_mismatch(data_dir: Path, logs: Logs) -> None:
    """Withholding the run never hides what needs no run: a stored canonical hash that isn't the re-parse's
    is a mismatch, logged, however the instance's limits stand."""
    with TestClient(make_app(data_dir)) as c:
        good = save(c, " OR ".join(TWO))
    bad = tampered(data_dir, good, canonical_hash="0" * 64)
    with TestClient(make_app(data_dir, max_verified_clauses=1)) as c:
        replay = c.get(f"/api/v1/records/{bad}").json()["replay"]
        assert (replay["status"], replay["refused"]) == ("mismatch", "API_TOO_MANY_VERIFIED_CLAUSES")
        error(c.get("/api/v1/export", params={"record_id": bad, "format": "ris"}), 409, "API_RECORD_MISMATCH")
    [line] = [x for x in mismatch_lines(logs) if x["record_id"] == bad]
    assert line["refused"] == "API_TOO_MANY_VERIFIED_CLAUSES" and line["ids_match"] is None


# --- the access line and the slow-verification warning ------------------------------------------------------------
def test_the_access_line_carries_the_verification_work(store: Store, logs: Logs) -> None:
    with TestClient(make_app(store.indexes.parent, slow_verification_seconds=1e-9)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        need = candidates(engine, VERIFIED)
        assert c.get(SEARCH, params={"q": VERIFIED}).status_code == 200  # cold
        assert c.get(SEARCH, params={"q": VERIFIED}).status_code == 200  # cached: no slot held
        assert c.get(SEARCH, params={"q": "trust"}).status_code == 200
    cold, warm, plain = [x for x in logs() if x["event"] == "request"]
    assert (cold["verified_clauses"], cold["verification_candidates"]) == (1, need)
    assert cold["verify_ms"] > 0 and "verify_ms" not in warm and warm["verification_candidates"] == need
    assert plain["verified_clauses"] == 0 and "verification_candidates" not in plain
    [slow] = [x for x in logs() if x["event"] == "verification_slow"]
    assert slow["level"] == "WARNING" and slow["verify_ms"] > 0 and slow["request_id"] == cold["request_id"]


def test_a_request_under_the_threshold_logs_no_warning(client: TestClient, logs: Logs) -> None:
    assert client.get(SEARCH, params={"q": '"trust model*"'}).status_code == 200
    assert [x for x in logs() if x["event"] == "verification_slow"] == []


# --- op serve ------------------------------------------------------------------------------------------------------
def test_op_serve_takes_the_verification_limits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, ApiConfig] = {}
    monkeypatch.setattr(api_server, "serve", lambda config, *a: seen.update(config=config))
    argv = ["--data-dir", str(tmp_path), "serve", "--max-verified-clauses", "4",
            "--max-verification-candidates", "1000"]  # fmt: skip
    assert cli.main(argv) == 0
    config = seen["config"]
    assert (config.max_verified_clauses, config.max_verification_candidates) == (4, 1000)
    assert config.verified_cost == 10  # min(export_weight 10, 60 / 4)
    assert ApiConfig(data_dir=tmp_path).max_verified_clauses == 16  # the flag's default is the config's


@pytest.mark.parametrize(
    ("flags", "says"),
    [
        (["--trusted-proxy", "0.0.0.0/0"], "trusted proxy 0.0.0.0/0 is wider than /8"),
        (["--max-verified-clauses", "0"], "max_verified_clauses: Input should be greater than or equal to 1"),
        (["--rate-capacity", "5", "--export-weight", "6"], "export_weight must not exceed capacity"),
    ],
)
def test_op_serve_says_why_an_option_is_refused(
    flags: list[str],
    says: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(api_server, "serve", lambda *a: pytest.fail("served"))
    assert cli.main(["--data-dir", str(tmp_path), "serve", *flags]) == 1
    err = capsys.readouterr().err
    assert "invalid serve options" in err and says in err
