"""Turns a raw HTTP capture into a committed crawler fixture (decision-004; spec 01 §Testing).

A capture is taken by a person in a manual research or `op ingest` run, never by a test, and is a JSON file
`{"url", "auth", "status", "headers", "body"}` (the bearer token is never part of it). This module has no
network code: it only rewrites captures.

What a fixture keeps real: ids, forum ids, numbers, venueids, venue strings, decisions and
recommendations, invitations, signatures that name a group, dates, pagination fields, the status code and
the rate-limit and content-type headers, and the HTML structure the adapters parse. What it replaces with
synthetic text of the same type: titles, abstracts, authors, author ids, keywords, reviews, comments,
bibtex, emails and profile ids (`~Name1`), and free text in general. Long listings are trimmed to a few
entries; the fixture's `_recorded.trimmed` says so.

    python backend/tests/fixtures/http/scrub.py <captures-dir>   # rewrites every capture under it

writes `backend/tests/fixtures/http/<same relative path>.json`.
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
RECORDED = "2026-09-29"
KEEP_HEADERS = ("content-type", "ratelimit-", "x-ratelimit-", "retry-after")
# Content keys whose values are controlled vocabulary or structure, kept verbatim.
KEEP_CONTENT = {"venue", "venueid", "decision", "recommendation", "pdf", "supplementary_material"}
# Group content keys that carry venueids and switches (group responses keep only these).
KEEP_GROUP_CONTENT = {
    "submission_id",
    "submission_name",
    "submission_venue_id",
    "withdrawn_venue_id",
    "desk_rejected_venue_id",
    "rejected_venue_id",
    "public_submissions",
    "public_withdrawn_submissions",
    "public_desk_rejected_submissions",
    "withdrawn_submission_id",
    "desk_rejected_submission_id",
    "decision_name",
    "decision_field_name",
    "accept_decision_options",
    "subtitle",
    "title",
    "start_date",
    "website",
}
# An email address or a profile id. Not a bare "@": venue strings like `Tiny Papers @ ICLR 2023` stay real.
PERSON = re.compile(r"[^\s@]+@[^\s@]+|^~")


class _Counter:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n


def _person(value: str, c: _Counter) -> str:
    if "@" in value:
        return f"synthetic.person{c.next()}@example.org"
    return f"~Synthetic_Person{c.next()}"


def _synthetic(key: str, value: Any, c: _Counter) -> Any:
    """A value of the same type as `value`, with no real text."""
    if isinstance(value, str):
        if value == "":
            return ""
        if key == "authorids" or PERSON.search(value):
            return _person(value, c)
        if key == "authors":
            return f"Synthetic Author {c.next()}"
        if key == "paperhash":
            return f"synthetic|synthetic_title_{c.next()}"
        return f"Synthetic {key.lower().replace('_', ' ').strip()} text {c.next()}."
    if isinstance(value, list):
        return [_synthetic(key, v, c) for v in value]
    if isinstance(value, dict):
        return {k: _synthetic(k, v, c) for k, v in value.items()}
    return value


def _scrub_content(content: dict[str, Any], c: _Counter) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in content.items():
        wrapped = isinstance(raw, dict) and "value" in raw
        value = raw["value"] if wrapped else raw
        if key in KEEP_CONTENT and not (isinstance(value, str) and PERSON.search(value)):
            new = value
        else:
            new = _synthetic(key, value, c)
        out[key] = {**raw, "value": new} if wrapped else new
    return out


def _scrub_strings(value: Any, c: _Counter) -> Any:
    if isinstance(value, str):
        return _person(value, c) if PERSON.search(value) else value
    if isinstance(value, list):
        return [_scrub_strings(v, c) for v in value]
    if isinstance(value, Mapping):
        return {k: _scrub_strings(v, c) for k, v in value.items()}
    return value


def scrub_note(note: dict[str, Any], c: _Counter) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in note.items():
        if key == "content" and isinstance(value, dict):
            out[key] = _scrub_content(value, c)
        elif key == "details" and isinstance(value, dict):
            out[key] = {
                k: (
                    [scrub_note(r, c) for r in v]
                    if k in ("directReplies", "replies")
                    else _scrub_strings(v, c)
                )
                for k, v in value.items()
            }
        elif key == "tauthor":
            out[key] = _person(str(value) + "@", c)
        else:
            out[key] = _scrub_strings(value, c)
    return out


def _decisive(note: dict[str, Any]) -> bool:
    content = note.get("content") or {}
    return "decision" in content or ("recommendation" in content and "Meta" in str(note.get("invitation")))


def _trim_forum(notes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """A v1 forum listing: keep the submission, every decision-bearing note and one other reply."""
    keep: list[dict[str, Any]] = []
    other = False
    for n in notes:
        if n.get("id") == n.get("forum") or _decisive(n):
            keep.append(n)
        elif not other:
            keep.append(n)
            other = True
    note = (
        f"forum listing trimmed from {len(notes)} to {len(keep)} notes (order kept)"
        if len(keep) < len(notes)
        else None
    )
    return keep, note


def scrub_json(url: str, body: Any) -> tuple[Any, str | None]:
    c = _Counter()
    trimmed = None
    if isinstance(body, dict) and "notes" in body:
        notes = body["notes"]
        if "forum=" in url:
            notes, trimmed = _trim_forum(notes)
        body = {**body, "notes": [scrub_note(n, c) for n in notes]}
    elif isinstance(body, dict) and "groups" in body:
        groups = []
        for g in body["groups"]:
            content = {k: v for k, v in (g.get("content") or {}).items() if k in KEEP_GROUP_CONTENT}
            groups.append(
                {
                    k: (content if k == "content" else _scrub_strings(v, c))
                    for k, v in g.items()
                    if k not in ("web", "members", "invitations", "details")
                }
            )
        body = {**body, "groups": groups}
        trimmed = (
            "group trimmed to its venueid, visibility and decision keys (web, members, invitations dropped)"
        )
    return body, trimmed


# --- HTML -------------------------------------------------------------------------------------------------


def _sub_text(pattern: str, page: str, label: str, c: _Counter) -> str:
    """Replace group 2 of every match (group 1 and 3 are kept) with synthetic text."""

    def replacement(m: re.Match[str]) -> str:
        synthetic = f"Synthetic {label} {c.next()}"
        # Keep the publisher's double-escaping shape while replacing the person's real nickname. The
        # HTML extractor's second unescape is otherwise impossible to exercise from a scrubbed fixture.
        if "&amp;quot;" in m.group(2):
            synthetic += " &amp;quot;alias&amp;quot;"
        elif "&amp;amp;" in m.group(2):
            synthetic += " &amp;amp; synthetic"
        return f"{m.group(1)}{synthetic}{m.group(3)}"

    return re.sub(pattern, replacement, page, flags=re.S)


def _keep_blocks(
    page: str, start: str, block: re.Pattern[str], per_kind: int, kind: re.Pattern[str]
) -> tuple[str, str]:
    """Keep the page head and tail, and at most `per_kind` blocks of each kind in between."""
    first = page.find(start)
    blocks = list(block.finditer(page, first))
    if first < 0 or not blocks:
        return page, ""
    seen: dict[str, int] = {}
    kept = []
    for m in blocks:
        found = kind.search(m.group(0))
        k = found.group(0) if found else ""
        if seen.get(k, 0) < per_kind:
            seen[k] = seen.get(k, 0) + 1
            kept.append(m.group(0))
    head, tail = page[: blocks[0].start()], page[blocks[-1].end() :]
    note = f"{len(kept)} of {len(blocks)} entries kept ({per_kind} per kind)"
    return head + "\n".join(kept) + tail, note


class _PaperSanitizer(HTMLParser):
    """Structurally rewrite every sensitive paper-page field without executing page content."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"})

    def __init__(self, c: _Counter) -> None:
        super().__init__(convert_charrefs=False)
        self.c = c
        self.out: list[str] = []
        self.real: list[tuple[str, str]] = []
        self.suppress: tuple[str, str | None] | None = None
        self.suppressed_tags: list[str] = []

    @staticmethod
    def _values(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        return {key.casefold(): value for key, value in attrs}

    @staticmethod
    def _tag(tag: str, attrs: list[tuple[str, str | None]], *, closed: bool = False) -> str:
        rendered = "".join(
            f' {key}="{html.escape(value, quote=True)}"' if value is not None else f" {key}"
            for key, value in attrs
        )
        return f"<{tag}{rendered}{' /' if closed else ''}>"

    def _sensitive(self, tag: str, values: dict[str, str | None]) -> tuple[str, str | None] | None:
        classes = set((values.get("class") or "").split())
        if tag == "code" and "citecode" in classes:
            return "citation", None
        if tag == "div" and (values.get("id") == "abstract" or "abstract" in classes):
            return "abstract", None
        if tag == "p" and "paper-abstract" in classes:
            return "abstract", "section"  # NeurIPS pages omit this paragraph's `</p>`
        if (tag == "p" and "paper-authors" in classes) or (tag == "span" and "authors" in classes):
            return "authors", None
        return None

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool = False) -> None:
        tag = tag.casefold()
        if self.suppress is not None:
            if not closed and tag not in self.VOID:
                self.suppressed_tags.append(tag)
            return
        values = self._values(attrs)
        if tag == "meta":
            key = (values.get("name") or values.get("property") or "").casefold()
            content = values.get("content")
            if content is not None and key in ("citation_title", "citation_author"):
                label = "title" if key == "citation_title" else "Author"
                self.real.append((content, label))
                if label == "Author":
                    parts = (
                        [p.strip() for p in content.split(",")]
                        if "," in content
                        else content.rsplit(" ", 1)[::-1]
                    )
                    self.real.extend((p, label) for p in parts if len(p) > 2)
                attrs = [(name, f"Synthetic {label} {self.c.next()}" if name.casefold() == "content" else value)
                         for name, value in attrs]  # fmt: skip
            elif content is not None and key in ("description", "og:description", "twitter:description"):
                attrs = [(name, f"Synthetic description {self.c.next()}" if name.casefold() == "content" else value)
                         for name, value in attrs]  # fmt: skip
        self.out.append(self._tag(tag, attrs, closed=closed))
        if not closed and tag not in self.VOID and (sensitive := self._sensitive(tag, values)) is not None:
            label, fallback = sensitive
            suffix = " &amp;quot;alias&amp;quot;" if label == "citation" else ""
            self.out.append(f"Synthetic {label} {self.c.next()}{suffix}")
            self.suppress = (tag, fallback)
            self.suppressed_tags = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self.suppress is not None:
            target, fallback = self.suppress
            if tag in self.suppressed_tags:
                index = len(self.suppressed_tags) - 1 - self.suppressed_tags[::-1].index(tag)
                del self.suppressed_tags[index:]
                return
            if tag not in (target, fallback):
                return
            self.suppress = None
            self.suppressed_tags = []
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.suppress is None:
            self.out.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.suppress is None:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.suppress is None:
            self.out.append(f"&#{name};")

    def handle_decl(self, decl: str) -> None:
        if self.suppress is None:
            self.out.append(f"<!{decl}>")


