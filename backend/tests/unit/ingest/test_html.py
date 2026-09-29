"""Adversarial bounds for the inert proceedings HTML tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from openproceedings.ingest.sources import html
from openproceedings.ingest.sources.html import MAX_DEPTH, HTMLBudgetError, node_text, parse
from openproceedings.ingest.sources.http import PageCache, SourceError


def test_deep_html_is_walked_iteratively_but_refused_past_the_explicit_depth_budget() -> None:
    within = min(MAX_DEPTH - 1, 1000)
    root = parse("<div>" * within + "kept" + "</div>" * within)
    assert node_text(root) == "kept" and len(root.iter("div")) == within

    too_deep = "<div>" * (MAX_DEPTH + 1) + "private" + "</div>" * (MAX_DEPTH + 1)
    with pytest.raises(ValueError, match="nesting exceeds"):
        parse(too_deep)


def test_element_budget_is_independent_of_the_depth_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(html, "MAX_ELEMENTS", 3)
    with pytest.raises(ValueError, match="more than 3 elements"):
        parse("<p>one</p><p>two</p><p>three</p><p>four</p>")


def test_a_budget_failure_names_the_page_and_how_to_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TASK-116: the page's URL, the `--refresh` route for an index page and the cache entry for a paper page;
    a SourceError (the CLI's one refusal line) that miners still count as an invalid record (a ValueError)."""
    monkeypatch.setattr(html, "MAX_ELEMENTS", 3)
    url = "https://proceedings.mlr.press/v28/muandet13.html"
    with pytest.raises(HTMLBudgetError) as refused:
        parse("<p>one</p><p>two</p><p>three</p><p>four</p>", url)
    entry = PageCache(tmp_path).path(url).relative_to(tmp_path)
    assert str(refused.value) == (
        f"{url}: HTML contains more than 3 elements; the cached page is corrupt or not the expected page. "
        "Re-fetch it: an index page with `op ingest <source> --refresh`; a paper page by deleting its cache "
        f"entry ({entry} under the source's cache directory) and re-running the ingest"
    )
    assert isinstance(refused.value, SourceError) and isinstance(refused.value, ValueError)
    assert refused.value.reason == "html_budget"
