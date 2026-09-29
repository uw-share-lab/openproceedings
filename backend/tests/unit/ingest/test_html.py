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


def _both(fragment: str) -> tuple[str, str]:
    """The fragment's text through the text parser (`text_of`) and the tree parser (`parse` + `node_text`)."""
    return html.text_of(fragment), node_text(parse(f"<p>{fragment}</p>"))


@pytest.mark.parametrize(
    ("fragment", "text"),
    [
        # TASK-128: a numeric reference is re-emitted with its `;`, so what follows is never read into it.
        ("Attention Sinks: A &#x27;Catch", "Attention Sinks: A 'Catch"),  # hex, then hex-digit letters
        ("A &#X27;Catch", "A 'Catch"),
        ("Errors-in-variables Fr&#xe9;chet", "Errors-in-variables Fréchet"),
        ("Fr&#233;chet", "Fréchet"),  # decimal, then hex-digit letters
        ("&#x27;123", "'123"),  # hex, then digits
        ("&#39;123", "'123"),  # decimal, then digits
        ("end &#x27;", "end '"),  # at the end of the text
        ("end &#39;", "end '"),
        ("&#x27;&#39;", "''"),  # back to back
        # Named references followed by letters: legacy names (decoded even without `;`) and HTML5-only ones
        # (which, re-emitted without `;`, were left undecoded).
        ("&amp;Catch", "&Catch"),
        ("&eacute;chet", "échet"),
        ("it&rsquo;s", "it’s"),
        ("wait&hellip;", "wait…"),
        ("&notin;x", "∉x"),
        ("&foo; bar", "&foo; bar"),  # an unknown name stays as written
        # Double escapes (the second, complete-entity-only unescape) are unchanged.
        ("&amp;#x27;Catch", "'Catch"),
        ("&amp;#39;s", "'s"),
        ("a &amp;amp; b, &amp;quot;q&amp;quot;", 'a & b, "q"'),
        ("&amp;copy is not an entity without its semicolon", "&copy is not an entity without its semicolon"),
        # A bare ampersand, or a reference with no `;`, is text (`_BARE_AMP`).
        ("R&amp;D and R&D", "R&D and R&D"),
        ("&R&D", "&R&D"),
        ("&#x27Catch", "&#x27Catch"),
        ("&#39 z", "&#39 z"),
        ("&copy", "&copy"),
        # a digit run ended by a tag, not `;`: HTMLParser alone would report charref "39" here
        ("&#39<", "&#39<"),
        ("&#39;<i>x</i>", "'x"),
    ],
)
def test_both_parsers_re_emit_each_reference_whole(fragment: str, text: str) -> None:
    assert _both(fragment) == (text, text)


def test_attribute_values_are_decoded_by_htmlparser_not_the_reference_handlers() -> None:
    """HTMLParser unescapes an attribute value itself (html.unescape), so the TASK-128 bug never reached
    attributes; pinned for the tree, `attrs` and `metas` alike."""
    value = "A &#x27;Catch Fr&#xe9;chet Fr&#233;chet it&rsquo;s &amp;#x27;9 R&D"
    decoded = "A 'Catch Fréchet Fréchet it’s '9 R&D"
    [anchor] = parse(f'<a title="{value}">x</a>').iter("a")
    assert anchor.attributes["title"] == "A 'Catch Fréchet Fréchet it’s &#x27;9 R&D"  # decoded once
    assert html.attrs(f'<a title="{value}">') == {"title": "A 'Catch Fréchet Fréchet it’s &#x27;9 R&D"}
    assert html.metas(f'<meta name="citation_title" content="{value}">', "citation_title") == [decoded]
