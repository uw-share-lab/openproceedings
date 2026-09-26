"""Controlled vocabularies shared by ingestion and the query language (spec 01 §Fields, §Track taxonomy).

Filter values in a query are checked against these; ingestion never writes a value outside them.
"""

from __future__ import annotations

# canonical spelling, keyed by the lowercase form a query may use (`venue:` is case-insensitive)
VENUES = {"neurips": "NeurIPS", "iclr": "ICLR", "icml": "ICML"}
TRACKS = (
    "main",
    "datasets_benchmarks",
    "position",
    "workshop",
    "competition",
    "tiny_papers",
    "blogpost",
    "other",
    "unknown",
)
STATUSES = ("accepted", "rejected", "withdrawn", "desk_rejected", "unknown")
TEXT_FIELDS = ("title", "abstract")
QUERY_FILTER_FIELDS = (  # every filter field a query may name, incl. Scholar's `source:` (cf. ast.FILTER_FIELDS)
    "venue",
    "year",
    "track",
    "status",
    "source",
)
