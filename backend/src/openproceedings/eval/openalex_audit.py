"""The OpenAlex fidelity audit, `op eval openalex` (spec 07; decision-049, milestone C Task 13).

OpenAlex fills an abstract only where every official source gave none, so its text can't be checked against an
official one on the records it fills. This audit measures it where both exist:
- **The DOI route.** Every record of FAccT 2022/2025/2026 and AIES 2024/2025 with an official abstract and a DOI,
  plus a seeded sample of AAAI 2010+'s (`sample`), is looked up by DOI as `op ingest openalex` looks them up
  (`openalex.doi_lookups`, batches of `openalex.BATCH`), and OpenAlex's abstract, rebuilt and cleaned by the fill's
  own rules (`openalex.abstract_of`), is compared with the official one (`compare`): per venue-year, how many are
  `exact`, `near_exact`, `truncated`, `similar` or `differs`, and how many have no work (`no_openalex`), a work with
  no abstract (`no_abstract`), a rebuild refusal (`refused`) or several works with differing texts (`duplicate`).
- **The title route** (`title_check`). AAAI 1980-2008 records carry no DOI and are matched by exact title key in
  the listings `openalex_sources.toml` names. The fill is replayed over the cached listings, a seeded sample of its
  title-route attaches is drawn, and each is checked against OpenAlex's authors for the work (one request per 50
  works, `authors_url`): an attach whose authors share no surname with the record's looks wrong.

Everything is fetched through the one OpenAlex fetcher and cache (`crawl.openalex_fetcher`: api.openalex.org only,
one request a second, keyless, no contact address), so `--offline` replays the cache and renders the same report
byte for byte. The audit writes no extract and never feeds a snapshot. The report quotes no abstract text: ids only
(OpenAlex ships no plaintext abstracts for legal reasons; the official ones are the proceedings').
"""

from __future__ import annotations

import json
import random
import shlex
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Literal, get_args

from openproceedings.ingest import openalex_table
from openproceedings.ingest.dedup import title_key
from openproceedings.ingest.record import OPENALEX_VENUES, PaperRecord
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.common import CrawlError

if TYPE_CHECKING:
    from openproceedings.ingest.openalex_table import Table
    from openproceedings.ingest.sources.http import Fetcher

Kind = Literal["exact", "near_exact", "truncated", "similar", "differs"]
KINDS: tuple[Kind, ...] = get_args(Kind)
# every outcome of one sampled record, in the report's column order
OUTCOMES: tuple[str, ...] = (*KINDS, "no_abstract", "no_openalex", "refused", "duplicate")
SIMILAR = 0.9  # token SequenceMatcher ratio at or above which a text is `similar`
NEAR_SPELLING = 0.75  # character ratio at or above which two surnames look like variants of one
AUDITED: Mapping[str, tuple[int, ...]] = {"FAccT": (2022, 2025, 2026), "AIES": (2024, 2025)}
AAAI_FROM = 2010  # AAAI's OJS years with official abstracts and DOIs
AAAI_SAMPLE = 1000
SEED = 49
TITLE_SAMPLE = 50
DIFFERS_SHOWN = 10  # `differs` examples the report names, by id
MAX_AUTHORS = 1000  # authorships read per work (a hostile answer is never read whole)
AUTHORS_SELECT = "id,authorships,biblio"
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})

type VenueYear = tuple[str, int]


def compare(official: str, openalex: str) -> Kind:
    """How OpenAlex's text of an abstract compares with the official one: `exact` (equal once whitespace is
    collapsed), `near_exact` (the same search tokens: `dedup.title_key`, the token contract), `truncated`
    (OpenAlex's tokens a strict prefix of the official ones), `similar` (token ratio ≥ 0.9), else `differs`."""
    if " ".join(official.split()) == " ".join(openalex.split()):
        return "exact"
    a, b = title_key(official).split(), title_key(openalex).split()
    if a == b:
        return "near_exact"
    if b and len(b) < len(a) and a[: len(b)] == b:
        return "truncated"
    return "similar" if SequenceMatcher(None, a, b, autojunk=False).ratio() >= SIMILAR else "differs"


