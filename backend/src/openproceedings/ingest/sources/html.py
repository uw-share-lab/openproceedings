"""Text out of proceedings HTML (neurips-proceedings skill §Abstract extraction; pmlr-proceedings §Page structure).

The standard-library HTML parser reads markup without executing or fetching anything. Rules:

- Block tags (`p`, `br`, `div`, `li`, headings, …) become a space; inline tags (`<i>`, `<sub>`) vanish, so
  `<i>k</i>-means` stays `k-means`. `script` and `style` bodies are dropped.
- Entities are decoded once, then only *complete* leftover entities once more: some pages are
  double-escaped (`&amp;quot;`), while a bare `&` (`R&D`) survives.
- The tree and text parsers keep references raw (`convert_charrefs=False`) and decode them in that one step, so
  each re-emits a reference whole, with its `;` (`_reference`). Without it the decode reads on into the next
  text: `&#x27;Catch` became `⟊tch`, `&rsquo;s` stayed `&rsquos` (TASK-128).
- An unterminated construct at the end with no `>` after it (`for all p<q we show`) stays text (`_feed_all`):
  Python 3.12.12+ (the CVE-2025-6069 fix) would drop it where 3.12.9 kept it (TASK-208).
- Only `script` and `style` bodies are raw text (`_RawTextParser`): 3.12.12+ would also read `title`,
  `textarea`, `xmp`, `iframe`, `noembed`, `noframes` and `plaintext` that way (TASK-208).
- Whitespace collapses to single spaces. LaTeX is kept verbatim (spec 03 decides its tokens).
- The tree is bounded (`MAX_DEPTH`, `MAX_ELEMENTS`). A page past a bound is `HTMLBudgetError`, which names the
  page's URL (when the miner passes it) and how to recover: a page that size is a corrupt or wrong cache entry,
  not a proceedings page, so it is fetched again (TASK-116).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from openproceedings.ingest.sources.http import SourceError, cache_name

_BLOCK_TAGS = frozenset(
    (
        "p", "br", "div", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
        "tr", "td", "th", "table", "section", "article", "header", "footer", "blockquote", "hr", "pre",
        "center",
    )
)  # fmt: skip
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_BARE_AMP = re.compile(r"&(?!#[0-9]{1,7};|#[xX][0-9a-fA-F]{1,6};|[A-Za-z][A-Za-z0-9]{1,31};)")
MAX_DEPTH = 1024
MAX_ELEMENTS = 250_000


class HTMLBudgetError(SourceError, ValueError):
    """A page past the parser's depth or element bound. A ValueError too, so a miner that counts a paper page it
    can't read as `invalid` still does; a listing page's failure refuses the crawl with this message."""

    reason = "html_budget"

    def __init__(self, what: str, url: str | None) -> None:
        if url is None:
            super().__init__(f"HTML {what}")
        else:
            super().__init__(
                f"{url}: HTML {what}; the cached page is corrupt or not the expected page. Re-fetch it: an index "
                "page with `op ingest <source> --refresh`; a paper page by deleting its cache entry "
                f"(pages/{cache_name(url)} under the source's cache directory) and re-running the ingest"
            )
        self.url = url


def unescape(text: str) -> str:
    """Decode entities once, then complete leftover entities once more (a double-escaped page)."""
    once = html.unescape(text)
    return _ENTITY.sub(lambda m: html.unescape(m.group(0)), once)


def _reference(name: str, *, numeric: bool) -> str:
    """A reference HTMLParser reported, written back exactly as the page had it. `_BARE_AMP` has already
    escaped every `&` that doesn't start a complete, `;`-terminated reference, so each one HTMLParser reports
    had its `;`; putting it back keeps `unescape` from reading the following text into the name or code
    point (`&#x27;Catch`, `&rsquo;s`). An unknown name (`&foo;`) stays literal, as it was on the page.
    The two rules change together: loosening `_BARE_AMP` (say, to keep `&copy` without `;`) would make this add
    a `;` the page never had."""
    return f"&#{name};" if numeric else f"&{name};"


def collapse(text: str) -> str:
    return " ".join(text.split())


@dataclass(slots=True)
class Element:
    """A minimal inert HTML element tree for the fixed proceedings-page grammars."""

    tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)

    def iter(self, tag: str | None = None) -> list[Element]:
        found: list[Element] = []
        stack = [child for child in reversed(self.children) if isinstance(child, Element)]
        while stack:
            child = stack.pop()
            if tag is None or child.tag == tag:
                found.append(child)
            stack.extend(
                grandchild for grandchild in reversed(child.children) if isinstance(grandchild, Element)
            )
        return found

    def has_class(self, name: str) -> bool:
        return name in self.attributes.get("class", "").split()

    def contains(self, other: Element) -> bool:
        return self is other or any(node is other for node in self.iter())


class _RawTextParser(HTMLParser):
    """HTMLParser with only `script` and `style` bodies read as raw text, as on 3.12.9 (TASK-208).

    3.12.12+ also reads `title` and `textarea` (escapable), `xmp`, `iframe`, `noembed`, `noframes` and `plaintext`
    as raw text, so one unclosed `<title>` in a listing would turn every later row into literal text and hide a
    later `citation_title` meta. Proceedings pages use none of these as containers of the text we read, so every
    parser here keeps the reading the corpus was built with."""

    def set_cdata_mode(self, elem: str, *, escapable: bool = False) -> None:
        if elem.lower() in ("script", "style"):
            super().set_cdata_mode(elem)  # never escapable: 3.12.9's signature has no such argument


class _TreeParser(_RawTextParser):
    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"})

    def __init__(self, url: str | None = None) -> None:
        super().__init__(convert_charrefs=False)
        self.url = url
        self.root = Element("document")
        self.stack = [self.root]
        self.elements = 0

    def _append(self, tag: str, attrs: list[tuple[str, str | None]], *, push: bool) -> None:
        if len(self.stack) > MAX_DEPTH:
            raise HTMLBudgetError(f"nesting exceeds {MAX_DEPTH} elements", self.url)
        if self.elements >= MAX_ELEMENTS:
            raise HTMLBudgetError(f"contains more than {MAX_ELEMENTS} elements", self.url)
        node = Element(
            tag.casefold(), {k.casefold(): v for k, v in attrs if v is not None}, parent=self.stack[-1]
        )
        self.elements += 1
        self.stack[-1].children.append(node)
        if push and node.tag not in self.VOID:
            self.stack.append(node)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._append(tag, attrs, push=True)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._append(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.stack[-1].children.append(_reference(name, numeric=False))

    def handle_charref(self, name: str) -> None:
        self.stack[-1].children.append(_reference(name, numeric=True))


def _feed_all(parser: _TreeParser | _TextParser, markup: str) -> None:
    """Feed all of `markup`, then close, keeping an unterminated tag-like tail as text (TASK-208).

    One `feed` leaves the input's unfinished end in `rawdata` (an undocumented attribute, so this rests on the
    exact `.python-version` pin and `test_html.py`). When that tail holds no `>` (`for all p<q we show`,
    `tail <!-- c`), no tag can end in it, and 3.12.9's `close` passed it on as text; from 3.12.12 (the
    CVE-2025-6069 fix) `close` drops it, which would cut a fragment's words. So such a tail is handed over as
    data here: the same text on either release (an unclosed script body now stays inside its element, where no
    reader looks). A tail with a `>` is left to `close`. One `handle_data`: linear. Raw only for the parsers
    with `convert_charrefs=False`, whose references `unescape` decodes later; 3.12.9 decoded them for `True`."""
    parser.feed(markup)
    tail = parser.rawdata
    if tail and ">" not in tail:
        parser.rawdata = ""
        parser.handle_data(tail)
    parser.close()


def parse(page: str, url: str | None = None) -> Element:
    """Parse bounded, already-fetched HTML into a non-executing element tree. `url` (the page's canonical URL)
    goes into an `HTMLBudgetError`; every miner passes it."""
    parser = _TreeParser(url)
    _feed_all(parser, _BARE_AMP.sub("&amp;", page))
    return parser.root


def node_text(node: Element) -> str:
    """Visible text under `node`, with the same whitespace/entity rules as `text_of`."""
    parts: list[str] = []
    stack: list[tuple[Element | str, bool]] = [(node, False)]
    while stack:
        current, closing = stack.pop()
        if isinstance(current, str):
            parts.append(current)
            continue
        if closing:
            if current.tag in _BLOCK_TAGS:
                parts.append(" ")
            continue
        if current.tag in ("script", "style"):
            continue
        if current.tag in _BLOCK_TAGS:
            parts.append(" ")
        stack.append((current, True))
        stack.extend((child, False) for child in reversed(current.children))
    return collapse(unescape("".join(parts)))


def text_after(container: Element, target: Element) -> str:
    """Visible text in `container` after `target`'s closing tag."""
    parts: list[str] = []
    seen = False
    stack: list[tuple[Element | str, bool]] = [(container, False)]
    while stack:
        current, closing = stack.pop()
        if isinstance(current, str):
            if seen:
                parts.append(current)
            continue
        if closing:
            if seen and current.tag in _BLOCK_TAGS:
                parts.append(" ")
            continue
        if current is target:
            seen = True
            continue
        if current.tag in ("script", "style"):
            continue
        if seen and current.tag in _BLOCK_TAGS:
            parts.append(" ")
        stack.append((current, True))
        stack.extend((child, False) for child in reversed(current.children))
    return collapse(unescape("".join(parts)))


class _TextParser(_RawTextParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.dropped = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in ("script", "style"):
            self.dropped += 1
        elif not self.dropped and tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.dropped and tag.casefold() in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in ("script", "style"):
            self.dropped = max(0, self.dropped - 1)
        elif not self.dropped and tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.dropped:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.dropped:
            self.parts.append(_reference(name, numeric=False))

    def handle_charref(self, name: str) -> None:
        if not self.dropped:
            self.parts.append(_reference(name, numeric=True))


def text_of(fragment: str) -> str:
    """Plain text of an HTML fragment (the rules in the module docstring)."""
    parser = _TextParser()
    # HTMLParser discards a bare ampersand in strings such as `R&D`; protect only non-entities first.
    _feed_all(parser, _BARE_AMP.sub("&amp;", fragment))
    return collapse(unescape("".join(parser.parts)))


class _TagParser(_RawTextParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag.casefold(), {k.casefold(): v for k, v in attrs if v is not None}))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def attrs(tag: str) -> dict[str, str]:
    """A tag's structurally parsed attributes, names lower-cased and values decoded once."""
    parser = _TagParser()
    parser.feed(tag)
    return parser.tags[0][1] if parser.tags else {}


def metas(page: str, name: str) -> list[str]:
    """The `content` of every `<meta name=…>` with this name, in page order, decoded and collapsed."""
    parser = _TagParser()
    parser.feed(page)
    return [
        collapse(unescape(a["content"]))
        for tag, a in parser.tags
        if tag == "meta" and a.get("name", "").casefold() == name.casefold() and "content" in a
    ]


def meta(page: str, name: str) -> str | None:
    found = metas(page, name)
    return found[0] if found else None
