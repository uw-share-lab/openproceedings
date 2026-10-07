"""NeurIPS proceedings miner (task-052) against the recorded, scrubbed fixtures (decision-004).

Scrubbing gave each abstract page a different synthetic title from its listing entry, so a case that needs
the two to agree edits the recorded page (a derived case, named as such); the untouched page is the
title-mismatch case. Pages the fixtures don't hold are cached as 404s (a missing page).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.coverage import crawl_dates
from openproceedings.ingest.classify import classify_neurips_listing
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.snapshot import build
from openproceedings.ingest.sources import neurips
from openproceedings.ingest.sources.common import MinerError, titles_match
from openproceedings.ingest.sources.crawl import ingest_neurips, load_crawls
from openproceedings.ingest.sources.html import MAX_DEPTH, HTMLBudgetError, text_of, unescape
from openproceedings.ingest.sources.http import canonical

from tests.unit.ingest.proceedings_helpers import (
    DB,
    MAIN,
    T0,
    T1,
    FakeTransport,
    fetcher,
    fixture_text,
    fixture_url,
    neurips_abs,
    response,
    seed,
    seed_fixture,
)

A13, B13 = "01386bd6d8e091c2ab4c7c7de644d37b", "021bbc7ee20b71134d53e20206bd6feb"
Y13 = "neurips/2013/year-index.json"
ABS13 = "neurips/2013/abstract.json"
BUILT = datetime(2026, 9, 28, tzinfo=UTC)


def cache_of(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def matching(title: str) -> Callable[[str], str]:
    """Derived case: the recorded abstract page, its (scrubbed) title set to the listing's."""
    return lambda text: text.replace("Synthetic title 3", title)


def seed_2013(cache: Path, *, match: bool = True) -> None:
    seed_fixture(cache, "neurips", Y13)
    seed_fixture(cache, "neurips", ABS13, edit=matching("Synthetic title 1") if match else None, at=T1)
    seed(cache, "neurips", neurips_abs(2013, B13), "", status=404, at=T1)


def mine(cache: Path, year: int) -> neurips.YearResult:
    f, _ = fetcher(cache / "neurips", None, neurips.HOSTS)
    return neurips.mine_year(year, f)


def by_id(records: list[PaperRecord]) -> dict[str, PaperRecord]:
    return {r.id: r for r in records}


def claim(r: PaperRecord, field: str) -> Claim:
    [c] = r.claims(field)  # type: ignore[arg-type]
    return c


# --- 2013: token-less URLs, main from host and year ------------------------------------------------------


def test_2013_listing_gives_accepted_main_records_with_their_evidence(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_2013(cache)
    result = mine(cache, 2013)
    records = by_id(result.records)
    a, b = records[f"op:neurips:2013:nips-{A13}"], records[f"op:neurips:2013:nips-{B13}"]
    assert set(records) == {a.id, b.id}
    assert {(r.venue, r.year, r.track, r.status) for r in (a, b)} == {("NeurIPS", 2013, "main", "accepted")}
    assert (a.title, a.abstract) == ("Synthetic title 1", "Synthetic abstract 1")
    assert a.authors == tuple(
        f"Synthetic Author {n}" for n in (8, 9, 6, 4, 10, 5, 7)
    )  # citation_author order
    assert a.urls.proceedings == neurips_abs(2013, A13)
    assert a.urls.pdf == f"https://{MAIN}/paper_files/paper/2013/file/{A13}-Paper.pdf"
    track = claim(a, "track")
    assert track.source == "neurips_proceedings" and track.url == neurips_abs(2013, A13)
    assert track.evidence == "proceedings.neurips.cc 2013: no track token, so the main track (host and year)"
    assert claim(a, "status").evidence == f"listed on {fixture_url(Y13)}"
    assert (
        claim(a, "track").fetched_at == T0 and claim(a, "abstract").fetched_at == T1
    )  # each page's own time
    # b's page is missing: no abstract (counted), authors as listed
    assert (b.abstract, b.authors) == (None, ("Synthetic authors 4",))
    [report] = result.reports
    assert (report.stated, report.listed, report.records, report.count_ok) == (360, 2, 2, False)  # trimmed
    assert (report.abstract_missing, report.page_missing, report.abstract_title_mismatch) == (1, 1, 0)
    assert report.role == "primary" and dict(report.tracks) == {"main": 2}


A87, B87 = "03004620ea802b9118dd44d69f07af56", "0316d8d63a0c252a3ec57921d7d2429b"
Y87 = "neurips/1987/year-index.json"
ABS87 = "neurips/1987/abstract.json"


def test_1987_the_first_nips_is_mined_like_any_token_less_year(tmp_path: Path) -> None:
    """decision-047 (TASK-204): the crawl starts at the first NIPS. The recorded 1987 year and abstract pages
    have the shape of 2013's (`paper-list`, `paper-count`, token-less `-Abstract.html` links), so the same
    host-and-year rule gives `main`, and the abstract page's citation_title matches its listing as recorded."""
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y87)
    seed_fixture(cache, "neurips", ABS87, at=T1)
    seed(cache, "neurips", neurips_abs(1987, B87), "", status=404, at=T1)
    result = mine(cache, 1987)
    records = by_id(result.records)
    a, b = records[f"op:neurips:1987:nips-{A87}"], records[f"op:neurips:1987:nips-{B87}"]
    assert {(r.venue, r.year, r.track, r.status) for r in (a, b)} == {("NeurIPS", 1987, "main", "accepted")}
    assert (a.title, a.abstract) == ("Synthetic title 1", "Synthetic abstract 5")
    assert a.authors == ("Synthetic Author 2", "Synthetic Author 3")
    assert a.urls.pdf == f"https://{MAIN}/paper_files/paper/1987/file/{A87}-Paper.pdf"
    assert a.venue_name == "Conference on Neural Information Processing Systems (NIPS 1987)"
    assert (
        claim(a, "track").evidence
        == "proceedings.neurips.cc 1987: no track token, so the main track (host and year)"
    )
    assert b.abstract is None
    [report] = result.reports
    assert (report.stated, report.listed, report.records, report.role) == (90, 2, 2, "primary")
    assert (report.abstract_missing, report.page_missing) == (1, 1)


