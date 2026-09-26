"""PaperRecord, Claim and content_hash (spec 01 §Record schema; record-schema skill; task-018)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from openproceedings.ingest.record import Claim, PaperRecord, Urls, content_hash
from pydantic import ValidationError

FETCHED = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def claim(field: str, value: Any, source: str = "openreview_v2", **kw: Any) -> Claim:
    return Claim(
        field=field,
        value=value,
        source=source,
        url=kw.get("url"),
        fetched_at=FETCHED,
        evidence=kw.get("evidence"),
    )  # type: ignore[arg-type]


def record(**overrides: Any) -> PaperRecord:
    fields: dict[str, Any] = {
        "id": "op:iclr:2024:iilhN2MycO",
        "title": "Trust Calibration in LLMs",
        "abstract": "We study trust.",
        "authors": ("A. Author", "B. Author"),
        "venue": "ICLR",
        "year": 2024,
        "track": "main",
        "status": "accepted",
        "presentation": None,
        "venue_id_raw": "ICLR.cc/2024/Conference",
        "urls": Urls(forum="https://openreview.net/forum?id=iilhN2MycO"),
        "keywords": ("trust",),
        "provenance": (claim("status", "accepted", evidence="venueid=ICLR.cc/2024/Conference"),),
    }
    fields.update(overrides)
    return PaperRecord.build(**fields)


def test_build_computes_the_hash() -> None:
    r = record()
    assert r.content_hash == content_hash(
        title=r.title, abstract=r.abstract, venue=r.venue, year=r.year, track=r.track, status=r.status
    )


def test_hash_is_sha256_of_canonical_json_of_the_searchable_and_filterable_fields() -> None:
    r = record(title="Trüst", abstract=None)
    body = {
        "abstract": None,
        "status": "accepted",
        "title": "Trüst",
        "track": "main",
        "venue": "ICLR",
        "year": 2024,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert r.content_hash == hashlib.sha256(canonical).hexdigest()


def test_hash_ignores_provenance_urls_keywords_presentation_authors_and_venue_id_raw() -> None:
    base = record()
    other = record(
        authors=("Someone Else",),
        venue_id_raw=None,
        provenance=(claim("status", "accepted"), claim("title", "x", "neurips_proceedings")),
        urls=Urls(pdf="https://x.pdf"),
        keywords=("other",),
        presentation="oral",
    )
    assert base.content_hash == other.content_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Other"),
        ("abstract", "Other."),
        ("track", "workshop"),
        ("status", "rejected"),
        ("year", 2023),
    ],
)
def test_hash_changes_with_every_covered_field(field: str, value: Any) -> None:
    changed = {field: value}
    if field == "year":
        changed["id"] = "op:iclr:2023:iilhN2MycO"
    assert record(**changed).content_hash != record().content_hash


def test_a_stale_hash_is_rejected_on_load() -> None:
    data = record().model_dump()
    data["title"] = "Tampered"
    with pytest.raises(ValidationError, match="content_hash"):
        PaperRecord.model_validate(data)


def test_round_trips_through_json() -> None:
    r = record()
    assert PaperRecord.model_validate_json(r.model_dump_json()) == r


INVALID: list[tuple[str, dict[str, Any]]] = [
    ("id scheme", {"id": "iclr:2024:x"}),
    ("id venue must match", {"id": "op:icml:2024:iilhN2MycO"}),
    ("id year must match", {"id": "op:iclr:2023:iilhN2MycO"}),
    ("id venue is lower-case", {"id": "op:ICLR:2024:iilhN2MycO"}),
    ("scholar snippet in abstract", {"abstract": "We study trust in large …"}),
    ("empty abstract (use None)", {"abstract": ""}),
    ("empty title", {"title": " "}),
    ("title not whitespace-collapsed", {"title": "Trust  in\nAI"}),
    ("unknown venue", {"venue": "ACL"}),
    ("unknown track", {"track": "tutorial"}),
    ("unknown status", {"status": "maybe"}),
    ("unknown presentation", {"presentation": "keynote"}),
    ("year out of range", {"year": 99, "id": "op:iclr:99:iilhN2MycO"}),
    ("id year zero-padded", {"id": "op:iclr:02024:iilhN2MycO"}),
    ("native id with a space", {"id": "op:iclr:2024:iilh N2MycO"}),
    ("native id with a colon", {"id": "op:iclr:2024:a:b"}),
    ("native id too short", {"id": "op:iclr:2024:ab"}),
    ("pmlr id on a non-ICML record", {"id": "op:iclr:2024:pmlr-v202-foo"}),
    ("nips id that isn't a hash", {"id": "op:neurips:2023:nips-zzz", "venue": "NeurIPS", "year": 2023}),
    (
        "iclr id on a NeurIPS record",
        {"id": "op:neurips:2024:iclr-0123456789abcdef0123456789abcdef", "venue": "NeurIPS"},
    ),
    ("whitespace abstract", {"abstract": "  "}),
    ("empty title", {"title": ""}),
    ("snippet at the start", {"abstract": "… we study trust"}),
    ("year below 1000", {"year": 999, "id": "op:iclr:0999:iilhN2MycO"}),
    ("year as a string", {"year": "2024"}),
    ("lone surrogate", {"title": "Trust \ud800"}),
]


@pytest.mark.parametrize(("why", "overrides"), INVALID, ids=[w for w, _ in INVALID])
def test_invalid_records_cannot_be_built(why: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        record(**overrides)


def test_an_extra_field_is_rejected() -> None:
    data = record().model_dump()
    data["source"] = "x"
    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


def test_valid_native_id_forms() -> None:
    assert record(id="op:iclr:2024:Ab_c-12").forum_id == "Ab_c-12"
    icml = record(id="op:icml:2024:pmlr-v235-smith24a", venue="ICML")
    assert icml.forum_id is None and icml.native == "pmlr-v235-smith24a"
    assert record(id="op:neurips:2024:nips-" + "a" * 32, venue="NeurIPS").forum_id is None
    assert record(id="op:iclr:2024:iclr-" + "0" * 32).forum_id is None


def test_a_real_abstract_may_contain_an_ellipsis() -> None:
    assert record(abstract="for inputs x₁, …, x_n we show").abstract == "for inputs x₁, …, x_n we show"


@pytest.mark.parametrize(
    "missing", ["id", "title", "abstract", "authors", "venue", "year", "track", "status"]
)
def test_every_required_field_is_required(missing: str) -> None:
    data = record().model_dump()
    del data[missing]
    with pytest.raises(ValidationError) as err:
        PaperRecord.model_validate(data)
    assert any(e["loc"] == (missing,) and e["type"] == "missing" for e in err.value.errors())


def test_defaults_for_optional_fields() -> None:
    minimal = PaperRecord.build(
        id="op:iclr:2024:iilhN2MycO", title="T", abstract=None, authors=(), venue="ICLR", year=2024,
        track="main", status="accepted",
    )  # fmt: skip
    assert (
        minimal.urls,
        minimal.venue_id_raw,
        minimal.presentation,
        minimal.keywords,
        minimal.provenance,
    ) == (Urls(), None, None, (), ())


def test_model_copy_revalidates_and_rehashes() -> None:
    r = record()
    changed = r.model_copy(update={"title": "Other"})
    assert changed.content_hash == record(title="Other").content_hash != r.content_hash
    with pytest.raises(ValidationError):
        r.model_copy(update={"venue": "ACL", "id": "garbage"})


def test_records_are_hashable() -> None:
    assert len({record(), record()}) == 1


def test_records_are_frozen() -> None:
    with pytest.raises(ValidationError):
        record().title = "x"  # type: ignore[misc]


def test_claims_and_urls_forbid_extras_and_are_frozen() -> None:
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="ris", fetched_at=FETCHED, extra=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Urls(foo="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Urls().pdf = "x"  # type: ignore[misc]


@pytest.mark.parametrize("source", ["openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris"])
def test_every_source_can_claim(source: str) -> None:
    assert claim("title", "x", source).source == source


def test_claim_fields_and_values_are_strict() -> None:
    with pytest.raises(ValidationError):
        claim("titel", "x")  # a misspelt field would silently match nothing
    with pytest.raises(ValidationError):
        claim("year", True)  # no bool -> int coercion
    with pytest.raises(ValidationError):
        claim("year", 1.0)


def test_one_claim_per_field_and_source_in_a_fixed_order() -> None:
    a, b = claim("title", "A"), claim("status", "accepted", url="https://x")
    assert record(provenance=(a, b)) == record(provenance=(b, a))  # order never matters
    with pytest.raises(ValidationError):
        record(provenance=(claim("title", "A"), claim("title", "B")))  # same field and source twice
    mixed = record(provenance=(claim("title", "A", url="https://x"), claim("title", "B", "pmlr")))
    assert [c.source for c in mixed.provenance] == ["openreview_v2", "pmlr"]  # None and str urls sort


def test_claims_are_frozen_hashable_and_need_an_aware_fetch_time() -> None:
    c = claim("title", "Trust")
    assert {c, claim("title", "Trust")} == {c}  # hashable, equal by value
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="openreview_v2", fetched_at=datetime(2026, 1, 1))  # naive
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="scholar", fetched_at=FETCHED)  # type: ignore[arg-type]
    assert claim("authors", ("A", "B")).value == ("A", "B")


def test_fetch_times_are_normalised_to_utc() -> None:
    est = timezone(timedelta(hours=-4))
    c = Claim(field="title", value="x", source="pmlr", fetched_at=datetime(2026, 9, 20, 8, 0, tzinfo=est))
    assert c.fetched_at == FETCHED and c.fetched_at.utcoffset() == timedelta(0)


def test_claims_for_a_field() -> None:
    r = record(provenance=(claim("title", "A"), claim("status", "accepted"), claim("title", "B", "pmlr")))
    assert [c.value for c in r.claims("title")] == ["A", "B"]
    assert isinstance(r.claims("title"), tuple)
