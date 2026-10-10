"""Adversarial bounds for the inert proceedings HTML tree."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from statistics import median

import pytest
from openproceedings.ingest.sources import html
from openproceedings.ingest.sources.html import (
    MAX_DEPTH,
    HTMLBudgetError,
    collapse,
    escape_bare_lt,
    metas,
    node_text,
    parse,
    text_of,
)
from openproceedings.ingest.sources.http import PageCache, SourceError

from tests.unit.test_python_pin import html_parser_fixed

FIXTURES = Path(__file__).parents[2] / "fixtures"


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
        ("<title>a<b>c</b></title> d", "ac d"),  # title, textarea, xmp, iframe: markup inside, as on 3.12.9
        ("<textarea>a<b>c</b></textarea> d", "ac d"),
        ("<xmp>a<b>c</xmp> d", "ac d"),
        ("<iframe>a<b>c</b></iframe> d", "ac d"),
        ("a <plaintext> b <i>c</i>", "a b c"),
        ("<noembed>a<b>c</b></noembed> d", "ac d"),
        ("<noframes>a<b>c</b></noframes> d", "ac d"),
        ("<style>.a<i{}</style><p>kept</p>", "kept"),  # style stays raw text
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


# --- a bare `<` (TASK-209) -------------------------------------------------------------------------------------
# Each row is the synthetic form (decision-004) of a shape the full crawl-cache replay found in a real abstract
# (docs/results/2026-10-07-bare-lt.md), which every Python release used to read as a tag and drop.
BARE_LT = [
    ("if a<b and c>d then", "if a<b and c>d then"),  # known name, attributes that are no attribute names
    ("<p>bound n<k</p>", "bound n<k"),  # an unknown name (TASK-208 read `bound n`)
    # in a paragraph: the `>` of its `</p>` is what turned these into tags (alone, TASK-208's tail rule kept them)
    ("<p>when $W<d$. Our main result</p>", "when $W<d$. Our main result"),
    ("<p>for $1<p<\\infty$. For $1\\leq p<2$, we show</p>", "for $1<p<\\infty$. For $1\\leq p<2$, we show"),
    ("<p>$P_T< \\! \\!<P_S$, we develop</p>", "$P_T< \\! \\!<P_S$, we develop"),
    ("<p>the case $j<i$. The network</p>", "the case $j<i$. The network"),
    ("<p>J == {Jdl<i<K is the set of weights</p>", "J == {Jdl<i<K is the set of weights"),
    ("a model $y = <x, \\theta^*>$", "a model $y = <x, \\theta^*>$"),
    ("predicting <human, action, object> triplets", "predicting <human, action, object> triplets"),
    ("experience tuples <s,a,s',r> from", "experience tuples <s,a,s',r> from"),
    ("code at <https://example.org/repo>.", "code at <https://example.org/repo>."),
    ("a framework called <projektor>, which", "a framework called <projektor>, which"),
    ("a solution such as <THEORY> and k<R>", "a solution such as <THEORY> and k<R>"),
    ("<p>kernel k<RT &gt;.</p>", "kernel k<RT >."),  # `rt` is an element; `&gt;.` is no attribute name
    ("<i and used to explain", "<i and used to explain"),  # an unterminated one, read the same
    ("a </projektor> b", "a </projektor> b"),  # an end tag with an unknown name
    ("a <b x='y > c", "a <b x='y > c"),  # an unterminated quoted value: no tag (TASK-208 read `a`)
]
REAL_TAGS = [
    ("a<b>c</b>", "ac"),  # `<b>` is a tag, as a browser reads it
    ("<p>x<sub>i</sub>-means</p>", "xi-means"),
    ("<table border><tr><td nowrap>cell</td></tr></table>", "cell"),  # bare legacy attributes
    ("<PRE WIDTH=80>pre</PRE>", "pre"),
    ('<a href="x"class="y">t</a>', "t"),  # no space after a quoted value
    ("<a href=/x/y?a=b>t</a>", "t"),
    ("one<br/>two<br />three", "one two three"),
    ("<o:p>word</o:p> <st1:place>w</st1:place>", "word w"),  # namespaced (Word's export)
    ("<my-el>x</my-el>", "x"),  # a custom element
    ("<span data-x>y</span>", "y"),
    ("<script>if (a<b && c>d) {}</script>after", "after"),  # a script body is copied as it is
    ('<p>x</p y="1">z', "x z"),  # an end tag with attributes
    ("a</b and c>d", "ad"),  # an end tag with a known name, whatever follows it
    ("<div v-cloak>t</div>after", "t after"),  # hyphenated attribute names: framework markup
    ("<p xml:lang>q</p><p xmlns>r</p>", "q r"),  # `xml` names
    ("<p data-track_id>q</p><p aria-x_y>r</p>", "q r"),  # any `data-`/`aria-` name, not only hyphenated ones
    ("<style amp-custom>.a{color:red}</style>t", "t"),  # a script or style tag is real whatever it says
    ("<script amp-boilerplate>var a=1;</script>t", "t"),
    ("<layer>l</layer><xml>x</xml>", "lx"),  # Netscape- and IE-era elements
]


@pytest.mark.parametrize(("markup", "text"), BARE_LT)
def test_a_bare_lt_stays_text(markup: str, text: str) -> None:
    """TASK-209: a `<` that doesn't start a real tag is text, with the words up to the next `>`."""
    assert text_of(markup) == node_text(parse(markup)) == text


