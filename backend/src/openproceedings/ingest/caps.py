"""The ingest caps on indexed text (spec 01 §Pipeline 2; decision-026, TASK-155): a run of combining marks keeps
at most `MAX_MARKS` marks, a title at most `MAX_TITLE` characters and an abstract at most `MAX_ABSTRACT`.

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
holds, for hostile
text only: an NFKD source, whose spacing accents are already a space and a mark, can trim differently from its
composed form (`_decomposed` keeps canonical forms alike, NFC and NFD). Trimmed text is then made
one a record accepts (`_tidy`): dropping marks can leave two spaces together, or a space or `…` at an end. A
title is whitespace-collapsed, and an abstract is stripped of whitespace and `…` at both ends. A title or
abstract past its length cap is cut first (before the mark cap) and tidied the same way. The title cap (the owner, 2026-10-02) bounds
every shape of run the mark rule might miss; real titles are at most 192 characters.

Nothing is trimmed silently: each claim whose value changed says what and why in its evidence (`TRIMMED`, shown
on the paper page), and the snapshot manifest names the records (`trimmed`). Text within both caps is returned
as it is, so a corpus with none over them snapshots byte-identically.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache

from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.query.normalize import KEEP, SUB, latex_mask

MAX_MARKS = 8  # combining marks (NFKD non-starters) kept per run
MAX_ABSTRACT = 20_000  # characters (code points) kept of an abstract
MAX_TITLE = 1_000  # characters (code points) kept of a title (the owner, 2026-10-02)
_LENGTH = {"title": MAX_TITLE, "abstract": MAX_ABSTRACT}
TRIMMED = "trimmed at ingest (decision-026):"  # how a claim's evidence says its value was trimmed
# the note as `_claim` writes it, ending the evidence: the whole of it, or after the source's own in parentheses
_NOTE = re.compile(rf"(?:^|\s\(){re.escape(TRIMMED)} [0-9a-z ,;]+\)?\Z")
CAPPED = ("title", "abstract")  # the indexed text fields


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
    NFKD source's split spacing accents): the base in NFD (a precomposed `ệ` brings its 2
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


def _claim(c: Claim) -> Claim:
    if c.field not in CAPPED or not isinstance(c.value, str):
        return c
    value, note = cap(c.field, c.value)
    if note is None:
        return c
    # the note goes last: an RIS abstract's evidence starts with its route and url (`dedup.attribution`)
    evidence = note if c.evidence is None else f"{c.evidence} ({note})"
    return Claim.model_validate({**c.model_dump(), "value": value, "evidence": evidence})


def cap_record(record: PaperRecord) -> PaperRecord:
    """`record` with its title, abstract and their claims capped alike (`record` itself when none changes)."""
    provenance = tuple(_claim(c) for c in record.provenance)
    update: dict[str, object] = {}
    for field in CAPPED:
        text = getattr(record, field)
        if text is not None and (capped := cap(field, text))[1] is not None:
            update[field] = capped[0]
    if not update and all(a is b for a, b in zip(provenance, record.provenance, strict=True)):
        return record
    return record.model_copy(update={**update, "provenance": provenance})


def cap_records(records: Iterable[PaperRecord]) -> list[PaperRecord]:
    """Every record capped (`cap_record`)."""
    return [cap_record(r) for r in records]


def is_trimmed(record: PaperRecord) -> bool:
    """Was any of `record`'s title or abstract claims trimmed at ingest (the manifest's `trimmed`)?"""
    return any(c.field in CAPPED and _NOTE.search(c.evidence or "") for c in record.provenance)
