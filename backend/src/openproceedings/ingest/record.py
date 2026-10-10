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
from types import MappingProxyType
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
    computed_field,
    field_validator,
    model_validator,
)

from openproceedings.ingest import volumes as _volumes
from openproceedings.ingest.classify import NEURIPS_DB_2021_ROUNDS
from openproceedings.vocab import Status, Track, Venue, venue_name

# The record's shape (fields, native-id forms, content_hash). A change is a new snapshot format: bump it.
# 7: the `crossref` and `facct_site` sources, the `doi-<toc>.<n>` native id (FAccT, AIES), `dblp-` ids for AAAI
# 1980-2008 (decision-049, milestone B); 6: the AAAI, AIES, FAccT and IASEAI venues, five tracks, the `ojs` source and the `ojs-<article id>` native id
# (decision-049); 5: the `dblp` and `icml_site` sources and the `dblp-<key>` native id (TASK-205/206, decision-047);
# 4: the `twin` and `invitation` claim fields (TASK-159, TASK-157; decision-029)
RECORD_SCHEMA_VERSION = "7"
# Sent with a record, never stored: computed from its fields, so a snapshot line never holds it (`record_line`)
# and the shape above is unchanged (TASK-112). Output only: a dump that is validated again excludes it.
DERIVED = frozenset({"venue_name"})

Source = Literal[
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site", "ojs",
    "crossref", "facct_site", "ris",
]  # fmt: skip
Presentation = Literal["oral", "spotlight", "poster"]
ClaimField = Literal[
    "title", "abstract", "authors", "venue", "year", "track", "status", "presentation", "venue_id_raw",
    "keywords", "urls.forum", "urls.pdf", "urls.proceedings", "urls.doi",
    # provenance only, never a record field: the ids of a v1 note's linked twins (TASK-159), and the OpenReview
    # submission invitation scholarmend 0.1.5 reads off a v1 note (TASK-157)
    "twin", "invitation",
]  # fmt: skip

_ID = re.compile(r"op:(neurips|iclr|icml|aaai|aies|facct|iaseai):([0-9]{4}):(\S+)")
# Native ids (record-schema skill): an OpenReview forum id, or a proceedings form tied to its venue.
PROCEEDINGS_NATIVE: dict[str, tuple[re.Pattern[str], frozenset[str]]] = {
    "pmlr": (re.compile(r"pmlr-v[0-9]+-[A-Za-z0-9_-]+"), frozenset({"ICML", "FAccT"})),
    # `-round1`/`-round2`: the 2021 D&B host, which numbers each round separately (urls.proceedings_native)
    "nips": (
        re.compile(rf"nips-[0-9a-f]{{32}}(?:-(?:{'|'.join(sorted(NEURIPS_DB_2021_ROUNDS))}))?"),
        frozenset({"NeurIPS"}),
    ),
    "iclr": (re.compile(r"iclr-[0-9a-f]{32}"), frozenset({"ICLR"})),
    # the dblp key after `conf/icml/` (ICML 1988-2012) or `conf/aaai/` (AAAI 1980-2008) in the pinned dblp release
    # (sources/dblp.py, decision-047, decision-049)
    "dblp": (re.compile(r"dblp-[A-Za-z0-9_-]+"), frozenset({"ICML", "AAAI"})),
    # an ojs.aaai.org article id (`oai:ojs.aaai.org:article/<id>`), unique across its journals (sources/ojs.py)
    "ojs": (re.compile(r"ojs-[0-9]+"), frozenset({"AAAI", "AIES", "IASEAI"})),
    # an ACM paper DOI's suffix, `10.1145/<toc>.<n>` → `doi-<toc>.<n>` (FAccT, AIES; sources/crossref.py)
    "doi": (re.compile(r"doi-[0-9]+\.[0-9]+"), frozenset({"FAccT", "AIES"})),
}
# tracks only one venue has (decision-049): IAAI and EAAI are printed in the AAAI volumes alone
VENUE_ONLY_TRACKS: Mapping[str, str] = MappingProxyType({"iaai": "AAAI", "eaai": "AAAI"})
# the years a `dblp-` id may name: ICML before PMLR (v28, 2013); AAAI before OJS (Vol. 24, 2010)
DBLP_YEARS: Mapping[str, range] = MappingProxyType({"ICML": range(1988, 2013), "AAAI": range(1980, 2009)})
# the years a `doi-` id may name: AIES before OJS (Vol. 7, 2024); FAccT after PMLR v81 (2018)
DOI_YEARS: Mapping[str, range] = MappingProxyType({"AIES": range(2018, 2024), "FAccT": range(2019, 10000)})


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


def _spaced(raw: str) -> tuple[str, int]:
    """`raw` with every control character (Unicode category Cc: C0, DEL and C1) a space and whitespace then
    collapsed, and how many it replaced. The count leaves out the controls that are whitespace (tab, line breaks,
    U+001C-U+001F, U+0085), which collapsing always turned into a space."""
    spaced = "".join(" " if unicodedata.category(c) == "Cc" else c for c in raw)
    replaced = sum(unicodedata.category(c) == "Cc" and not c.isspace() for c in raw)
    return " ".join(spaced.split()), replaced


