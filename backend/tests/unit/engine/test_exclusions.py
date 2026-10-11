"""Exclusion accounting (spec 03 §Exclusion accounting; default-filters, prisma-reporting skills): both engines
against a brute-force count over the 200-record fixture, the overlap rule on a hand-built corpus, and
counts from `identification_ast`, never from re-parsing `identification_query`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.exclusions import Excluded, excluded
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import Engine, EngineInputError, EngineInternalError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import PaperRecord
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
    "trust NOT track:workshop",  # a top-level NOT of a track filter: the user's own, only status defaults
    "track:(main OR datasets_benchmarks OR position) track:workshop",  # default-equal beside another: own
    "(trust track:(main OR position OR datasets_benchmarks)) model",  # a default inside a nested AND
    "model OR language",
    '"language model" OR benchmark*',
]


def tantivy_of(
    records: Sequence[Rec | PaperRecord],
    root: Path,
    schema_version: str | None = None,
    tokenizer_version: str | None = None,
) -> TantivyEngine:
    """An engine over a fresh index of `records` (at `schema_version`, the current one by default). A fixture
    `Rec` becomes a snapshot record (`as_paper`); a `PaperRecord` is indexed as it is, its provenance (and so its
    `abstract_kind`) kept."""
    snap = root / "snap"
    snap.mkdir(parents=True)
    papers = tuple(
        sorted((r if isinstance(r, PaperRecord) else as_paper(r) for r in records), key=lambda p: p.id)
    )
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    return TantivyEngine(
        build_index(
            snap, root / "indexes", BUILT, schema_version=schema_version, tokenizer_version=tokenizer_version
        ).path
    )


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, Engine]:
    return ReferenceEngine(RECORDS), tantivy_of(RECORDS, tmp_path_factory.mktemp("excl"))


def run(engine: Engine, result: ParseResult) -> Excluded:
    """As the API calls it: with the search's own total."""
    return excluded(engine, result, len(engine.match_ids(result.effective_ast)))  # type: ignore[arg-type]


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
        got = run(engine, result)
        assert got == expected
        assert got.total == sum(got.track.values()) + sum(got.status.values())
        for bucket in (got.track, got.status):  # the order spec 04 pins: by count, ties by name, unknown last
            named = [(-n, v) for v, n in bucket.items() if v != "unknown"]
            assert named == sorted(named) and list(bucket)[-1] == "unknown"


def test_the_fixture_exercises_every_bucket(engines: tuple[Engine, Engine]) -> None:
    got = run(engines[0], parsed("track:(main OR datasets_benchmarks OR position) status:accepted"))
    assert got.track == {"workshop": 28, "unknown": 31}
    assert got.status == {"rejected": 27, "withdrawn": 20, "unknown": 19}
    assert got.total == 200 - 75  # 75 accepted main/datasets_benchmarks/position records


def test_a_rejected_workshop_paper_counts_once_under_track(tmp_path: Path) -> None:
    records = [
        Rec("fx:001", "trust", None, track="workshop", status="rejected"),
        Rec("fx:002", "trust", None, track="main", status="rejected"),
        Rec("fx:003", "trust", None, track="unknown", status="unknown"),
        Rec("fx:004", "trust", None, track="main", status="unknown"),
        Rec("fx:005", "trust", None),
    ]
    for engine in (ReferenceEngine(records), tantivy_of(records, tmp_path)):
        assert run(engine, parsed("trust")).to_json() == {
            "total": 4,
            "track": {"workshop": 1, "unknown": 1},
            "status": {"rejected": 1, "unknown": 1},
        }


def test_buckets_are_ordered_by_count_then_name() -> None:
    tracks = ["workshop", "competition", "competition", "workshop", "unknown", "other"]
    records = [Rec(f"fx:{i:03d}", "trust", None, track=t) for i, t in enumerate(tracks)]
    got = run(ReferenceEngine(records), parsed("trust"))
    assert list(got.track.items()) == [("competition", 2), ("workshop", 2), ("other", 1), ("unknown", 1)]