def mine_1987_with(tmp_path: Path, abstract: str) -> neurips.YearResult:
    """Derived case: the recorded 1987 abstract page with its (scrubbed) abstract text replaced."""
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y87)
    seed_fixture(cache, "neurips", ABS87, edit=lambda t: t.replace("Synthetic abstract 5", abstract), at=T1)
    seed(cache, "neurips", neurips_abs(1987, B87), "", status=404, at=T1)
    return mine(cache, 1987)


@pytest.mark.parametrize(
    "placeholder", ["Abstract Unavailable", "  abstract   unavailable ", "Abstract Missing"]
)
def test_an_old_pages_placeholder_is_no_abstract(tmp_path: Path, placeholder: str) -> None:
    """NeurIPS 1987-2003 abstract pages show `Abstract Unavailable` where they have none (50 in the 2026-10-06
    cache by 2003; decision-047): the record has no abstract, counted as missing, never a searchable placeholder."""
    result = mine_1987_with(tmp_path, placeholder)
    a = by_id(result.records)[f"op:neurips:1987:nips-{A87}"]
    assert a.abstract is None and a.claims("abstract") == ()
    [report] = result.reports
    assert (report.abstract_missing, report.page_missing, report.abstract_short) == (2, 1, 0)


def test_pdf_extraction_codes_are_repaired_and_counted(tmp_path: Path) -> None:
    """`(cid:173)` is the extractor's soft hyphen at a line break: the word is joined again; any other `(cid:N)` is a
    lost glyph and becomes a space (decision-047). The claim's evidence and the listing say so."""
    text = "Unsu(cid:173) pervised learning of princi(cid:173)ples with (cid:3) marks and enough words here."
    result = mine_1987_with(tmp_path, text)
    a = by_id(result.records)[f"op:neurips:1987:nips-{A87}"]
    assert a.abstract == "Unsupervised learning of principles with marks and enough words here."
    assert claim(a, "abstract").evidence == (
        "p.paper-abstract (citation_title matches the listing) (3 PDF-extraction (cid:N) codes repaired)"
    )
    [report] = result.reports
    assert (report.abstract_pdf_codes, report.abstract_short) == (1, 0)
    assert report.to_manifest()["abstract_pdf_codes"] == 1


def test_a_short_abstract_is_kept_and_counted(tmp_path: Path) -> None:
    """A fragment the extractor left (`Advances`, an author's name) is the page's text: kept, never guessed away, and
    counted (`abstract_short`, fewer than 5 words) so a reviewer can see it."""
    result = mine_1987_with(tmp_path, "Leslie Pack Kaelbling")
    assert by_id(result.records)[f"op:neurips:1987:nips-{A87}"].abstract == "Leslie Pack Kaelbling"
    [report] = result.reports
    assert report.abstract_short == 1 and report.to_manifest()["abstract_short"] == 1
    assert "abstract_pdf_codes" not in report.to_manifest()  # listed only when there are any