@pytest.mark.parametrize(("markup", "text"), REAL_TAGS)
def test_real_tags_still_parse(markup: str, text: str) -> None:
    """Real markup is copied unchanged (`escape_bare_lt` leaves it as it is), so it parses as before."""
    assert html.escape_bare_lt(markup) == markup
    assert text_of(markup) == node_text(parse(markup)) == text


def test_a_bare_lt_no_longer_reshapes_the_tree() -> None:
    """A `<li and c>` in a listing row used to open a third list item; the listing keeps its two rows."""
    rows = parse("<ul><li>one if a<li and c>d</li><li>two</li></ul>").iter("li")
    assert [node_text(row) for row in rows] == ["one if a<li and c>d", "two"]
    page = '<p>x<y, "z</p><meta name="citation_title" content="T &lt; U">'
    assert metas(page, "citation_title") == ["T < U"]
    # a bare `<` with an open quote used to read the meta into its attributes (`metas` escapes too)
    page = "x<y 'z " + '<meta name="citation_title" content="T">' + "<p>'x>y</p>"
    assert metas(page, "citation_title") == ["T"]


def test_every_committed_proceedings_page_is_unchanged_by_the_escape() -> None:
    """The recorded HTML pages have no bare `<` outside script and style: the escape changes none of them, so every
    crawler reads them exactly as before. (XML responses, ojs.aaai.org's OAI-PMH, are read by expat, never by the
    HTML path.)"""
    pages = sorted(FIXTURES.glob("http/**/*.json"))
    checked = 0
    for path in pages:
        response = json.loads(path.read_text(encoding="utf-8")).get("response", {})
        body = response.get("text")
        if not isinstance(body, str) or "bare-lt" in path.name:
            continue
        if "xml" in response.get("headers", {}).get("content-type", ""):
            continue
        assert html.escape_bare_lt(body) == body, path
        checked += 1
    assert checked >= 10


def test_the_shared_path_keeps_a_bare_lt_on_neurips_and_pmlr_pages() -> None:
    """Real cached pages' structure (NeurIPS 2024, PMLR v202), scrubbed (decision-004), with synthetic abstracts
    that carry the shapes the replay found. Before TASK-209 the NeurIPS abstract read `… when $Wd then, for $1
    that predicts triplets; …` and the PMLR one stopped at `… and for $2`."""
    from openproceedings.ingest.sources import neurips, pmlr

    from tests.unit.ingest.proceedings_helpers import fixture_text

    page = neurips.parse_abstract_page(fixture_text("neurips/2024/abstract-bare-lt.json"))
    assert page.abstract == (
        "Synthetic opening sentence about gradient flow (GF) when $W<d$. Synthetic words if a<b and c>d then, for "
        "$1<p\\le2$ and $k<n$, with a model called <projektor> that predicts <human, action, object> triplets; "
        "synthetic emphasis stays markup. Code: <https://github.com/synthetic/repo>. Synthetic closing sentence."
    )
    paper = pmlr.parse_paper_page(fixture_text("pmlr/v202/paper-bare-lt.json"))
    assert paper.abstract == (
        "Synthetic opening words, achieving a bound for $1\\leq p<2$ and for $2<p<\\infty$. For $1\\leq p<2$, "
        "synthetic words show the bound is tight, and $P_T< \\! \\!<P_S$ holds. Synthetic closing sentence."
    )


