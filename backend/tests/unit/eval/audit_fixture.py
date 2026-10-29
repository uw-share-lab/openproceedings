"""A small corpus for the OpenAlex fidelity audit (`op eval openalex`), built from claims through `dedup.resolve` as
the snapshot's records are. Synthetic text (decision-004). The audited venue-years (FAccT 2022/2025/2026, AIES
2024-2026, AAAI 2010+) hold official abstracts and DOIs; the rest are records the sample must leave out: another
FAccT year, a record with no DOI, a record with no abstract, and AAAI 1980-2008 dblp records with no DOI (the title
route's)."""

from __future__ import annotations

from datetime import UTC, datetime

from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import resolve
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Source

T = datetime(2026, 10, 10, tzinfo=UTC)


def _claim(field: ClaimField, value: ClaimValue, source: Source) -> Claim:
    return Claim(field=field, value=value, source=source, fetched_at=T, evidence="fixture")


def build(rid: str, venue: str, year: int, *, title: str, doi: str | None, abstract: str | None,
          source: Source, official: Source, authors: tuple[str, ...] = ()) -> PaperRecord:  # fmt: skip
    claims = [_claim(f, v, source) for f, v in (
        ("title", title), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"))]  # fmt: skip
    if authors:
        claims.append(_claim("authors", tuple(authors), source))
    if doi:
        claims += [
            _claim("urls.doi", doi, source),
            _claim("urls.proceedings", f"https://doi.org/{doi}", source),
        ]
    if abstract:
        claims.append(_claim("abstract", abstract, official))
    return resolve(rid, claims)[0]


def acm(venue: str, year: int, n: int, *, abstract: str | None = None, doi: bool = True) -> PaperRecord:
    toc = acm_table.TABLE.proceedings[(venue, year)].toc
    return build(f"op:{venue.lower()}:{year}:doi-{toc}.{n}", venue, year, title=f"{venue} paper {n}",
                 doi=f"10.1145/{toc}.{n}" if doi else None,
                 abstract=f"An abstract about paper {n}." if abstract is None else abstract or None,
                 source="crossref", official="facct_site")  # fmt: skip


def ojs(venue: str, year: int, n: int) -> PaperRecord:
    return build(f"op:{venue.lower()}:{year}:ojs-{n}", venue, year, title=f"{venue} paper {n}",
                 doi=f"10.1609/{venue.lower()}.v{year - 1986}i1.{n}", abstract=f"An abstract about paper {n}.",
                 source="ojs", official="ojs")  # fmt: skip


def dblp(year: int, key: str, title: str, authors: tuple[str, ...]) -> PaperRecord:
    return build(f"op:aaai:{year}:dblp-{key}", "AAAI", year, title=title, doi=None, abstract=None, source="dblp",
                 official="dblp", authors=authors)  # fmt: skip


def records() -> list[PaperRecord]:
    out = [acm("FAccT", y, 3500 + i) for y in (2022, 2025, 2026) for i in range(2)]
    out += [ojs("AIES", y, 100 * y + i) for y in (2024, 2025, 2026) for i in range(2)]
    out += [ojs("AAAI", 2010 + i % 15, 1000 + i) for i in range(12)]
    out += [
        acm("FAccT", 2023, 3600),  # not an audited year
        acm("FAccT", 2025, 3700, doi=False),  # no DOI to look up
        acm("FAccT", 2025, 3701, abstract=""),  # no official abstract to compare with
        dblp(1990, "SmithL90", "A Planning Paper", ("Ann Smith", "Bo Li")),
    ]
    return sorted(out, key=lambda r: r.id)
