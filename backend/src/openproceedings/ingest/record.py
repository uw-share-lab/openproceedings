"""The corpus record (spec 01 §Record schema; record-schema skill).

`PaperRecord` is the only thing the index build reads. It is frozen and strict: a record without a year,
with a Scholar snippet for an abstract, or with an id that disagrees with its venue and year cannot be
built. `content_hash` covers exactly the searchable and filterable fields, and a record whose stored hash
doesn't match its fields fails to load, so a hash can never go stale. `provenance` keeps every claim from
every source, including the ones precedence overruled (decision-005).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openproceedings.vocab import STATUSES, TRACKS, VENUES

Source = Literal["openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris"]
Venue = Literal["NeurIPS", "ICLR", "ICML"]
Track = Literal[
    "main",
    "datasets_benchmarks",
    "position",
    "workshop",
    "competition",
    "tiny_papers",
    "blogpost",
    "other",
    "unknown",
]
Status = Literal["accepted", "rejected", "withdrawn", "desk_rejected", "unknown"]
Presentation = Literal["oral", "spotlight", "poster"]
ClaimValue = str | int | tuple[str, ...] | None

_ID = re.compile(r"op:([a-z]+):([0-9]{4}):(\S+)")
_SNIPPET = "…"  # Scholar truncates abstracts with an ellipsis: never a real abstract

assert set(VENUES.values()) == set(Venue.__args__)  # type: ignore[attr-defined]
assert set(TRACKS) == set(Track.__args__) and set(STATUSES) == set(Status.__args__)  # type: ignore[attr-defined]


class Claim(BaseModel):
    """One source's statement about one field. Frozen and scalar (tuples for lists), so claims are
    hashable and set-comparable. `fetched_at` comes from the cache entry, never from build time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    value: ClaimValue
    source: Source
    url: str | None = None
    fetched_at: datetime
    evidence: str | None = None  # e.g. `venueid=ICLR.cc/2024/Conference`

    @field_validator("fetched_at")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware (a cache entry's time)")
        return v.astimezone(UTC)


class Urls(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    forum: str | None = None
    pdf: str | None = None
    proceedings: str | None = None
    doi: str | None = None


def content_hash(*, title: str, abstract: str | None, venue: str, year: int, track: str, status: str) -> str:
    """sha256 of the canonical JSON of the searchable and filterable fields (record-schema skill). A re-crawl
    that only refreshes provenance, urls, keywords or presentation leaves it unchanged."""
    body = {
        "title": title,
        "abstract": abstract,
        "venue": venue,
        "year": year,
        "track": track,
        "status": status,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PaperRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str  # op:<venue lower-case>:<year>:<native>; never changes once a snapshot has shipped it
    title: str
    abstract: str | None
    authors: tuple[str, ...]
    venue: Venue
    year: int = Field(ge=1000, le=9999)
    track: Track
    status: Status
    presentation: Presentation | None = None
    venue_id_raw: str | None = None
    urls: Urls = Urls()
    keywords: tuple[str, ...] = ()  # stored and shown, never indexed as text (guarantee 2)
    provenance: tuple[Claim, ...] = ()
    content_hash: str

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a record needs a title")
        if v != " ".join(v.split()):
            raise ValueError(
                "title must be whitespace-collapsed (raw text otherwise: no search normalization)"
            )
        return v

    @field_validator("abstract")
    @classmethod
    def _abstract(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("an absent abstract is None, not an empty string")
        if v is not None and _SNIPPET in v:
            raise ValueError("abstract contains `…`: a Scholar snippet, never a real abstract")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        m = _ID.fullmatch(self.id)
        if m is None:
            raise ValueError(f"id {self.id!r} is not op:<venue>:<year>:<native>")
        if m.group(1) != self.venue.lower() or int(m.group(2)) != self.year:
            raise ValueError(f"id {self.id!r} disagrees with venue {self.venue} / year {self.year}")
        expected = content_hash(
            title=self.title,
            abstract=self.abstract,
            venue=self.venue,
            year=self.year,
            track=self.track,
            status=self.status,
        )
        if self.content_hash != expected:
            raise ValueError("content_hash does not match the record's fields (stale or tampered)")
        return self

    @classmethod
    def build(cls, **fields: Any) -> PaperRecord:
        """A record with its content_hash computed from its fields."""
        fields["content_hash"] = content_hash(
            title=fields["title"],
            abstract=fields.get("abstract"),
            venue=fields["venue"],
            year=fields["year"],
            track=fields["track"],
            status=fields["status"],
        )
        return cls(**fields)

    def claims(self, field: str) -> list[Claim]:
        """Every claim about `field`, including the ones precedence overruled."""
        return [c for c in self.provenance if c.field == field]
