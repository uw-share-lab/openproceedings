"""The ingest caps (spec 01 §Pipeline 2). On indexed text (decision-026, TASK-155): a run of combining marks keeps
at most `MAX_MARKS` marks, a title at most `MAX_TITLE` characters and an abstract at most `MAX_ABSTRACT`. On every
other stored string, a length cap each (decision-053, TASK-279; the last paragraph).

CPython's NFKC canonical reordering is superlinear in a run of marks whose combining classes alternate
(`a` + `\\u0301\\u0338` × n), so one hostile abstract would cost the index build and every search that
highlights it. A `q` is capped at 2,000 code points; stored text is capped here, once, before dedup
(`snapshot.load_sources`), on every record and every title and abstract claim alike.

A mark is a character whose NFKD form starts with a non-zero canonical combining class: every combining
character, and the five that decompose to one (U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F). A run is the marks
after one base character, or at the start of the text, counted in NFKD non-starters, the base's own included (a
precomposed `ệ` brings 2). A base is a letter or digit that is not a mark and that the tokenizer keeps
(`normalize.latex_mask`: KEEP, or SUB for a math command it spells in Unicode). Any other character neither
counts nor ends a run: a space, punctuation, an invisible character the tokenizer drops, or a letter of LaTeX
markup it drops (the `H` of `\\H{…}`). The tokenizer joins a word across the invisible characters and markup,
so a run split only by them reaches NFC whole. A run split by a space or punctuation is capped
as one, which real text never needs: its longest run is 1. So no word the tokenizer forms holds more than
`MAX_MARKS` consecutive non-starters, and its NFC is linear.

A run within the cap is left as it is. One over it has its base (NFD) and its marks (NFKD) decomposed and put
in canonical order (`_decomposed`), and keeps its first `MAX_MARKS` non-starters (`_trimmed`). Every other
character is kept as it was. So every canonical form of the same text (NFC, NFD, marks stored in another order)
trims to the same characters, and two sources whose titles shared a dedup key still share it. The length caps count
the NFKD length and cut before the last space that fits (`_cut`), so every form keeps the same words. One limit
holds: an NFKC or NFKD source, whose spacing accents (`´`) are already a space and a mark, can trim differently
from its composed form, since only a letter or digit ends a run, so 9 or more spaced-out accents with only
spaces or punctuation between them make one run there (`_decomposed` keeps canonical forms alike, NFC and NFD).
Real text never has 9 spacing accents in a row. Trimmed text is then made
one a record accepts (`_tidy`): dropping marks can leave two spaces together, or a space or `…` at an end. A
title is whitespace-collapsed, and an abstract is stripped of whitespace and `…` at both ends. A title or
abstract past its length cap is cut first (before the mark cap) and tidied the same way. The title cap (the owner, 2026-10-02) bounds
every shape of run the mark rule might miss; real titles are at most 192 characters.

Nothing is trimmed silently: each claim whose value changed says what and why in its evidence (`TRIMMED`, shown
on the paper page), and the snapshot manifest names the records (`trimmed`). Text within both caps is returned
as it is, so a corpus with none over them snapshots byte-identically.

The other stored strings have length caps too (decision-053, TASK-279), for size alone: none is tokenized, but every
one is written whole into every snapshot, export and API response. `FIELD_CAPS` gives a DOI 1,000 characters, a URL
2,048, an author name 1,000, a keyword 2,000, a `venue_id_raw` or `invitation` 500, each counted and cut as a title is
(`_cut`), and a claim's url 2,048 and its evidence 4,000. Each is at least 2.7 times the longest value in the
2026-10-16 snapshot, so they trim no record of it. An over-cap value is trimmed and flagged in its claim's evidence
(`CUT`), never refused, so every record stays whole. A cut DOI, URL or venue id is no valid link (nor a venue id an
id), so it is kept only as text for people to read: the claim keeps the cut value (the paper page shows it as text, flagged), and no `urls`
slot or `venue_id_raw` is taken from it (`cut_identifier`: `dedup.resolve`, and `cap_record` by the same rule). A
claim's own url, which is only ever a link, is dropped when it is over its cap. Dedup still reads a cut URL as naming
its paper when the cut left what it names unchanged (a long query string after a proceedings page's path), and reads
nothing from one whose cut changed it (`unread_identifier`: a forum URL's `id` cut short is a valid id of another
paper). A URL the record's own id was read from, which a cut at the cap would unname, is replaced by that id's page
address rebuilt from the id (`_own_page`), so it still names the record and only the id bounds it (TASK-281). An
`iclr_archive` target, whose id hashes the whole URL, is cut and unread like any other (`dedup` accepts that record as
standing for itself, by the crawler's own claim only).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from urllib.parse import urlparse

from openproceedings.ingest import urls
from openproceedings.ingest.record import Claim, ClaimField, PaperRecord
from openproceedings.query.normalize import KEEP, SUB, latex_mask

MAX_MARKS = 8  # combining marks (NFKD non-starters) kept per run
MAX_ABSTRACT = 20_000  # characters (code points) kept of an abstract
MAX_TITLE = 1_000  # characters (code points) kept of a title (the owner, 2026-10-02)
_LENGTH = {"title": MAX_TITLE, "abstract": MAX_ABSTRACT}
TRIMMED = "trimmed at ingest (decision-026):"  # how a claim's evidence says its value was trimmed
# the note as `_claim` writes it, ending the evidence: the whole of it, or after the source's own in parentheses
_NOTE = re.compile(rf"(?:^|\s\(){re.escape(TRIMMED)} [0-9a-z ,;]+\)?\Z")
CAPPED = ("title", "abstract")  # the indexed text fields

# The other stored strings (decision-053, TASK-279): characters counted in NFKD and cut as a title is (`_cut`). The
# longest of each in snapshot 2026-10-16-03eab0ef56c4 (173,518 records, every claim included): DOI 34, URL 154 (a
# claim's url 154), author 81, keyword 733 (an abstract a source split into keywords), venue_id_raw 65, invitation
# none, evidence 469.
MAX_DOI = 1_000
MAX_URL = 2_048
MAX_AUTHOR = 1_000
MAX_KEYWORD = 2_000
MAX_VENUE_ID = 500
MAX_INVITATION = 500
MAX_EVIDENCE = 4_000  # a claim's whole evidence, the trim notes included
# the fields a cut value of names nothing: no `urls` slot, venue id or id is ever taken from one (`cut_identifier`)
IDENTIFIERS: tuple[ClaimField, ...] = (
    "urls.forum",
    "urls.pdf",
    "urls.proceedings",
    "urls.doi",
    "venue_id_raw",
)
FIELD_CAPS: dict[str, int] = {
    "urls.forum": MAX_URL, "urls.pdf": MAX_URL, "urls.proceedings": MAX_URL, "urls.doi": MAX_DOI,
    "authors": MAX_AUTHOR, "keywords": MAX_KEYWORD, "venue_id_raw": MAX_VENUE_ID, "invitation": MAX_INVITATION,
}  # fmt: skip
CUT = "trimmed at ingest (decision-053):"  # how a claim's evidence says one of these was cut
# the note as `_claim` writes it, always last: the whole evidence, or after the rest in parentheses
_CUT_NOTE = re.compile(rf"(?:^|\s\(){re.escape(CUT)} ([0-9a-z ,;]+)\)?\Z")
_VALUE_CUT = "value cut from "
_UNREAD = "not read as an id"  # a cut URL that no longer names what it named whole
# a URL replaced by its page's address rebuilt from the record's id, so that it still names the record (`_own_page`)
_OWN = "rebuilt as the page of the record id it names"
_URL_SLOTS = ("urls.forum", "urls.pdf", "urls.proceedings", "urls.doi")


@lru_cache(maxsize=4096)
def _nfkd(ch: str) -> str:
    return unicodedata.normalize("NFKD", ch)


def is_mark(ch: str) -> bool:
    """Does `ch` extend the run of combining marks before it (its NFKD form starts with a non-starter)?"""
    decomposed = _nfkd(ch)
    return bool(decomposed) and unicodedata.combining(decomposed[0]) != 0


@lru_cache(maxsize=4096)
def is_base(ch: str) -> bool:
    """Does `ch` start a new run: a letter or digit that is not a mark? Nothing else does, because the tokenizer
    joins a word across the characters it drops (zero-width joiners, variation selectors, the grapheme joiner,
    soft hyphens, enclosing marks, LaTeX `\\-`), so marks on either side of one reach NFC as one run."""
    return ch.isalnum() and not is_mark(ch)


def _segments(text: str) -> list[str]:
    """`text` split before every base character the tokenizer keeps: each piece is one base (or the text's
    start) and its run. A letter of LaTeX markup it drops (the `H` of `\\H{…}`, a command name outside math) is
    no base: the word goes on across it, as across an invisible character. A math command it reads as its
    Unicode spelling (`\\alpha`, SUB) is one."""
    mask = latex_mask(text)
    cuts = [i for i, ch in enumerate(text) if i and (mask[i] == SUB or (mask[i] == KEEP and is_base(ch)))]
    return [text[i:j] for i, j in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def _decomposed(segment: str) -> list[str]:
    """The characters of `segment` that make its run, decomposed, alike for its canonical forms (NFC, NFD; not an
    NFKC or NFKD source's split spacing accents): the base in NFD (a precomposed `ệ` brings its 2
    marks; its canonical form, so `ﬁ` stays `ﬁ`) and each mark in NFKD (so U+FF9E and U+0F73 are the marks NFKC
    makes of them). Every other character, such as a space, punctuation or an invisible one, is kept as it is
    and holds no mark here: a spacing accent such as `´` is a space and a mark to NFKC, but a starter comes
    first, so it begins no run. Each run of non-starters is stably sorted by combining class, as canonical
    ordering does, so every form of the same text decomposes alike."""
    out: list[str] = []
    run: list[str] = []
    for i, ch in enumerate(segment):
        if is_mark(ch):
            run += _nfkd(ch)
            continue
        out += sorted(run, key=unicodedata.combining)
        run = []
        if i == 0 and is_base(ch):
            base = unicodedata.normalize("NFD", ch)
            out.append(base[0])
            run = list(base[1:])
        else:
            out.append(ch)
    return out + sorted(run, key=unicodedata.combining)


def _trimmed(chars: list[str]) -> str:
    """A run over the cap (`_decomposed`), keeping its first `MAX_MARKS` non-starters. The rest is as it was, so
    every form of the same text trims to the same characters, and two sources whose titles shared a dedup key
    still share it."""
    kept: list[str] = []
    marks = 0
    for c in chars:
        if unicodedata.combining(c):
            marks += 1
            if marks > MAX_MARKS:
                continue
        kept.append(c)
    return "".join(kept)


def cap_marks(text: str) -> tuple[str, int]:
    """`text` with each run of marks cut to `MAX_MARKS` non-starters (the base's own included), and how many
    were dropped (`text` itself when none was). A run within the cap is left as it is; one over it is
    decomposed and trimmed (`_decomposed`, `_trimmed`)."""
    if text.isascii():  # most text: no marks at all
        return text, 0
    pieces: list[str] = []
    dropped = 0
    for segment in _segments(text):
        if not any(map(is_mark, segment)):  # a base brings at most a few marks of its own
            pieces.append(segment)
            continue
        chars = _decomposed(segment)
        marks = sum(unicodedata.combining(c) != 0 for c in chars)
        if marks > MAX_MARKS:
            segment = _trimmed(chars)
            dropped += marks - MAX_MARKS
        pieces.append(segment)
    return ("".join(pieces), dropped) if dropped else (text, 0)


def _tidy(field: str, text: str) -> str:
    """Trimmed `text` as a record accepts it. Dropping marks can leave two spaces together or a space or `…` at an
    end (the marks after them are gone), and a cut abstract can end in either: a title is whitespace-collapsed,
    an abstract has no whitespace or `…` at either end (`PaperRecord`)."""
    if field == "title":
        return " ".join(text.split())
    while text != (stripped := text.strip().strip("…")):
        text = stripped
    return text


def _cut(text: str, most: int) -> str | None:
    """`text` cut so that its NFKD form holds at most `most` characters, or None when it already does. The cut
    falls before the last space that fits (or, with none, the last base character that does), where every form
    of the same text (NFC, NFD, NFKC, NFKD) has the same NFKD length, so every form keeps the same words. A cut
    counted in code points as stored fell at a different place in each form, and NFC can't fix it (U+0F73 and
    U+0958 never recompose): the TASK-155 track-classifier review."""
    length = fits = 0
    space = base = None
    for i, ch in enumerate(text):
        if ch.isspace():
            space = i
        elif is_base(ch):
            base = i
        length += len(_nfkd(ch))
        if length > most:
            break
        fits = i + 1
    else:
        return None
    # a text with no space or base in reach (marks or punctuation only, hostile) is cut where it fits
    return text[: space or base or fits]


def cap(field: str, text: str) -> tuple[str, str | None]:
    """`text` as a record's `field` may hold it, and the note saying what was trimmed (None: `text` itself).
    The length cap cuts first (`_cut`), then the mark cap trims what is left, then `_tidy`."""
    notes = []
    capped = text
    if (cut := _cut(text, _LENGTH[field])) is not None:
        capped = cut
    capped, dropped = cap_marks(capped)
    if dropped:
        notes.append(f"{dropped} combining marks dropped past {MAX_MARKS} in a run")
    if cut is not None or dropped:
        capped = _tidy(field, capped)
    if cut is not None:
        notes.append(f"cut from {len(text):,} to {len(capped):,} characters")
    return (capped, f"{TRIMMED} {'; '.join(notes)}") if notes else (text, None)


def _length(text: str) -> int:
    """`text`'s length as the caps count it: its NFKD form's (`_cut`)."""
    return len(text) if text.isascii() else sum(len(_nfkd(ch)) for ch in text)


def cut(text: str, most: int) -> str | None:
    """`text` cut to `most` characters as a title is (`_cut`: counted in NFKD, before the last space that fits) and
    stripped of whitespace at both ends, or None when it fits (decision-053)."""
    kept = _cut(text, most)
    return None if kept is None else kept.strip()


def _items(values: tuple[str, ...], most: int) -> tuple[tuple[str, ...], int]:
    """`values` with each cut to `most` (`cut`), and how many were (`values` itself when none was)."""
    cuts = [cut(v, most) for v in values]
    n = sum(x is not None for x in cuts)
    return (tuple(v if x is None else x for v, x in zip(values, cuts, strict=True)), n) if n else (values, 0)


def _evidence(evidence: str | None, notes: list[str]) -> str | None:
    """`evidence` with each note after it, in parentheses (a note with none before it is the whole evidence), cut
    first if need be so that the whole holds at most `MAX_EVIDENCE` characters. `notes[-1]` is the `CUT` note when
    there is one, and a cut adds `evidence cut from <n> characters` to it."""

    def joined(head: str | None, tail: list[str]) -> str | None:
        out = head
        for note in tail:
            out = note if not out else f"{out} ({note})"
        return out

    whole = joined(evidence, notes)
    if evidence is None or whole is None or _length(whole) <= MAX_EVIDENCE:
        return whole
    said = f"evidence cut from {len(evidence):,} characters"
    if notes and notes[-1].startswith(CUT):
        notes = [*notes[:-1], f"{notes[-1]}; {said}"]
    else:
        notes = [*notes, f"{CUT} {said}"]
    room = (
        MAX_EVIDENCE - _length(joined("x", notes) or "") + 1
    )  # what the notes leave for the source's evidence
    return joined(cut(evidence, room) or None, notes)


def _names(c: Claim, url: str) -> tuple[object, ...]:
    """What dedup reads `url` as naming when `c` claims it: a proceedings id (`urls.native`; an `iclr_archive`
    target's, whose id hashes the whole URL), a forum id, and a proceedings page's parts (`dedup.proceedings_ids`,
    `forum_ids`, `_names_creative_ai`). A URL no parser can read (an OJS article id past Python's int digit limit)
    names nothing anyone can match: a fresh object, unequal to any other."""
    try:
        archive = (
            urls.iclr_archive_target(url)
            if (c.source, c.field) == ("iclr_archive", "urls.proceedings")
            else None
        )
        return urls.native(url), urls.forum_id(url), urls.proceedings_parts(url), archive and archive[0]
    except ValueError:
        return (object(),)


def _own_page(c: Claim, url: str, own: str) -> str | None:
    """The canonical page address of the record's own proceedings id `own`, built from what `url` names, when `url`
    names `own` (`urls.native` read the id from it); else None (decision-053). Each form's page is rebuilt from the
    parsed id alone, so its length is the id's plus a fixed host and path, and leading zeros or any text past the id
    are gone: a NeurIPS or ICLR page `…/paper_files/paper/<year>/hash/<hash>-Abstract[-<round>].html` on its own host,
    a PMLR paper `proceedings.mlr.press/v<N>/<key>.html`, a dblp record page, an OJS article on its journal, a DOI
    link. Kept only if it names `own` too. An `iclr_archive` id hashes the whole URL and is never `urls.native`'s, so
    nothing is built for it."""
    if _names(c, url)[0] != own:  # only a URL the record's own id was read from (never another paper's)
        return None
    parsed = urlparse(url)
    page: str | None = None
    if (parts := urls.proceedings_parts(url)) is not None:
        rounds = "".join(
            f"-{r}" for r in own.split("-")[2:]
        )  # the 2021 D&B host's round (`proceedings_native`)
        page = f"https://{parsed.netloc.lower()}/paper_files/paper/{parts[1]}/hash/{parts[2]}-Abstract{rounds}.html"
    elif (paper := urls.pmlr(url)) is not None:
        page = f"https://proceedings.mlr.press/v{paper[0]}/{paper[1]}.html"
    elif (key := urls.dblp_icml(url)) is not None:
        page = urls.dblp_record_url(f"conf/icml/{key}")
    elif (key := urls.dblp_aaai(url)) is not None:
        page = urls.dblp_record_url(f"conf/aaai/{key}")
    elif (article := urls.ojs_article(url)) is not None:
        page = f"https://ojs.aaai.org/index.php/{parsed.path.split('/')[2]}/article/view/{article}"
    elif (doi := urls.acm_doi(url)) is not None:
        page = f"https://doi.org/{doi}"
    return page if page is not None and _names(c, page)[0] == own else None


def _claim(c: Claim, own: str | None = None) -> Claim:
    """`c` under every cap: its title or abstract (`cap`), its value or each item of it (`FIELD_CAPS`), its url and
    its evidence, flagged in its evidence (`c` itself when nothing changes). `own` is the record's own proceedings
    id: a URL the id was read from, which a cut at the cap would unname, becomes the id's page address instead
    (`_own_page`, decision-053). That is decided from the value and the id alone, so no text a source writes can
    claim it."""
    value, url, notes, said = c.value, c.url, [], []
    if c.field in CAPPED and isinstance(value, str):
        value, note = cap(c.field, value)
        notes += [note] if note else []
    most = FIELD_CAPS.get(c.field)
    if most is not None and isinstance(value, str) and (kept := cut(value, most)) is not None:
        whole = _names(c, value)
        if c.field in _URL_SLOTS and _names(c, kept) != whole:  # its prefix names another paper, or none
            if own is not None and (to_own := _own_page(c, value, own)) is not None:
                if to_own != value:  # its page's address, rebuilt from the id: it names the record still
                    said.append(f"{_VALUE_CUT}{len(value):,} to {len(to_own):,} characters, {_OWN}")
                    value = to_own
                # it ends at the id: kept whole, still a valid link, and flagged once (not again on a second pass)
                elif _OWN not in _cut_parts(c):
                    said.append(f"value of {len(value):,} characters kept, {_OWN}")
            else:
                said += [f"{_VALUE_CUT}{len(value):,} to {len(kept):,} characters", _UNREAD]
                value = kept
        else:
            said.append(f"{_VALUE_CUT}{len(value):,} to {len(kept):,} characters")
            value = kept
    elif most is not None and isinstance(value, tuple):
        value, n = _items(value, most)
        said += [f"{n} value{'' if n == 1 else 's'} cut to at most {most:,} characters"] if n else []
    if (
        url is not None and _length(url) > MAX_URL
    ):  # only ever a link (the source's page): a cut one would mislead
        said.append(f"url of {len(url):,} characters dropped")
        url = None
    notes += [f"{CUT} {'; '.join(said)}"] if said else []
    evidence = _evidence(c.evidence, notes)
    if not notes and evidence == c.evidence:
        return c
    # the notes go last: an RIS abstract's evidence starts with its route and url (`dedup.attribution`)
    return Claim.model_validate({**c.model_dump(), "value": value, "url": url, "evidence": evidence})


def _cut_parts(c: Claim) -> str:
    """What the `CUT` note ending an `IDENTIFIERS` claim's evidence says ('' when there is none)."""
    m = _CUT_NOTE.search(c.evidence or "") if c.field in IDENTIFIERS else None
    return m.group(1) if m else ""


def cut_identifier(c: Claim) -> bool:
    """Is `c` a DOI, URL or venue id claim whose value the caps cut (decision-053)? A cut one is text for people to
    read: no `urls` slot or `venue_id_raw` is taken from it (`dedup.resolve`), so no page link, export or DOI join
    uses it, and dedup reads no Creative AI evidence from a cut venue id."""
    return _VALUE_CUT in _cut_parts(c)


def unread_identifier(c: Claim) -> bool:
    """Is `c` a URL claim whose cut changed what it names (decision-053): a forum id, a proceedings id or page
    parts that the whole URL didn't name, or none where it named one? Dedup then reads no id from it. A cut that
    left what it names alone (a long query string after a proceedings page's path) still names its paper."""
    return _UNREAD in _cut_parts(c)


def cap_record(record: PaperRecord) -> PaperRecord:
    """`record` with every capped field and every claim capped alike (`record` itself when none changes). A `urls`
    slot or `venue_id_raw` over its cap, or whose claims the caps cut, holds what `dedup.resolve` takes from the
    claims (`dedup.resolved_value`: never a cut one), so the record still equals what its claims resolve to."""
    from openproceedings.ingest import dedup  # here: dedup imports this module

    own = record.native if record.forum_id is None else None
    provenance = tuple(_claim(c, own) for c in record.provenance)
    update: dict[str, object] = {}
    for field in CAPPED:
        text = getattr(record, field)
        if text is not None and (capped := cap(field, text))[1] is not None:
            update[field] = capped[0]
    for field, most in (("authors", MAX_AUTHOR), ("keywords", MAX_KEYWORD)):
        if (items := _items(getattr(record, field), most))[1]:
            update[field] = items[0]
    slots: dict[str, str | None] = {}
    for field in IDENTIFIERS:
        held = (
            record.venue_id_raw
            if field == "venue_id_raw"
            else getattr(record.urls, field.removeprefix("urls."))
        )
        over = held is not None and _length(held) > FIELD_CAPS[field]
        if over or any(c.field == field and cut_identifier(c) for c in provenance):
            value = dedup.resolved_value(provenance, field)
            if value != held:
                slots[field] = value if isinstance(value, str) else None
    if "venue_id_raw" in slots:
        update["venue_id_raw"] = slots.pop("venue_id_raw")
    if slots:
        update["urls"] = record.urls.model_copy(update={f.removeprefix("urls."): v for f, v in slots.items()})
    if not update and all(a is b for a, b in zip(provenance, record.provenance, strict=True)):
        return record
    return record.model_copy(update={**update, "provenance": provenance})


def cap_records(records: Iterable[PaperRecord]) -> list[PaperRecord]:
    """Every record capped (`cap_record`)."""
    return [cap_record(r) for r in records]


def is_trimmed(record: PaperRecord) -> bool:
    """Was any of `record`'s claims trimmed at ingest (the manifest's `trimmed`): a title or abstract
    (decision-026), or any other capped value, url or evidence (decision-053)?"""
    return any(
        _CUT_NOTE.search(c.evidence or "") or (c.field in CAPPED and _NOTE.search(c.evidence or ""))
        for c in record.provenance
    )