def test_an_abstract_is_taken_only_when_citation_title_matches(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_2013(cache, match=False)  # the recorded page: its citation_title is not the listed title
    result = mine(cache, 2013)
    a = by_id(result.records)[f"op:neurips:2013:nips-{A13}"]
    assert a.abstract is None and a.authors == ("Synthetic authors 3",) and a.urls.pdf is None
    [report] = result.reports
    assert (report.abstract_missing, report.abstract_title_mismatch) == (2, 1)


# --- the track vocabulary and its rules ---------------------------------------------------------------------


def test_2022_conference_and_the_datasets_and_benchmarks_alias(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", "neurips/2022/year-index.json")
    shas = {"002262941c9edfd472a79298b2ac5e17": "Conference", "00295cede6e1600d344b5cd6d9fd4640": "Conference",
            "004bed4e186fdd7ebb73aad6e97c2332": "Datasets_and_Benchmarks",
            "0378c7692da36807bdec87ab043cdadc": "Datasets_and_Benchmarks"}  # fmt: skip
    for sha, token in shas.items():
        seed(cache, "neurips", neurips_abs(2022, sha, token), "", status=404)
    result = mine(cache, 2022)
    tracks = {r.native.removeprefix("nips-"): r.track for r in result.records}
    assert tracks == {sha: "main" if t == "Conference" else "datasets_benchmarks" for sha, t in shas.items()}
    db = by_id(result.records)["op:neurips:2022:nips-004bed4e186fdd7ebb73aad6e97c2332"]
    assert "alias" in (claim(db, "track").evidence or "")
    [report] = result.reports
    assert dict(report.tracks) == {
        "main": 2,
        "datasets_benchmarks": 2,
    }  # the alias never counts as a second track
    assert report.role == "confirm"  # OpenReview hosts NeurIPS from 2021


def test_2024_db_track_page_gives_abstract_doi_and_pdf(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", "neurips/2024/year-index.json")
    db = "013cf29a9e68e4411d0593040a8a1eb3"
    seed_fixture(cache, "neurips", "neurips/2024/abstract-db-track.json", edit=matching("Synthetic title 3"))
    for sha, token in (("000f947dcaff8fbffcc3f53a1314f358", "Conference"),
                       ("00295cede6e1600d344b5cd6d9fd4640", "Conference"),
                       ("017761f94a1cd66d01c041aff85492c4", "Datasets_and_Benchmarks_Track")):  # fmt: skip
        seed(cache, "neurips", neurips_abs(2024, sha, token), "", status=404)
    records = by_id(mine(cache, 2024).records)
    r = records[f"op:neurips:2024:nips-{db}"]
    assert (r.track, r.abstract, r.urls.doi) == (
        "datasets_benchmarks",
        "Synthetic abstract 1",
        "10.52202/079017-0016",
    )
    assert (
        r.urls.pdf
        == f"https://{MAIN}/paper_files/paper/2024/file/{db}-Paper-Datasets_and_Benchmarks_Track.pdf"
    )
    assert sorted(x.track for x in records.values()) == [
        "datasets_benchmarks",
        "datasets_benchmarks",
        "main",
        "main",
    ]


def test_2025_mines_the_creative_ai_and_main_conference_volumes_without_an_unfollowed_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = cache_of(tmp_path)
    listings = ("neurips/2025/year-index.json", "neurips/2025/vol38-main-conference.json")
    for rel in listings:
        seed_fixture(cache, "neurips", rel)
        parsed = neurips.parse_year_index(fixture_text(rel), fixture_url(rel))
        for entry in parsed.entries:
            seed(cache, "neurips", entry.url, "", status=404)
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.sources.neurips"):
        result = mine(cache, 2025)
    assert {r.track for r in result.records} == {
        "main",
        "datasets_benchmarks",
        "position",
        "other",
    }
    creative, main = result.reports
    assert creative.see_also == []
    assert main.see_also == []
    assert [dict(report.tracks) for report in result.reports] == [
        {"other": 2},
        {"main": 2, "datasets_benchmarks": 2, "position": 2},
    ]
    assert "listing_see_also_unfollowed" not in [r.getMessage() for r in caplog.records]


def test_2021_reads_the_main_page_and_the_db_host(tmp_path: Path) -> None:
    """The 2021 main page isn't recorded; the 2013 page (same template, `data-track="none"`) moved to 2021
    stands in for it (derived case)."""
    cache = cache_of(tmp_path)
    seed_fixture(
        cache, "neurips", Y13, url=f"https://{MAIN}/paper_files/paper/2021",
        edit=lambda t: t.replace("/paper/2013/", "/paper/2021/"),
    )  # fmt: skip
    seed_fixture(cache, "neurips", "neurips/2021/db-host-year-index.json")
    for sha in (A13, B13):
        seed(cache, "neurips", neurips_abs(2021, sha), "", status=404)
    rounds = {"013d407166ec4fa56eb1e1f8cbe183b9": "round1", "0336dcbab05b9d5ad24f4333c7658a0e": "round2",
              "03c6b06952c750899bb03d998e631860": "round2", "0777d5c17d4066b82ab86dff8a46af6f": "round1"}  # fmt: skip
    for sha, token in rounds.items():
        seed(cache, "neurips", neurips_abs(2021, sha, token, host=DB), "", status=404)
    result = mine(cache, 2021)
    tracks = {r.native: r.track for r in result.records}
    assert tracks == {
        f"nips-{A13}": "main", f"nips-{B13}": "main",
        **{f"nips-{sha}-{token}": "datasets_benchmarks" for sha, token in rounds.items()},
    }  # fmt: skip
    main, db = result.reports
    assert (main.listed, db.listed, db.stated, db.count_ok) == (2, 4, None, True)
    r = by_id(result.records)["op:neurips:2021:nips-0336dcbab05b9d5ad24f4333c7658a0e-round2"]
    assert r.urls.proceedings == neurips_abs(2021, "0336dcbab05b9d5ad24f4333c7658a0e", "round2", host=DB)
    assert r.authors == ("Synthetic authors 6",)  # the D&B host lists authors in <i>


def test_a_2021_db_link_without_a_round_is_skipped_not_given_a_bare_hash(tmp_path: Path) -> None:
    """Derived case: one round-1 link on the recorded D&B page loses its round token. Its hash alone could be
    any of three papers, so it gets no id: counted as `no_round`, never built as `nips-<hash>` (TASK-118)."""
    cache = cache_of(tmp_path)
    bare = "013d407166ec4fa56eb1e1f8cbe183b9"
    seed_fixture(
        cache, "neurips", "neurips/2021/db-host-year-index.json", url=f"https://{DB}/paper/2021",
        edit=lambda t: t.replace(f"{bare}-Abstract-round1", f"{bare}-Abstract"),
    )  # fmt: skip
    seed_fixture(
        cache, "neurips", Y13, url=f"https://{MAIN}/paper_files/paper/2021",
        edit=lambda t: t.replace("/paper/2013/", "/paper/2021/"),
    )  # fmt: skip
    rest = {"0336dcbab05b9d5ad24f4333c7658a0e": "round2", "03c6b06952c750899bb03d998e631860": "round2",
            "0777d5c17d4066b82ab86dff8a46af6f": "round1"}  # fmt: skip
    for url in [neurips_abs(2021, A13), neurips_abs(2021, B13)] + [
        neurips_abs(2021, sha, token, host=DB) for sha, token in rest.items()
    ]:
        seed(cache, "neurips", url, "", status=404)
    result = mine(cache, 2021)
    _main, db = result.reports
    assert (db.listed, db.skipped["no_round"]) == (4, 1)
    assert not any(bare in r.native for r in result.records)
    assert sorted(r.native for r in result.records if r.track == "datasets_benchmarks") == sorted(
        f"nips-{sha}-{token}" for sha, token in rest.items()
    )


def test_2021_db_papers_sharing_a_hash_are_all_kept(tmp_path: Path) -> None:
    """The path hash is md5 of the paper's number, and the D&B host numbers round 1, round 2 and the main track
    separately: the live 2021 page (2026-09-29) has 27 hashes in both rounds and 27 shared with the main track,
    all different papers. Derived case: the recorded D&B page with round-1 entries re-pointed at a round-2
    paper's hash and at a main-track paper's hash."""
    cache = cache_of(tmp_path)
    r2 = "0336dcbab05b9d5ad24f4333c7658a0e"
    seed_fixture(
        cache, "neurips", Y13, url=f"https://{MAIN}/paper_files/paper/2021",
        edit=lambda t: t.replace("/paper/2013/", "/paper/2021/"),
    )  # fmt: skip
    seed_fixture(
        cache, "neurips", "neurips/2021/db-host-year-index.json",
        edit=lambda t: t.replace("013d407166ec4fa56eb1e1f8cbe183b9-Abstract-round1", f"{r2}-Abstract-round1")
        .replace("0777d5c17d4066b82ab86dff8a46af6f-Abstract-round1", f"{A13}-Abstract-round1"),
    )  # fmt: skip
    pages = [neurips_abs(2021, A13), neurips_abs(2021, B13)] + [
        neurips_abs(2021, sha, token, host=DB)
        for sha, token in [(A13, "round1"), (r2, "round1"), (r2, "round2"),
                           ("03c6b06952c750899bb03d998e631860", "round2")]
    ]  # fmt: skip
    for url in pages:
        seed(cache, "neurips", url, "", status=404)
    result = mine(cache, 2021)
    ids = sorted(r.native for r in result.records)
    assert ids == sorted([
        f"nips-{A13}", f"nips-{B13}", f"nips-{A13}-round1", f"nips-{r2}-round1", f"nips-{r2}-round2",
        "nips-03c6b06952c750899bb03d998e631860-round2",
    ])  # fmt: skip
    _main, db = result.reports
    assert (db.listed, db.skipped.get("duplicate", 0)) == (4, 0)
    assert {r.track for r in result.records if r.native.endswith(("-round1", "-round2"))} == {
        "datasets_benchmarks"
    }


@pytest.mark.parametrize(
    ("host", "year", "token", "track"),
    [
        (MAIN, 2013, None, "main"),
        (MAIN, 2021, None, "main"),
        (MAIN, 2022, None, "unknown"),  # a token-less link after 2021: no rule
        ("papers.nips.cc", 2015, None, "main"),
        (MAIN, 2022, "Conference", "main"),
        (MAIN, 2023, "Datasets_and_Benchmarks", "datasets_benchmarks"),
        (MAIN, 2024, "Datasets_and_Benchmarks", "unknown"),  # the alias is the <=2023 spelling only
        (MAIN, 2024, "Datasets_and_Benchmarks_Track", "datasets_benchmarks"),
        (MAIN, 2025, "Position_Paper_Track", "position"),
        (MAIN, 2025, "Creative_AI_Track", "other"),
        (MAIN, 2024, "Mystery_Track", "unknown"),
        (MAIN, 2021, "round1", "unknown"),  # round tokens belong to the D&B host
        (DB, 2021, "round1", "datasets_benchmarks"),
        (DB, 2021, "round2", "datasets_benchmarks"),
        (DB, 2022, "round1", "unknown"),
        (DB, 2021, None, "unknown"),
        ("proceedings.iclr.cc", 2021, None, "unknown"),
    ],
)
def test_listing_track_rules(host: str, year: int, token: str | None, track: str) -> None:
    cls, rule = classify_neurips_listing(host, year, token)
    assert (cls.track, cls.status, cls.venue, cls.year) == (track, "accepted", "NeurIPS", year)
    assert rule and (track != "unknown") == ("no rule" not in rule and "not a NeurIPS" not in rule)


def test_an_unknown_token_is_counted_and_flagged_never_main(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(
        cache, "neurips", "neurips/2024/year-index.json",
        edit=lambda t: t.replace("-Abstract-Conference.html", "-Abstract-Mystery_Track.html"),
    )  # fmt: skip
    for sha, token in (("000f947dcaff8fbffcc3f53a1314f358", "Mystery_Track"),
                       ("00295cede6e1600d344b5cd6d9fd4640", "Mystery_Track"),
                       ("013cf29a9e68e4411d0593040a8a1eb3", "Datasets_and_Benchmarks_Track"),
                       ("017761f94a1cd66d01c041aff85492c4", "Datasets_and_Benchmarks_Track")):  # fmt: skip
        seed(cache, "neurips", neurips_abs(2024, sha, token), "", status=404)
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.sources.neurips"):
        result = mine(cache, 2024)
    [report] = result.reports
    assert (report.unknown_track, report.tracks["unknown"]) == (2, 2)
    assert [r.getMessage() for r in caplog.records].count("listing_attention") == 1


def test_links_that_dont_parse_or_name_another_year_are_skipped_and_counted(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(
        cache, "neurips", Y13,
        edit=lambda t: t.replace(f"2013/hash/{B13}", f"2012/hash/{B13}").replace(A13, "abc"),
    )  # fmt: skip
    result = mine(cache, 2013)
    assert result.records == []
    assert dict(result.reports[0].skipped) == {"unparsed_link": 1, "wrong_year": 1}
    legacy = f'href="https://papers.nips.cc/paper_files/paper/2013/hash/{A13}-Abstract.html"'
    seed_fixture(
        cache,
        "neurips",
        Y13,
        edit=lambda t: t.replace(f'href="{neurips_abs(2013, A13)[len("https://" + MAIN) :]}"', legacy),
    )
    seed(cache, "neurips", neurips_abs(2013, B13), "", status=404)
    result = mine(cache, 2013)  # a link off the crawl's hosts is never fetched: counted, not an abort
    assert [r.native for r in result.records] == [f"nips-{B13}"]
    assert dict(result.reports[0].skipped) == {"off_host": 1}


# --- extraction golden cases (derived from the recorded page structure) ----------------------------------


@pytest.mark.parametrize(
    ("html", "text"),
    [
        ("<p>First.</p><p>Second.</p>", "First. Second."),
        ("Line<br>break", "Line break"),
        ("<i>k</i>-means and x<sub>i</sub>", "k-means and xi"),
        ("R&amp;D and R&D", "R&D and R&D"),
        ("a &amp;amp; b, &amp;quot;q&amp;quot;", 'a & b, "q"'),  # double-escaped
        ("&amp;copy is not an entity without its semicolon", "&copy is not an entity without its semicolon"),
        ("  lots \n of\t space  ", "lots of space"),
        ("$\\mathcal{O}(n^2)$ and \\(x\\)", "$\\mathcal{O}(n^2)$ and \\(x\\)"),  # LaTeX verbatim
        ("<script>var x = '<p>';</script>kept", "kept"),
    ],
)
def test_text_extraction(html: str, text: str) -> None:
    assert text_of(html) == text


def test_unescape_decodes_only_complete_leftover_entities() -> None:
    assert unescape("&amp;lt;b&amp;gt;") == "<b>"
    assert unescape("AT&amp;T") == "AT&T"


@pytest.mark.parametrize(
    ("listed", "page", "same"),
    [
        ("Deep Nets", "Deep nets", True),
        ("Deep Nets", "Deep Nets!", True),
        ("$k$-Means Clustering", "-Means Clustering", True),  # a leading formula one side dropped
        ("Means Clustering", "$k$-Means Clustering", True),
        ("Deep Nets", "Shallow Nets", False),
        ("Deep Nets", None, False),
        ("$x$", "", False),
    ],
)
def test_titles_match(listed: str, page: str | None, same: bool) -> None:
    assert titles_match(listed, page) is same


@pytest.mark.parametrize(
    ("abstract", "kept"),
    [
        ("<p>Real text with x<sub>1</sub>, …, x<sub>n</sub> inside.</p>", "Real text with x1, …, xn inside."),
        ("… a snippet", None),
        ("a snippet …", None),
        ("   ", None),
        ("$\\alpha$ &amp;amp; <b>bold</b>", "$\\alpha$ & bold"),
    ],
)
def test_abstract_golden_cases(tmp_path: Path, abstract: str, kept: str | None) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y13)
    seed_fixture(
        cache, "neurips", ABS13,
        edit=lambda t: matching("Synthetic title 1")(t).replace("Synthetic abstract 1", abstract),
    )  # fmt: skip
    seed(cache, "neurips", neurips_abs(2013, B13), "", status=404)
    a = by_id(mine(cache, 2013).records)[f"op:neurips:2013:nips-{A13}"]
    assert a.abstract == kept


def test_the_recorded_2025_page_decodes_its_double_escaped_author() -> None:
    parsed = neurips.parse_year_index(
        fixture_text("neurips/2025/year-index.json"), fixture_url("neurips/2025/year-index.json")
    )
    assert parsed.entries[0].authors == ('Synthetic authors 3 "alias"',)


def test_listing_parser_is_attribute_order_independent_and_ignores_authors_before_the_paper_link() -> None:
    page = """<span data-x='1' class='paper-count'>1 paper</span>
    <ul data-x='1' class='extra paper-list'>
      <li><span class='paper-authors'>Decoy Person</span>
          <a data-x='1' href='hash-Abstract-Conference.html'>Actual Title</a>
          <span data-x='1' class='extra paper-authors'>Actual One, Actual Two</span></li>
    </ul>"""
    parsed = neurips.parse_year_index(page, "https://proceedings.neurips.cc/paper_files/paper/2025/")
    assert parsed.stated == 1 and parsed.unlinked == 0
    assert parsed.entries == [
        neurips.Entry(
            "https://proceedings.neurips.cc/paper_files/paper/2025/hash-Abstract-Conference.html",
            "Actual Title",
            ("Actual One", "Actual Two"),
        )
    ]


# --- crawl, resume, dry run, window, snapshot ----------------------------------------------------------------


def live_2013(match: bool = True) -> dict[str, object]:
    page = fixture_text(ABS13)
    return {
        fixture_url(Y13): response(fixture_text(Y13)),
        neurips_abs(2013, A13): response(matching("Synthetic title 1")(page) if match else page),
        neurips_abs(2013, B13): response("", 404),
    }


def test_crawl_writes_a_marker_and_resumes_from_the_cache(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    broken = live_2013()
    broken[neurips_abs(2013, B13)] = response("", 403)  # the crawl stops on a refusal
    t = FakeTransport(broken)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="HTTP 403"):
        ingest_neurips([2013], cache, transport=t, min_interval=0)
    assert not (cache / "neurips" / "crawls").exists()  # no marker: the snapshot doesn't see a half year
    t = FakeTransport(live_2013())  # type: ignore[arg-type]
    out = ingest_neurips([2013], cache, transport=t, min_interval=0)
    assert t.calls == [neurips_abs(2013, B13)]  # only the page that failed; the rest came from the cache
    assert (out["requests"], out["cached"]) == (1, 2)
    assert (cache / "neurips" / "crawls" / "2013.json").is_file()
    records, sources = load_crawls(cache)
    assert {r.id for r in records} == {f"op:neurips:2013:nips-{A13}", f"op:neurips:2013:nips-{B13}"}
    entry = sources["neurips_proceedings"]
    [listing] = entry["listings"]
    assert listing["year"] == 2013 and entry["crawl_window"] == listing["crawl_window"]
    assert load_crawls(cache) == (records, sources)  # a function of the cache: the same every time


def test_dry_run_reads_only_the_index(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    t = FakeTransport(live_2013())  # type: ignore[arg-type]
    out = ingest_neurips([2013], cache, transport=t, dry_run=True, min_interval=0)
    assert t.calls == [fixture_url(Y13)] and out["dry_run"] is True
    [listing] = out["listings"]
    assert (listing["to_fetch"], listing["records"], listing["tracks"]) == (2, 0, {"main": 2})
    assert not (cache / "neurips" / "crawls").exists()


def test_an_unpublished_year_and_one_before_the_window_are_refused(tmp_path: Path) -> None:
    t = FakeTransport({f"https://{MAIN}/paper_files/paper/2026": response("", 404)})
    with pytest.raises(MinerError) as e:
        ingest_neurips([2026], cache_of(tmp_path), transport=t, min_interval=0)
    assert e.value.reason == "no_listing"
    with pytest.raises(MinerError) as e:
        ingest_neurips([1986], cache_of(tmp_path), transport=t, min_interval=0)
    assert e.value.reason == "before_window"


def test_snapshot_build_includes_finished_crawls_offline(tmp_path: Path) -> None:
    cache = cache_of(tmp_path)
    seed_2013(cache)
    ingest_neurips([2013], cache, offline=True)
    first = build(cache, tmp_path / "snapshots", BUILT)
    manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {"NeurIPS": {"2013": {"main": {"accepted": 2}}}}
    assert manifest["abstract_missing"] == {"NeurIPS": {"2013": 1}}
    assert set(manifest["sources"]) == {"neurips_proceedings"}  # no RIS cached, so no `ris` entry
    assert crawl_dates(manifest)["neurips_proceedings"] == {"from": T0.isoformat(), "to": T1.isoformat()}
    [listing] = manifest["sources"]["neurips_proceedings"]["listings"]
    assert (listing["stated"], listing["listed"], listing["count_ok"]) == (360, 2, False)
    again = build(cache, tmp_path / "snapshots", BUILT)
    assert (again.snapshot_hash, again.created) == (first.snapshot_hash, False)  # a function of the cache


def test_proceedings_cross_check_openreview_through_dedup(tmp_path: Path) -> None:
    """AC #2: a NeurIPS 2022 paper on both sides merges on its title; the proceedings decide acceptance and
    OpenReview the track, and each disagreement is a conflicts.csv row (decision-005)."""
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", "neurips/2022/year-index.json")
    for sha, token in (("002262941c9edfd472a79298b2ac5e17", "Conference"), ("00295cede6e1600d344b5cd6d9fd4640", "Conference"),
                       ("004bed4e186fdd7ebb73aad6e97c2332", "Datasets_and_Benchmarks"),
                       ("0378c7692da36807bdec87ab043cdadc", "Datasets_and_Benchmarks")):  # fmt: skip
        seed(cache, "neurips", neurips_abs(2022, sha, token), "", status=404)
    proceedings = mine(cache, 2022).records

    def openreview(forum: str, title: str, track: str, status: str) -> PaperRecord:
        claims = [
            Claim(field=f, value=v, source="openreview_v1", url=f"https://openreview.net/forum?id={forum}",
                  fetched_at=T0, evidence="venue=NeurIPS 2022 Submitted")
            for f, v in (("title", title), ("venue", "NeurIPS"), ("year", 2022), ("track", track), ("status", status))
        ]  # fmt: skip
        return PaperRecord.build(id=f"op:neurips:2022:{forum}", title=title, abstract=None, authors=(),
                                 venue="NeurIPS", year=2022, track=track, status=status, provenance=tuple(claims))  # fmt: skip

    result = dedup([*proceedings, openreview("Forum00001", "Synthetic title 1", "main", "rejected"),
                    openreview("Forum00003", "Synthetic Title 3", "datasets_benchmarks", "accepted")])  # fmt: skip
    records = by_id(list(result.records))
    assert records["op:neurips:2022:Forum00001"].status == "accepted"  # listed → accepted, over OpenReview
    assert {(c.id, c.field, c.resolution) for c in result.conflicts} == {
        ("op:neurips:2022:Forum00001", "status", "precedence:neurips_proceedings"),
    }
    assert records["op:neurips:2022:Forum00003"].track == "datasets_benchmarks"
    assert len(result.records) == 4 and len(result.merges) == 2


# --- parser budgets and record-level logs (TASK-116) --------------------------------------------------------

TOO_DEEP = "<html>" + "<div>" * (MAX_DEPTH + 1) + "</html>"


def test_a_paper_page_past_the_html_budget_is_a_debug_line_counted_in_one_listing_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y13)
    for sha in (A13, B13):
        seed(cache, "neurips", neurips_abs(2013, sha), TOO_DEEP, at=T1)
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = mine(cache, 2013)
    [report] = result.reports
    assert report.skipped["invalid"] == 2 and result.records == []
    invalid = [r for r in caplog.records if r.getMessage() == "neurips_record_invalid"]
    assert {r.levelno for r in invalid} == {logging.DEBUG} and {r.__dict__["error"] for r in invalid} == {
        "HTMLBudgetError"
    }
    assert {r.__dict__["url"] for r in invalid} == {canonical(neurips_abs(2013, s)) for s in (A13, B13)}
    # the listing's own lines only (the recorded 2013 page is trimmed, so its count mismatches); no per-record one
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r.getMessage() for r in warnings] == ["listing_count_mismatch", "listing_attention"]
    assert warnings[1].__dict__["skipped"] == {"invalid": 2}


def test_a_listing_page_past_the_html_budget_names_its_url_and_how_to_recover(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    listing = canonical(neurips.listing_urls(2013)[0])
    seed(data / "cache", "neurips", listing, TOO_DEEP)
    f, _ = fetcher(data / "cache" / "neurips", None, neurips.HOSTS)
    with pytest.raises(HTMLBudgetError) as refused:
        neurips.mine_year(2013, f)
    entry = f.cache.path(listing).relative_to(f.cache.root)  # pages/<sha256[:2]>/<sha256>.json
    message = str(refused.value)
    assert message.startswith(f"{listing}: HTML nesting exceeds {MAX_DEPTH} elements")
    assert "--refresh" in message and f"({entry} under the source's cache directory)" in message
    assert (refused.value.url, refused.value.reason) == (listing, "html_budget")

    code = cli.main(["--data-dir", str(data), "ingest", "neurips", "--year", "2013", "--offline"])
    err = capsys.readouterr().err
    assert code == 1 and f"op ingest neurips: {listing}: HTML nesting exceeds" in err
    [line] = [e for e in map(json.loads, (x for x in err.splitlines() if x.startswith("{")))
              if e.get("event") == "cli_refused"]  # fmt: skip
    assert (line["level"], line["reason"], line["error"]) == ("WARNING", "html_budget", "HTMLBudgetError")


def test_the_reports_first_fetch_is_the_index_page(tmp_path: Path) -> None:
    """`ListingReport.fetched[0]` is the listing's own read (reconcile dates its absence claims by it)."""
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y13, at=T1)  # the index page read after its paper pages
    seed_fixture(cache, "neurips", ABS13, edit=matching("Synthetic title 1"), at=T0)
    seed(cache, "neurips", neurips_abs(2013, B13), "", status=404, at=T0)
    [report] = mine(cache, 2013).reports
    assert report.fetched[0] == T1 and T0 in report.fetched[1:]


def test_a_listed_title_with_a_control_character_keeps_its_paper() -> None:
    """decision-036 (TASK-180 review): the listing is no longer dropped as `invalid`; the control character
    becomes a space and the title claim's evidence says so."""
    from openproceedings.ingest.sources.http import Page

    native = "nips-" + "a" * 32
    url = f"https://proceedings.neurips.cc/paper_files/paper/2024/hash/{'a' * 32}-Abstract-Conference.html"
    listing = "https://proceedings.neurips.cc/paper_files/paper/2024"
    t0 = datetime(2026, 9, 29, tzinfo=UTC)
    index, page = Page(listing, 200, "", t0), Page(url, 404, "", t0)
    entry = neurips.Entry(url, "Induc\x02tive Trust", ("A One",))
    record, _, _ = neurips._record(
        2024, native, entry, "main", "track token Conference", listing, index, page
    )
    assert record.title == "Induc tive Trust"
    assert (
        claim(record, "title").evidence == f"year index {listing} (1 control character replaced by a space)"
    )
    clean, _, _ = neurips._record(2024, native, neurips.Entry(url, "Inductive Trust", ("A One",)), "main",
                               "track token Conference", listing, index, page)  # fmt: skip
    assert claim(clean, "title").evidence == f"year index {listing}"


def test_a_page_abstract_with_a_control_character_is_imported_with_a_space() -> None:
    """decision-044 (TASK-188): the title rule, for abstracts; the claim's evidence says so."""
    from openproceedings.ingest.sources.http import Page

    native = "nips-" + "a" * 32
    url = f"https://proceedings.neurips.cc/paper_files/paper/2024/hash/{'a' * 32}-Abstract-Conference.html"
    listing = "https://proceedings.neurips.cc/paper_files/paper/2024"
    t0 = datetime(2026, 9, 29, tzinfo=UTC)
    html = (
        '<meta name="citation_title" content="Inductive Trust">'
        '<p class="paper-abstract">Quanti\x02fying trust\x00</p>'
    )
    index, page = Page(listing, 200, "", t0), Page(url, 200, html, t0)
    entry = neurips.Entry(url, "Inductive Trust", ("A One",))
    record, missing, cleaned = neurips._record(
        2024, native, entry, "main", "track token Conference", listing, index, page
    )
    assert (record.abstract, missing, cleaned.spaced, cleaned.pdf_codes) == ("Quanti fying trust", None, 2, 0)
    assert claim(record, "abstract").evidence == (
        "p.paper-abstract (citation_title matches the listing) (2 control characters replaced by a space)"
    )


def test_a_listing_counts_the_abstracts_that_lost_a_control_character(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-199 (decision-044): from the miner's own count, in the report, its manifest when above 0 and the
    listing's done line; never a WARNING (the abstract is kept). A listing with none keeps its manifest shape."""
    cache = cache_of(tmp_path)
    seed_fixture(cache, "neurips", Y13)
    edit = matching("Synthetic title 1")
    seed_fixture(
        cache,
        "neurips",
        ABS13,
        edit=lambda t: edit(t).replace("Synthetic abstract 1", "Synthetic\x02abstract\x001"),
        at=T1,
    )
    seed(cache, "neurips", neurips_abs(2013, B13), "", status=404, at=T1)
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):
        result = mine(cache, 2013)
    assert by_id(result.records)[f"op:neurips:2013:nips-{A13}"].abstract == "Synthetic abstract 1"
    [report] = result.reports
    assert report.abstract_control_characters == 1 == report.to_manifest()["abstract_control_characters"]
    [done] = [r for r in caplog.records if r.getMessage() == "neurips_listing_mined"]
    assert done.__dict__["abstract_control_characters"] == 1
    # the fixture's own count mismatch warns; the counter is never part of a WARNING
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not [r for r in warnings if "abstract_control_characters" in r.__dict__]
    plain = cache_of(tmp_path / "plain")
    seed_2013(plain)
    [clean] = mine(plain, 2013).reports
    assert clean.abstract_control_characters == 0 and "abstract_control_characters" not in clean.to_manifest()
