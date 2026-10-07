"""Adversarial bounds for the inert proceedings HTML tree."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openproceedings.ingest.sources import html
from openproceedings.ingest.sources.html import (
    MAX_DEPTH,
    HTMLBudgetError,
    collapse,
    metas,
    node_text,
    parse,
    text_of,
)
from openproceedings.ingest.sources.http import PageCache, SourceError

from tests.unit.test_python_pin import html_parser_fixed


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


def test_malformed_markup_parses_in_linear_time() -> None:
    """CVE-2025-6069 (TASK-208): before the fix, HTMLParser's `close` took quadratic time on an unterminated
    construct at the end of its input, so one malformed cached page could stall a crawl or a snapshot replay.

    The first ten inputs are CPython's own regression inputs (python/cpython#135462) at a sixth of its size; their
    tails hold no `>`, so `_feed_all` keeps them as text and never asks `close` to parse them. The last two end in
    tails with a `>`, which `close` does parse: on 3.12.9 they cost 0.14 s at n = 3,000 and grow with the
    square of n; a fixed release takes milliseconds at n = 20,000. No wall clock is read (testing-standards
    §Rules 5): a vulnerable interpreter fails the version check first, with the reason, instead of hanging."""
    running = sys.version_info[:3]
    assert html_parser_fixed(running), (
        f"Python {'.'.join(map(str, running))} has CVE-2025-6069: run the release .python-version pins"
    )
    n = 20_000
    kept = (
        "<a " * n,
        "<a a=" * n,
        "</a " * 14 * n,
        "</a a=" * 11 * n,
        "<!--" * 4 * n,
        "<!" * 60 * n,
        "<?" * 19 * n,
        "</$" * 15 * n,
        "<![CDATA[" * 9 * n,
        "<!doctype" * 35 * n,
    )
    for page in kept:
        # every entry point the miners use: the tree, fragment text, and the meta/attribute reader
        assert node_text(parse(page)) == text_of(page) == collapse(page)
        assert metas(page, "citation_title") == []
    for page in ("<!--x>" * n, "<!--a>b" * n):  # an unterminated comment: close() reads it to the end
        assert node_text(parse(page)) == text_of(page) == ""
        assert metas(page, "citation_title") == []


@pytest.mark.parametrize(
    ("markup", "text"),
    [
        ("for all p<q we show", "for all p<q we show"),  # an abstract's inequality, at a fragment's end
        ("title <i>x</i> and p<q", "title x and p<q"),
        ("x &amp; y <a", "x & y <a"),
        ("tail <!-- c", "tail <!-- c"),
        ("end </a", "end </a"),
        ("<p>bound n<k</p>", "bound n"),  # a later `>` makes it a tag, on every release
        ("<title>a<b>c</b></title> d", "ac d"),  # title, textarea, xmp, iframe: markup inside, as on 3.12.9
        ("<textarea>a<b>c</b></textarea> d", "ac d"),
        ("<xmp>a<b>c</xmp> d", "ac d"),
        ("<iframe>a<b>c</b></iframe> d", "ac d"),
        ("a <plaintext> b <i>c</i>", "a b c"),
    ],
)
def test_text_is_read_as_on_3_12_9(markup: str, text: str) -> None:
    """TASK-208: the readings 3.12.12+ changed that `html.py` keeps as 3.12.9 had them, so a fragment keeps its
    words and a page its structure on either release. A tail with no `>` stays text (`_feed_all`): 3.12.12+'s
    `close` would drop it. Only `script` and `style` are raw text (`_RawTextParser`)."""
    assert text_of(markup) == node_text(parse(markup)) == text


def test_an_unclosed_raw_text_tag_does_not_swallow_the_rows_after_it() -> None:
    """3.12.12+ reads an unclosed `<title>` to the end as text: a listing would lose every later row, and the
    abstract page its `citation_title` (TASK-208)."""
    assert len(parse("<ul><li>Why <title> tags</li><li>Second paper</li></ul>").iter("li")) == 2
    assert metas('<title>x<meta name="citation_title" content="T">', "citation_title") == ["T"]
    script = parse("<p>one</p><script>x<y").iter("script")
    assert [node.children for node in script] == [["x<y"]]  # an unclosed script body stays inside it


@pytest.mark.parametrize(
    ("markup", "text"),
    [
        ("a <!-- b > c", "a"),  # a tail with a `>` is left to close(): an unterminated comment
        ("a <![CDATA[ b > c", "a"),
        ("a <b x='y > c", "a"),  # an unterminated quoted attribute value
        ("a <!--> b", "a b"),  # HTML5's empty comment
        ("a <!-- b --!> c", "a c"),
    ],
)
def test_the_readings_left_to_the_pinned_parser(markup: str, text: str) -> None:
    """What 3.12.12+ reads differently from 3.12.9 and `html.py` leaves to it (spec 08 "Python pin"); 3.12.9
    kept each of these as text. Pinned here so a release that changes them again shows up."""
    assert html_parser_fixed(sys.version_info[:3])
    assert text_of(markup) == node_text(parse(markup)) == text
