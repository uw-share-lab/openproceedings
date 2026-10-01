"""`op takedown check` (TASK-136 AC8, decision-022; spec 08 §Deploy): does a running instance serve any listed
abstract, from any index version it loads?

It asks the API itself, over HTTP, as a client would (so it checks what is served, whatever the code path), for
each id on the takedown list:

- `GET /papers/{id}` (the served index): no `abstract`, no abstract claim, `abstract_withheld` true; and with a
  query that finds the paper by its title, no abstract highlight spans;
- `GET /search` with that query: the paper's hit has no abstract, no abstract spans, no `abstract_source`, and
  `abstract_withheld` true;
- `GET /export` in every format, for every index version `GET /meta` lists (`index_version=`), with the query
  that selects a venue-year (filters only, every track and status): once per version, format and venue-year
  that holds a listed id (so a list of many ids costs cells × versions × 4 exports, versions outermost, so each
  pinned index is opened once). Wherever a listed paper is in the file it has no abstract and says a takedown
  withheld it (RIS `N1` / BibTeX `abstract_withheld` = the takedown sentence, CSV and JSONL `abstract_withheld`
  true with reason `takedown`); a paper found in one format of a version must be in all four (a format the
  check can no longer read is a problem, never a silent pass).

- `GET /export` (JSONL) of each listed paper's title in every venue and year, for every index version
  (TASK-067): a record under another id with the same title and authors that carries an abstract is the paper
  served under an id it had before (a rekey) or as a duplicate a later build merged; the API withholds those
  too (`takedowns.same_paper`), so one that isn't is a problem (list that id too). The title and authors come
  from `/papers` on the served index, or from a version's JSONL export of the id.

Only the served index answers `/papers` and `/search`, so the span and marker checks there cover it alone; the
route tests (`tests/contract/test_takedowns.py`) cover highlights on every path, since a title query rarely
lights abstract words. Run it as the operator's account (it reads the log), against the API itself (e.g.
`http://127.0.0.1:8000` on the host), not through the proxy: it follows no redirect, and it waits out a 429's
`Retry-After` (every export costs the rate limit's export weight).

A listed id that no loaded index version holds is a problem too (a typo, or a paper whose id changed and whose
older versions are retired: `op snapshot build` reports such ids as `takedowns_unmatched`). Every problem names the id, the index version and the response;
never an abstract's text. The HTTP layer is a `Fetch` (a path and parameters in, the status and body out): the
CLI's is `urllib` against `--api`, a test's is the in-process app.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from openproceedings.export import FORMATS, TAKEDOWN
from openproceedings.query.normalize import normalize
from openproceedings.takedowns import Withheld, same_paper
from openproceedings.vocab import STATUSES, TRACKS, VENUES

API = "/api/v1"
EVERY = f"track:({' OR '.join(TRACKS)}) status:({' OR '.join(STATUSES)})"
MAX_TITLE_WORDS = 12  # words of the title a search for the paper names (enough to find it, short of any cap)

type Fetch = Callable[[str, Mapping[str, str]], tuple[int, str]]


@dataclass(frozen=True, slots=True)
class Report:
    """What `check` found: each problem (empty when nothing listed is served), and how much it checked."""

    problems: tuple[str, ...]
    ids: int
    index_versions: tuple[str, ...]
    exports: int  # export bodies read


def cell_query(rid: str) -> str:
    """Filters only: the paper's venue and year (from its id), every track and status, so an export of it holds
    the paper on any index version that has it."""
    _op, venue, year, _native = rid.split(":", 3)
    return f"venue:{VENUES[venue]} year:{year} {EVERY}"


def title_query(title: str, rid: str | None) -> str | None:
    """A query that finds the paper by (the start of) its title within its venue-year (`rid`'s), or in every
    venue and year (`rid` None); None when the title has no word that reads back as itself."""
    words: list[str] = []
    for w in normalize(title):  # the leading run of words that read back as themselves: a phrase has no gaps
        if not (w.isascii() and w.isalnum()) or len(words) == MAX_TITLE_WORDS:
            break
        words.append(w)
    if not words or normalize(" ".join(words)) != words:
        return None
    return f'title:"{" ".join(words)}" {EVERY if rid is None else cell_query(rid)}'


def check(fetch: Fetch, listed: Withheld, merges: Iterable[tuple[str, str]] = ()) -> Report:
    """Every problem with how the instance behind `fetch` serves the ids `listed` (module docstring); `merges`
    are every snapshot's (survivor, merged) pairs (`snapshot.merges_on_disk`), for the over-withholding check."""
    problems: list[str] = []
    status, body = fetch(f"{API}/meta", {})
    if status != 200:
        return Report(
            (f"GET /meta answered {status}: is the API up and serving an index?",), len(listed), (), 0
        )
    versions = tuple(json.loads(body)["index_versions"])
    # each listed paper's title and authors, from the served index or any version's export of it
    papers = {rid: paper for rid in sorted(listed) if (paper := _served(fetch, rid, problems)) is not None}
    found = set(papers)
    cells: dict[str, list[str]] = {}
    for rid in sorted(listed):
        cells.setdefault(cell_query(rid), []).append(rid)
    exports = 0
    for version in versions:  # outermost: each pinned index is opened once, not once per id
        for query, ids in cells.items():
            held: dict[str, set[str]] = {}  # id → the formats of this version's export that hold it
            answered: set[str] = set()  # the formats that answered 200 (a failed one is reported once, above)
            for fmt in FORMATS:
                status, text = fetch(f"{API}/export", {"format": fmt, "q": query, "index_version": version})
                exports += 1
                if status != 200:
                    problems.append(f"{', '.join(ids)}: export {fmt} of index {version} answered {status}")
                    continue
                answered.add(fmt)
                for rid in ids:
                    if fmt == "jsonl" and rid not in papers:
                        papers.update(
                            (o["id"], o) for o in map(json.loads, text.splitlines()) if o["id"] == rid
                        )
                    verdict = _in_export(fmt, text, rid)
                    if verdict is None:
                        continue
                    held.setdefault(rid, set()).add(fmt)
                    if verdict:
                        problems.append(f"{rid}: the {fmt} export of index {version} {verdict}")
            for rid, formats in sorted(held.items()):
                found.add(rid)
                problems += [
                    f"{rid}: the {fmt} export of index {version} doesn't hold it, though its "
                    f"{sorted(formats)[0]} export does (can this check still read {fmt}?)"
                    for fmt in FORMATS
                    if fmt in answered and fmt not in formats
                ]
        exports += _other_ids(fetch, version, papers, problems)
    # after the versions: a listed paper only a pinned version holds is checked too
    _merged_elsewhere(fetch, papers, tuple(merges), problems)
    problems += [
        f"{rid}: no index this instance loads holds it; check the id on the list"
        for rid in sorted(listed - found)
    ]
    return Report(tuple(problems), len(listed), versions, exports)


def _merged_elsewhere(
    fetch: Fetch,
    papers: Mapping[str, Mapping[str, Any]],
    merges: tuple[tuple[str, str], ...],
    problems: list[str],
) -> None:
    """The other direction (TASK-067 review): each id a snapshot's merges.csv links to a listed paper is withheld
    as that paper (`takedowns.same_paper`). One the served index holds under another title is a suspect merge,
    its abstract withheld though no takedown names it: a problem naming the id (never a title). One the served
    index doesn't hold (404, a merged-away id) is skipped; any other answer is a problem."""
    nodes = {rid for pair in merges for rid in pair}
    for rid, paper in sorted(papers.items()):
        title = normalize(paper["title"])
        for other in sorted(same_paper(frozenset({rid}), merges, nodes) - {rid}):
            status, body = fetch(f"{API}/papers/{urllib.parse.quote(other, safe=':')}", {})
            if status not in (200, 404):
                problems.append(f"{other}: GET /papers answered {status}")
            elif status == 200 and normalize(json.loads(body)["paper"]["title"]) != title:
                problems.append(
                    f"{other}: withheld as {rid}'s paper (a snapshot's merges.csv links them), but its title "
                    "differs; check that merge"
                )


def _other_ids(
    fetch: Fetch, version: str, papers: Mapping[str, Mapping[str, Any]], problems: list[str]
) -> int:
    """TASK-067: a version may hold a listed paper under another id (an id it had before a rekey, or a
    duplicate a later build merged), which the API withholds too (`takedowns.same_paper`). One JSONL export
    per listed paper, of its title in every venue and year: a record under another id with the same title and
    authors that carries an abstract is a problem. The number of exports read."""
    n = 0
    for rid, paper in sorted(papers.items()):
        query = title_query(paper["title"], None)
        if query is None:
            continue  # reported by `_served` for the served index; nothing to search by
        status, text = fetch(f"{API}/export", {"format": "jsonl", "q": query, "index_version": version})
        n += 1
        if status != 200:
            problems.append(f"{rid}: the jsonl export of its title on index {version} answered {status}")
            continue
        same = (normalize(paper["title"]), paper["authors"])
        problems += [
            f"{o['id']}: the jsonl export of index {version} serves the abstract of {rid}'s paper under this "
            "id; list it too"
            for o in map(json.loads, text.splitlines())
            if o["id"] != rid and o["abstract"] is not None and (normalize(o["title"]), o["authors"]) == same
        ]
    return n


def _served(fetch: Fetch, rid: str, problems: list[str]) -> dict[str, Any] | None:
    """The served index's paper page and search hit for `rid`; the paper when the served index holds it."""
    status, body = fetch(f"{API}/papers/{urllib.parse.quote(rid, safe=':')}", {})
    if status == 404:
        return None
    if status != 200:
        problems.append(f"{rid}: GET /papers answered {status}")
        return None
    page = json.loads(body)
    paper: dict[str, Any] = page["paper"]
    version = page["index_version"]
    if paper["abstract"] is not None or any(c["field"] == "abstract" for c in paper["provenance"]):
        problems.append(f"{rid}: /papers on index {version} serves its abstract or an abstract claim")
    if page.get("abstract_withheld") is not True:
        problems.append(f"{rid}: /papers on index {version} doesn't mark the abstract withheld")
    query = title_query(paper["title"], rid)
    if query is None:
        problems.append(f"{rid}: its title gives no query to find its search hit by; check /search by hand")
        return paper
    status, body = fetch(f"{API}/papers/{urllib.parse.quote(rid, safe=':')}", {"q": query})
    lit = json.loads(body) if status == 200 else None
    if lit is None or lit["matched"] is not True:
        problems.append(
            f"{rid}: /papers?q= by its title answered {status} or didn't match it; check it by hand"
        )
    elif lit["highlights"]["abstract"]:
        problems.append(f"{rid}: /papers?q= on index {version} highlights the withheld abstract")
    status, body = fetch(f"{API}/search", {"q": query, "limit": "200"})
    if status != 200:
        problems.append(f"{rid}: /search for it answered {status}")
        return paper
    hits = [h for h in json.loads(body)["hits"] if h["id"] == rid]
    if not hits:
        problems.append(f"{rid}: /search by its title didn't return it; check /search by hand")
    for hit in hits:
        if hit["abstract"] is not None or hit["highlights"]["abstract"] or hit["abstract_source"] is not None:
            problems.append(
                f"{rid}: its /search hit on index {version} serves the abstract, its spans or its source"
            )
        if hit.get("abstract_withheld") is not True:
            problems.append(f"{rid}: its /search hit on index {version} doesn't mark the abstract withheld")
    return paper


def _in_export(fmt: str, text: str, rid: str) -> str | None:
    """None when the export doesn't hold `rid`; "" when it holds it withheld and marked; else what is wrong."""
    records = list(_records(fmt, text, rid))
    if not records:
        return None
    for held, marked in records:
        if held:
            return "serves its abstract"
        if not marked:
            return "doesn't say a takedown withheld it"
    return ""


def _records(fmt: str, text: str, rid: str) -> Iterator[tuple[bool, bool]]:
    """(has an abstract, is marked withheld by a takedown) for each record of `rid` in an export body."""
    if fmt == "jsonl":
        for line in text.splitlines():
            obj: dict[str, Any] = json.loads(line)
            if obj["id"] == rid:
                reason = obj.get("abstract_withheld_reason")
                yield (
                    obj["abstract"] is not None,
                    obj.get("abstract_withheld") is True and reason == "takedown",
                )
    elif fmt == "csv":
        for row in csv.DictReader(io.StringIO(text.removeprefix("﻿"))):
            if row["id"] == rid:
                marked = row["abstract_withheld"] == "true" and row["abstract_withheld_reason"] == "takedown"
                yield bool(row["abstract"]), marked
    elif fmt == "ris":
        for entry in text.split("ER  - \n"):
            lines = entry.splitlines()
            if f"ID  - {rid}" in lines:
                yield any(x.startswith("AB  - ") for x in lines), f"N1  - {TAKEDOWN}" in lines
    else:  # bibtex: one entry per blank-line-separated block, each naming its id
        for entry in text.split("\n}\n\n"):
            if f"  openproceedings_id = {{{rid}}}" in entry.splitlines():
                lines = entry.splitlines()
                yield (
                    any(x.startswith("  abstract = ") for x in lines),
                    f"  abstract_withheld = {{{TAKEDOWN}}}," in lines,
                )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: the check asks the API itself, so a redirect means it is talking to something else
    (the refusal comes back as the 3xx, which the check reports as a problem)."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def retry_after(value: str | None) -> float:
    """A 429's `Retry-After` as seconds to wait: its whole seconds, capped at 60; 1 when absent or not seconds."""
    text = (value or "").strip()
    return float(min(int(text), 60)) if text.isascii() and text.isdecimal() else 1.0


def http(base: str, *, retries: int = 5, timeout: float = 300.0) -> Fetch:
    """A `Fetch` against the API at `base` (`http://127.0.0.1:8000`, an http(s) URL the CLI checked): no
    redirects, `timeout` seconds per socket operation, a 429 waited out (`Retry-After`) up to `retries` times."""
    root = base.rstrip("/")
    opener = urllib.request.build_opener(_NoRedirect)

    def fetch(path: str, params: Mapping[str, str]) -> tuple[int, str]:
        url = root + path + (f"?{urllib.parse.urlencode(params)}" if params else "")
        for attempt in range(retries + 1):
            try:
                with opener.open(url, timeout=timeout) as r:
                    return int(r.status), r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries:
                    time.sleep(retry_after(e.headers.get("Retry-After")))
                    continue
                return e.code, e.read().decode("utf-8", "replace")
        raise AssertionError("unreachable")

    return fetch
