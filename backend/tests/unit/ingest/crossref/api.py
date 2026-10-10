"""Crossref REST answers in the shape api.crossref.org serves (checked live 2026-10-10); synthetic text."""

import json
from typing import Any

JSON = {"content-type": "application/json"}
TABLE_TEXT = """
[[proceedings]]
venue = "FAccT"
year = 2023
doi = "10.1145/3593013"
title = "Proceedings of the 2023 ACM Conference on Fairness, Accountability, and Transparency"
window_from = 2023-06-01
window_until = 2023-06-30
dois = 3
verified = 2026-10-10
source = "test"

[[not_paper]]
doi = "10.1145/3593013.3594100"
kind = "tutorial"
reason = "a one-page tutorial abstract"
"""


def work(doi: str, *, title: str | None = "A Paper", subtitle: str | None = None,
         authors: tuple[tuple[str, str], ...] = (("Jane", "Doe"),), type_: str = "proceedings-article",
         page: str | None = "1-10", **extra: Any) -> dict[str, Any]:  # fmt: skip
    item: dict[str, Any] = {"DOI": doi, "type": type_,
                            "author": [{"given": g, "family": f, "sequence": "first" if i == 0 else "additional"}
                                       for i, (g, f) in enumerate(authors)]}  # fmt: skip
    if title is not None:
        item["title"] = [title]
    if subtitle is not None:
        item["subtitle"] = [subtitle]
    if page is not None:
        item["page"] = page
    return item | extra


def works_page(*items: dict[str, Any], cursor: str | None = "c2", total: int | None = None) -> str:
    message = {"facets": {}, "total-results": len(items) if total is None else total, "items": list(items),
               "items-per-page": 1000, "query": {"start-index": 0, "search-terms": None}}  # fmt: skip
    if cursor is not None:
        message["next-cursor"] = cursor
    return json.dumps(
        {"status": "ok", "message-type": "work-list", "message-version": "1.0.0", "message": message}
    )


def proceedings(doi: str = "10.1145/3593013",
                title: str = "Proceedings of the 2023 ACM Conference on Fairness, Accountability, and Transparency",
                isbn: tuple[str, ...] = ("9798400701924",)) -> str:  # fmt: skip
    return json.dumps(
        {
            "status": "ok",
            "message-type": "work",
            "message-version": "1.0.0",
            "message": {"DOI": doi, "type": "proceedings", "title": [title], "ISBN": list(isbn)},
        }
    )
