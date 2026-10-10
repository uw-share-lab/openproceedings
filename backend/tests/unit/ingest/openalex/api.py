"""OpenAlex /works answers in the shape api.openalex.org serves (checked live in Task 12); synthetic text."""

import json
from typing import Any

JSON = {"content-type": "application/json"}


def inverted(text: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, w in enumerate(text.split()):
        out.setdefault(w, []).append(i)
    return out


def work(wid: str, doi: str | None, *, title: str = "A Paper", year: int = 2023, text: str | None = "An abstract.",
         sources: tuple[str, ...] = ("S1",), raw: Any = None) -> dict[str, Any]:  # fmt: skip
    return {"id": f"https://openalex.org/{wid}", "doi": None if doi is None else f"https://doi.org/{doi}",
            "title": title, "publication_year": year,
            "primary_location": {"source": {"id": f"https://openalex.org/{sources[0]}"}} if sources else None,
            "abstract_inverted_index": raw if raw is not None else (None if text is None else inverted(text))}  # fmt: skip


def page(*works: dict[str, Any], count: int | None = None, cursor: str | None = None) -> str:
    meta: dict[str, Any] = {"count": len(works) if count is None else count, "per_page": 200}
    if cursor is not None:
        meta["next_cursor"] = cursor
    return json.dumps({"meta": meta, "results": list(works)})
