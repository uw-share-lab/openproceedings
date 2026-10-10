"""`op eval openalex` (milestone C Task 13): OpenAlex's abstracts measured against official ones, per venue-year, and
the title route's attaches checked against the record's authors; fetched through the one OpenAlex fetcher and cache,
so an `--offline` re-run reproduces the report byte for byte."""

import json
import zlib
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.eval import openalex_audit as oa
from openproceedings.ingest import openalex_table
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.http import Fetcher, PageCache, canonical

from tests.unit.eval import audit_fixture
from tests.unit.ingest.openalex import api
from tests.unit.ingest.proceedings_helpers import FakeTransport, response


@pytest.mark.parametrize(("official", "other", "kind"), [
    ("A study of trust.", "A study of trust.", "exact"),
    ("A study  of trust.", "A study of trust.", "exact"),
    ("A Study of Trust!", "a study of trust", "near_exact"),  # the same search tokens
    ("A study of trust in models.", "A study of trust", "truncated"),
    (" ".join(["word"] * 50) + " end", " ".join(["word"] * 50) + " fin", "similar"),
    ("A study of trust.", "Something else entirely.", "differs"),
])  # fmt: skip
def test_compare(official: str, other: str, kind: str) -> None:
    assert oa.compare(official, other) == kind


def test_the_sample_is_seeded_and_covers_the_named_venue_years() -> None:
    from tests.unit.eval.audit_fixture import (
        records,
    )  # FAccT 2022/2025/2026, AIES 2024-2025, AAAI 2010+ (official)

    one, two = oa.sample(records(), aaai_sample=5, seed=49), oa.sample(records(), aaai_sample=5, seed=49)
    assert [r.id for r in one] == [r.id for r in two]
    assert {(r.venue, r.year) for r in one if r.venue != "AAAI"} == {
        ("FAccT", 2022),
        ("FAccT", 2025),
        ("FAccT", 2026),
        ("AIES", 2024),
        ("AIES", 2025),
    }
    assert sum(r.venue == "AAAI" for r in one) == 5 and all(r.abstract_kind == "official" for r in one)


def test_the_sample_leaves_out_other_years_records_with_no_doi_and_no_official_abstract() -> None:
    picked = {r.id for r in oa.sample(audit_fixture.records(), aaai_sample=5, seed=49)}
    assert not picked & {"op:facct:2023:doi-3593013.3600", "op:facct:2025:doi-3715275.3700",
                         "op:facct:2025:doi-3715275.3701", "op:aaai:1990:dblp-SmithL90"}  # fmt: skip
    assert len(oa.sample(audit_fixture.records(), aaai_sample=500, seed=49)) == 10 + 12  # all, when fewer
    assert {r.id for r in oa.sample(audit_fixture.records(), aaai_sample=5, seed=50)} != picked


def test_render_reports_rates_per_venue_year_and_the_reproduction_command() -> None:
    result = oa.AuditResult(
        rows={("FAccT", 2025): {"exact": 3, "near_exact": 1, "differs": 1, "no_openalex": 1}}
    )
    text = oa.render(result, oa.Meta(snapshot="2026-10-11-abc", commit="0000000", seed=49, aaai_sample=1000))
    assert "| FAccT | 2025 | 6 | 3 (50.0%) | 1 (16.7%)" in text and "op eval openalex --offline" in text
    assert "ACM's published version" in text and "`abstract_kind: openalex`" in text
    aies = oa.render(oa.AuditResult(rows={("AIES", 2024): {"exact": 1}}), oa.Meta(snapshot="s", commit="c", seed=49,
                                                                                aaai_sample=0))  # fmt: skip
    assert "A note on FAccT" not in aies


# --- the audit through a fetcher ----------------------------------------------------------------------------


def _fetcher(cache: Path, t: FakeTransport | None) -> Fetcher:
    """OpenAlex's fetcher as `crawl.openalex_fetcher` builds it (same cache keys), without its 1 s pacing."""
    return Fetcher(PageCache(cache / openalex.CACHE_DIR), t, hosts=openalex.HOSTS, min_interval=0,
                   accept="application/json", expect="json", keep_query=True)  # fmt: skip


def _script(t: FakeTransport, url: str, *works: dict) -> None:
    t.script[canonical(url, keep_query=True)] = [response(api.page(*works), headers=api.JSON)]


def _seed_dois(t: FakeTransport, picked: list, answers: dict[str, list[dict]]) -> None:
    """One batch per venue-year (its DOIs sorted), answered with `answers[doi]` (default: the official text)."""
    groups: dict[tuple[str, int], list] = {}
    for r in picked:
        groups.setdefault((r.venue, r.year), []).append(r)
    for rs in groups.values():
        dois = sorted(openalex.bare_doi(r.urls.doi) for r in rs)
        works = [w for r in rs for w in answers.get(openalex.bare_doi(r.urls.doi),
                 [api.work(f"W{zlib.crc32(r.id.encode())}", openalex.bare_doi(r.urls.doi), text=r.abstract)])]  # fmt: skip
        _script(t, openalex.doi_url(dois), *works)