def _paper_page(page: str, c: _Counter) -> str:
    """A paper page (NeurIPS abstract page, PMLR paper page): every copy of its free text goes.

    The page repeats the title, authors and abstract in meta tags, headings and citation boxes, so the
    real strings are collected first and then replaced wherever they occur; the citation boxes and the
    abstract block are replaced whole.
    """
    parser = _PaperSanitizer(c)
    parser.feed(page)
    parser.close()
    page = "".join(parser.out)
    for text, label in sorted(parser.real, key=lambda t: -len(t[0])):
        synthetic = f"Synthetic {label} {c.next()}"
        for encoded in (html.escape(text, quote=True), html.escape(text, quote=False), text):
            if encoded:
                page = page.replace(encoded, synthetic)
    return page


_ICLR_PAPER = re.compile(
    r'(<a\b[^>]*\bhref="(?:https?://)?(?:www\.)?(?:arxiv\.org/abs/|(?:beta\.)?openreview\.net/forum\?id=)[^"]+"[^>]*>)'
    r"(.*?)"
    r"(</a>)",
    re.I | re.S,
)
_ICLR_SECTION = re.compile(r'(<h3\b[^>]*\bid="([^"]+)"[^>]*>.*?</h3>)(.*?)(?=<h3\b|$)', re.I | re.S)