def title_text(raw: str) -> tuple[str, int]:
    """A source's title as a record stores it, and how many control characters it lost (TASK-180): every
    control character becomes a space, then whitespace is collapsed (`_spaced`). Nothing else changes, so the
    stored title is otherwise the source's. A space, never a deletion: the tokenizer reads a control character
    as a separator (`SPEC\x02TRUM` is `spec`, `trum`), so the stored title's tokens are the raw title's
    (`$`-math aside, where a space beside a delimiter reads differently), and an invisible character never
    fuses two words."""
    return _spaced(raw)


def abstract_text(raw: str) -> tuple[str, int]:
    """A source's abstract as a record stores it, and how many control characters it lost: the title rule
    (`title_text`; decision-044, TASK-188). Every importer already collapsed an abstract's whitespace, so only
    an abstract that held a control character changes. Its tokens do not (`modal\x02ity` was `modal`, `ity`
    before and is after); the record model does not refuse a control character in an abstract, so a snapshot
    built before this still loads. Empty when nothing is left. The same function as `title_text` under the
    field's own name, so each importer names what it stores."""
    return _spaced(raw)


def controls_evidence(evidence: str, replaced: int) -> str:
    """A title or abstract claim's evidence, saying how many control characters `title_text` or
    `abstract_text` replaced (nothing is silent; decision-036, decision-044). Unchanged when none were."""
    if not replaced:
        return evidence
    return f"{evidence} ({replaced} control character{'' if replaced == 1 else 's'} replaced by a space)"


def title_evidence(evidence: str, replaced: int) -> str:
    """A title claim's evidence: `controls_evidence` under the title's own name, kept for the importers that
    call it beside `title_text`."""
    return controls_evidence(evidence, replaced)


_REPLACED = re.compile(r" \(([1-9][0-9]*) control characters? replaced by a space\)\Z")


def title_controls_replaced(record: PaperRecord) -> int:
    """How many control characters `title_text` replaced in the record's title, read back from its title claims'
    evidence (`title_evidence`); 0 when none were. The crawl reports count the titles this is above 0 for."""
    return sum(
        int(m.group(1)) for c in record.provenance
        if c.field == "title" and (m := _REPLACED.search(c.evidence or ""))
    )  # fmt: skip


# Every string a record or claim holds: strict, and encodable, so a snapshot can always be written.
Text = Annotated[StrictStr, AfterValidator(_utf8)]
type ClaimValue = Text | StrictInt | tuple[Text, ...] | None
# What each claim field's value must be (a claim with the wrong kind of value says nothing reliable).
_CLAIM_KINDS: dict[str, type] = {"year": int, "authors": tuple, "keywords": tuple, "twin": tuple}


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

    @computed_field(  # type: ignore[prop-decorator]
        description="The conference's full name and the acronym it went by that year, e.g. `International "
        "Conference on Learning Representations (ICLR 2024)`: the venue string exports use (RIS `T2`; BibTeX "
        "`booktitle`, or the `note`'s `Submitted to …` for a paper not accepted). Derived from `venue` and "
        "`year`; never stored."
    )
    @property
    def venue_name(self) -> str:
        return venue_name(self.venue, self.year)

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
        form = PROCEEDINGS_NATIVE.get(native.split("-", 1)[0])
        if form is not None:
            pattern, venues = form
            if not pattern.fullmatch(native) or self.venue not in venues:
                raise ValueError(
                    f"native id {native!r} is not a valid {'/'.join(sorted(venues))} proceedings id for {self.venue}"
                )
            if native.startswith("pmlr-") and self.venue != "ICML":
                number = int(native.split("-", 2)[1][1:])
                if _volumes.PMLR_NATIVE_VOLUMES.get(number, ("", 0, ""))[:2] != (self.venue, self.year):
                    raise ValueError(
                        f"native id {native!r} is not a {self.venue} {self.year} PMLR volume's (pmlr_volumes.toml)"
                    )
            if native.startswith("dblp-") and self.year not in DBLP_YEARS[self.venue]:
                raise ValueError(
                    f"native id {native!r} is not a valid id for {self.venue} {self.year}: dblp ids are ICML "
                    "1988-2012 and AAAI 1980-2008"
                )
            if native.startswith("doi-") and self.year not in DOI_YEARS[self.venue]:
                raise ValueError(
                    f"native id {native!r} is not a valid id for {self.venue} {self.year}: doi ids are AIES "
                    "2018-2023 and FAccT 2019 on"
                )
            if native.rsplit("-", 1)[-1] in NEURIPS_DB_2021_ROUNDS and self.year != 2021:
                raise ValueError(
                    f"native id {native!r} is not a valid id for {self.year}: D&B rounds are 2021 only"
                )
        elif not FORUM_ID.fullmatch(native):
            raise ValueError(f"native id {native!r} is neither an OpenReview forum id nor a proceedings id")
        if (only := VENUE_ONLY_TRACKS.get(self.track)) is not None and only != self.venue:
            raise ValueError(f"track {self.track!r} is only an {only} track, not {self.venue}'s")
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
        return None if self.native.split("-", 1)[0] in PROCEEDINGS_NATIVE else self.native

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
        data = self.model_dump(exclude={*DERIVED})
        data.update(update or {})
        data["content_hash"] = _HASH_PLACEHOLDER
        return self.model_validate(data, context={_REHASH: True})

    def claims(self, field: ClaimField) -> tuple[Claim, ...]:
        """Every claim about `field`, including the ones precedence overruled."""
        return tuple(c for c in self.provenance if c.field == field)