def test_audit_counts_each_class_per_venue_year(tmp_path: Path) -> None:
    picked = oa.sample(audit_fixture.records(), aaai_sample=12, seed=49)
    facct = sorted((r for r in picked if (r.venue, r.year) == ("FAccT", 2025)), key=lambda r: r.id)
    aies = sorted((r for r in picked if (r.venue, r.year) == ("AIES", 2024)), key=lambda r: r.id)
    d = [openalex.bare_doi(r.urls.doi) for r in (*facct, *aies)]
    t = FakeTransport({})
    _seed_dois(t, picked, {
        d[0]: [api.work("W11", d[0], text=facct[0].abstract.upper())],  # near_exact
        d[1]: [],  # no work: no_openalex
        d[2]: [api.work("W12", d[2], raw={"An": [0], "abstract": [2]})],  # a gap: refused
        d[3]: [api.work("W13", d[3], text="One text."), api.work("W14", d[3], text="Another text.")],  # duplicate
    })  # fmt: skip
    result = oa.audit(picked, _fetcher(tmp_path, t))
    assert result.rows[("FAccT", 2025)] == {"near_exact": 1, "no_openalex": 1}
    assert result.rows[("AIES", 2024)] == {"refused": 1, "duplicate": 1}
    assert result.rows[("FAccT", 2022)] == {"exact": 2}
    assert result.refusals == {"inverted_gap": 1}
    assert sum(sum(row.values()) for row in result.rows.values()) == len(picked)


def test_a_work_with_no_abstract_is_counted_apart_from_no_work(tmp_path: Path) -> None:
    picked = [r for r in oa.sample(audit_fixture.records(), aaai_sample=0, seed=49) if r.venue == "FAccT"]
    t = FakeTransport({})
    first = openalex.bare_doi(picked[0].urls.doi)
    _seed_dois(t, picked, {first: [api.work("W21", first, text=None)]})
    result = oa.audit(picked, _fetcher(tmp_path, t))
    assert result.rows[(picked[0].venue, picked[0].year)]["no_abstract"] == 1


def test_an_offline_rerun_renders_the_same_report_without_a_request(tmp_path: Path) -> None:
    picked = oa.sample(audit_fixture.records(), aaai_sample=12, seed=49)
    t = FakeTransport({})
    _seed_dois(t, picked, {})
    meta = oa.Meta(snapshot="s", commit="c", seed=49, aaai_sample=12)
    live = oa.render(oa.audit(picked, _fetcher(tmp_path, t)), meta)
    sent = len(t.calls)
    offline = _fetcher(tmp_path, None)
    assert oa.render(oa.audit(picked, offline), meta) == live and len(t.calls) == sent
    assert offline.stats.network == 0


def test_the_report_quotes_no_abstract_text(tmp_path: Path) -> None:
    picked = oa.sample(audit_fixture.records(), aaai_sample=12, seed=49)
    t = FakeTransport({})
    first = openalex.bare_doi(picked[0].urls.doi)
    _seed_dois(t, picked, {first: [api.work("W31", first, text="Entirely unrelated words here.")]})
    result = oa.audit(picked, _fetcher(tmp_path, t))
    text = oa.render(result, oa.Meta(snapshot="s", commit="c", seed=49, aaai_sample=12))
    assert picked[0].id in text  # a `differs` example, by id
    assert all(r.abstract not in text for r in picked) and "unrelated" not in text


# --- the title route's attaches -----------------------------------------------------------------------------

TABLE = openalex_table.load("""
[[listing]]
venue = "AAAI"
year = 1990
source_ids = ["S77"]
works = 3
verified = 2026-10-10
source = "test"
""")


def _authors(*names: str) -> list[dict]:
    return [{"author_position": "first" if i == 0 else "middle", "author": {"display_name": n},
             "raw_author_name": n} for i, n in enumerate(names)]  # fmt: skip


def _title_corpus() -> list:
    d = audit_fixture.dblp
    return [d(1990, "SmithL90", "A Planning Paper", ("Ann Smith 0001", "Bo Li")),
            d(1990, "JonesK90", "Search in Graphs", ("Kay Jones",)),
            d(1990, "NguyenT90", "Learning Rules", ("Thi Nguyễn",)),
            d(1990, "OtherX90", "Nobody Lists This", ("X Other",))]  # fmt: skip


def _seed_title(t: FakeTransport, authorships: dict[str, list[dict]]) -> None:
    _script(t, openalex.listing_url(TABLE.listings[("AAAI", 1990)]),
            api.work("W1", None, title="A Planning Paper", year=1990, text="An abstract one."),
            api.work("W2", None, title="Search in Graphs", year=1990, text="An abstract two."),
            api.work("W3", None, title="Learning rules", year=1990, text="An abstract three."))  # fmt: skip
    body = {"meta": {"count": 3, "per_page": 50},
            "results": [{"id": f"https://openalex.org/{w}", "authorships": a, "biblio": {"first_page": "1"}}
                        for w, a in sorted(authorships.items())]}  # fmt: skip
    t.script[canonical(oa.authors_url(["W1", "W2", "W3"]), keep_query=True)] = [
        response(json.dumps(body), headers=api.JSON)
    ]


