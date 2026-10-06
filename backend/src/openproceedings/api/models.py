"""The response models of `/parse`, `/search`, `/papers/{id}`, `/compare`, `/meta` and `/coverage`: the contract (spec 04; api-contract
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
from openproceedings.ingest.dedup import Origin
from openproceedings.ingest.record import PaperRecord, Presentation, Source, Urls
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import MIN_YEAR, FilterField, Node, TextField
from openproceedings.query.clauses import ParsedFilters
from openproceedings.query.parser import MAX_QUERY_LENGTH, Mode
from openproceedings.query.wordforms import SkippedTerm, WordForm
from openproceedings.records import Excluded as Excluded  # one schema for the exclusion accounting
from openproceedings.records import SearchRecord
from openproceedings.search import NotCounted
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


def versions(index_version: str, tokenizer_version: str) -> dict[str, str]:
    """The three versions a response carries: the index's it ran on and the tokenizer that index was built with
    (the query was read with it), and this code's query version."""
    return {
        "index_version": index_version,
        "tokenizer_version": tokenizer_version,
        "query_version": QUERY_VERSION,
    }


# --- /parse ------------------------------------------------------------------------------------------
class ParseRequest(Model):
    q: str = Field(description=Q_DOC)
    mode: Mode = Field(default="native", description=MODE_DOC)


