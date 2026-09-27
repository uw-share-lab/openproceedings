"""The response models of `/parse`, `/search`, `/papers/{id}`, `/meta` and `/coverage`: the contract (spec 04; api-contract
skill). Every response carries `index_version`, `tokenizer_version` and `query_version` (`Versioned`).

Spans are half-open `[start, end)` code-point ranges over the raw source: the stored title or abstract for
`highlights`, the query input `q` for a diagnostic's `span` (spec 04 §Conventions).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.ingest.record import PaperRecord, Presentation, Urls
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import FilterField, Node, TextField
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode
from openproceedings.records import SearchRecord
from openproceedings.vocab import Status, Track, Venue

Sort = Literal["relevance", "year_desc", "year_asc", "title"]  # tantivy_engine.SORTS (a test pins them equal)
MAX_LIMIT = 200  # spec 04: `limit` above it is a 422 API_BAD_PARAM, never clamped
DEFAULT_LIMIT = 50  # the Engine protocol's page size
type Span = tuple[int, int]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Versioned(Model):
    index_version: str
    tokenizer_version: str
    query_version: str


def versions(index_version: str) -> dict[str, str]:
    """The three versions a response carries: the served index's, and this code's tokenizer and query."""
    return {
        "index_version": index_version,
        "tokenizer_version": TOKENIZER_VERSION,
        "query_version": QUERY_VERSION,
    }


# --- /parse ------------------------------------------------------------------------------------------
class ParseRequest(Model):
    q: str
    mode: Mode = "native"


class ParseResponse(Versioned):
    """02's `ParseResult` without `identification_ast` (it stays server-side; spec 04 §Endpoints). A query
    with errors is still a 200 here: `errors` holds them, and every Optional is null."""

    mode: Mode
    ast: Node | None  # as typed, spans into q
    effective_ast: Node | None  # canonical, with the default filters (inserted ones span (len(q), len(q)))
    canonical: str | None
    canonical_hash: str | None
    identification_query: str | None  # "" = every record
    defaults: list[FilterField]
    warnings: list[Diagnostic]
    errors: list[Diagnostic]
    translations: list[Diagnostic]


# --- /search -----------------------------------------------------------------------------------------
class QueryInfo(Model):
    input: str
    canonical: str
    canonical_hash: str
    identification_query: str  # "" = every record; may be all-negative (spec 02 §Default filters)
    warnings: list[Diagnostic]
    translations: list[Diagnostic]
    expansions: dict[str, list[str]]  # "<stem><op>" → every term it expands to (guarantee 6)


class Excluded(Model):
    """What the default filters removed (spec 03 §Exclusion accounting): the buckets sum to `total`, each
    map is ordered by count (largest first, ties by name) with `unknown` last and always present."""

    total: int
    track: dict[str, int]
    status: dict[str, int]


class Facets(Model):
    """Disjunctive (decision-001): each field counted without its own top-level conjuncts. Values that
    occur only; years as strings."""

    venue: dict[str, int]
    year: dict[str, int]
    track: dict[str, int]
    status: dict[str, int]


class Highlights(Model):
    title: list[Span]
    abstract: list[Span]


class Hit(Model):
    id: str
    title: str
    abstract: str | None
    authors: list[str]
    venue: Venue
    year: int
    track: Track
    status: Status  # the record schema's (task-035 review decision)
    presentation: Presentation | None
    score: float
    highlights: Highlights
    urls: Urls


class SearchResponse(Versioned):
    query: QueryInfo
    total: int  # the whole matched set: independent of sort, offset and limit
    excluded: Excluded
    facets: Facets
    hits: list[Hit]


# --- /papers/{id} ------------------------------------------------------------------------------------
class PaperResponse(Versioned):
    paper: PaperRecord  # the snapshot record the index was built from (spec 01), provenance included


# --- /records (task-037; spec 04 §Search records) -----------------------------------------------------
# The top-level versions of a record response are those the replay ran on; the record's own are in `record`.
class RecordRequest(Model):
    q: str
    mode: Mode = "native"


class RecordCreated(Versioned):
    record_id: str
    url: str  # the record page's path (`/record/<record_id>`, spec 05), relative to the site


class ChangedInput(Model):
    input: Literal["snapshot_hash", "tokenizer_version", "schema_version", "ranking_params", "query_version"]
    kind: Literal["corpus", "method"]  # snapshot_hash is corpus drift; every other input is method drift
    recorded: JsonValue
    current: JsonValue


class ReplayInfo(Model):
    status: Literal["reproduced", "drifted", "mismatch"]
    index_version: str  # the index the replay ran on (the pinned one unless drifted)
    query_version: str
    total: int | None  # null when the canonical string no longer runs (`refused`)
    excluded: Excluded | None
    ids_hash: str | None
    ids_match: bool
    excluded_match: bool
    refused: DiagnosticCode | None  # why the canonical string no longer runs on a drifted replay
    changed: list[ChangedInput]  # empty unless drifted
    added: int  # ids the replay matched that the record doesn't hold
    removed: int  # ids the record holds that the replay didn't match
    membership_identical: bool  # added == removed == 0 (a drifted +0/−0 is reported, not hidden)


class RecordResponse(Versioned):
    record: SearchRecord
    replay: ReplayInfo


class DiffEntry(Model):
    id: str
    title: str | None  # null when no index on this instance still holds the paper


class RecordDiff(Versioned):
    record_id: str
    status: Literal["reproduced", "drifted", "mismatch"]
    recorded_index_version: str
    changed: list[ChangedInput]
    added: list[DiffEntry]  # sorted by id
    removed: list[DiffEntry]
    membership_identical: bool


# --- /meta -------------------------------------------------------------------------------------------
class Vocabularies(Model):
    venue: list[Venue]
    track: list[Track]
    status: list[Status]


class MetaResponse(Versioned):
    index_versions: list[str] = Field(
        description="every index on this instance, sorted; the served one included"
    )
    text_fields: list[TextField]
    filter_fields: list[FilterField]
    values: Vocabularies


# --- /coverage ---------------------------------------------------------------------------------------
class CoverageCell(Model):
    track: Track
    status: Status
    count: int


class VenueYearCoverage(Model):
    """One venue-year of the snapshot (`coverage.breakdown`): its cells in vocabulary order (`unknown`
    last, never folded), and its unknown and missing-abstract counts, 0 included."""

    venue: Venue
    year: int
    records: int
    abstract_missing: int
    unknown_track: int
    unknown_status: int
    cells: list[CoverageCell]


class CoverageTotals(Model):
    records: int  # = the index's document count
    abstract_missing: int
    unknown_track: int
    unknown_status: int


class SnapshotInfo(Model):
    """The snapshot the served index was built from, as its manifest records it."""

    name: str
    snapshot_hash: str
    crawl_date: str  # the last fetch's UTC date
    crawl_from: str  # the first and last fetch (UTC)
    crawl_to: str
    built_at: str
    sources: list[str]


class CoverageResponse(Versioned):
    snapshot: SnapshotInfo
    totals: CoverageTotals
    venue_years: list[VenueYearCoverage]  # by venue name, then year