def _audited(r: PaperRecord) -> bool:
    return r.abstract_kind == "official" and openalex.bare_doi(r.urls.doi) is not None


def sample(
    records: Iterable[PaperRecord], *, aaai_sample: int = AAAI_SAMPLE, seed: int = SEED
) -> list[PaperRecord]:
    """The records the DOI route audits, in id order: every record of FAccT 2022/2025/2026 and AIES 2024/2025 with
    an official abstract and a DOI, plus `random.Random(seed).sample` of `aaai_sample` such AAAI 2010+ records,
    taken in id order before sampling (all of them when there are fewer)."""
    rs = sorted((r for r in records if _audited(r)), key=lambda r: r.id)
    named = [r for r in rs if r.year in AUDITED.get(r.venue, ())]
    pool = [r for r in rs if r.venue == "AAAI" and r.year >= AAAI_FROM]
    picked = random.Random(seed).sample(pool, min(aaai_sample, len(pool)))
    return sorted([*named, *picked], key=lambda r: r.id)


def aaai_pool(records: Iterable[PaperRecord]) -> int:
    """How many AAAI 2010+ records the AAAI sample is drawn from."""
    return sum(1 for r in records if r.venue == "AAAI" and r.year >= AAAI_FROM and _audited(r))


# --- the title route's check --------------------------------------------------------------------------------

Verdict = Literal["agree", "wrong", "unverifiable"]


@dataclass(frozen=True, slots=True)
class WorkAuthors:
    names: tuple[str, ...]  # display names in OpenAlex's author order
    pages: bool  # whether OpenAlex holds a first page for the work (`biblio.first_page`)


@dataclass(frozen=True, slots=True)
class TitleAttach:
    record_id: str
    work_id: str
    year_ok: bool  # OpenAlex's publication_year is the record's
    ours_first: str | None  # the record's first-author surname (`surname`)
    theirs_first: str | None  # OpenAlex's first-author surname
    shared: int  # surnames the two author lists share
    theirs: int  # authors OpenAlex lists for the work
    pages: bool
    verdict: Verdict

    @property
    def first_match(self) -> bool:
        return self.ours_first is not None and self.ours_first == self.theirs_first


@dataclass(frozen=True, slots=True)
class TitleCheck:
    attached: int  # title-route attaches the fill makes from the cached listings
    candidates: int  # DOI-less AAAI 1980-2008 records with no abstract
    refused: Mapping[str, int]  # the fill's refusals over those listings
    sampled: tuple[TitleAttach, ...]


def surname(name: str) -> str | None:
    """A person's surname as a comparison key: the part before a comma (`Smith, Ann`), else the last word that is
    not a dblp homonym number (`Ann Smith 0001`) or a suffix (`Jr.`), with marks dropped (NFKD), case-folded,
    letters and digits only; None when nothing is left."""
    if "," in name:
        part = name.split(",", 1)[0]
    else:
        words = [w for w in name.split() if not w.isdigit() and w.casefold().strip(".") not in _SUFFIXES]
        part = words[-1] if words else ""
    folded = "".join(c for c in unicodedata.normalize("NFKD", part) if not unicodedata.combining(c))
    key = "".join(c for c in folded.casefold() if c.isalnum())
    return key or None


def authors_url(work_ids: Sequence[str]) -> str:
    """One request for up to `openalex.BATCH` works' authors and page fields, by OpenAlex work id."""
    if not 0 < len(work_ids) <= openalex.BATCH:
        raise ValueError(f"an authors batch holds 1 to {openalex.BATCH} works")
    return (f"https://{openalex.HOST}/works?filter=ids.openalex:{'|'.join(sorted(work_ids))}"
            f"&per-page={openalex.BATCH}&select={AUTHORS_SELECT}")  # fmt: skip