def test_excluded_is_read_only_and_unhashable(engines: tuple[Engine, Engine]) -> None:
    got = run(engines[0], parsed("trust"))
    with pytest.raises(TypeError):
        got.track["workshop"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        hash(got)


def test_only_default_clauses_are_accounted(engines: tuple[Engine, Engine]) -> None:
    own = run(engines[0], parsed("trust track:workshop"))
    assert own.track == {"unknown": 0}  # the user's track set is a limit, not an exclusion
    none = run(engines[0], parsed("trust track:workshop status:rejected"))
    assert none == Excluded(0, {"unknown": 0}, {"unknown": 0})


@pytest.mark.parametrize(
    "q", ["track:(main OR datasets_benchmarks OR position) status:accepted", "status:accepted NOT model"]
)
def test_counts_come_from_the_tree_never_the_string(engines: tuple[Engine, Engine], q: str) -> None:
    result = parsed(q)
    assert result.identification_query in ("", "NOT model")  # the two strings that can't be re-parsed
    garbled = result.model_copy(update={"identification_query": "((("})
    for engine in engines:
        assert run(engine, garbled) == run(engine, result) == brute(RECORDS, result)


def test_a_query_with_errors_is_refused(engines: tuple[Engine, Engine]) -> None:
    with pytest.raises(EngineInputError):
        excluded(engines[0], parse("NOT trust"), 0)


def test_a_wildcard_over_the_cap_is_refused_not_counted(tmp_path: Path) -> None:
    records = [Rec(f"fx:{i:03d}", f"trust{i:03d}", None) for i in range(210)]
    result = parsed("trust*")
    for engine in (ReferenceEngine(records), tantivy_of(records, tmp_path)):
        with pytest.raises(EngineInputError) as e:
            excluded(engine, result, 0)
        assert e.value.code == DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS


def test_buckets_that_do_not_add_up_are_an_internal_error(engines: tuple[Engine, Engine]) -> None:
    class Miscounting(ReferenceEngine):
        def facets(self, ast, fields=("status",)):  # type: ignore[no-untyped-def]
            out = super().facets(ast, fields)
            return {f: {**c, "withdrawn": c.get("withdrawn", 0) + 1} for f, c in out.items()}

    with pytest.raises(EngineInternalError, match="don't sum") as e:
        run(Miscounting(RECORDS), parsed("trust"))
    assert isinstance(e.value, InternalError)  # a 5xx, logged at ERROR
    with pytest.raises(EngineInternalError, match="don't sum"):  # a total that isn't the search's
        excluded(engines[1], parsed("trust"), len(engines[1].match_ids(parsed("trust").effective_ast)) + 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("q", ["trust", "trust OR track:workshop", "trust track:workshop"])
def test_a_cold_exclusion_only_call_aggregates_only_the_default_fields(tmp_path: Path, q: str) -> None:
    """`excluded` with no `facets` on a TantivyEngine aggregates only `ORDER` (track, status), as `search.run`
    does without facets (TASK-166): never schema 4's `abstract_kind` or the other combo fields, whose deeper
    nested aggregation cost the cold bench a third of its time (PR #134), and it builds no per-value bitmaps, no
    value table and, with no verified clause, no ord table. The counts are the brute-force ones."""
    engine = tantivy_of(RECORDS, tmp_path)
    assert "abstract_kind" in engine.combo  # schema 4: the field the exclusion path must not aggregate
    result = parsed(q)
    assert run(engine, result) == brute(RECORDS, result)
    assert {key.split("\x00")[0] for key in engine.faceted} == {"track,status"}
    assert engine._masks is None and engine._index is None and engine._ords is None


def test_the_narrowed_path_keeps_an_abstract_kind_clause_in_the_base(tmp_path: Path) -> None:
    """`abstract_kind` is not aggregated on the exclusion-only path (`ORDER`), so a top-level `abstract_kind:`
    clause stays in the collected base, never set aside: the counts are the oracle's and the full combo's, over
    the every-kind corpus with some workshop and rejected papers to remove."""
    from tests.fixtures.corpus import abstract_kinds

    corpus = [
        # the OpenAlex `trust` papers are 0, 12, 24, 36, 48: three to workshops, one rejected, one kept
        r.model_copy(
            update={"track": "workshop"} if i % 24 == 0 else {"status": "rejected"} if i == 12 else {}
        )
        for i, r in enumerate(abstract_kinds.records())
    ]
    engine, oracle = tantivy_of(corpus, tmp_path), ReferenceEngine(corpus)
    result = parsed("trust abstract_kind:openalex")
    total = len(engine.match_ids(result.effective_ast))  # type: ignore[arg-type]
    narrow = excluded(engine, result, total)
    assert (total, narrow.to_json()) == (
        1,
        {"total": 4, "track": {"workshop": 3, "unknown": 0}, "status": {"rejected": 1, "unknown": 0}},
    )
    assert narrow == excluded(oracle, result, total) == excluded(engine, result, total, facets=engine.facets)
    keys = [k for k in engine.faceted if k.startswith("track,status\x00")]
    assert keys and all("abstract_kind" in k for k in keys)  # the clause is in each narrowed base
