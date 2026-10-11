"""The OpenAlex fill (decision-049): replayed from the pinned extract after dedup, only into a null abstract of
an AAAI, AIES or FAccT record; DOI exact or one-to-one title key; refusals counted, never forced."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest import openalex_table
from openproceedings.ingest.dedup import attribution, resolve
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.openalex import api

T = datetime(2026, 10, 10, tzinfo=UTC)
D1, D2 = "10.1145/3593013.3594011", "10.1145/3593013.3594012"
TABLE = openalex_table.load("""
[[listing]]
venue = "AAAI"
year = 1990
source_ids = ["S77"]
works = 3
verified = 2026-10-10
source = "test"
""")


def rec(rid: str, venue: str, year: int, *, title: str = "A Paper", doi: str | None = None,
        abstract: tuple[str, str] | None = None, source: str = "crossref") -> PaperRecord:  # fmt: skip
    fields = [("title", title), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted")]
    if doi:
        fields += [("urls.doi", doi), ("urls.proceedings", f"https://doi.org/{doi}")]
    claims = [Claim(field=f, value=v, source=source, fetched_at=T, evidence="t") for f, v in fields]
    if abstract:
        claims.append(
            Claim(field="abstract", value=abstract[0], source=abstract[1], fetched_at=T, evidence="t")
        )
    return resolve(rid, claims)[0]


def doi_lookup(*works, requested=(D1, D2)) -> openalex.Lookup:
    parsed = openalex.parse_works(api.page(*works)).works
    return openalex.Lookup(
        "doi", openalex.doi_url(list(requested)), T, tuple(sorted(requested)), None, None, parsed
    )


def ext(*lookups) -> openalex.Extract:
    return openalex.Extract("0" * 64, tuple(lookups))


def test_a_doi_match_fills_the_null_abstract_credited_to_the_papers_page() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    (out,), report = openalex.fill(
        [r], ext(doi_lookup(api.work("W1", D1, text="An OpenAlex abstract."))), TABLE
    )
    assert out.abstract == "An OpenAlex abstract." and out.abstract_kind == "openalex"
    (claim,) = out.claims("abstract")
    assert claim.url == "https://api.openalex.org/works/W1" and "https://openalex.org/W1" in claim.evidence
    att = attribution(
        out.abstract, out.provenance, forum=None, proceedings=out.urls.proceedings, native=out.native
    )
    assert att is not None and att.url == f"https://doi.org/{D1}"
    assert (report.candidates, report.attached_doi) == (1, 1)


@pytest.mark.parametrize(
    ("rid", "venue", "year", "source"),
    [
        ("op:icml:2005:dblp-Smith05", "ICML", 2005, "dblp"),
        ("op:iaseai:2026:ojs-40000", "IASEAI", 2026, "ojs"),
    ],
)
def test_other_venues_are_never_touched(rid, venue, year, source) -> None:
    r = rec(rid, venue, year, doi=D1, source=source)
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1))), TABLE)
    assert out is r and report.candidates == 0


def test_an_official_abstract_is_never_overwritten() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1, abstract=("Official.", "facct_site"))
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1, text="Other."))), TABLE)
    assert out is r and out.abstract_kind == "official" and report.official_won == 1


def test_an_official_abstract_in_a_later_crawl_wins_over_the_extract() -> None:
    """The pinned extract still holds OpenAlex's text; the new build's record has OJS's: the official one stays."""
    lookup = doi_lookup(api.work("W1", D1, text="An OpenAlex abstract."))
    before = rec("op:aaai:2020:ojs-1", "AAAI", 2020, doi=D1, source="ojs")
    (filled,), _ = openalex.fill([before], ext(lookup), TABLE)
    later = rec(
        "op:aaai:2020:ojs-1", "AAAI", 2020, doi=D1, source="ojs", abstract=("An official abstract.", "ojs")
    )
    (kept,), report = openalex.fill([later], ext(lookup), TABLE)
    assert (filled.abstract_kind, kept.abstract_kind, kept.abstract) == (
        "openalex",
        "official",
        "An official abstract.",
    )
    assert report.official_won == 1 and report.attached_doi == 0


def test_a_truncated_openalex_doi_attaches_nothing() -> None:
    r = rec("op:facct:2025:doi-3715275.3732001", "FAccT", 2025, doi="10.1145/3715275.3732001")
    lookup = doi_lookup(
        requested=("10.1145/3715275.3732001",)
    )  # OpenAlex holds `…373200`: the filter finds none
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_unmatched"] == 1


def test_duplicate_works_with_differing_texts_attach_nothing() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W1", D1, text="One text."), api.work("W2", D1, text="Another text."))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_duplicate"] == 1


def test_duplicate_works_with_one_text_attach_once_citing_both() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W2", D1, text="Same text."), api.work("W1", D1, text="Same  text."))
    (out,), _ = openalex.fill([r], ext(lookup), TABLE)
    (claim,) = out.claims("abstract")
    assert out.abstract == "Same text." and claim.url.endswith("/W1") and "W2" in claim.evidence


