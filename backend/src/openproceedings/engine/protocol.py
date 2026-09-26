"""The engine contract (spec 03 §Two engines, one contract), shared by ReferenceEngine and TantivyEngine.

Only types live here, so the two engines can share it without sharing any matching logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openproceedings.query.ast import Node, Wildcard


class Searchable(Protocol):
    """The fields of a snapshot record (spec 01) that search reads: two text fields and four filters."""

    @property
    def id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def abstract(self) -> str | None: ...
    @property
    def venue(self) -> str: ...
    @property
    def year(self) -> int: ...
    @property
    def track(self) -> str: ...
    @property
    def status(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SearchResult:
    total: int
    ids: tuple[str, ...]  # one page, in the engine's order


FACET_FIELDS = ("venue", "year", "track", "status")
MAX_EXPANSIONS = 200  # spec 02: more distinct expanded terms than this is an error, never a truncation


class Engine(Protocol):
    index_version: str

    def search(
        self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50
    ) -> SearchResult: ...
    def match_ids(self, ast: Node) -> frozenset[str]: ...
    def expand(self, wildcard: Wildcard) -> list[str]: ...
    def facets(self, ast: Node, fields: tuple[str, ...] = FACET_FIELDS) -> dict[str, dict[str, int]]: ...
