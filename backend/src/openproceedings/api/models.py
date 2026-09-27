"""The response models of `/parse`, `/search`, `/papers/{id}`, `/meta` and `/coverage`: the contract (spec 04; api-contract
skill). Every response carries `index_version`, `tokenizer_version` and `query_version` (`Versioned`).

Spans are half-open `[start, end)` code-point ranges over the raw source: the stored title or abstract for
`highlights`, the query input `q` for a diagnostic's `span` (spec 04 §Conventions).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.ingest.record import PaperRecord, Presentation, Urls
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import MIN_YEAR, FilterField, Node, TextField
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import MAX_QUERY_LENGTH, Mode
from openproceedings.records import Excluded as Excluded  # one schema for the exclusion accounting
from openproceedings.records import SearchRecord
from openproceedings.timestamps import CrawlWindow, Timestamp
from openproceedings.vocab import Status, Track, Venue

Sort = Literal["relevance", "year_desc", "year_asc", "title"]  # tantivy_engine.SORTS (a test pins them equal)
MAX_LIMIT = 200  # spec 04: `limit` above it is a 422 API_BAD_PARAM, never clamped
DEFAULT_LIMIT = 50  # the Engine protocol's page size
type Span = tuple[int, int]

# parameter descriptions (the generated client shows them)
Q_DOC = (
    f"The query (spec 02 grammar). At most {MAX_QUERY_LENGTH:,} Unicode code points: a longer one is 422 "
    "`PARSE_TOO_LONG`, refused before it is parsed; so is one whose canonical form (defaults written out) is "
    "longer, refused after canonicalising."
)
MODE_DOC = "`native` (this grammar) or `scholar` (Google Scholar / Publish or Perish syntax, translated)."
SORT_DOC = "The order of `hits`. Never changes `total` or membership (guarantee 5)."
OFFSET_DOC = "Hits to skip. Past the end is an empty page, not an error."
LIMIT_DOC = "Hits per page, 0 to 200. Over 200 is 422 `API_BAD_PARAM`, never clamped."
PAPER_ID = r"^op:(neurips|iclr|icml):[0-9]{4}:\S+$"  # `op:<venue>:<year>:<native>` (spec 01 §Ids)
RECORD_ID = r"^[A-Za-z0-9_-]{12}$"  # records.RECORD_ID (a test pins them equal)
PAPER_ID_DOC = "A paper id, `op:<venue>:<year>:<native>`. Any other shape is 422 `API_BAD_PARAM`."
RECORD_ID_DOC = (
    "A search record id: 12 characters of `A-Z a-z 0-9 - _`. Any other shape is 422 `API_BAD_PARAM`."
)


class Model(BaseModel):
    """A response model. Every field is always sent (a null included), so the schema marks every field
    required, a defaulted one too (`json_schema_serialization_defaults_required`; spec 04 §Conventions)."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)


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
    q: str = Field(description=Q_DOC)
    mode: Mode = Field(default="native", description=MODE_DOC)


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
    year: int = Field(ge=MIN_YEAR)  # as PaperRecord.year: a hit and its paper agree field by field
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
    q: str = Field(description=Q_DOC)
    mode: Mode = Field(default="native", description=MODE_DOC)


class RecordCreated(Versioned):
    record_id: str
    page: str = Field(
        description="The record page's path on the site (`/record/<record_id>`, spec 05), relative to the "
        "site's origin. The API resource is the `Location` header (`/api/v1/records/<record_id>`)."
    )


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
    # why the canonical string no longer runs (it doesn't parse, or the engine refuses it); the status stays
    # `drifted`, or `mismatch` under the record's own versions, and no membership comparison happened
    refused: DiagnosticCode | None
    changed: list[ChangedInput]  # empty unless drifted
    added_total: int | None  # ids the replay matched that the record doesn't hold; null when `refused`
    removed_total: int | None  # ids the record holds that the replay didn't match; null when `refused`
    membership_identical: bool | None  # added == removed == 0 (+0/−0 is reported); null when `refused`


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
    refused: DiagnosticCode | None  # as in ReplayInfo: then both lists are empty and the totals null
    changed: list[ChangedInput]
    offset: int
    limit: int  # each list is the page [offset, offset + limit) of its full, id-sorted list
    added_total: int | None
    removed_total: int | None
    added: list[DiffEntry]  # sorted by id
    removed: list[DiffEntry]
    membership_identical: bool | None


# --- /meta -------------------------------------------------------------------------------------------
class Vocabularies(Model):
    venue: list[Venue]
    track: list[Track]
    status: list[Status]


class MetaResponse(Versioned):
    index_versions: list[str] = Field(
        description="every index this instance can serve, sorted, the served one included: an index this "
        "code can't open (another tokenizer, schema or Tantivy version) or one currently refused is left out"
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
    crawl_date: date  # the last fetch's UTC date
    crawl_dates: dict[str, CrawlWindow]  # as a search record's: `*` is the corpus-wide window
    built_at: Timestamp
    sources: list[str]


class CoverageResponse(Versioned):
    snapshot: SnapshotInfo
    totals: CoverageTotals
    venue_years: list[VenueYearCoverage]  # by venue name, then year