def _unreadable(why: str) -> CrawlError:
    return CrawlError(f"an OpenAlex authors answer {why}", reason="openalex_unreadable")  # never the body


def parse_authors(text: str) -> dict[str, WorkAuthors]:
    """An `authors_url` answer: each work's author names and whether it has a first page. An answer that is not a
    JSON object with `meta.count` and a `results` list of works with `W…` ids stops (`openalex_unreadable`)."""
    if len(text) > openalex.MAX_ANSWER:
        raise _unreadable("is too long")
    try:
        body = json.loads(text)
    except (ValueError, RecursionError) as e:
        raise _unreadable("is not JSON") from e
    meta = body.get("meta") if isinstance(body, dict) else None
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(meta, dict) or type(meta.get("count")) is not int or not isinstance(results, list):
        raise _unreadable("is not a work list (meta.count and results)")
    if len(results) > openalex.PER_PAGE:
        raise _unreadable("holds too many works")
    out: dict[str, WorkAuthors] = {}
    for item in results:
        wid = item.get("id") if isinstance(item, dict) else None
        m = openalex._ID.fullmatch(wid) if isinstance(wid, str) else None
        if m is None:
            raise _unreadable("has a work with no OpenAlex work id")
        assert isinstance(item, dict)
        ships = item.get("authorships")
        names: list[str] = []
        for a in (ships if isinstance(ships, list) else [])[:MAX_AUTHORS]:
            author = a.get("author") if isinstance(a, dict) else None
            name = author.get("display_name") if isinstance(author, dict) else None
            if not isinstance(name, str) and isinstance(a, dict):
                name = a.get("raw_author_name")
            if isinstance(name, str) and name.strip():
                names.append(name)
        biblio = item.get("biblio")
        first_page = biblio.get("first_page") if isinstance(biblio, dict) else None
        out[m.group(1)] = WorkAuthors(tuple(names), isinstance(first_page, str) and bool(first_page.strip()))
    return out


def _authors(work_ids: Sequence[str], fetcher: Fetcher) -> dict[str, WorkAuthors]:
    ids = sorted(work_ids)
    out: dict[str, WorkAuthors] = {}
    for i in range(0, len(ids), openalex.BATCH):
        page = fetcher.get(authors_url(ids[i : i + openalex.BATCH]))
        if not page.ok:
            raise CrawlError(f"an OpenAlex authors batch answered HTTP {page.status}", reason="no_listing")
        out.update(parse_authors(page.text))
    return out


def _judge(r: PaperRecord, work: openalex.Work, theirs: WorkAuthors | None) -> TitleAttach:
    ours = [s for a in r.authors if (s := surname(a))]
    names = theirs.names if theirs else ()
    them = [s for a in names if (s := surname(a))]
    year_ok = work.year == r.year
    shared = len(set(ours) & set(them))
    first = ours[0] if ours else None
    verdict: Verdict = (
        "wrong" if not year_ok
        else "unverifiable" if not ours or not them
        else "agree" if shared or first == them[0]
        else "wrong"
    )  # fmt: skip
    return TitleAttach(record_id=r.id, work_id=work.id, year_ok=year_ok, ours_first=first,
                       theirs_first=them[0] if them else None, shared=shared, theirs=len(names),
                       pages=bool(theirs and theirs.pages), verdict=verdict)  # fmt: skip


def _work_id(r: PaperRecord) -> str:
    """The OpenAlex work a filled record's abstract came from (its claim's url, `openalex.work_url`)."""
    url = next(c.url for c in r.claims("abstract") if c.source == openalex.SOURCE)
    assert url is not None
    return url.rsplit("/", 1)[-1]


