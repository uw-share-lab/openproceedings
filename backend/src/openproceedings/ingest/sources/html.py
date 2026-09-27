"""Text out of proceedings HTML (neurips-proceedings skill §Abstract extraction; pmlr-proceedings §Page structure).

The pages are server-rendered and regular, so a few anchored patterns read them; nothing here executes or
fetches anything. Rules:

- Block tags (`p`, `br`, `div`, `li`, headings, …) become a space; inline tags (`<i>`, `<sub>`) vanish, so
  `<i>k</i>-means` stays `k-means`. `script` and `style` bodies are dropped.
- Entities are decoded once, then only *complete* leftover entities once more: some pages are
  double-escaped (`&amp;quot;`), while a bare `&` (`R&D`) survives.
- Whitespace collapses to single spaces. LaTeX is kept verbatim (spec 03 decides its tokens).
"""

from __future__ import annotations

import html
import re

_DROP = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_TAGS = (
    "p|br|div|li|ul|ol|dl|dt|dd|h[1-6]|tr|td|th|table|section|article|header|footer|blockquote|hr|pre|center"
)
_BLOCK = re.compile(rf"</?(?:{_BLOCK_TAGS})\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def unescape(text: str) -> str:
    """Decode entities once, then complete leftover entities once more (a double-escaped page)."""
    once = html.unescape(text)
    return _ENTITY.sub(lambda m: html.unescape(m.group(0)), once)


def collapse(text: str) -> str:
    return " ".join(text.split())


def text_of(fragment: str) -> str:
    """Plain text of an HTML fragment (the rules in the module docstring)."""
    fragment = _COMMENT.sub(" ", _DROP.sub(" ", fragment))
    return collapse(unescape(_TAG.sub("", _BLOCK.sub(" ", fragment))))


def attrs(tag: str) -> dict[str, str]:
    """A tag's attributes, names lower-cased, values raw (not yet unescaped)."""
    return {
        m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3) for m in _ATTR.finditer(tag)
    }


def metas(page: str, name: str) -> list[str]:
    """The `content` of every `<meta name=…>` with this name, in page order, decoded and collapsed."""
    out = []
    for m in _META.finditer(page):
        a = attrs(m.group(0))
        if a.get("name", "").lower() == name and "content" in a:
            out.append(collapse(unescape(a["content"])))
    return out


def meta(page: str, name: str) -> str | None:
    found = metas(page, name)
    return found[0] if found else None