def test_a_work_for_a_doi_not_asked_is_refused() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W9", "10.1145/9999999.1"), requested=(D1,))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert (
        out.abstract is None and report.refused["doi_mismatch"] == 1 and report.refused["doi_unmatched"] == 1
    )


def _listing(*works) -> openalex.Lookup:
    row = TABLE.listings[("AAAI", 1990)]
    return openalex.Lookup(
        "listing",
        openalex.listing_url(row),
        T,
        (),
        "AAAI",
        1990,
        openalex.parse_works(api.page(*works)).works,
    )


def test_a_doi_less_record_matches_one_work_by_exact_title_key() -> None:
    r = rec("op:aaai:1990:dblp-Smith90", "AAAI", 1990, title="Planning Under Uncertainty", source="dblp")
    lookup = _listing(
        api.work("W5", None, title="Planning under uncertainty.", year=1990, text="Old abstract."),
        api.work("W6", None, title="Planning under uncertainty, revisited", year=1990),
    )
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract == "Old abstract." and report.attached_title == 1
    assert "exact title key" in out.claims("abstract")[0].evidence


def test_two_works_or_two_records_sharing_a_title_key_attach_nothing() -> None:
    a = rec("op:aaai:1990:dblp-A90", "AAAI", 1990, title="Learning", source="dblp")
    b = rec("op:aaai:1990:dblp-B90", "AAAI", 1990, title="Learning.", source="dblp")
    one = _listing(api.work("W5", None, title="Learning", year=1990))
    two = _listing(
        api.work("W5", None, title="Learning", year=1990), api.work("W6", None, title="learning", year=1990)
    )
    (x, y), report = openalex.fill([a, b], ext(one), TABLE)
    assert x.abstract is None and y.abstract is None and report.refused["title_ambiguous"] == 2
    (z,), report = openalex.fill([a], ext(two), TABLE)
    assert z.abstract is None and report.refused["title_ambiguous"] == 1


def test_a_title_match_whose_doi_is_another_records_is_refused() -> None:
    r = rec("op:aaai:1990:dblp-A90", "AAAI", 1990, title="Learning", source="dblp")
    other = rec("op:aaai:1991:dblp-B91", "AAAI", 1991, title="Other", source="dblp", doi="10.1609/x.1")
    lookup = _listing(api.work("W5", "10.1609/x.1", title="Learning", year=1990))
    (out, _o), report = openalex.fill([r, other], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_mismatch"] == 1


def test_a_record_nothing_looked_up_is_counted_not_queried() -> None:
    r = rec("op:aies:2019:doi-3306618.3314200", "AIES", 2019, doi="10.1145/3306618.3314200")
    (_out,), report = openalex.fill([r], ext(), TABLE)
    assert report.not_queried == 1


def test_a_listing_the_table_has_changed_since_is_not_replayed() -> None:
    r = rec("op:aaai:1990:dblp-Smith90", "AAAI", 1990, title="Learning", source="dblp")
    lookup = _listing(api.work("W5", None, title="Learning", year=1990))
    moved = openalex_table.load(TABLE_TEXT_MOVED)  # the row now names another source: the extract's is stale
    (out,), report = openalex.fill([r], ext(lookup), moved)
    assert out.abstract is None and report.refused["listing_stale"] == 1 and report.not_queried == 0
    assert report.attached_title == 0


TABLE_TEXT_MOVED = """
[[listing]]
venue = "AAAI"
year = 1990
source_ids = ["S78"]
works = 3
verified = 2026-10-10
source = "test"
"""


@pytest.mark.parametrize(("raw", "text", "reason"), [
    ({"a": [0], "b": [2]}, None, "inverted_gap"), (None, None, "no_abstract"),
    ({"…": [0]}, None, "abstract_unusable")])  # fmt: skip
def test_a_doi_match_with_no_usable_abstract_is_refused_with_why(raw, text, reason) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1, raw=raw, text=text))), TABLE)
    assert out.abstract is None and report.refused == {reason: 1} and report.attached_doi == 0


def test_the_fill_report_goes_in_the_manifest_sorted() -> None:
    report = openalex.FillReport(source="openalex", extract="e")
    report.refused.update({"title_unmatched": 1, "doi_unmatched": 2})
    assert list(report.to_manifest()["refused"]) == ["doi_unmatched", "title_unmatched"]
    assert openalex.FillReport.manifest_key == "fills"


def test_a_doi_less_record_with_an_official_abstract_still_makes_a_title_key_ambiguous() -> None:
    """One work, two records sharing its key: never credited to the one without an abstract (I-1)."""
    a = rec(
        "op:aaai:1990:dblp-A90", "AAAI", 1990, title="Panel", source="dblp", abstract=("Official.", "dblp")
    )
    b = rec("op:aaai:1990:dblp-B90", "AAAI", 1990, title="Panel.", source="dblp")
    lookup = _listing(api.work("W5", None, title="Panel", year=1990, text="OpenAlex text."))
    (x, y), report = openalex.fill([a, b], ext(lookup), TABLE)
    assert x.abstract == "Official." and y.abstract is None
    assert report.refused["title_ambiguous"] == 1 and report.attached_title == 0