def title_check(
    records: Iterable[PaperRecord], fetcher: Fetcher, *, seed: int = SEED, size: int = TITLE_SAMPLE,
    table: Table | None = None,
) -> TitleCheck | None:  # fmt: skip
    """The title route's attaches, checked: the fill replayed over the table's listings (each read whole from the
    fetcher's cache, `openalex.listing_lookup`), `random.Random(seed).sample` of `size` of its title-route attaches
    (in id order before sampling), and each judged against OpenAlex's authors for the work (`_judge`): `agree` when
    the years match and the author lists share a surname (or the first authors' surnames match), `unverifiable`
    when either list is empty, else `wrong`. None when the table has no listing rows."""
    table = table or openalex_table.TABLE
    if not table.listings:
        return None
    lookups = tuple(openalex.listing_lookup(row, fetcher, refresh=False) for row in table.listings.values())
    pool = [r for r in records if r.venue in OPENALEX_VENUES]
    filled, report = openalex.fill(pool, openalex.Extract("0" * 64, lookups), table)
    listed = {(r.venue, r.year) for r in pool} & set(table.listings)
    attaches = sorted(
        (r for r in filled if (r.venue, r.year) in listed and r.abstract_kind == "openalex"),
        key=lambda r: r.id,
    )  # a listed venue-year's records are AAAI 1980-2008's, all DOI-less: every OpenAlex abstract is the title route's
    picked = sorted(random.Random(seed).sample(attaches, min(size, len(attaches))), key=lambda r: r.id)
    works = {w.id: w for lk in lookups for w in lk.works}
    chosen = {r.id: works[_work_id(r)] for r in picked}
    theirs = _authors([w.id for w in chosen.values()], fetcher) if chosen else {}
    candidates = sum(1 for r in pool if (r.venue, r.year) in listed and r.abstract is None)
    return TitleCheck(attached=len(attaches), candidates=candidates, refused=dict(sorted(report.refused.items())),
                      sampled=tuple(_judge(r, chosen[r.id], theirs.get(chosen[r.id].id)) for r in picked))  # fmt: skip


# --- the DOI route ------------------------------------------------------------------------------------------


@dataclass
class AuditResult:
    rows: dict[VenueYear, dict[str, int]]  # venue-year -> outcome -> count (an outcome with none left out)
    refusals: Counter[str] = field(default_factory=Counter)  # why each `refused` was refused
    differs: list[str] = field(default_factory=list)  # the ids classed `differs`, in id order
    foreign: int = 0  # works a batch returned for a DOI it didn't ask for (never compared)
    title: TitleCheck | None = None


def audit(records: Iterable[PaperRecord], fetcher: Fetcher) -> AuditResult:
    """The DOI route over `records` (`sample`'s): per venue-year, its DOIs sorted and batched as the crawl batches
    them, each record's works compared with its official abstract (`compare`) or counted `no_openalex`,
    `no_abstract`, `refused` (with why) or `duplicate` (several works with differing texts; several with one text
    count once)."""
    groups: dict[VenueYear, list[PaperRecord]] = {}
    for r in sorted(records, key=lambda r: r.id):
        groups.setdefault((r.venue, r.year), []).append(r)
    result = AuditResult(rows={})
    for key in sorted(groups):
        row: Counter[str] = Counter()
        rs = groups[key]
        dois = sorted({d for r in rs if (d := openalex.bare_doi(r.urls.doi)) and openalex.queryable(d)})
        by_doi: dict[str, list[openalex.Work]] = {}
        for i in range(0, len(dois), openalex.BATCH):
            for lk in openalex.doi_lookups(dois[i : i + openalex.BATCH], fetcher, refresh=False):
                for w in lk.works:
                    if w.doi in lk.requested:
                        by_doi.setdefault(w.doi, []).append(w)
                    else:
                        result.foreign += 1
        for r in rs:
            doi = openalex.bare_doi(r.urls.doi)
            assert doi is not None and r.abstract is not None  # `sample`'s records
            if not openalex.queryable(doi):
                row["refused"] += 1
                result.refusals["doi_unqueryable"] += 1
                continue
            works = by_doi.get(doi, [])
            read = [openalex.abstract_of(w) for w in works]
            texts = {c.text for c, _ in read if c is not None and c.text is not None}
            if not works:
                row["no_openalex"] += 1
            elif len(texts) > 1:
                row["duplicate"] += 1
            elif texts:
                kind = compare(r.abstract, texts.pop())
                row[kind] += 1
                if kind == "differs":
                    result.differs.append(r.id)
            elif why := next((why for _, why in read if why), None):
                row["refused"] += 1
                result.refusals[why] += 1
            else:
                row["no_abstract"] += 1
        result.rows[key] = dict(row)
    return result