def _iclr_entry(paper: re.Match[str], c: _Counter, *, list_item: bool) -> str:
    title = f"{paper.group(1)}Synthetic title {c.next()}{paper.group(3)}"
    authors = f"Synthetic Author {c.next()}; Synthetic Author {c.next()}"
    if list_item:
        return f'<li class="level1"><div class="li"> {title}<br/>\n{authors}</div></li>'
    return (
        '<p dir="ltr"><span style="font-weight:bold">'
        f'{title}</span></p><p dir="ltr"><span style="font-style:italic">'
        f"{authors}</span></p>"
    )


def _iclr_index(page: str, c: _Counter) -> tuple[str, str]:
    """A minimal, still-structural excerpt of an accepted-paper archive page.

    The 2014 Google Sites page and the 2015/2016 DokuWiki pages wrap entries differently. The adapter's
    contract is their shared paper link plus adjacent author text, so retain those two real shapes and the
    stable target URLs while replacing every title and person.
    """
    papers = list(_ICLR_PAPER.finditer(page))
    google_sites = next(
        (
            section
            for section in _ICLR_SECTION.finditer(page)
            if section.group(2) == "sites-page-title-header"
        ),
        None,
    )
    sections = []
    kept = 0
    if google_sites is not None:
        selected = list(_ICLR_PAPER.finditer(google_sites.group(3)))[:2]
        kept = len(selected)
        entries = "\n".join(_iclr_entry(paper, c, list_item=False) for paper in selected)
        body = f"{google_sites.group(1)}{entries}"
    else:
        for section in _ICLR_SECTION.finditer(page):
            section_papers = list(_ICLR_PAPER.finditer(section.group(3)))[:2]
            if not section_papers:
                continue
            kept += len(section_papers)
            entries = "\n".join(_iclr_entry(paper, c, list_item=True) for paper in section_papers)
            sections.append(f'{section.group(1)}<ol data-fixture-section="{section.group(2)}">{entries}</ol>')
    if google_sites is None and sections:
        body = "\n".join(sections)
    elif google_sites is None:
        selected = papers[:3]
        kept = len(selected)
        body = "\n".join(_iclr_entry(paper, c, list_item=False) for paper in selected)
    heading = "Accepted Papers (Conference Track)"
    excerpt = f"<!doctype html><html><head><title>{heading}</title></head><body><h1>{heading}</h1>{body}</body></html>\n"
    return (
        excerpt,
        f"{kept} of {len(papers)} paper entries kept (2 per section); surrounding archive page removed",
    )