class ParseResponse(Versioned):
    """02's `ParseResult` without `identification_ast` (it stays server-side; spec 04 §Endpoints), plus
    `filters` (`query.clauses.filter_clauses`, TASK-078) and `word_forms` and `word_forms_skipped`
    (`query.wordforms.report`, TASK-175, TASK-192). A query with errors is still a 200 here: `errors` holds
    them, and every Optional is null."""

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
    word_forms: list[WordForm] | None = Field(
        description="Each place a `$` can be added to a term the `COMPAT_NO_STEMMING` notice names, in order "
        "(spec 02 §Word forms; TASK-175): the UI inserts `insert` at code point `at` of `q`, an edit of the "
        "query text the reader triggers and sees. The server has parsed `q` with every one inserted. Near the "
        "2,000-code-point cap, only the terms whose `$` fit (in the order they are first written; TASK-192). "
        "Empty outside Scholar mode and when no term can take a `$`. Null exactly when `errors` is non-empty."
    )
    word_forms_skipped: list[SkippedTerm] | None = Field(
        description="Each term the `COMPAT_NO_STEMMING` notice names that `word_forms` offers in no place, once, "
        "in the notice's order, with the `reason` it gets no `$` (spec 02 §Word forms; TASK-192). Empty outside "
        "Scholar mode and when every named term is offered. Null exactly when `errors` is non-empty."
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


ABSTRACT_SOURCE_DOC = (
    "Where the hit's `abstract` came from, for attribution (decision-018). `source`: the provenance claim "
    "precedence took it from (decision-005), as `GET /papers/{id}` lists it; `ris` means it came through an "
    "imported RIS file. `origin`: the site that published it, for a `ris` claim read from the claim's evidence "
    "(`scholarmend:openreview_api` → `openreview`, `scholarmend:proceedings_page` → the proceedings its "
    "`urls.proceedings` names), null when that names no known site. `url`: the paper's page at `origin` (the "
    "OpenReview forum, or the proceedings page; PMLR's CC BY 4.0 terms ask for this link), null when there is "
    "none. The whole object is null when `abstract` is null or no claim holds its text."
)
ORIGIN_DOC = (
    "The site that published the abstract; null when the claim names none this instance knows. `iclr_archive` "
    "can't occur yet: the ICLR archive supplies no abstracts (spec 01 §Sources)."
)


ABSTRACT_WITHHELD_DOC = (
    "True when this instance withholds the paper's abstract at a rights holder's request (a takedown, "
    "decision-018, decision-022): `abstract` is then null, `abstract_source` null and the abstract's highlight "
    "spans empty, though an older index version may still match the query on the withheld text (decision-022: "
    "a saved search's ids never change). False otherwise: a null `abstract` with this false means the sources "
    "gave none."
)
TWINS_DOC = (
    "The ids of this paper's twins (decision-029): another record of the same paper that the index keeps "
    "separate, never merged, such as an ICLR 2017 workshop-listing copy and its conference submission. Each is "
    "a paper on this same index (`GET /papers/{id}`), and each record keeps matching on its own text, so both "
    "can be hits. Usually empty; one or two ids otherwise, sorted."
)
MISSING_COUNT_DOC = (
    "Of `records`, those without an abstract because their sources gave none (title-only). Abstracts withheld at "
    "a rights holder's request are counted in `abstract_withheld` instead (decision-022), including ids the "
    "takedown list names since the snapshot was built, so this can drop after a reload of the same "
    "`index_version`; `op eval coverage` reports the snapshot's own counts."
)
WITHHELD_COUNT_DOC = (
    "Of `records`, those whose abstract this instance withholds at a rights holder's request (a takedown, "
    "decision-022): counted here, not in `abstract_missing`."
)


class AbstractSource(Model):
    source: Source
    origin: Origin | None = Field(description=ORIGIN_DOC)
    url: str | None


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
    abstract_source: AbstractSource | None = Field(description=ABSTRACT_SOURCE_DOC)  # TASK-134: additive
    abstract_withheld: bool = Field(description=ABSTRACT_WITHHELD_DOC)  # TASK-136: additive
    twins: list[str] = Field(description=TWINS_DOC)  # TASK-162: additive


IDENTIFIED_DOC = (
    "Records identified within the query's own limits (PRISMA): the count of `identification_query`, i.e. "
    "`total` + `excluded.total`. The number `op search` prints as `identified`."
)
UNCLASSIFIED_DOC = (
    "Of `excluded.total`, the records removed as unclassified rather than ineligible: `excluded.track.unknown` "
    "+ `excluded.status.unknown`. The number `op search` prints as `unclassified`."
)


GROUPS_DOC = (
    "TASK-176 (additive): for a query that is an AND of concept groups, how many papers each group matches "
    "alone and how many the query matches without it, so a reviewer can see which group narrows the search. "
    "A group is a top-level AND conjunct that searches text and is not negated. The query's filters (the "
    "default track and status filters included) and its `NOT` clauses apply to every count, so none is "
    "below `total`. Exact, and the same for the same canonical query and `index_version`; it never changes "
    "`total`, `hits`, `facets` or `excluded`."
)


class GroupCount(Model):
    span: Span = Field(description="Half-open code-point range of the group in `q` (its node in `ast`).")
    total: int = Field(
        description="This group alone: how many papers the query matches with every other group removed. "
        "Never below the search's `total`."
    )
    total_without: int = Field(
        description="The query without this group: how many papers it matches with this group removed and "
        "every other group kept. Never below the search's `total`; the difference is what this group removes."
    )


class GroupCounts(Model):
    counts: list[GroupCount] = Field(
        description="Each group's count, in query order. Empty when `not_counted` says why."
    )
    groups_total: int = Field(description="How many groups the query has.")
    limit: int = Field(
        description="The most groups this instance counts for one query (`op serve --max-counted-groups`)."
    )
    not_counted: NotCounted | None = Field(
        description="Why `counts` is empty, null when it isn't: `fewer_than_two_groups` (the query is not an "
        "AND of groups), `too_many_groups` (`groups_total` is over `limit`), `too_costly` (counting them would read more "
        "terms or verified ids than this instance allows, `/meta` `limits`: shorten the `NOT` clauses or use longer wildcard stems), `busy` (the counting workers were taken by other searches), `count_failed` or `timed_out` "
        "(the counts could not be computed, or not in time; search again). The search itself is complete "
        "in every case."
    )


class SearchResponse(Versioned):
    query: QueryInfo
    total: int  # the whole matched set: independent of sort, offset and limit
    excluded: Excluded
    identified_total: int = Field(description=IDENTIFIED_DOC)  # TASK-090: additive
    unclassified_total: int = Field(description=UNCLASSIFIED_DOC)
    facets: Facets
    groups: GroupCounts = Field(description=GROUPS_DOC)
    hits: list[Hit]


# --- /compare (TASK-177; spec 04 §Comparing with a RIS file) ---------------------------------------------
# how a record of the file was matched to an index record, or why it has none (`scholar_compare.Match`:
# its `rule`s, then its `problem`s; a test pins the two lists equal)
MatchedBy = Literal[
    "forum_id",
    "proceedings_id",
    "doi",
    "title_venue_year",
    "not_found",
    "ambiguous",
    "no_year",
    "no_venue",
    "truncated_title",
]
# why a paper is on one side only (`scholar_compare`'s classes: `ONLY_SCHOLAR` and `ONLY_OP`; pinned by a test)
CompareReason = Literal[
    "our_bug",
    "query_limit",
    "filtered",
    "compat_reading",
    "coverage_gap",
    "stemming",
    "full_text",
    "scholar_cap",
    "scholar_missed",
    "unsettled",
]
NotComparedReason = Literal["venue_unrecognised", "venue", "year"]  # `scholar_compare.Dropped.reason`


class CompareQuery(Model):
    input: str
    mode: Mode
    canonical: str
    canonical_hash: str


class CompareRow(Model):
    """One paper of a comparison. A row of `kept`, `dropped` or `not_in_index` is a paper of the file (its
    first record, `ris_record`; its title as the file wrote it); a row of `added` is an index record."""

    ris_record: int | None = Field(
        description="The record's position in the file, from 1 (the paper's first record when the file "
        "repeats it). Null on an `added` row."
    )
    copies: int = Field(description="How many records of the file are this paper; 0 on an `added` row.")
    id: str | None = Field(
        description="The index record's id (`/papers/{id}`). Null on a `not_in_index` row."
    )
    title: str = Field(
        description="The file's title for a paper of the file, the index record's for an `added` row."
    )
    venue: str | None = Field(
        description="The index record's venue when it has one, else the venue the file names (as written)."
    )
    year: int | None
    matched_by: MatchedBy | None = Field(
        description="How the file's record was matched to the index, by spec 01's merge rules in their order "
        "(`forum_id`, `proceedings_id`, `doi`: a DOI the index record carries, in the venue and year the file "
        "states, `title_venue_year`), or why it has no index record (`not_found`, "
        "`ambiguous`: its id or title names several records, `no_year`, `no_venue`, `truncated_title`). Null "
        "on an `added` row."
    )
    reason: CompareReason | None = Field(
        description="Why the paper is on one side only (spec 07 §B's classes): for `dropped`, `query_limit` (a "
        "filter clause the query itself writes, such as `year:` or `venue:`, excludes it, whatever its text; "
        "`detail` names the clause), `filtered` (a default filter removes it: its track or status), `full_text` (no title or abstract match), "
        "`stemming` (it matches only with another inflected form), `compat_reading` (it matches as Google "
        "Scholar reads the string); for `not_in_index`, `coverage_gap`, `query_limit` (by the file's own venue and year) or `unsettled`; for `added`, "
        "`scholar_missed`, `compat_reading` or `scholar_cap`. `unsettled`: a person must decide. `our_bug`: "
        "the reference matcher and the served index disagree (report it). Null on a `kept` row that has none."
    )
    detail: str = Field(
        description="The evidence for `reason`, in words (which filter, which word forms, which group of the "
        "query); empty when there is none, and for a record whose abstract is withheld."
    )
    settled: bool = Field(description="False when the automation can't decide and a person must.")
    independent: bool | None = Field(
        description="Whether the index record has a source other than an imported RIS set (a crawl). False: "
        "the index holds this paper only because a RIS set was imported, so a match to it says nothing about "
        "the index's coverage. Null without an index record."
    )
    fails_filters: bool = Field(
        description="Whether the index record fails one of the query's default filters."
    )
    abstract_withheld: bool = Field(
        description="Whether the index record's abstract is withheld (decision-022): this row then has an "
        "empty `detail`, since the evidence can name word forms of the abstract. Its list and `reason` stand. "
        "False on a `not_in_index` row."
    )


class NotComparedRow(Model):
    """A record of the file left out before comparing: it is not a paper of the three venues."""

    ris_record: int
    title: str
    venue: str = Field(description="The venue the file names, as written (may be empty).")
    year: int | None
    reason: NotComparedReason = Field(
        description="`venue_unrecognised`: its venue string is none of the indexed venues' names; `venue`, "
        "`year`: it matched an index record outside the compared venues or years."
    )


class CompareCsv(Model):
    """Each list as a CSV file's text (UTF-8, to be saved with its BOM as sent; one header row), written by
    the server with the export's cell guard, so a client saves it as it is and never builds a cell itself."""

    kept: str
    dropped: str
    not_in_index: str
    added: str
    not_compared: str


class ReasonTotals(Model):
    """How many rows of each list have each `reason` (only the reasons that occur, in spec 07 §B's order), so
    a client shows why papers were dropped without counting rows itself."""

    kept: dict[str, int]
    dropped: dict[str, int]
    not_in_index: dict[str, int]
    added: dict[str, int]


class CompareResponse(Versioned):
    """A RIS file against a query's result on the served index. Every record of the file is counted once:
    `records_total` = `not_compared_total` + `duplicates_total` + `papers_total`, and `papers_total` =
    `kept_total` + `dropped_total` + `not_in_index_total`. `kept_total` + `added_total` = `total`."""

    query: CompareQuery
    total: int = Field(description="`/search`'s `total` for the same query and index: the whole result.")
    records_total: int = Field(description="Records read from the file.")
    not_compared_total: int = Field(description="Of them, records outside the indexed venues.")
    duplicates_total: int = Field(description="Of them, records that repeat a paper already counted.")
    papers_total: int = Field(description="Papers of the file that were compared.")
    kept_total: int = Field(description="Papers of the file the query's result holds.")
    dropped_total: int = Field(description="Papers of the file the index holds and the result doesn't.")
    not_in_index_total: int = Field(description="Papers of the file with no index record.")
    added_total: int = Field(description="Papers of the result that the file doesn't hold.")
    kept_ris_only_total: int = Field(
        description="Of `kept_total`, papers whose index record has no source but an imported RIS set "
        "(`independent` false): the index holds them only because of an import."
    )
    dropped_ris_only_total: int = Field(description="Of `dropped_total`, the same.")
    reason_totals: ReasonTotals
    kept: list[CompareRow]
    dropped: list[CompareRow]
    not_in_index: list[CompareRow]
    added: list[CompareRow]
    not_compared: list[NotComparedRow]
    csv: CompareCsv
    added_ris: str = Field(
        description="The papers the query adds (`added`), as `GET /export` writes RIS for them: the same "
        "records byte for byte, in id order, each abstract with its source, a withheld one left out and marked "
        "(decision-021, decision-022). The only abstracts in the response, each one `/search` serves for the "
        "same hit; nothing of the file is in it. Empty when nothing is added."
    )
    next_comparison_seconds: int = Field(
        ge=0,
        description="Whole seconds until this client's network may start another comparison on this instance "
        "(decision-035: a pause in proportion to the slot time this one used); 0 when it may start one now, "
        "always on a local instance and with the rate limit off. Sooner is 429 `API_RATE_LIMITED`.",
    )


# --- /papers/{id} ------------------------------------------------------------------------------------
PAPER_Q_DOC = (
    f"Optional: a query (spec 02 grammar) whose highlights to return for this paper, admitted exactly as "
    f"`/search` admits `q` (at most {MAX_QUERY_LENGTH:,} code points, else 422 `PARSE_TOO_LONG`; one that "
    "doesn't parse is a 422 with its diagnostics). Without it, `matched` and `highlights` are null."
)
PAPER_MODE_DOC = f"{MODE_DOC} Only with `q`: `scholar` without `q` is 422 `API_BAD_PARAM`."


class PaperResponse(Versioned):
    paper: PaperRecord = Field(
        description="The snapshot record the index was built from (spec 01), provenance included. When "
        "`abstract_withheld`, it comes without its abstract and its abstract claims, and its `content_hash` is "
        "recomputed for what it shows (decision-022)."
    )
    matched: bool | None = Field(
        description="With `q`: whether the query (default filters included) matches this paper on this "
        "index, i.e. whether `/search` would count it in `total`. Null without `q`."
    )
    highlights: Highlights | None = Field(
        description="With `q`: the spans `/search` gives this paper as a hit for that query, over "
        "`paper.title` and `paper.abstract` (code points over the raw text); both lists empty when "
        "`matched` is false. Null without `q`."
    )
    abstract_withheld: bool = Field(description=ABSTRACT_WITHHELD_DOC)  # TASK-136: additive
    twins: list[str] = Field(description=TWINS_DOC)  # TASK-162: additive


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
        "`replay=false`; never null otherwise (decision-014)."
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
    max_counted_groups: int = Field(
        description="TASK-176: the most concept groups `/search` counts for one query; a query with more "
        "gets its result with `groups.not_counted: too_many_groups`"
    )
    max_counted_terms: int = Field(
        description="TASK-176: the most terms the group counts of one query may read, summed over the trees "
        "counted (N groups of G terms in all, K terms in the kept text clauses: N·G + 2·N·K; a wildcard "
        "counts its expansions); more is `groups.not_counted: too_costly`, never a refusal of the search"
    )
    max_counted_ids: int = Field(
        description="TASK-176: the most verified ids the group counts of one query may read, summed the "
        "same way over its position-verified clauses' matches; more is `groups.not_counted: too_costly`"
    )
    compare: CompareLimits | None = Field(
        description="`POST /compare`'s caps (TASK-177), or null when comparisons are not offered: this "
        "instance's operator has not turned them on (the route answers 403 `API_COMPARE_DISABLED`; on an "
        "instance on by its loopback default, also to a request that came through a proxy or from a page not "
        "on that machine), or the served index's comparison table could not be built (503 `API_BUSY` until a "
        "reload). A client doesn't offer comparisons while it is null"
    )


class CompareLimits(Model):
    """What `POST /compare` takes on this instance (TASK-177): each cap refuses a request over it with a typed
    error, never cuts it short."""

    max_body_bytes: int = Field(
        description="the largest RIS file, in bytes; a larger body is 413 `API_BODY_TOO_LARGE`, before it is read"
    )
    max_records: int = Field(
        description="the most records one file may hold; more is 413 `API_RIS_TOO_LARGE`"
    )
    max_line_length: int = Field(
        description="the longest line of the file, in Unicode code points, tag included; a longer one is 413 "
        "`API_RIS_TOO_LARGE`"
    )
    max_title_length: int = Field(
        description="the longest title or venue line's value, in Unicode code points (the corpus's own title "
        "cap); a longer one is 413 `API_RIS_TOO_LARGE`"
    )
    max_results: int = Field(
        description="the most papers of the query's result that the file doesn't hold; more is 422 "
        "`API_COMPARE_TOO_COSTLY`"
    )
    max_seconds: float = Field(
        description="the wall time one comparison's work gets; past it, 503 `API_BUSY` without `Retry-After` "
        "(the same request would run as long again)"
    )
    max_response_bytes: int = Field(
        description="the largest answer, in bytes; a comparison whose answer would be larger is 422 "
        "`API_COMPARE_TOO_COSTLY`"
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


class TrackCoverage(Model):
    """One spec 07 §C cell, venue × year × track (TASK-082): what the snapshot indexed for the track, beside
    the official accepted count where one is sourced (`official_counts.py`, each with its citation)."""

    track: Track
    records: int = Field(description="Records of this track, every status.")
    indexed_accepted: int = Field(description="Of `records`, those with status `accepted`.")
    abstract_missing: int = Field(description=MISSING_COUNT_DOC)
    abstract_withheld: int = Field(description=WITHHELD_COUNT_DOC)  # TASK-136: additive
    sources: list[Source] = Field(description="The sources the track's records came from (claim sources).")
    official_accepted: int | None = Field(
        description="The official accepted count for this venue, year and track; null where none is sourced."
    )
    official_counts: str | None = Field(
        description="What `official_accepted` counts (e.g. orals, spotlights and posters, after withdrawals)."
    )
    official_citation: str | None = Field(
        description="Where `official_accepted` comes from: a URL or citation."
    )
    official_accessed: date | None = Field(description="When `official_citation` was read.")
    delta: int | None = Field(description="`indexed_accepted` − `official_accepted`; null without one.")
    delta_pct: float | None = Field(
        description="`delta` as a percentage of `official_accepted` (unrounded); null without one."
    )
    gated: bool = Field(
        description="Whether the M4 coverage gate applies: a main-track or D&B cell with an official count."
    )
    within_gate: bool | None = Field(
        description="For a gated cell, whether |`delta`| is at most 1% of `official_accepted`; null otherwise."
    )


class VenueYearCoverage(Model):
    """One venue-year of the snapshot (`coverage.breakdown`): its cells in vocabulary order (`unknown`
    last, never folded), and its unknown and missing-abstract counts, 0 included."""

    venue: Venue
    year: int
    records: int
    abstract_missing: int = Field(description=MISSING_COUNT_DOC)
    abstract_withheld: int = Field(description=WITHHELD_COUNT_DOC)  # TASK-136: additive
    unknown_track: int
    unknown_status: int
    cells: list[CoverageCell]
    statuses_indexed: list[Status] = Field(  # TASK-082: additive
        description="The statuses this venue-year's sources can contain at all, in vocabulary order (spec 07 "
        "§C): a proceedings-only venue-year lists `accepted` alone, since no rejected paper exists there to "
        "exclude. A status can be listed with no record in `cells`."
    )
    tracks: list[TrackCoverage] = Field(  # TASK-082: additive
        description="One entry per track with records here, in vocabulary order (`unknown` last)."
    )


class CoverageTotals(Model):
    records: int  # = the index's document count
    abstract_missing: int = Field(description=MISSING_COUNT_DOC)
    abstract_withheld: int = Field(description=WITHHELD_COUNT_DOC)  # TASK-136: additive
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
        "were run, in local time with no recorded offset), `scholar_query_dates_utc` (the same, converted to "
        "UTC with a recorded offset), or `mixed` / `mixed_utc` (`*` over both; `mixed` while some of its "
        "Scholar dates are local). Open set: new values may be added within /api/v1; handle a "
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