# --- the report ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Meta:
    snapshot: str  # the snapshot's directory name
    commit: str  # the code's commit
    seed: int
    aaai_sample: int
    day: date | None = None
    aaai_pool: int | None = None  # AAAI 2010+ records the sample is drawn from
    title_sample: int = TITLE_SAMPLE
    ruling: str | None = (
        None  # the decision taken on the title route's findings (`--ruling`), printed as given
    )

    @property
    def command(self) -> str:
        words = [f"uv run op eval openalex --offline --snapshot {self.snapshot} --seed {self.seed} "
                 f"--aaai-sample {self.aaai_sample}"]  # fmt: skip
        if self.title_sample != TITLE_SAMPLE:
            words.append(f"--title-sample {self.title_sample}")
        if self.day is not None:
            words.append(f"--date {self.day.isoformat()}")
        if self.ruling is not None:
            words.append(f"--ruling {shlex.quote(self.ruling)}")
        return " ".join(words)


def _rate(n: int, total: int) -> str:
    return f"{n:,} ({100 * n / total:.1f}%)" if total else f"{n:,} (–)"


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "–"


_METHOD = """\
Each sampled record has an official abstract (FAccT's from the official FAccT pages, `facct_site`; AIES's and
AAAI's from ojs.aaai.org, `ojs`) and a DOI. Each venue-year's DOIs were looked up in OpenAlex in sorted batches of
50, as `op ingest openalex` looks them up, and each work's `abstract_inverted_index` was rebuilt and cleaned by the
fill's own rules (`openalex.abstract_of`: a gap, two words at one position or any other shape is refused). OpenAlex's
text is then compared with the official one:

- `exact`: equal once whitespace is collapsed.
- `near_exact`: the same search tokens (`dedup.title_key`, the token contract): every search matches both alike.
- `truncated`: OpenAlex's tokens are a strict prefix of the official ones.
- `similar`: a token `SequenceMatcher` ratio of at least 0.9.
- `differs`: anything else.
- `no_abstract`: OpenAlex has the work but no abstract for it.
- `no_openalex`: no OpenAlex work answers for the DOI.
- `refused`: the work's abstract was refused by the rebuild or cleaning (why is listed below the table).
- `duplicate`: several works answer for the DOI with differing texts (several with one text are compared once).

Each rate is of the records compared in that row. No abstract text is quoted here; records are named by id."""


_FACCT_NOTE = """\
**A note on FAccT.** FAccT agrees far less often than AAAI or AIES, whose official abstracts come from ojs.aaai.org.
FAccT's official abstracts come from the conference's own pages (`facct_site`). Most of FAccT's `similar` and
`differs` cases are about the same length as the official text and mostly open with the same words, so they look
like another version of the same abstract rather than noise: OpenAlex likely carries ACM's published version, not
the conference site's text. A few are entirely different texts. An abstract the fill takes from OpenAlex is labelled
`abstract_kind: openalex`, never `official`, so the label already tells a reader the text is OpenAlex's, which may be
ACM's version rather than the site's."""