def scrub_html(url: str, page: str) -> tuple[str, str | None]:
    c = _Counter()
    note = None
    if "api2.openreview.net" in url or "api.openreview.net" in url:
        title = re.search(r"<title>.*?</title>", page, re.S)
        return (
            f"<!DOCTYPE html>\n<html><head>{title.group(0) if title else ''}</head><body>…</body></html>\n",
            ("challenge page reduced to its <title>; the real page loads a Turnstile widget"),
        )
    if "iclr.cc/archive/" in url:
        page, note = _iclr_index(page, c)
    elif "proceedings.neurips.cc" in url or "datasets-benchmarks-proceedings" in url:
        if "-Abstract" in url:
            page = _paper_page(page, c)
        else:
            li = re.compile(r"<li class=\"[^\"]*\"[^>]*>.*?</li>", re.S)
            page, note = _keep_blocks(page, 'paper-list">', li, 2, re.compile(r'class="[^"]*"'))
            page = _sub_text(r'(<a title="paper title" href="[^"]*">)(.*?)(</a>)', page, "title", c)
            page = _sub_text(r'(<span class="paper-authors">)(.*?)(</span>)', page, "authors", c)
            page = _sub_text(r"(</a> <i>)(.*?)(</i>)", page, "authors", c)
    elif "proceedings.mlr.press" in url:
        if url.rstrip("/").endswith("proceedings.mlr.press"):
            li = re.compile(r'<li><a href="v\d+"><b>Volume \d+</b></a>.*?</li>', re.S)
            wanted = re.compile(
                r'"v(28|32|37|48|70|80|97|119|123|133|139|162|176|202|220|235|251|267|292|318)"'
            )
            first = page.find('<li><a href="v')
            blocks = list(li.finditer(page, max(first, 0)))
            kept = [m.group(0) for m in blocks if wanted.search(m.group(0))]
            if blocks:
                page = page[: blocks[0].start()] + "\n".join(kept) + page[blocks[-1].end() :]
                note = f"volume list trimmed to {len(kept)} of {len(blocks)} volumes (ICML, NeurIPS competition, examples)"
        elif url.endswith(".html"):
            page = _paper_page(page, c)
        else:
            div = re.compile(r'<div class="paper">.*?\n</div>', re.S)
            page, note = _keep_blocks(page, '<div class="paper">', div, 3, re.compile(r"^$"))
            page = _sub_text(r'(<p class="title">)(.*?)(</p>)', page, "title", c)
            page = _sub_text(r'(<span class="authors">)(.*?)(</span>)', page, "authors", c)
            page = _sub_text(r"(<p><strong>Editors: )(.*?)(</strong></p>)", page, "editors", c)
    return page, note


def fixture(capture: dict[str, Any]) -> dict[str, Any]:
    url = capture["url"]
    headers = {k.lower(): v for k, v in capture["headers"].items() if k.lower().startswith(KEEP_HEADERS)}
    response: dict[str, Any] = {"status": capture["status"], "headers": headers}
    text = capture["body"]
    trimmed = None
    if "json" in headers.get("content-type", ""):
        body, trimmed = scrub_json(url, json.loads(text))
        response["json"] = body
    else:
        page, trimmed = scrub_html(url, text)
        response["text"] = page
    recorded: dict[str, Any] = {
        "date": RECORDED,
        "run": "authenticated OpenReview fixture run",
        "scrubbed": "decision-004: free text synthetic; ids, venueids, venue strings, invitations, dates, headers real",
    }
    if trimmed:
        recorded["trimmed"] = trimmed
    return {
        "_recorded": recorded,
        "request": {"method": "GET", "url": url, "authenticated": bool(capture.get("auth"))},
        "response": response,
    }


def main(captures: Path) -> None:
    for src in sorted(captures.rglob("*.json")):
        rel = src.relative_to(captures)
        out = HERE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        data = fixture(json.loads(src.read_text(encoding="utf-8")))
        out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(rel, len(out.read_bytes()))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
