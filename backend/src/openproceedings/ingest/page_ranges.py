"""Page ranges for the tables' `[[section]]` rows (decision-050): one start-page reader and one range check, shared
by `dblp_aaai_table` (dblp `pages`) and `acm_table` (Crossref `page`), so the two tables read pages alike."""

from __future__ import annotations

import re
from typing import Any

# "856", "1425-1426", "1853-" (no end page), "1-1"; at most 9 digits a side, so an overlong value from a source is no
# page (a 5,000-digit int would raise in int()) rather than a crash
_START = re.compile(r"([0-9]{1,9})(?:-[0-9]{0,9})?")


def start_page(pages: str | None) -> int | None:
    """The start page of a `pages` field ("1425-1426" → 1425, "856" → 856, "1853-" → 1853), else None."""
    m = _START.fullmatch(pages or "")
    return int(m.group(1)) if m else None


def checked_range(pages: Any, where: str) -> tuple[int, int]:
    """A row's `pages = [first, last]`: two positive integers, first <= last (ValueError naming `where`)."""
    if (
        not isinstance(pages, list)
        or len(pages) != 2
        or not all(type(p) is int and p > 0 for p in pages)
        or pages[0] > pages[1]
    ):
        raise ValueError(f"{where}: pages must be [first, last], positive, first <= last")
    return pages[0], pages[1]


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether two inclusive page ranges share a page (touching at one page counts)."""
    return a[0] <= b[1] and b[0] <= a[1]