def _table(result: AuditResult) -> list[str]:
    head = "| Venue | Year | Compared | " + " | ".join(f"`{o}`" for o in OUTCOMES) + " |"
    lines = [head, "|" + "---|" * (3 + len(OUTCOMES))]
    totals: Counter[str] = Counter()
    for (venue, year), row in sorted(result.rows.items()):
        n = sum(row.values())
        totals.update(row)
        lines.append(
            f"| {venue} | {year} | {n:,} | " + " | ".join(_rate(row.get(o, 0), n) for o in OUTCOMES) + " |"
        )
    n = sum(totals.values())
    lines.append(f"| **All** | | **{n:,}** | " + " | ".join(_rate(totals[o], n) for o in OUTCOMES) + " |")
    return lines


def _title_section(check: TitleCheck, meta: Meta) -> list[str]:
    s = check.sampled
    agree = [a for a in s if a.verdict == "agree"]
    wrong = [a for a in s if a.verdict == "wrong"]
    unverifiable = [a for a in s if a.verdict == "unverifiable"]
    refused = ", ".join(f"`{k}` {v:,}" for k, v in check.refused.items()) or "none"
    lines = [
        "## The title route (AAAI 1980–2008): wrong-attach check",
        "",
        "AAAI 1980–2008 records have no DOI. The fill matches each one by exact title key in the year's OpenAlex "
        "listing (`openalex_sources.toml`), attaching only when one listed work and one DOI-less record share the "
        "key. The listing source also holds proceedings volumes, other venues' papers and OCR-garbled titles, so "
        "an exact title could still name another paper. The fill was replayed over the cached listings (no new "
        "listing fetch). A seeded sample of its title-route attaches was then checked against OpenAlex's authors "
        f"for each work (seed {meta.seed}; one request per 50 works, `select={AUTHORS_SELECT}`).",
        "",
        f"- DOI-less AAAI 1980–2008 records with no abstract: {check.candidates:,}; title-route attaches: "
        f"{check.attached:,}; the fill's refusals: {refused}.",
        f"- Sampled: {len(s):,} of {check.attached:,} attaches.",
        f"- Year: OpenAlex's `publication_year` equals ours in {sum(a.year_ok for a in s):,} of {len(s):,}. The "
        "listing is filtered by year and the fill requires the year, so this holds by construction.",
        f"- Authors: OpenAlex lists authors for {sum(a.theirs > 0 for a in s):,} of {len(s):,}; the first-author "
        f"surname matches ours in {sum(a.first_match for a in s):,}; the lists share at least one surname in "
        f"{sum(a.shared > 0 for a in s):,}.",
        f"- Pages: OpenAlex holds a first page for {sum(a.pages for a in s):,} of {len(s):,}. Our records carry no "
        "page field, so pages can't be compared.",
        "",
        f"**Verdict:** {len(agree):,} agree ({_pct(len(agree), len(s))}), {len(wrong):,} look wrong "
        f"({_pct(len(wrong), len(s))}), {len(unverifiable):,} can't be checked "
        f"({_pct(len(unverifiable), len(s))}; no authors on one side). `agree`: the years match and the author lists share a surname "
        "(surnames compared without marks or case, dblp's homonym numbers dropped). `wrong`: OpenAlex lists "
        "authors and none of their surnames is any of ours.",
    ]
    if wrong:
        lines += ["", "| Record | OpenAlex work | Our first-author surname | OpenAlex's first-author surname |",
                  "|---|---|---|---|"]  # fmt: skip
        lines += [f"| `{a.record_id}` | `{a.work_id}` | {a.ours_first or '–'} | {a.theirs_first or '–'} |"
                  for a in wrong]  # fmt: skip
        near = sum(_near_spelling(a) for a in wrong)
        lines += ["", f"{near:,} of the {len(wrong):,} that look wrong have a first-author surname close to ours (a "
                  f"character ratio of at least {NEAR_SPELLING}): by the look of them, spelling or OCR variants of "
                  "the same surname."]  # fmt: skip
        first_also = sum(not a.first_match for a in agree)
        lines += [
            "",
            "Rules that would exclude them:"
            if meta.ruling
            else "Rules that would exclude them (the fill rule is unchanged here; the choice is the controller's):",
            "",
            f"- **Require at least one shared author surname:** excludes all {len(wrong):,} that look wrong, and "
            f"also the {len(unverifiable):,} that can't be checked.",
            f"- **Require a matching first-author surname:** excludes all {len(wrong):,} that look wrong, and also "
            f"{first_also:,} that agree on another author and the {len(unverifiable):,} that can't be checked.",
        ]
    else:
        lines += ["", "No sampled attach looks wrong, so no rule change is indicated by this sample."]
    if meta.ruling:
        lines += ["", f"**Ruling:** {meta.ruling}"]
    return lines


