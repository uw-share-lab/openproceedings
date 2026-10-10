"""`abstract_kind` (docs/plans/2026-10-09-new-venues-design.md §Data model): derived from the abstract's claims,
never stored or hashed; `openalex` only when every claim holding the abstract's text is OpenAlex's."""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest.dedup import PRECEDENCE, Attribution, attribution, resolve
from openproceedings.ingest.record import (
    DERIVED,
    RECORD_SCHEMA_VERSION,
    Claim,
    abstract_kind_of,
)  # fmt: skip
from openproceedings.ingest.snapshot import record_line
from pydantic import ValidationError

T = datetime(2026, 10, 10, tzinfo=UTC)
TEXT = "An abstract about calibrated trust in language models."


def _claim(field: str, value: object, source: str, url: str | None = None) -> Claim:
    return Claim(field=field, value=value, source=source, url=url, fetched_at=T, evidence="test")


def _base(source: str = "crossref", venue: str = "FAccT", year: int = 2023) -> list[Claim]:
    url = "https://api.crossref.org/works/10.1145/3593013.3594011"
    return [_claim(f, v, source, url) for f, v in (
        ("title", "A Paper"), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"),
        ("urls.doi", "10.1145/3593013.3594011"), ("urls.proceedings", "https://doi.org/10.1145/3593013.3594011"))]  # fmt: skip


def _openalex(text: str = TEXT) -> Claim:
    return _claim("abstract", text, "openalex", "https://api.openalex.org/works/W123")


def test_schema_is_8_and_the_kind_is_derived() -> None:
    assert RECORD_SCHEMA_VERSION == "8" and frozenset({"venue_name", "abstract_kind"}) == DERIVED


@pytest.mark.parametrize(
    ("abstract", "sources", "kind"),
    [(None, (), "none"), (TEXT, (), "official"), (TEXT, ("openalex",), "openalex"),
     (TEXT, ("ojs", "openalex"), "official"), (TEXT, ("facct_site",), "official")],
)  # fmt: skip
def test_abstract_kind_of(abstract, sources, kind) -> None:
    claims = [_claim("abstract", abstract, s) for s in sources]
    assert abstract_kind_of(abstract, claims) == kind


def test_a_claim_holding_other_text_does_not_count() -> None:
    claims = [_claim("abstract", TEXT, "openalex"), _claim("abstract", "Another text.", "ojs")]
    assert abstract_kind_of(TEXT, claims) == "openalex"


def test_a_record_without_provenance_derives_official_with_an_abstract_and_none_without() -> None:
    # the fixtures' case: no claims at all
    assert abstract_kind_of(TEXT, ()) == "official" and abstract_kind_of(None, ()) == "none"


def test_the_kind_is_sent_never_stored_and_never_hashed() -> None:
    record, _ = resolve("op:facct:2023:doi-3593013.3594011", [*_base(), _openalex()])
    assert record.abstract_kind == "openalex" and record.model_dump()["abstract_kind"] == "openalex"
    assert "abstract_kind" not in record_line(record)
    plain, _ = resolve(
        "op:facct:2023:doi-3593013.3594011", [*_base(), _claim("abstract", TEXT, "facct_site")]
    )
    assert plain.content_hash == record.content_hash  # same text, another source: no hash change
    assert plain.abstract_kind == "official"


@given(st.permutations(["openalex", "ojs"]))
def test_the_official_abstract_wins_whatever_the_claim_order(order: list[str]) -> None:
    official, other = "The official abstract.", "OpenAlex's text of it."
    claims = [*_base("ojs", "AAAI", 2020)]
    for source in order:
        claims.append(_claim("abstract", official if source == "ojs" else other, source))
    record, _ = resolve("op:aaai:2020:ojs-28000", claims)
    assert record.abstract == official and record.abstract_kind == "official"
    assert PRECEDENCE["abstract"][-1] == "openalex"


# every venue outside OPENALEX_VENUES: the three spec 01 forbids, and IASEAI (whose abstracts are all official)
@pytest.mark.parametrize(("venue", "year", "rid", "source"), [
    ("NeurIPS", 2024, "op:neurips:2024:AbCd1234", "openreview_v2"),
    ("ICLR", 2024, "op:iclr:2024:AbCd1234", "openreview_v2"),
    ("ICML", 2003, "op:icml:2003:dblp-MannorRG03", "dblp"),  # a pre-2013 ICML key (`conf/icml/MannorRG03`)
    ("IASEAI", 2026, "op:iaseai:2026:ojs-40000", "ojs"),
])  # fmt: skip
def test_an_openalex_claim_is_refused_outside_aaai_aies_and_facct(
    venue: str, year: int, rid: str, source: str
) -> None:
    claims = [_claim(f, v, source) for f, v in (
        ("title", "A Paper"), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"))]  # fmt: skip
    with pytest.raises((ValidationError, ValueError), match="OpenAlex"):
        resolve(rid, [*claims, _openalex()])


def test_an_openalex_claim_on_another_field_is_refused() -> None:
    with pytest.raises((ValidationError, ValueError), match="OpenAlex"):
        resolve("op:facct:2023:doi-3593013.3594011", [*_base(), _claim("title", "X", "openalex")])


def test_an_openalex_abstract_is_credited_to_the_papers_page_never_the_api() -> None:
    page = "https://doi.org/10.1145/3593013.3594011"
    got = attribution(TEXT, [_openalex()], forum=None, proceedings=page, native="doi-3593013.3594011")
    assert got == Attribution("openalex", "openalex", page)
