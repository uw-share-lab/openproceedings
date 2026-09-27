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
from openproceedings.engine.index import VERSION_NAME
from openproceedings.ingest.record import PaperRecord, Presentation, Urls
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import MIN_YEAR, FilterField, Node, TextField
from openproceedings.query.clauses import ParsedFilters
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
DIFF_OFFSET_DOC = "Entries of each list (`added`, `removed`) to skip. Past the end is an empty list."
DIFF_LIMIT_DOC = "Entries of each list per page, 0 to 200. Over 200 is 422 `API_BAD_PARAM`, never clamped."
# `op:<venue>:<year>:<native>` (spec 01 §Ids). `venue` is an open enum (decision-009), so the pattern takes
# any venue-shaped name: a venue this code doesn't know is a 404 (`is_paper_id` refuses it), never a 422
PAPER_ID = r"^op:[a-z][a-z0-9]*:[0-9]{4}:[A-Za-z0-9_-]+$"
RECORD_ID = r"^[A-Za-z0-9_-]{12}$"  # records.RECORD_ID (a test pins them equal)
VERSION_PARAM = f"^(?:{VERSION_NAME.pattern})$"  # an index_version as a client may name one (never `current`)
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
    """02's `ParseResult` without `identification_ast` (it stays server-side; spec 04 §Endpoints), plus
    `filters` (`query.clauses.filter_clauses`, TASK-078). A query with errors is still a 200 here: `errors`
    holds them, and every Optional is null."""

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
    filters: ParsedFilters | None = Field(
        description="Each filter field's top-level clause, for facet and include clicks (spec 02 §Filter "
        "clauses; decision-011): its code-point span in `q` and the values it admits, or a zero-width span at "
        "the end for an applied default or an unrestricted field; `toggleable` false with a `reason` when a "
        "click can't rewrite it. Null exactly when `errors` is non-empty."
    )


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


IDENTIFIED_DOC = (
    "Records identified within the query's own limits (PRISMA): the count of `identification_query`, i.e. "
    "`total` + `excluded.total`. The number `op search` prints as `identified`."
)
UNCLASSIFIED_DOC = (
    "Of `excluded.total`, the records removed as unclassified rather than ineligible: `excluded.track.unknown` "
    "+ `excluded.status.unknown`. The number `op search` prints as `unclassified`."
)


class SearchResponse(Versioned):
    query: QueryInfo
    total: int  # the whole matched set: independent of sort, offset and limit
    excluded: Excluded
    identified_total: int = Field(description=IDENTIFIED_DOC)  # TASK-090: additive
    unclassified_total: int = Field(description=UNCLASSIFIED_DOC)
    facets: Facets
    hits: list[Hit]


# --- /papers/{id} ------------------------------------------------------------------------------------
PAPER_Q_DOC = (
    f"Optional: a query (spec 02 grammar) whose highlights to return for this paper, admitted exactly as "
    f"`/search` admits `q` (at most {MAX_QUERY_LENGTH:,} code points, else 422 `PARSE_TOO_LONG`; one that "
    "doesn't parse is a 422 with its diagnostics). Without it, `matched` and `highlights` are null."
)
PAPER_MODE_DOC = f"{MODE_DOC} Only with `q`: `scholar` without `q` is 422 `API_BAD_PARAM`."


class PaperResponse(Versioned):
    paper: PaperRecord  # the snapshot record the index was built from (spec 01), provenance included
    matched: bool | None = Field(
        description="With `q`: whether the query (default filters included) matches this paper on this "
        "index, i.e. whether `/search` would count it in `total`. Null without `q`."
    )
    highlights: Highlights | None = Field(
        description="With `q`: the spans `/search` gives this paper as a hit for that query, over "
        "`paper.title` and `paper.abstract` (code points over the raw text); both lists empty when "
        "`matched` is false. Null without `q`."
    )


