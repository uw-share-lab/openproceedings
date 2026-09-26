"""Controlled vocabularies shared by ingestion and the query language (spec 01 §Fields, §Track taxonomy).

Filter values in a query are checked against these; ingestion never writes a value outside them.
"""

from __future__ import annotations

from typing import Literal, get_args

# The types are the single source; the value tuples derive from them, so they can't drift apart.
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

# canonical spelling, keyed by the lowercase form a query may use (`venue:` is case-insensitive)
VENUES: dict[str, str] = {v.lower(): v for v in get_args(Venue)}
TRACKS: tuple[str, ...] = get_args(Track)
STATUSES: tuple[str, ...] = get_args(Status)
TEXT_FIELDS = ("title", "abstract")
QUERY_FILTER_FIELDS = (  # every filter field a query may name, incl. Scholar's `source:` (cf. ast.FILTER_FIELDS)
    "venue",
    "year",
    "track",
    "status",
    "source",
)