def test_a_title_match_in_another_year_attaches_nothing() -> None:
    r = rec("op:aaai:1990:dblp-Smith90", "AAAI", 1990, title="Planning", source="dblp")
    lookup = _listing(api.work("W5", None, title="Planning", year=1991, text="Wrong year."))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["title_unmatched"] == 1


def test_an_openalex_attach_runs_the_record_guard() -> None:
    """`_attach` builds a validated record: an OpenAlex claim on a venue outside AAAI/AIES/FAccT is refused."""
    from pydantic import ValidationError

    r = rec("op:icml:2005:dblp-Smith05", "ICML", 2005, source="dblp")
    lookup = doi_lookup(api.work("W1", D1, text="Text."))
    cleaned, _ = openalex.abstract_of(lookup.works[0])
    assert cleaned is not None
    with pytest.raises(ValidationError):
        openalex._attach(r, lookup.works, cleaned, lookup, "by DOI")


CHOICE = (
    TABLE_TEXT_MOVED.replace("S78", "S77")
    + f"""
[[duplicate_choice]]
doi = "{D1}"
work = "W2"
reason = "the same abstract; W1's copy has PDF-extraction damage"
verified = 2026-10-10
source = "TASK-231"
"""
)


def test_a_pinned_duplicate_choice_attaches_the_chosen_work_and_is_counted() -> None:
    """TASK-231 (owner ruling 2026-10-10): a cited `[[duplicate_choice]]` row picks one of a DOI's works whose texts
    differ; the record is filled by DOI from that work alone, and counted `duplicate_chosen` too."""
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W1", D1, text="Damaged te- xt."), api.work("W2", D1, text="Clean text."))
    (out,), report = openalex.fill([r], ext(lookup), openalex_table.load(CHOICE))
    (claim,) = out.claims("abstract")
    assert out.abstract == "Clean text." and claim.url.endswith("/W2") and "W1" not in claim.evidence
    assert "duplicate_choice" in claim.evidence
    assert (report.attached_doi, report.duplicate_chosen, sum(report.refused.values())) == (1, 1, 0)
    assert report.to_manifest()["duplicate_chosen"] == 1


def test_without_its_choice_row_the_same_duplicate_is_still_refused() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W1", D1, text="Damaged te- xt."), api.work("W2", D1, text="Clean text."))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_duplicate"] == 1 and report.duplicate_chosen == 0


@pytest.mark.parametrize("works", [
    (api.work("W1", D1, text="One."), api.work("W3", D1, text="Two.")),  # the chosen work is not returned
    (api.work("W2", D1, text="Only one work."),),  # no longer a duplicate
])  # fmt: skip
def test_a_choice_whose_work_is_not_among_the_returned_duplicates_stops(works) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    with pytest.raises(CrawlError, match="duplicate_choice") as e:
        openalex.fill([r], ext(doi_lookup(*works)), openalex_table.load(CHOICE))
    assert e.value.reason == "duplicate_choice_unmatched"


def test_a_choice_for_a_doi_the_extract_never_asked_is_inert() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    (_out,), report = openalex.fill([r], ext(), openalex_table.load(CHOICE))
    assert report.not_queried == 1 and report.duplicate_chosen == 0


def test_a_chosen_work_with_no_usable_abstract_is_refused_with_why_never_another_work() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W1", D1, text="Other text."), api.work("W2", D1, raw={"a": [1]}))
    (out,), report = openalex.fill([r], ext(lookup), openalex_table.load(CHOICE))
    assert out.abstract is None and report.refused == {"inverted_gap": 1} and report.duplicate_chosen == 0


def test_apply_warns_once_when_the_operator_must_re_run_the_crawl(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Gate C round 1: `openalex_attention`, one aggregate WARNING with counts only, when a candidate went
    unqueried or its listing row changed since the crawl (re-run `op ingest openalex`); none otherwise."""
    from openproceedings.ingest.dedup import DedupResult

    unasked = rec("op:aies:2019:doi-3306618.3314200", "AIES", 2019, doi="10.1145/3306618.3314200")
    openalex.write_extract(tmp_path, ())
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest"):
        openalex.apply(DedupResult((unasked,), (), ()), tmp_path)
    [warning] = [r for r in caplog.records if r.getMessage() == "openalex_attention"]
    assert warning.levelno == logging.WARNING and warning.__dict__["not_queried"] == 1
    assert "listing_stale" not in warning.__dict__ and unasked.id not in str(warning.__dict__)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest"):
        openalex.apply(DedupResult((), (), ()), tmp_path)
    assert not [r for r in caplog.records if r.getMessage() == "openalex_attention"]
