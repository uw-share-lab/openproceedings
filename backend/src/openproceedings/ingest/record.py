"""The corpus record (spec 01 §Record schema; record-schema skill).

`PaperRecord` is the only thing the index build reads. It is frozen and strict: a record without a year,
with a Scholar snippet for an abstract, or with an id that disagrees with its venue, year or native-id
form cannot be built. `content_hash` covers exactly the searchable and filterable fields (title, abstract,
venue, year, track, status). It is computed when a record is built (`PaperRecord.build`), recomputed by
`model_copy(update=...)` (both ask for it through the validation context, which stored data can't
reach), and re-checked when a record is loaded, so a hash can never go stale.
`model_construct` skips validation and must never be used on records. `provenance` keeps every claim
(one per field and source), in a fixed order, including the ones precedence overruled (decision-005).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from openproceedings.vocab import Status, Track, Venue, venue_name

# The record's shape (fields, native-id forms, content_hash). A change is a new snapshot format: bump it.
RECORD_SCHEMA_VERSION = "1"

Source = Literal["openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris"]
Presentation = Literal["oral", "spotlight", "poster"]
ClaimField = Literal[
    "title", "abstract", "authors", "venue", "year", "track", "status", "presentation", "venue_id_raw",
    "keywords", "urls.forum", "urls.pdf", "urls.proceedings", "urls.doi",
]  # fmt: skip

_ID = re.compile(r"op:(neurips|iclr|icml):([0-9]{4}):(\S+)")
# Native ids (record-schema skill): an OpenReview forum id, or a proceedings form tied to its venue.
_PROCEEDINGS_NATIVE = {
    "pmlr": (re.compile(r"pmlr-v[0-9]+-[A-Za-z0-9_-]+"), "ICML"),
    "nips": (re.compile(r"nips-[0-9a-f]{32}"), "NeurIPS"),
    "iclr": (re.compile(r"iclr-[0-9a-f]{32}"), "ICLR"),
}


def is_paper_id(text: str) -> bool:
    """Whether `text` has the shape of a record id, `op:<venue>:<year>:<native>` (a cheap check before any
    lookup; the record itself checks the rest)."""
    return _ID.fullmatch(text) is not None


FORUM_ID = re.compile(r"(?=.*[A-Za-z0-9])[A-Za-z0-9_-]{4,64}")
_SNIPPET = (
    "…"  # a Scholar snippet starts or ends with an ellipsis; a real abstract may contain one (`x₁, …, x_n`)
)
_REHASH = "rehash"  # validation-context key: only `build` and `model_copy` set it
_HASH_PLACEHOLDER = "0" * 64


def _utf8(v: str) -> str:
    try:
        v.encode("utf-8")
    except UnicodeEncodeError as e:  # a lone surrogate
        raise ValueError("text must be valid Unicode (no lone surrogates)") from e
    return v


# Every string a record or claim holds: strict, and encodable, so a snapshot can always be written.
Text = Annotated[StrictStr, AfterValidator(_utf8)]
type ClaimValue = Text | StrictInt | tuple[Text, ...] | None
# What each claim field's value must be (a claim with the wrong kind of value says nothing reliable).
_CLAIM_KINDS: dict[str, type] = {"year": int, "authors": tuple, "keywords": tuple}


class Claim(BaseModel):
    """One source's statement about one field. Frozen and scalar (tuples for lists), so claims are
    hashable and set-comparable. `fetched_at` comes from the cache entry, never from build time."""

    # every field is always sent, so the API schema marks every one required (spec 04 §Conventions)
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, json_schema_serialization_defaults_required=True
    )

    field: ClaimField
    value: ClaimValue
    source: Source
    url: Text | None = None
    fetched_at: datetime
    evidence: Text | None = None  # e.g. `venueid=ICLR.cc/2024/Conference`

    @field_validator("fetched_at")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware (a cache entry's time)")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        kind = _CLAIM_KINDS.get(self.field, str)
        if not isinstance(self.value, kind):  # StrictInt already refuses bool
            raise ValueError(f"a {self.field} claim's value must be a {kind.__name__}")
        return self

    def sort_key(self) -> tuple[str, str, str, str]:
        """The provenance order (a `None` url sorts first). Total within a record, which rejects two claims
        for one (field, source); dedup adds its own tie-break when it merges claims."""
        return (self.field, self.source, self.url or "", self.fetched_at.isoformat())


def _url(v: str) -> str:
    """An http(s) URL on one line: no whitespace, control, line or paragraph separator (an export writes it
    as one RIS/BibTeX line, and a newline in it could forge a record)."""
    if not v.startswith(("https://", "http://")) or not _single_line(v) or not urlparse(v).hostname:
        raise ValueError("a URL must be http(s) with a host and no whitespace, control or format characters")
    return v


def _doi(v: str) -> str:
    if not re.fullmatch(r"10\.\d+(?:\.\d+)*/\S+", v) or not _single_line(v):
        raise ValueError("a DOI must look like 10.NNNN/suffix, with no whitespace or control characters")
    return v


# no whitespace and nothing in the control (Cc), line (Zl) or paragraph (Zp) categories
_SINGLE_LINE = re.compile(r"[^\s\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def _single_line(v: str) -> bool:
    """One printable line: `_SINGLE_LINE`, and no format (Cf) character (zero-width, bidi controls, soft
    hyphen, tags), which could make an exported URL read as another."""
    return bool(_SINGLE_LINE.fullmatch(v)) and not any(unicodedata.category(c) == "Cf" for c in v)


Url = Annotated[Text, AfterValidator(_url)]


def is_url(v: str) -> bool:
    """Would `v` be accepted as a record URL?"""
    try:
        _url(v)
    except ValueError:
        return False
    return True


Doi = Annotated[Text, AfterValidator(_doi)]


class Urls(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    forum: Url | None = None
    pdf: Url | None = None
    proceedings: Url | None = None
    doi: Doi | None = None


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
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    id: str  # op:<venue lower-case>:<year>:<native>; never changes once a snapshot has shipped it
    title: StrictStr
    abstract: StrictStr | None
    authors: tuple[Text, ...]
    venue: Venue
    year: StrictInt = Field(ge=1000)  # the id's four digits bound it above
    track: Track
    status: Status
    presentation: Presentation | None = None
    venue_id_raw: Text | None = None
    urls: Urls = Urls()
    keywords: tuple[Text, ...] = ()  # stored and shown, never indexed as text (guarantee 2)
    provenance: tuple[Claim, ...] = ()
    content_hash: str  # checked against the fields on every load; only build/model_copy compute it

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a record needs a title")
        if any(unicodedata.category(c) == "Cc" for c in v):
            raise ValueError("title contains a control character")
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
        if v != v.strip():
            raise ValueError("abstract has leading or trailing whitespace (importers strip it; it is hashed)")
        if v.startswith(_SNIPPET) or v.endswith(_SNIPPET):
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
    def _consistent(self, info: ValidationInfo) -> Self:
        m = _ID.fullmatch(self.id)
        if m is None:
            raise ValueError(f"id {self.id!r} is not op:<venue>:<year>:<native>")
        if m.group(1) != self.venue.lower() or int(m.group(2)) != self.year:
            raise ValueError(f"id {self.id!r} disagrees with venue {self.venue} / year {self.year}")
        venue_name(self.venue, self.year)  # a year the venue wasn't held: refused here, never mid-export
        native = m.group(3)
        form = _PROCEEDINGS_NATIVE.get(native.split("-", 1)[0])
        if form is not None:
            pattern, venue = form
            if not pattern.fullmatch(native) or venue != self.venue:
                raise ValueError(
                    f"native id {native!r} is not a valid {venue} proceedings id for {self.venue}"
                )
        elif not FORUM_ID.fullmatch(native):
            raise ValueError(f"native id {native!r} is neither an OpenReview forum id nor a proceedings id")
        expected = content_hash(
            title=self.title,
            abstract=self.abstract,
            venue=self.venue,
            year=self.year,
            track=self.track,
            status=self.status,
        )
        if info.context and info.context.get(_REHASH):
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
                "content_hash": _HASH_PLACEHOLDER,
            },
            context={_REHASH: True},
        )

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A validated copy: every invariant is re-checked and the hash recomputed for the new fields."""
        data = self.model_dump()
        data.update(update or {})
        data["content_hash"] = _HASH_PLACEHOLDER
        return self.model_validate(data, context={_REHASH: True})

    def claims(self, field: ClaimField) -> tuple[Claim, ...]:
        """Every claim about `field`, including the ones precedence overruled."""
        return tuple(c for c in self.provenance if c.field == field)
