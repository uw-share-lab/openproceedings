"""A small corpus with every abstract kind (decision-049), for the schema-4 differential and facet tests. Built
from claims through `dedup.resolve`, as the snapshot's records are, so `abstract_kind` is derived, never set.
Synthetic text (decision-004); the `doi-` ids name each venue-year's real ACM proceedings (`acm_table.TABLE`), as
a record's id must. Pinned: add records at the end only.

Every fourth record from the first is OpenAlex-only, from the second official and OpenAlex with the same text
(official), from the third official-only, from the fourth without an abstract (none)."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache

from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import resolve
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Source

T = datetime(2026, 10, 10, tzinfo=UTC)
WORDS = ("trust", "calibration", "agents", "fairness", "planning", "audit")
SIZE = 60


def _claim(field: ClaimField, value: ClaimValue, source: Source) -> Claim:
    return Claim(field=field, value=value, source=source, fetched_at=T, evidence="fixture")


def _claims(
    source: Source, venue: str, year: int, title: str, extra: list[tuple[ClaimField, str, Source]]
) -> list[Claim]:
    base: list[tuple[ClaimField, ClaimValue]] = [
        ("title", title), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"),
    ]  # fmt: skip
    return [_claim(f, v, source) for f, v in base] + [_claim(f, v, s) for f, v, s in extra]


def _native(venue: str, year: int, i: int) -> str:
    if venue == "AAAI":
        return f"dblp-K{i}"
    return f"doi-{acm_table.TABLE.proceedings[(venue, year)].toc}.{3594000 + i}"


@cache
def _built() -> tuple[PaperRecord, ...]:
    out = []
    for i in range(SIZE):
        w, kind = WORDS[i % len(WORDS)], i % 4
        venue, year = (("AAAI", 1990 + i % 18), ("AIES", 2018 + i % 6), ("FAccT", 2019 + i % 8))[i % 3]
        source: Source = "dblp" if venue == "AAAI" else "crossref"
        official: Source = "ris" if source == "dblp" else source  # dblp gives no abstract
        text = f"An abstract about {w} number {i}."
        extra: list[tuple[ClaimField, str, Source]] = [
            [("abstract", text, "openalex")],
            [("abstract", text, official), ("abstract", text, "openalex")],
            [("abstract", text, official)],
            [],
        ][kind]
        record_id = f"op:{venue.lower()}:{year}:{_native(venue, year, i)}"
        record, _conflicts = resolve(record_id, _claims(source, venue, year, f"{w} paper {i}", extra))
        out.append(record)
    return tuple(out)


def records() -> list[PaperRecord]:
    """The corpus, in build order (a fresh list each call; the records are frozen)."""
    return list(_built())