def test_the_title_check_names_an_attach_whose_authors_disagree(tmp_path: Path) -> None:
    t = FakeTransport({})
    _seed_title(t, {"W1": _authors("A. Smith", "B. Li"), "W2": _authors("Someone Else"),
                    "W3": _authors("T. Nguyen")})  # fmt: skip
    check = oa.title_check(_title_corpus(), _fetcher(tmp_path, t), seed=49, size=50, table=TABLE)
    assert check.attached == 3 and len(check.sampled) == 3
    verdicts = {a.record_id: a.verdict for a in check.sampled}
    assert verdicts == {"op:aaai:1990:dblp-SmithL90": "agree", "op:aaai:1990:dblp-JonesK90": "wrong",
                        "op:aaai:1990:dblp-NguyenT90": "agree"}  # fmt: skip
    assert all(a.year_ok for a in check.sampled)
    text = oa.render(oa.AuditResult(rows={}, title=check), oa.Meta(snapshot="s", commit="c", seed=49,
                                                                 aaai_sample=0))  # fmt: skip
    assert "op:aaai:1990:dblp-JonesK90" in text and "W2" in text
    assert "first-author surname" in text


def test_the_title_check_calls_a_work_with_no_authors_unverifiable(tmp_path: Path) -> None:
    t = FakeTransport({})
    _seed_title(t, {"W1": [], "W2": _authors("Kay Jones")})  # W3 missing from the answer
    check = oa.title_check(_title_corpus(), _fetcher(tmp_path, t), seed=49, size=50, table=TABLE)
    verdicts = {a.record_id: a.verdict for a in check.sampled}
    assert verdicts["op:aaai:1990:dblp-SmithL90"] == "unverifiable"
    assert verdicts["op:aaai:1990:dblp-NguyenT90"] == "unverifiable"
    assert verdicts["op:aaai:1990:dblp-JonesK90"] == "agree"


def test_the_title_check_samples_by_seed(tmp_path: Path) -> None:
    t = FakeTransport({})
    _seed_title(t, {"W1": _authors("A. Smith"), "W2": _authors("Kay Jones"), "W3": _authors("T. Nguyen")})
    for pair in (["W1", "W2"], ["W1", "W3"], ["W2", "W3"]):  # whichever two the seed picks
        t.script[canonical(oa.authors_url(pair), keep_query=True)] = [
            response(json.dumps({"meta": {"count": 2}, "results": []}), headers=api.JSON)
        ]
    two = oa.title_check(_title_corpus(), _fetcher(tmp_path / "a", t), seed=49, size=2, table=TABLE)
    again = oa.title_check(_title_corpus(), _fetcher(tmp_path / "b", t), seed=49, size=2, table=TABLE)
    assert len(two.sampled) == 2 and two.attached == 3 and two == again


@pytest.mark.parametrize(("name", "surname"), [
    ("Ann Smith 0001", "smith"), ("Smith, Ann", "smith"), ("Thi Nguyễn", "nguyen"), ("A. O'Neil", "oneil"),
    ("  ", None),
])  # fmt: skip
def test_surname(name: str, surname: str | None) -> None:
    assert oa.surname(name) == surname


def test_parse_authors_refuses_an_answer_that_is_not_a_work_list() -> None:
    from openproceedings.ingest.sources.common import CrawlError

    with pytest.raises(CrawlError):
        oa.parse_authors("[]")
    assert oa.parse_authors(json.dumps({"meta": {"count": 0}, "results": []})) == {}


# --- the command --------------------------------------------------------------------------------------------


def test_op_eval_openalex_offline_writes_the_report_from_the_cache(tmp_path: Path, monkeypatch) -> None:
    from tests.unit.engine.test_index import snapshot_of

    records = audit_fixture.records()
    data = tmp_path / "data"
    snap = snapshot_of(records, data / "snapshots" / "2026-10-10-abc")
    monkeypatch.setattr(openalex_table, "TABLE", openalex_table.load(""))  # no listing rows: no title check
    t = FakeTransport({})
    picked = oa.sample(records, aaai_sample=3, seed=49)
    _seed_dois(t, picked, {})
    oa.audit(picked, _fetcher(data / "cache", t))  # the cache a live run would leave
    out = tmp_path / "results"
    code = cli.main(["--data-dir", str(data), "eval", "openalex", "--snapshot", snap.name, "--aaai-sample", "3",
                     "--offline", "--out", str(out), "--date", "2026-10-10"])  # fmt: skip
    assert code == 0
    text = (out / "2026-10-10-openalex-audit.md").read_text()
    assert "| FAccT | 2025 | 2 | 2 (100.0%)" in text
    assert "op eval openalex --offline --snapshot 2026-10-10-abc --seed 49 --aaai-sample 3" in text
