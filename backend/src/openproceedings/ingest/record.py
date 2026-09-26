"""The corpus record (spec 01 §Record schema; record-schema skill).

`PaperRecord` is the only thing the index build reads. It is frozen and strict: a record without a year,
with a Scholar snippet for an abstract, or with an id that disagrees with its venue, year or native-id
form cannot be built. `content_hash` covers exactly the searchable and filterable fields (title, abstract,
venue, year, track, status). It is computed when a record is built (`PaperRecord.build`), recomputed by
`model_copy(update=...)`, and re-checked when a record is loaded, so a hash can never go stale.
`model_construct` skips validation and must never be used on records. `provenance` keeps every claim
(one per field and source), in a fixed order, including the ones precedence overruled (decision-005).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

from openproceedings.vocab import Status, Track, Venue

Source = Literal["openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris"]
Presentation = Literal["oral", "spotlight", "poster"]
ClaimField = Literal[
    "title", "abstract", "authors", "venue", "year", "track", "status", "presentation", "venue_id_raw",
    "keywords", "urls.forum", "urls.pdf", "urls.proceedings", "urls.doi",
]  # fmt: skip
type ClaimValue = StrictStr | StrictInt | tuple[StrictStr, ...] | None

_ID = re.compile(r"op:(neurips|iclr|icml):([0-9]{4}):(\S+)")
# Native ids (record-schema skill): an OpenReview forum id, or a proceedings form tied to its venue.
_PROCEEDINGS_NATIVE = {
    "pmlr": (re.compile(r"pmlr-v[0-9]+-[A-Za-z0-9_-]+"), "ICML"),
    "nips": (re.compile(r"nips-[0-9a-f]{32}"), "NeurIPS"),
    "iclr": (re.compile(r"iclr-[0-9a-f]{32}"), "ICLR"),
}
_FORUM_ID = re.compile(r"[A-Za-z0-9_-]{4,}")
_SNIPPET = (
    "…"  # a Scholar snippet starts or ends with an ellipsis; a real abstract may contain one (`x₁, …, x_n`)
)
_PENDING = "pending"  # content_hash placeholder used only inside `build` and `model_copy`


def _utf8(v: str) -> str:
    try:
        v.encode("utf-8")
    except UnicodeEncodeError as e:  # a lone surrogate
        raise ValueError("text must be valid Unicode (no lone surrogates)") from e
    return v


class Claim(BaseModel):
    """One source's statement about one field. Frozen and scalar (tuples for lists), so claims are
    hashable and set-comparable. `fetched_at` comes from the cache entry, never from build time."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    field: ClaimField
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

    def sort_key(self) -> tuple[str, str, str, str]:
        """A total order (a `None` url sorts first), used for provenance and snapshot files."""
        return (self.field, self.source, self.url or "", self.fetched_at.isoformat())


class Urls(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    forum: str | None = None
    pdf: str | None = None
    proceedings: str | None = None
    doi: str | None = None


def content_hash(*, title: str, abstract: str | None, venue: str, year: int, track: str, status: str) -> str:
    """sha256 of the canonical JSON of the searchable and filterable fields (record-schema skill). A change
    to provenance, urls, keywords, presentation, authors or venue_id_raw leaves it unchanged."""
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
    title: StrictStr
    abstract: StrictStr | None
    authors: tuple[StrictStr, ...]
    venue: Venue
    year: StrictInt = Field(ge=1000, le=9999)
    track: Track
    status: Status
    presentation: Presentation | None = None
    venue_id_raw: str | None = None
    urls: Urls = Urls()
    keywords: tuple[StrictStr, ...] = ()  # stored and shown, never indexed as text (guarantee 2)
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
        return _utf8(v)

    @field_validator("abstract")
    @classmethod
    def _abstract(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("an absent abstract is None, not an empty string")
        if v.strip().startswith(_SNIPPET) or v.strip().endswith(_SNIPPET):
            raise ValueError("abstract starts or ends with `…`: a Scholar snippet, never a real abstract")
        return _utf8(v)

    @field_validator("provenance")
    @classmethod
    def _provenance(cls, v: tuple[Claim, ...]) -> tuple[Claim, ...]:
        seen: set[tuple[str, str]] = set()
        for c in v:
            if (c.field, c.source) in seen:
                raise ValueError(f"two claims for ({c.field}, {c.source}): one claim per field and source")
            seen.add((c.field, c.source))
        return tuple(sorted(v, key=Claim.sort_key))  # equality and snapshots never depend on input order

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        m = _ID.fullmatch(self.id)
        if m is None:
            raise ValueError(f"id {self.id!r} is not op:<venue>:<year>:<native>")
        if m.group(1) != self.venue.lower() or int(m.group(2)) != self.year:
            raise ValueError(f"id {self.id!r} disagrees with venue {self.venue} / year {self.year}")
        native = m.group(3)
        form = _PROCEEDINGS_NATIVE.get(native.split("-", 1)[0])
        if form is not None:
            pattern, venue = form
            if not pattern.fullmatch(native) or venue != self.venue:
                raise ValueError(
                    f"native id {native!r} is not a valid {venue} proceedings id for {self.venue}"
                )
        elif not _FORUM_ID.fullmatch(native):
            raise ValueError(f"native id {native!r} is neither an OpenReview forum id nor a proceedings id")
        expected = content_hash(
            title=self.title,
            abstract=self.abstract,
            venue=self.venue,
            year=self.year,
            track=self.track,
            status=self.status,
        )
        if self.content_hash == _PENDING:
            object.__setattr__(
                self, "content_hash", expected
            )  # build / model_copy: hash the validated values
        elif self.content_hash != expected:
            raise ValueError("content_hash does not match the record's fields (stale or tampered)")
        return self

    @property
    def native(self) -> str:
        return self.id.split(":", 3)[3]

    @property
    def forum_id(self) -> str | None:
        """The OpenReview forum id, if the record's native id is one (dedup merges on it first)."""
        return None if self.native.split("-", 1)[0] in _PROCEEDINGS_NATIVE else self.native

    @classmethod
    def build(
        cls,
        *,
        id: str,
        title: str,
        abstract: str | None,
        authors: tuple[str, ...],
        venue: str,
        year: int,
        track: str,
        status: str,
        presentation: str | None = None,
        venue_id_raw: str | None = None,
        urls: Urls | None = None,
        keywords: tuple[str, ...] = (),
        provenance: tuple[Claim, ...] = (),
    ) -> PaperRecord:
        """A record with its content_hash computed from its validated fields."""
        return cls.model_validate(
            {
                "id": id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "venue": venue,
                "year": year,
                "track": track,
                "status": status,
                "presentation": presentation,
                "venue_id_raw": venue_id_raw,
                "urls": urls or Urls(),
                "keywords": keywords,
                "provenance": provenance,
                "content_hash": _PENDING,
            }
        )

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A validated copy: every invariant is re-checked and the hash recomputed for the new fields."""
        data = self.model_dump()
        data.update(update or {})
        data["content_hash"] = _PENDING
        return self.model_validate(data)

    def claims(self, field: ClaimField) -> tuple[Claim, ...]:
        """Every claim about `field`, including the ones precedence overruled."""
        return tuple(c for c in self.provenance if c.field == field)
