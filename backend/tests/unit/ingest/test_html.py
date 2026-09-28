"""Adversarial bounds for the inert proceedings HTML tree."""

from __future__ import annotations

import pytest
from openproceedings.ingest.sources import html
from openproceedings.ingest.sources.html import MAX_DEPTH, node_text, parse


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
