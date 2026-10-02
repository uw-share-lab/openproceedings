"""The ingest caps on indexed text (spec 01 §Pipeline 2; decision-026, TASK-155): a run of combining marks keeps
at most `MAX_MARKS` marks per base character, and an abstract at most `MAX_ABSTRACT` characters.

CPython's NFKC canonical reordering is superlinear in a run of marks whose combining classes alternate
(`a` + `\\u0301\\u0338` × n), so one hostile abstract would cost the index build and every search that highlights
it. A `q` is capped at 2,000 code points; stored text is capped here, once, before dedup (`snapshot.load_sources`),
so every source's claims are trimmed alike and still compare as they did. A mark is a character whose
compatibility decomposition starts with a non-zero canonical combining class: every combining character, and the
five that decompose to one (U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F). A run is the marks after one base character
(a letter or digit that is not a mark), or at the start of the text. Any other character (a space, punctuation, an
invisible character the tokenizer drops) neither counts nor ends a run: the tokenizer joins a word across the
invisible ones, so a run split only by them reaches NFC whole, and a run split by a space or punctuation is capped
as one, which real text never needs (its longest run is 1). So no word the tokenizer forms holds more than about
twice `MAX_MARKS` consecutive non-starters after NFKD, and its NFC is linear. Marks past the cap are dropped (title and abstract, the two indexed fields); an
abstract past its cap is cut there, then stripped of trailing whitespace and `…` (a record's abstract ends in
neither). Nothing is trimmed silently: each claim whose value changed says what and why in its evidence
(`TRIMMED`, shown on the paper page), and the snapshot manifest names the records (`trimmed`). Text within both
caps is returned as it is, so a corpus with none over them snapshots byte-identically.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache

from openproceedings.ingest.record import Claim, PaperRecord

MAX_MARKS = 8  # combining marks kept per base character
MAX_ABSTRACT = 20_000  # characters (code points) kept of an abstract
TRIMMED = "trimmed at ingest (decision-026):"  # how a claim's evidence says its value was trimmed
# the note as `_claim` writes it, ending the evidence: the whole of it, or after the source's own in parentheses
_NOTE = re.compile(rf"(?:^|\s\(){re.escape(TRIMMED)} [0-9a-z ,;]+\)?\Z")
CAPPED = ("title", "abstract")  # the indexed text fields; only the abstract has a length cap


@lru_cache(maxsize=4096)
def is_mark(ch: str) -> bool:
    """Does `ch` extend the run of combining marks before it (its NFKD form starts with a non-starter)?"""
    decomposed = unicodedata.normalize("NFKD", ch)
    return bool(decomposed) and unicodedata.combining(decomposed[0]) != 0


@lru_cache(maxsize=4096)
def is_base(ch: str) -> bool:
    """Does `ch` start a new run: a letter or digit that is not a mark? Nothing else does, because the tokenizer
    joins a word across the characters it drops (zero-width joiners, variation selectors, the grapheme joiner,
    soft hyphens, enclosing marks, LaTeX `\\-`), so marks on either side of one reach NFC as one run."""
    return ch.isalnum() and not is_mark(ch)


def cap_marks(text: str) -> tuple[str, int]:
    """`text` with each run of marks cut to `MAX_MARKS`, and how many marks were dropped (`text` itself when
    none was)."""
    if text.isascii():  # most text: no marks at all
        return text, 0
    kept: list[str] = []
    run = dropped = 0
    for ch in text:
        if not is_mark(ch):
            run = 0 if is_base(ch) else run
        elif run == MAX_MARKS:
            dropped += 1
            continue
        else:
            run += 1
        kept.append(ch)
    return ("".join(kept), dropped) if dropped else (text, 0)


def _cut(text: str) -> str:
    """`text` cut to `MAX_ABSTRACT`, with no trailing whitespace or `…` left (a record would refuse either)."""
    out = text[:MAX_ABSTRACT]
    while out != (stripped := out.rstrip().rstrip("…")):
        out = stripped
    return out


def cap(field: str, text: str) -> tuple[str, str | None]:
    """`text` as a record's `field` may hold it, and the note saying what was trimmed (None: `text` itself)."""
    capped, dropped = cap_marks(text)
    notes = [f"{dropped} combining marks dropped past {MAX_MARKS} per base character"] if dropped else []
    if field == "abstract" and len(capped) > MAX_ABSTRACT:
        cut = _cut(capped)
        notes.append(f"cut from {len(capped):,} to {len(cut):,} characters")
        capped = cut
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