def _near_spelling(a: TitleAttach) -> bool:
    """Whether the two first-author surnames look like variants of one (`NEAR_SPELLING`)."""
    if a.ours_first is None or a.theirs_first is None:
        return False
    return SequenceMatcher(None, a.ours_first, a.theirs_first, autojunk=False).ratio() >= NEAR_SPELLING


def render(result: AuditResult, meta: Meta) -> str:
    """The report: a header (snapshot, commit, seed and sample sizes, date), the reproduction command, the method,
    the per-venue-year table with each class's rate and a totals row, the refusals, a few `differs` ids, a closing
    paragraph stating the exact and near-exact rates, and the title route's check when there is one."""
    totals: Counter[str] = Counter()
    for row in result.rows.values():
        totals.update(row)
    n = sum(totals.values())
    named = "; ".join(f"{v} {', '.join(map(str, ys))}" for v, ys in AUDITED.items())
    pool = f" of {meta.aaai_pool:,}" if meta.aaai_pool is not None else ""
    lines = [
        "# OpenAlex fidelity audit" + (f" ({meta.day.isoformat()})" if meta.day else ""),
        "",
        f"- Snapshot: `{meta.snapshot}`",
        f"- Code: commit `{meta.commit}`",
        f"- Sample: seed {meta.seed}; every record with an official abstract and a DOI of {named}; and "
        f"{meta.aaai_sample:,}{pool} such AAAI {AAAI_FROM}+ records, drawn in id order. Title-route check: "
        f"{meta.title_sample:,} attaches.",
        *([f"- Date: {meta.day.isoformat()}"] if meta.day else []),
        "",
        "Reproduce (from the OpenAlex cache, no network):",
        "",
        "```",
        meta.command,
        "```",
        "",
        "## Method",
        "",
        _METHOD,
        "",
        "## The DOI route: OpenAlex's abstract against the official one",
        "",
        *_table(result),
        "",
        "Refusals: "
        + (", ".join(f"`{k}` {v:,}" for k, v in sorted(result.refusals.items())) or "none")
        + ".",
    ]
    if result.foreign:
        lines.append(
            f"Works returned for a DOI the batch didn't ask for (not compared): {result.foreign:,}; it is "
            "in no count above, so no figure changes."
        )
    if result.differs:
        shown = ", ".join(f"`{rid}`" for rid in result.differs[:DIFFERS_SHOWN])
        more = (
            f" (the first {DIFFERS_SHOWN} of {len(result.differs):,})"
            if len(result.differs) > DIFFERS_SHOWN
            else ""
        )
        lines.append(f"`differs` examples{more}: {shown}.")
    exact, near = totals["exact"], totals["near_exact"]
    lines += [
        "",
        f"Of {n:,} records compared, OpenAlex's abstract is exact for {exact:,} ({_pct(exact, n)}) and near-exact "
        f"for {near:,} ({_pct(near, n)}): together {exact + near:,} ({_pct(exact + near, n)}) would match every "
        "search exactly as the official abstract does.",
    ]
    if any(venue == "FAccT" for venue, _ in result.rows):
        lines += ["", _FACCT_NOTE]
    if result.title is not None:
        lines += ["", *_title_section(result.title, meta)]
    return "\n".join(lines) + "\n"
