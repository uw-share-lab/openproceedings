"""Exclusion accounting (spec 03 §Exclusion accounting; default-filters, prisma-reporting skills): both engines
against a brute-force count over the 200-record fixture, the overlap rule on a hand-built corpus, and
counts from `identification_ast`, never from re-parsing `identification_query`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.engine.exclusions import Excluded, excluded
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import Engine, EngineError, EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.snapshot import render
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.parser import ParseResult, parse

from tests.corpus import Rec, fixture_records
from tests.golden.test_tantivy_200 import as_paper

BUILT = datetime(2026, 9, 26, tzinfo=UTC)
RECORDS = fixture_records()

QUERIES = [
    "trust",
    "trust status:accepted",  # a typed default is the default
    "track:(main OR datasets_benchmarks OR position) status:accepted",  # identification_query ""
    "status:accepted NOT model",  # identification_query all-negative
    "trust OR track:workshop",  # nested: the default still applies
    "trust track:workshop",  # the user's own track set: only status is a default
    "trust track:workshop status:rejected",  # no defaults: nothing excluded
    "trust year:2020..2023",  # a user limit stays in "identified"
    "model OR language",
    '"language model" OR benchmark*',
]


def tantivy_of(records: list[Rec], root: Path) -> TantivyEngine:
    snap = root / "snap"
    snap.mkdir(parents=True)
    papers = tuple(sorted((as_paper(r) for r in records), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    return TantivyEngine(build_index(snap, root / "indexes", BUILT).path)


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, Engine]:
    return ReferenceEngine(RECORDS), tantivy_of(RECORDS, tmp_path_factory.mktemp("excl"))


def parsed(q: str) -> ParseResult:
    result = parse(q)
    assert result.effective_ast is not None, result.errors
    return result


def brute(records: list[Rec], result: ParseResult) -> Excluded:
    """Independent of exclusions.py: identified minus matched, each record bucketed by the first default
    (track, then status) it fails."""
    oracle = ReferenceEngine(records)
    ast = result.identification_ast
    identified = {r.id for r in records} if ast is None else oracle.match_ids(ast)
    matched = oracle.match_ids(result.effective_ast)  # type: ignore[arg-type]
    buckets: dict[str, dict[str, int]] = {"track": {}, "status": {}}
    for r in records:
        if r.id in identified and r.id not in matched:
            field = next(
                f
                for f in ("track", "status")
                if f in result.defaults and getattr(r, f) not in DEFAULT_CLAUSES[f]
            )
            value = getattr(r, field)
            buckets[field][value] = buckets[field].get(value, 0) + 1
    shaped = {
        f: {**{v: n for v, n in sorted(b.items()) if v != "unknown"}, "unknown": b.get("unknown", 0)}
        for f, b in buckets.items()
    }
    return Excluded(len(identified) - len(matched), shaped["track"], shaped["status"])  # fmt: skip


@pytest.mark.parametrize("q", QUERIES)
def test_both_engines_match_the_brute_force_count(engines: tuple[Engine, Engine], q: str) -> None:
    result = parsed(q)
    expected = brute(RECORDS, result)
    for engine in engines:
        got = excluded(engine, result)
        assert got == expected
        assert got.total == sum(got.track.values()) + sum(got.status.values())
        assert list(got.track)[-1] == list(got.status)[-1] == "unknown"


def test_the_fixture_exercises_every_bucket(engines: tuple[Engine, Engine]) -> None:
    got = excluded(engines[0], parsed("track:(main OR datasets_benchmarks OR position) status:accepted"))
    assert got.track == {"workshop": 28, "unknown": 31}
    assert got.status == {"rejected": 27, "withdrawn": 20, "unknown": 19}
    assert got.total == 200 - 75  # 75 accepted main/datasets_benchmarks/position records


def test_a_rejected_workshop_paper_counts_once_under_track() -> None:
    records = [
        Rec("a:1", "trust", None, track="workshop", status="rejected"),
        Rec("a:2", "trust", None, track="main", status="rejected"),
        Rec("a:3", "trust", None, track="unknown", status="unknown"),
        Rec("a:4", "trust", None, track="main", status="unknown"),
        Rec("a:5", "trust", None),
    ]
    got = excluded(ReferenceEngine(records), parsed("trust"))
    assert got.to_json() == {
        "total": 4,
        "track": {"workshop": 1, "unknown": 1},
        "status": {"rejected": 1, "unknown": 1},
    }


def test_only_default_clauses_are_accounted(engines: tuple[Engine, Engine]) -> None:
    own = excluded(engines[0], parsed("trust track:workshop"))
    assert own.track == {"unknown": 0}  # the user's track set is a limit, not an exclusion
    none = excluded(engines[0], parsed("trust track:workshop status:rejected"))
    assert none == Excluded(0, {"unknown": 0}, {"unknown": 0})


@pytest.mark.parametrize(
    "q", ["track:(main OR datasets_benchmarks OR position) status:accepted", "status:accepted NOT model"]
)
def test_counts_come_from_the_tree_never_the_string(engines: tuple[Engine, Engine], q: str) -> None:
    result = parsed(q)
    assert result.identification_query in ("", "NOT model")  # the two strings that can't be re-parsed
    garbled = result.model_copy(update={"identification_query": "((("})
    for engine in engines:
        assert excluded(engine, garbled) == excluded(engine, result) == brute(RECORDS, result)


def test_a_query_with_errors_is_refused(engines: tuple[Engine, Engine]) -> None:
    with pytest.raises(EngineInputError):
        excluded(engines[0], parse("NOT trust"))


def test_buckets_that_do_not_add_up_are_an_internal_error(engines: tuple[Engine, Engine]) -> None:
    class Miscounting(ReferenceEngine):
        def facets(self, ast, fields=("status",)):  # type: ignore[no-untyped-def]
            out = super().facets(ast, fields)
            return {f: {**c, "withdrawn": c.get("withdrawn", 0) + 1} for f, c in out.items()}

    with pytest.raises(EngineError, match="don't sum"):
        excluded(Miscounting(RECORDS), parsed("trust"))
