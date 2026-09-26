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


def test_hash_ignores_provenance_urls_keywords_presentation_and_authors_order_of_claims() -> None:
    base = record()
    other = record(
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
    ("extra field", {"source": "x"}),
]


@pytest.mark.parametrize(("why", "overrides"), INVALID, ids=[w for w, _ in INVALID])
def test_invalid_records_cannot_be_built(why: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        record(**overrides)


def test_missing_year_track_or_status_is_invalid() -> None:
    for missing in ("year", "track", "status"):
        data = record().model_dump()
        del data[missing]
        with pytest.raises(ValidationError):
            PaperRecord.model_validate(data)


def test_records_are_frozen() -> None:
    with pytest.raises(ValidationError):
        record().title = "x"  # type: ignore[misc]


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