# --- /records (task-037; spec 04 §Search records) -----------------------------------------------------
# The top-level versions of a record response are those the replay ran on; the record's own are in `record`.
class RecordRequest(Model):
    q: str = Field(description=Q_DOC)
    mode: Mode = Field(default="native", description=MODE_DOC)
    index_version: str | None = Field(
        default=None,
        pattern=VERSION_PARAM,
        description="Optional (TASK-091): the index the search was shown on. The record is saved only if the "
        "served index is still that one; otherwise 409 `API_INDEX_VERSION_UNAVAILABLE` and nothing is saved "
        "(a hot swap never freezes the query on another index than the one shown). Absent: the served index.",
    )


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
    ids_match: bool | None  # null when `refused`: nothing was compared
    excluded_match: bool | None  # null when `refused`
    # why the canonical string wasn't run: it doesn't parse or the engine refuses it (the status stays
    # `drifted`, or `mismatch` under the record's own versions), or this instance withholds it
    # (`API_TOO_MANY_VERIFIED_CLAUSES`, `API_QUERY_TOO_COSTLY`: its limits are below what the query needs; then
    # `drifted` on its own index too, unless a check that needs no run fails). No membership comparison happened
    refused: DiagnosticCode | None
    verified_clauses: int | None  # the canonical's position-verified clauses; null when it doesn't parse
    changed: list[ChangedInput]  # empty unless drifted
    added_total: int | None  # ids the replay matched that the record doesn't hold; null when `refused`
    removed_total: int | None  # ids the record holds that the replay didn't match; null when `refused`
    membership_identical: bool | None  # added == removed == 0 (+0/−0 is reported); null when `refused`
    identified_total: int | None = Field(  # TASK-090: additive
        description="The replay's `total` + `excluded.total` (records identified within the query's own "
        "limits). Null when `refused`."
    )
    unclassified_total: int | None = Field(
        description="The replay's `excluded.track.unknown` + `excluded.status.unknown`. Null when `refused`."
    )


class RecordResponse(Versioned):
    """The stored record and a replay of it. With `replay=false` (TASK-091) nothing is replayed: `replay` is
    null and the top-level versions are the served index's and this code's."""

    record: SearchRecord
    replay: ReplayInfo | None = Field(
        description="The replay check (HTTP 200 whatever its status). Null exactly when the request asked "
        "`replay=false`; never null otherwise (decision-012)."
    )


class DiffEntry(Model):
    id: str
    title: str | None  # null when no index on this instance still holds the paper


class RecordDiff(Versioned):
    record_id: str
    status: Literal["reproduced", "drifted", "mismatch"]
    recorded_index_version: str
    refused: DiagnosticCode | None  # as in ReplayInfo: then both lists are empty and the totals null
    verified_clauses: int | None  # as in ReplayInfo
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


class Limits(Model):
    """This instance's limits on a query (TASK-089), so a client need not hard-code them: the parser's length
    and depth caps, and the served config's verification limits (`op serve` flags; another instance may
    differ)."""

    max_query_length: int = Field(
        description="the longest `q` in Unicode code points; a longer one, or one whose canonical form is "
        "longer, is 422 `PARSE_TOO_LONG` (from `/parse`, a 200 whose `errors` hold it)"
    )
    max_query_depth: int = Field(
        description="the deepest nesting of groups and `NOT`s a `q` may have; deeper is 422 `PARSE_TOO_DEEP` "
        "(from `/parse`, a 200 whose `errors` hold it)"
    )
    max_verified_clauses: int = Field(
        description="the most position-verified clauses a query may have; more is 422 "
        "`API_TOO_MANY_VERIFIED_CLAUSES`"
    )
    max_verification_candidates: int = Field(
        description="the most candidate documents a query's position-verified clauses may read, summed over "
        "each clause's fields; more is 422 `API_QUERY_TOO_COSTLY`"
    )


class MetaResponse(Versioned):
    index_versions: list[str] = Field(
        description="every index this instance can serve, sorted, the served one included: an index this "
        "code can't open (another tokenizer, schema or Tantivy version) or one currently refused is left out"
    )
    text_fields: list[TextField]
    filter_fields: list[FilterField]
    values: Vocabularies
    limits: Limits


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
    crawl_dates_kind: dict[str, str] = Field(  # TASK-091: additive, a search record's derivation
        description="Per `crawl_dates` key, what its window's ends are, derived as a search record's: `crawl` "
        "(fetch times, UTC), `scholar_query_dates` (a bootstrap source's window: when its Scholar searches "
        "were run) or `mixed` (`*` over both). Open set: new values may be added within /api/v1; handle a "
        "value you don't know."
    )
    identification_citable: bool = Field(
        description="Whether a search's counts on this snapshot can be cited as PRISMA identification numbers, "
        "derived as a search record's: false when every source is a bootstrap one (the corpus is then an "
        "earlier search's output, not a database)."
    )


class CoverageResponse(Versioned):
    snapshot: SnapshotInfo
    totals: CoverageTotals
    venue_years: list[VenueYearCoverage]  # by venue name, then year