def test_a_bare_lt_costs_linear_time() -> None:
    """Shapes that make a tag match scan far, at n = 20,000: each scan ends at the next `<` outside a quoted
    value. The output is checked here; the cost in `test_escape_bare_lt_is_linear`."""
    n = 20_000
    for page in ('<a x="' + "<a " * n, "<b and c " * n, "<a x='" * n, "<a x=\"'" * n, "<p<" * n, "a<b" * n):
        assert node_text(parse(page)) == text_of(page) == collapse(page)
        assert metas(page, "citation_title") == []
    long_tag = "<a" + " x" * n  # one tag with 20,000 attributes and no `>`
    assert text_of(long_tag) == collapse(long_tag)


def cpu_batch(f: Callable[[str], object], arg: str) -> float:
    """Amortize the CPU clock over four calls without excluding allocation or GC cost."""
    t = time.thread_time()
    for _ in range(4):
        f(arg)
    return (time.thread_time() - t) / 4


@pytest.mark.parametrize(
    "shape",
    [
        lambda n: "<a" + "\xa0x" * n,  # a name that could give back Unicode whitespace to the attribute run
        lambda n: "<a" + "\x0bx" * n,
        lambda n: "<a" + " x" * n,
        lambda n: "<a" + "'" * n,
        lambda n: "<a" + '"x' * n,
        lambda n: "</" + "a" * n,
        lambda n: "</a" + "'" * n,
        # one attempt per `<`: each failed attempt must stop near its own `<`, not scan on to the end of the
        # input (the automated push review's shape for a quadratic total across positions)
        lambda n: '<a x="' * n,
        lambda n: '</a "' * n,
        lambda n: "<a-" * n,
        lambda n: "<x:y " * n,
        lambda n: "<a x='" + "<b and c " * n,
        lambda n: "</a '" + "<p<" * n,
        lambda n: "<!--" + "<a x=\"'" * n,
    ],
)
def test_escape_bare_lt_is_linear(shape: Callable[[int], str]) -> None:
    """testing-standards §CPU growth checks: quadrupling the input costs ~4x when linear, ~16x when quadratic.
    Before the name and attribute runs were possessive, a tag name gave characters back and the attribute run
    rescanned the rest of the input for each one (TASK-209 review: 0.84 s at n = 2,000, 3.4 s at 4,000)."""
    small_arg, large_arg = shape(1_000), shape(4_000)
    escape_bare_lt(small_arg)
    escape_bare_lt(large_arg)
    pairs = []
    for round_number in range(9):
        if round_number % 2:  # alternate the order against size-correlated CPU frequency and allocation drift
            large = cpu_batch(escape_bare_lt, large_arg)
            small = cpu_batch(escape_bare_lt, small_arg)
        else:
            small = cpu_batch(escape_bare_lt, small_arg)
            large = cpu_batch(escape_bare_lt, large_arg)
        pairs.append((small, large))
    ratio = median(large / max(small, 1e-9) for small, large in pairs)
    assert ratio < 8, (ratio, pairs)


@pytest.mark.parametrize(
    ("markup", "text"),
    [
        ("a <!-- b > c", "a"),  # a tail with a `>` is left to close(): an unterminated comment
        ("a <![CDATA[ b > c", "a"),
        ("a <!--> b", "a b"),  # HTML5's empty comment
        ("a <!-- b --!> c", "a c"),
        ("<script>s</script x>after", "after"),  # an end tag with attributes ends the script
        ("a </p y='>'> b", "a b"),  # an end tag with a quoted `>`
        ("<a href==x>t</a>", "t"),  # `href==x`: the value is `=x` (checked below)
    ],
)
def test_the_readings_left_to_the_pinned_parser(markup: str, text: str) -> None:
    """What 3.12.12+ reads differently from 3.12.9 and `html.py` leaves to it (spec 08 "Python pin"); 3.12.9
    read each of these differently. Pinned here so a release that changes them again shows up."""
    running = sys.version_info[:3]
    assert html_parser_fixed(running), (
        f"Python {'.'.join(map(str, running))} has CVE-2025-6069: run the release .python-version pins"
    )
    assert text_of(markup) == node_text(parse(markup)) == text
    if "href==" in markup:
        assert [a.attributes["href"] for a in parse(markup).iter("a")] == ["=x"]
