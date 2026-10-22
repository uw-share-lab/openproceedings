"""The ingest caps on indexed text (TASK-155, decision-026; spec 01 §Pipeline 2): a run of combining marks keeps
at most 8 marks, an abstract at most 20,000 characters, and whatever is trimmed is flagged in
the claim's evidence and the snapshot manifest, never silently. And every other stored string's length cap
(TASK-279, decision-053): trimmed and flagged alike, and a cut DOI, URL or venue id is never a link or an id."""

from __future__ import annotations

import json
import logging
import random
import sys
import unicodedata
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest import urls
from openproceedings.ingest.caps import (
    CAPPED,
    CUT,
    FIELD_CAPS,
    IDENTIFIERS,
    MAX_ABSTRACT,
    MAX_AUTHOR,
    MAX_DOI,
    MAX_EVIDENCE,
    MAX_KEYWORD,
    MAX_MARKS,
    MAX_TITLE,
    MAX_URL,
    MAX_VENUE_ID,
    TRIMMED,
    cap,
    cap_marks,
    cap_record,
    cap_records,
    cut,
    cut_identifier,
    is_mark,
    is_trimmed,
    names_own_record,
    unread_identifier,
)
from openproceedings.ingest.dedup import (
    _cluster,
    attribution,
    dedup,
    forum_ids,
    is_creative_ai,
    is_listing,
    proceedings_ids,
    resolve,
    title_key,
)
from openproceedings.ingest.record import Claim, PaperRecord, Urls
from openproceedings.ingest.snapshot import build, ingest_ris, load_records
from openproceedings.query.normalize import tokenize

from tests.timing import cpu
from tests.unit.ingest.test_record import claim, record
from tests.unit.ingest.test_snapshot import BUILT, REJECTED, source

ACUTE, SLASH = "́", "̸"  # combining classes 230 and 1: alternating, NFKC's reordering is superlinear
HOSTILE = "a" + (ACUTE + SLASH) * 50  # one base and 100 marks
RIS_ABSTRACT = "A synthetic abstract of a rejected submission."


def test_a_combining_character_is_a_mark_and_a_base_is_not() -> None:
    assert is_mark(ACUTE) and is_mark(SLASH)
    assert not is_mark("a") and not is_mark("é") and not is_mark(" ") and not is_mark("ि")  # ccc 0 sign


@pytest.mark.parametrize("ch", ["ཱི", "ཱུ", "ཱྀ", "ﾞ", "ﾟ"])
def test_a_character_that_decomposes_to_a_mark_is_one(ch: str) -> None:
    # combining class 0 itself, but NFKD starts with a non-starter, so NFKC reorders it like any mark
    assert unicodedata.combining(ch) == 0 and is_mark(ch)


def test_every_combining_character_is_a_mark() -> None:
    assert all(is_mark(chr(c)) for c in range(sys.maxunicode + 1) if unicodedata.combining(chr(c)))


def test_a_run_keeps_its_first_eight_marks() -> None:
    assert cap_marks(HOSTILE) == ("a" + SLASH * 8, 92)  # in NFKD order: the slashes (class 1) sort first


def test_each_base_starts_a_new_run() -> None:
    text = ("x" + ACUTE * MAX_MARKS) * 3
    assert cap_marks(text) == (text, 0)  # eight per base is within the cap, however many bases
    assert cap_marks("x" + ACUTE * 9 + "y" + ACUTE * 10) == ("x" + ACUTE * 8 + "y" + ACUTE * 8, 3)


def test_a_run_at_the_start_of_the_text_is_capped_too() -> None:
    assert cap_marks(ACUTE * 12 + "x") == (ACUTE * 8 + "x", 4)


@pytest.mark.parametrize(
    "sep",
    ["\u200d", "\ufe00", "\u034f", "\u00ad", "\u20dd", "\\-", " ", "-"],
    ids=["zwj", "variation-selector", "grapheme-joiner", "soft-hyphen", "enclosing-mark", "latex-hyphen", "space",
         "hyphen"],
)  # fmt: skip
def test_only_a_letter_or_digit_ends_a_run(sep: str) -> None:
    # the tokenizer joins a word across the invisible characters and `\-`, so marks on both sides reach NFC as
    # one run (TASK-155 security review): only a base a word restarts on, a letter or digit, ends a run
    marks = "\u0316\u0301" * 4  # 8 marks, combining classes 220 and 230 alternating
    out, dropped = cap_marks("\u0e01" + (marks + sep) * 3)
    assert dropped == 16 and out == "\u0e01" + "\u0316" * 4 + "\u0301" * 4 + sep * 3
    assert cap_marks("\u0e01" + marks + sep + "\u0e02" + marks)[1] == 0  # a letter after it: a new run


def test_a_precomposed_base_brings_its_own_marks_to_the_run() -> None:
    # counted in NFKD, so the same text precomposed or decomposed is over the cap alike: `ệ` brings 2
    assert cap_marks("\u1ec7" + ACUTE * 6) == ("\u1ec7" + ACUTE * 6, 0)
    assert (
        cap_marks("\u1ec7" + ACUTE * 7)
        == cap_marks("e\u0323\u0302" + ACUTE * 7)
        == ("e\u0323\u0302" + ACUTE * 6, 1)
    )


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("\u0915" + "\u0301\u0323" * 5, "\u0915" + "\u0323" * 5 + "\u0301" * 5),  # marks in another order
        ("\u0958" + ACUTE * 9, "\u0915\u093c" + ACUTE * 9),  # precomposed against decomposed (dedup review)
        ("o" + "\u0f73" * 3 + "\u0f71\u0f72" * 9, "o" + "\u0f71\u0f72" * 12),  # Tibetan, kept by the fold
    ],
)
def test_every_form_of_the_same_text_trims_alike(one: str, other: str) -> None:
    # two sources holding one title in different Unicode forms share a dedup title key; the cap must not split
    # them (TASK-155 dedup and track-classifier reviews), so a run over the cap is trimmed in its NFKD form
    assert title_key(one) == title_key(other)
    assert cap_marks(one) == cap_marks(other)
    assert title_key(cap_marks(one)[0]) == title_key(cap_marks(other)[0])


def test_a_stored_order_and_its_canonical_order_keep_one_title_key_after_the_cap() -> None:
    # the track-classifier review's check: one title stored with its marks in another order than NFD's shares a
    # title key with the canonical form, and keeping the first 8 marks in stored order split 276 of these 500
    rng = random.Random(155)
    marks = "\u0f71\u0f72\u0f73\u0f74\u05b0\u05b4\u0591\u093c\u0301\u0323\u0327\u0338"
    for _ in range(500):
        text = "".join(
            rng.choice("\u0f40\u05d0\u0915o") + "".join(rng.choice(marks) for _ in range(rng.randint(6, 14)))
            for _ in range(rng.randint(1, 3))
        )
        canonical = unicodedata.normalize("NFD", text)
        assert title_key(text) == title_key(canonical)
        assert title_key(cap_marks(text)[0]) == title_key(cap_marks(canonical)[0])


# what a hostile title or abstract mixes (TASK-155 review): marks of alternating classes, drawn as often as the
# rest together; bases the fold keeps and drops; the invisible characters, whole LaTeX accent macros and other
# markup the tokenizer joins a word across; separators and math. Drawn uniformly from one list, a run past the
# cap almost never formed: the rule before round 2 passed 300 such draws; with these weights it failed 39 of 200
_MARKS = ["\u0301", "\u0316", "\u0338", "\u0323", "\u0f73", "\uff9e"]
_OTHER = [
    "\u0e01", "a", "\u0915", "\u1ec7", "1",  # bases
    "\u200d", "\u00ad", "\ufe00", "\u034f", "\u20dd",  # invisible: dropped, the word joined across them
    "\\H{\u200d}", "\\v{\u00ad}", "\\u{\ufe00}", "\\c{\u034f}", '\\"{}', "\\H{", "{", "}", "\\-", "\\",
    "\\alpha", "$", "H",  # LaTeX
    " ", "-", ".",  # separators
]  # fmt: skip
_PIECE = st.one_of(st.sampled_from(_MARKS), st.sampled_from(_MARKS), st.sampled_from(_OTHER))


@given(st.lists(_PIECE, min_size=100, max_size=400).map("".join), st.sampled_from(CAPPED))
def test_no_token_from_capped_text_holds_a_run_past_the_cap(text: str, field: str) -> None:
    # the invariant that keeps NFC linear, over random mixes: whatever the tokenizer joins, a word it forms from
    # capped text holds at most MAX_MARKS consecutive non-starters
    for token in tokenize(cap(field, text)[0]):
        run = longest = 0
        for ch in unicodedata.normalize("NFD", token.text):
            run = run + 1 if unicodedata.combining(ch) else 0
            longest = max(longest, run)
        assert longest <= MAX_MARKS


_SPACING = ["\u00b4", "\u00a8", "\u02d8", "\u00af", "\u00b8", "\u1fed", "\u2026", "\uff01", "\u2103", " "]


@given(st.lists(st.one_of(_PIECE, st.sampled_from(_SPACING)), min_size=20, max_size=200).map("".join))
def test_a_capped_title_or_abstract_is_still_one_a_record_accepts(text: str) -> None:
    # TASK-155 security round 3: decomposing every character of a trimmed run in NFKD turned a spacing accent
    # (`´` is a space and a mark to NFKD) into two spaces, which the record refuses, aborting the build
    title = " ".join(text.split())
    # every leading and trailing `…` and space: an abstract may not start or end with `…` (a Scholar snippet),
    # and stripping `…` then spaces once left `… …x` as `…x` (found by the nightly profile, 2026-10-05)
    abstract = title.strip("… ")
    if not title or not abstract:
        return
    capped_title, capped_abstract = cap("title", title)[0], cap("abstract", abstract)[0]
    built = record(
        title=capped_title, abstract=capped_abstract
    )  # validated: collapsed title, stripped abstract
    assert built.title == capped_title and built.abstract == capped_abstract


@pytest.mark.parametrize("accent", ["\u00b4", "\u00a8", "\u02d8", "\u1fbd", "\u2026", "\u2103", "\uff01"])
def test_a_trimmed_run_keeps_every_character_but_its_marks_as_it_was(accent: str) -> None:
    title = "\u0e01" + "\u0316\u0301" * 5 + f" {accent} title"
    capped, note = cap("title", title)
    assert capped == "\u0e01" + "\u0316" * 5 + "\u0301" * 3 + f" {accent} title"
    assert note == f"{TRIMMED} 2 combining marks dropped past 8 in a run"


def test_an_accent_macro_doesnt_end_a_run() -> None:
    # the round-2 security probe: `\H{` + an invisible character + `}` is markup the tokenizer joins across, so
    # its letter is no base; uncapped, 4,000 of these made one word with a run of 32,000 marks
    marks = "\u0316\u0301" * 4
    capped, dropped = cap_marks("\u0e01" + (marks + "\\H{\u200d}") * 4_000)
    assert dropped == 8 * 3_999 and len(capped) == 9 + 5 * 4_000  # every mark after the first 8 dropped
    assert cap_marks("\u0e01" + marks + "\\H{x}" + marks)[1] == 0  # a kept letter inside the braces is a base


def test_no_word_the_tokenizer_forms_from_capped_text_holds_a_long_run() -> None:
    # the invariant that keeps NFC linear: a bounded run of non-starters in every token, whatever separates them
    marks = "\u0316\u0301" * 50
    for sep in ("\u200d", "\ufe00", "\u034f", "\u00ad", "\u20dd", "\\-", ""):
        capped, _ = cap("abstract", ("\u0e01" + marks + sep) * 200)
        for token in tokenize(capped):
            run = longest = 0
            for ch in unicodedata.normalize("NFD", token.text):
                run = run + 1 if unicodedata.combining(ch) else 0
                longest = max(longest, run)
            assert longest <= MAX_MARKS


def test_ordinary_text_is_returned_as_it_is() -> None:
    for text in ("Trust in LLMs", "Gödel, Erdős and Đặng", "ป่า ภาษา", "がぎ", "x₁, …, x_n", "a" + ACUTE * 8):
        out, dropped = cap_marks(text)
        assert out is text and dropped == 0
        assert cap("abstract", text) == (text, None)


def test_cap_notes_the_marks_it_dropped() -> None:
    assert cap("title", HOSTILE) == (
        "a" + SLASH * 8,
        f"{TRIMMED} 92 combining marks dropped past 8 in a run",
    )


def test_a_long_abstract_is_cut_and_noted() -> None:
    text = "word " * 5_000 + "end"  # 25,003 characters
    out, note = cap("abstract", text)
    assert len(out) <= MAX_ABSTRACT and text.startswith(out) and out == out.strip()
    assert len(out) == 19_999  # the cut ends on a space, which is stripped
    assert note == f"{TRIMMED} cut from 25,003 to 19,999 characters"  # the length kept, not the cap


def test_a_cut_abstract_never_ends_in_whitespace_or_an_ellipsis() -> None:
    # a record refuses either: whitespace is stripped by importers, a trailing `…` reads as a Scholar snippet
    text = "x" * (MAX_ABSTRACT - 3) + " … …" + "y" * 10
    out, note = cap("abstract", text)
    assert out == "x" * (MAX_ABSTRACT - 3)
    assert note == f"{TRIMMED} cut from 20,011 to 19,997 characters"


def test_every_form_of_a_long_title_is_cut_alike() -> None:
    # TASK-155 track-classifier review: cut in code points as stored, each form of one title was cut at another
    # place (900 of 900 random pairs split their dedup key; NFC first still split 24, as U+0F73 and U+0958 never
    # recompose). Cut at the last space within the NFKD length, every form keeps the same words
    words = ["Trust", "\u00e9t\u00e9", "\u0915\u093c\u093e", "o\u0f73", "\u1ec7", "na\u0303o"] * 60
    title = " ".join(words)
    forms = [unicodedata.normalize(f, title) for f in ("NFC", "NFD", "NFKC", "NFKD")]
    assert len({title_key(f) for f in forms}) == 1 and max(map(len, forms)) > MAX_TITLE
    capped = [cap("title", f) for f in forms]
    assert all(note is not None for _, note in capped)
    assert len({title_key(c) for c, _ in capped}) == 1
    assert all(len(unicodedata.normalize("NFKD", c)) <= MAX_TITLE for c, _ in capped)


def test_a_length_cut_falls_before_a_word_or_where_it_fits() -> None:
    nfc = "Title " + "\u00e9" * 600  # the last space within the NFKD length, alike in NFC and NFD
    nfd = unicodedata.normalize("NFD", nfc)
    assert cap("title", nfc)[0] == cap("title", nfd)[0] == "Title"
    word = "\u00e9" * 600  # no space: before the last base that fits
    assert title_key(cap("title", word)[0]) == title_key(cap("title", unicodedata.normalize("NFD", word))[0])
    assert cap("title", word)[0] == "\u00e9" * 500
    assert cap("title", ACUTE * 1_200)[0] == ACUTE * 8  # no base at all: cut where it fits, then the mark cap


def test_a_long_title_is_cut_collapsed_and_noted() -> None:
    title = "word " * 300 + "end"  # 1,503 characters
    out, note = cap("title", title)
    assert out == ("word " * 200).strip() and len(out) == 999  # cut at 1,000, then the trailing space
    assert note == f"{TRIMMED} cut from 1,503 to 999 characters"
    assert cap("title", "x" * MAX_TITLE) == ("x" * MAX_TITLE, None)  # at the cap: unchanged


def test_both_caps_are_noted_together() -> None:
    _, note = cap("abstract", HOSTILE + " x" * MAX_ABSTRACT)
    assert note == (
        f"{TRIMMED} 92 combining marks dropped past 8 in a run; cut from 40,101 to 19,907 characters"
    )


def test_a_record_and_its_claims_are_trimmed_alike_and_flagged() -> None:
    long_abstract = "y " * MAX_ABSTRACT
    r = record(
        title="Trust " + HOSTILE,
        abstract=long_abstract.strip(),
        provenance=(
            claim("title", "Trust " + HOSTILE, evidence="content.title"),
            claim("abstract", long_abstract.strip()),  # no evidence: the note is the evidence
            claim("status", "accepted", evidence="venueid=ICLR.cc/2024/Conference"),
        ),
    )
    [out] = cap_records([r])
    assert out.title == "Trust a" + SLASH * 8
    assert out.abstract is not None and len(out.abstract) <= MAX_ABSTRACT
    [title] = out.claims("title")
    [abstract] = out.claims("abstract")
    assert title.value == out.title and abstract.value == out.abstract
    assert title.evidence == f"content.title ({TRIMMED} 92 combining marks dropped past 8 in a run)"
    assert abstract.evidence == f"{TRIMMED} cut from 39,999 to 19,999 characters"
    assert out.claims("status") == r.claims("status")  # nothing else changes
    assert out.content_hash != r.content_hash  # rehashed for the trimmed text
    # the abstract's attribution still finds the claim that holds its text
    assert attribution(out.abstract, out.claims("abstract"), forum=None, proceedings=None, native=out.native)


def test_a_record_under_both_caps_is_the_same_object() -> None:
    r = record()
    assert cap_records([r])[0] is r and not is_trimmed(r)


def test_a_claim_over_the_cap_is_trimmed_when_the_records_own_text_is_not() -> None:
    # another source's title claim lost to precedence: still trimmed and flagged, the record's title unchanged
    r = record(
        title="Plain",
        provenance=(
            claim("title", "Plain", evidence="content.title"),
            claim("title", "Plain " + HOSTILE, source="pmlr", evidence="title"),
        ),
    )
    [out] = cap_records([r])
    assert out is not r and out.title == "Plain" and is_trimmed(out)
    kept, trimmed = sorted(out.claims("title"), key=lambda c: c.source != "openreview_v2")
    assert kept.evidence == "content.title" and kept.value == "Plain"
    assert trimmed.value == "Plain a" + SLASH * 8 and trimmed.evidence is not None
    assert trimmed.evidence.startswith(f"title ({TRIMMED}")


@pytest.mark.parametrize(
    ("evidence", "flagged"),
    [
        (f"{TRIMMED} 3 combining marks dropped past 8 in a run", True),
        (f"content.abstract ({TRIMMED} cut from 25,003 to 19,999 characters)", True),
        (f"scholarmend:proceedings_page {TRIMMED} 3 forged", False),  # mid-evidence, not the note's form
        (f"content.abstract ({TRIMMED} 3 marks) and more", False),  # not at the end
        ("content.abstract", False),
    ],
)
def test_only_the_notes_own_form_flags_a_record(evidence: str, flagged: bool) -> None:
    r = record(provenance=(claim("abstract", "We study trust.", evidence=evidence),))
    assert is_trimmed(r) is flagged


def test_a_proceedings_page_evidence_keeps_its_url_first() -> None:
    # dedup.attribution reads the url after `scholarmend:proceedings_page `: the note goes after it
    ev = "scholarmend:proceedings_page https://proceedings.neurips.cc/paper/2024/hash/x-Abstract.html"
    r = record(provenance=(claim("abstract", HOSTILE, source="ris", evidence=ev),), abstract=HOSTILE)
    [out] = cap_records([r])
    assert (
        out.claims("abstract")[0].evidence == f"{ev} ({TRIMMED} 92 combining marks dropped past 8 in a run)"
    )


@pytest.fixture
def hostile_cache(tmp_path: Path) -> Path:
    edit = lambda t: t.replace(RIS_ABSTRACT, RIS_ABSTRACT[:-1] + HOSTILE)  # noqa: E731
    ingest_ris([source(tmp_path, edit=edit)], tmp_path / "cache")
    return tmp_path / "cache"


def test_a_snapshot_trims_a_hostile_abstract_and_names_its_record(
    hostile_cache: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="openproceedings.ingest.snapshot")
    result = build(hostile_cache, tmp_path / "snapshots", BUILT)
    records = load_records(result.path)  # re-validated, content_hash included
    trimmed = records[REJECTED]
    assert trimmed.abstract is not None and trimmed.abstract.startswith(RIS_ABSTRACT[:-1] + "a")
    assert len(trimmed.abstract) == len(RIS_ABSTRACT) + MAX_MARKS  # the base kept 8 of its 100 marks
    assert all(is_mark(c) for c in trimmed.abstract[len(RIS_ABSTRACT) :])
    assert all(c.value == trimmed.abstract for c in trimmed.claims("abstract"))
    assert all(TRIMMED in (c.evidence or "") for c in trimmed.claims("abstract"))
    assert HOSTILE not in (result.path / "records.jsonl").read_text(encoding="utf-8")
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trimmed"] == [REJECTED]
    # the build says so once, as a count (never the ids), on the built path and the already-built one
    build(hostile_cache, tmp_path / "snapshots", BUILT)
    logged = [(r.message, r.levelname, getattr(r, "trimmed", None)) for r in caplog.records]
    assert [x for x in logged if x[0].startswith("snapshot_")] == [
        ("snapshot_trimmed", "WARNING", 1), ("snapshot_built", "INFO", 1),
        ("snapshot_trimmed", "WARNING", 1), ("snapshot_exists", "INFO", 1),
    ]  # fmt: skip
    assert not any(REJECTED in str(r.__dict__) for r in caplog.records)


def test_a_snapshot_with_nothing_to_trim_has_no_trimmed_key(tmp_path: Path) -> None:
    ingest_ris([source(tmp_path)], tmp_path / "cache")
    result = build(tmp_path / "cache", tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert "trimmed" not in manifest  # an untouched corpus keeps the manifest it had


def test_tokenizing_the_largest_capped_abstract_stays_linear() -> None:
    # TASK-155 AC #3: the worst text the caps allow, 20,000 characters of a base whose marks the fold keeps (Thai)
    # and 8 alternating marks (classes 220 and 230, no slash cluster), all one word, tokenizes within 20x plain
    # text of that length and under half a second; the same marks uncapped grow superlinearly
    worst = ("\u0e01" + "\u0316\u0301" * 4) * (MAX_ABSTRACT // 9)
    assert cap("abstract", worst) == (worst, None)
    plain = "\u0e01" * len(worst)

    def secs(text: str) -> float:
        return cpu(lambda: tokenize(text))  # tests/timing.py: CPU time, the garbage collector paused

    secs(plain)
    capped, base = min(secs(worst) for _ in range(5)), min(secs(plain) for _ in range(5))
    assert capped < max(base, 0.002) * 20
    assert capped < 0.5  # the budget: a stored abstract at the cap tokenizes in well under half a second


# --- the other stored strings (decision-053, TASK-279) ---------------------------------------------------------------


def _sized(field: str, n: int) -> str:
    """A value of `field` exactly `n` characters long, with no space (so a cut keeps exactly the cap)."""
    if field == "urls.doi":
        return "10.1234/" + "d" * (n - 8)
    if field.startswith("urls."):
        return "https://example.org/" + "u" * (n - 20)
    return "v" * n


# claims for every field `record()` holds, so it resolves to itself (`dedup.resolve`) once its urls are added
_RESOLVABLE = (
    claim("title", "Trust Calibration in LLMs"),
    claim("abstract", "We study trust."),
    claim("venue", "ICLR"),
    claim("year", 2024),
    claim("track", "main"),
    claim("status", "accepted", evidence="venueid=ICLR.cc/2024/Conference"),
)


_STRING_FIELDS = sorted(f for f in FIELD_CAPS if f not in ("authors", "keywords"))


@pytest.mark.parametrize("field", _STRING_FIELDS)
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_a_string_claim_is_cut_only_past_its_cap_and_flagged(field: str, delta: int) -> None:
    most = FIELD_CAPS[field]
    value = _sized(field, most + delta)
    r = record(provenance=(claim(field, value, source="ris", evidence="mended.ris:UR"),))
    out = cap_record(r)
    if delta <= 0:
        assert out is r and not is_trimmed(out)
        return
    [c] = out.claims(field)
    assert c.value == value[:most] and len(c.value) == most
    assert c.evidence == f"mended.ris:UR ({CUT} value cut from {most + 1:,} to {most:,} characters)"
    assert is_trimmed(out)
    assert cut_identifier(c) is (field in IDENTIFIERS)


@pytest.mark.parametrize(("field", "most"), [("authors", MAX_AUTHOR), ("keywords", MAX_KEYWORD)])
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_each_name_and_keyword_is_cut_only_past_its_cap_and_flagged(
    field: str, most: int, delta: int
) -> None:
    items = ("A. Author", "w" * (most + delta))
    r = record(**{field: items}, provenance=(claim(field, items, evidence="content." + field),))
    out = cap_record(r)
    if delta <= 0:
        assert out is r
        return
    assert getattr(out, field) == ("A. Author", "w" * most)  # the record's field and its claim alike
    [c] = out.claims(field)
    assert c.value == getattr(out, field)
    assert c.evidence == f"content.{field} ({CUT} 1 value cut to at most {most:,} characters)"
    assert is_trimmed(out) and not cut_identifier(c)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_a_venue_id_past_its_cap_is_text_in_its_claim_and_none_on_the_record(delta: int) -> None:
    vid = "ICLR.cc/2024/Conference/" + "x" * (MAX_VENUE_ID - 24 + delta)
    r = record(
        authors=(), keywords=(), urls=Urls(), venue_id_raw=vid,
        provenance=(*_RESOLVABLE, claim("venue_id_raw", vid, evidence="content.venueid")),
    )  # fmt: skip
    out = cap_record(r)
    assert (out is r) is (delta <= 0)
    # a cut venue id could read as another track's id (`…/Conference` from a workshop's), so it is no id
    assert out.venue_id_raw == (vid if delta <= 0 else None)
    assert out.claims("venue_id_raw")[0].value == vid[:MAX_VENUE_ID]
    assert resolve(out.id, out.provenance)[0] == out


@pytest.mark.parametrize(
    ("slot", "most"), [("doi", MAX_DOI), ("forum", MAX_URL), ("pdf", MAX_URL), ("proceedings", MAX_URL)]
)
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_a_doi_or_url_past_its_cap_leaves_its_urls_slot_empty(slot: str, most: int, delta: int) -> None:
    value = _sized(f"urls.{slot}", most + delta)
    r = record(
        authors=(), keywords=(), venue_id_raw=None, urls=Urls(**{slot: value}),
        provenance=(*_RESOLVABLE, claim(f"urls.{slot}", value, evidence="citation")),
    )  # fmt: skip
    out = cap_record(r)
    assert getattr(out.urls, slot) == (value if delta <= 0 else None)
    # a cut one is text in its claim, never a link: the record still equals what its own claims resolve to
    assert resolve(out.id, out.provenance)[0] == out
    assert [c.value for c in out.claims(f"urls.{slot}")] == [value[:most]]


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_a_claims_own_url_past_its_cap_is_dropped_and_flagged(delta: int) -> None:
    url = _sized("urls.pdf", MAX_URL + delta)
    r = record(provenance=(claim("abstract", "We study trust.", url=url, evidence="content.abstract"),))
    out = cap_record(r)
    [c] = out.claims("abstract")
    if delta <= 0:
        assert out is r and c.url == url
        return
    assert c.url is None and c.value == "We study trust."
    assert c.evidence == f"content.abstract ({CUT} url of {MAX_URL + 1:,} characters dropped)"
    assert is_trimmed(out)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_evidence_past_its_cap_is_cut_with_its_note_inside_the_cap(delta: int) -> None:
    route = "scholarmend:proceedings_page https://proceedings.neurips.cc/paper/2024/hash/x-Abstract.html "
    evidence = route + "e" * (MAX_EVIDENCE - len(route) + delta)  # one long last word: a cut falls before it
    r = record(provenance=(claim("abstract", "We study trust.", source="ris", evidence=evidence),))
    out = cap_record(r)
    [c] = out.claims("abstract")
    if delta <= 0:
        assert out is r
        return
    assert c.evidence is not None and len(c.evidence) <= MAX_EVIDENCE
    # the route and its url stay first (`attribution`); the cut falls before the last space, as a title's does
    assert c.evidence == f"{route.strip()} ({CUT} evidence cut from {MAX_EVIDENCE + 1:,} characters)"
    assert is_trimmed(out) and cap_record(out) is out  # capped once: a second pass changes nothing


def test_a_title_cut_and_an_evidence_cut_keep_both_notes_inside_the_cap() -> None:
    title, evidence = "Trust " * 400, "e" * MAX_EVIDENCE
    r = record(title=title.strip(), provenance=(claim("title", title.strip(), evidence=evidence),))
    out = cap_record(r)
    [c] = out.claims("title")
    assert c.evidence is not None and len(c.evidence) <= MAX_EVIDENCE and c.evidence.startswith("eee")
    assert c.evidence.endswith(
        f"e ({TRIMMED} cut from 2,399 to 995 characters) ({CUT} evidence cut from 4,000 characters)"
    )
    assert is_trimmed(out) and cap_record(out) is out


def test_a_cut_forum_url_that_names_another_paper_is_never_read_as_its_id() -> None:
    # hostile: padding before the id, so the cut leaves `id=` a valid forum id of some other paper
    whole = "https://openreview.net/forum?pad=" + "p" * (MAX_URL - 43) + "&id=Other12345" + "6" * 20
    r = record(provenance=(claim("urls.forum", whole, evidence="note.id"),))
    out = cap_record(r)
    [c] = out.claims("urls.forum")
    assert urls.forum_id(str(c.value)) == "Other1"  # the prefix names another (valid) forum id
    assert unread_identifier(c) and cut_identifier(c)
    assert "Other1" not in forum_ids(out)
    assert c.evidence is not None and c.evidence.endswith("characters; not read as an id)")


def test_a_cut_query_string_still_names_its_proceedings_paper() -> None:
    # a long tracking query after a proceedings page's path: the cut keeps the path, so the page still names itself
    page = "https://proceedings.neurips.cc/paper_files/paper/2024/hash/00112233445566778899aabbccddeeff-Abstract.html"
    whole = page + "?utm=" + "q" * MAX_URL
    r = record(
        provenance=(claim("urls.proceedings", whole, source="neurips_proceedings", evidence="listing"),)
    )
    out = cap_record(r)
    [c] = out.claims("urls.proceedings")
    assert cut_identifier(c) and not unread_identifier(c)  # no link, still its id
    assert proceedings_ids(out.provenance) == {"nips-00112233445566778899aabbccddeeff"}


def test_a_cut_proceedings_url_that_loses_its_page_names_nothing() -> None:
    whole = "https://proceedings.mlr.press/v235/" + "k" * MAX_URL + ".html"
    r = record(provenance=(claim("urls.proceedings", whole, source="pmlr", evidence="listing"),))
    out = cap_record(r)
    [c] = out.claims("urls.proceedings")
    assert unread_identifier(c) and proceedings_ids(out.provenance) == set()


def test_an_invitation_or_keyword_cut_is_text_not_an_identifier() -> None:
    long = "x" * (MAX_KEYWORD + 1)
    out = cap_record(
        record(keywords=(long,), provenance=(claim("keywords", (long,)), claim("invitation", long)))
    )
    assert is_trimmed(out) and not any(cut_identifier(c) or unread_identifier(c) for c in out.provenance)


def test_a_slot_whose_best_claim_is_cut_takes_the_next_claim_that_isnt() -> None:
    # two sources claim a DOI and the higher-ranked one is over the cap: the record takes the other, as resolve does
    long, short = _sized("urls.doi", MAX_DOI + 1), "10.1234/short"
    r = record(
        authors=(), keywords=(), venue_id_raw=None, urls=Urls(doi=long),
        provenance=(*_RESOLVABLE, claim("urls.doi", long, evidence="a"), claim("urls.doi", short, source="ris")),
    )  # fmt: skip
    out = cap_record(r)
    assert out.urls.doi == short and resolve(out.id, out.provenance)[0] == out


def _pmlr(page: str, *more: Claim) -> PaperRecord:
    """A PMLR ICML 2024 listing whose id is read from its own page URL, as the miner builds one."""
    native = urls.native(page)
    assert native is not None
    pmlr = {"source": "pmlr", "evidence": "listing"}
    return record(
        id=f"op:icml:2024:{native}", venue="ICML", venue_id_raw=None, keywords=(), urls=Urls(proceedings=page),
        provenance=(
            claim("urls.proceedings", page, **pmlr), claim("title", "Trust Calibration in LLMs", **pmlr),
            claim("venue", "ICML", **pmlr), claim("year", 2024, **pmlr), claim("track", "main", **pmlr),
            claim("status", "accepted", **pmlr), claim("authors", ("A. Author", "B. Author"), **pmlr),
            claim("abstract", "We study trust.", **pmlr), *more,
        ),
    )  # fmt: skip


def test_a_listing_whose_own_page_url_is_cut_still_names_itself_and_builds() -> None:
    # the id was read from the whole URL: the cut text names another key, so it is unread, but the record keeps its
    # own id as a listing and dedup's self-naming check doesn't refuse the build (decision-053)
    r = _pmlr("https://proceedings.mlr.press/v235/" + "k" * (MAX_URL + 10) + ".html")
    out = cap_record(r)
    [c] = out.claims("urls.proceedings")
    assert unread_identifier(c) and names_own_record(c) and out.urls.proceedings is None
    assert proceedings_ids(out.provenance) == set() and is_listing(out)
    assert list(dedup([out]).records) == [out]


def test_an_ojs_listing_whose_own_page_url_is_cut_is_still_a_listing_by_its_own_id() -> None:
    # ojs is no proceedings source, so only its own id makes it a listing (`is_listing`, the cluster's ids)
    article = "7" * (MAX_URL + 10)
    page = f"https://ojs.aaai.org/index.php/AAAI/article/view/{article}"
    ojs = {"source": "ojs", "evidence": "dc:identifier"}
    r = record(
        id=f"op:aaai:2020:ojs-{article}", venue="AAAI", year=2020, venue_id_raw=None, keywords=(),
        urls=Urls(proceedings=page),
        provenance=(
            claim("urls.proceedings", page, **ojs), claim("title", "Trust Calibration in LLMs", **ojs),
            claim("venue", "AAAI", **ojs), claim("year", 2020, **ojs), claim("track", "main", **ojs),
            claim("status", "accepted", **ojs), claim("authors", ("A. Author", "B. Author"), **ojs),
            claim("abstract", "We study trust.", **ojs),
        ),
    )  # fmt: skip
    out = cap_record(r)
    assert names_own_record(out.claims("urls.proceedings")[0]) and proceedings_ids(out.provenance) == set()
    assert is_listing(out)
    cluster = _cluster([out])
    assert cluster.proceedings_ids == {out.native} and cluster.listed and cluster.crawled
    assert list(dedup([out]).records) == [out]


def test_a_slot_at_its_cap_with_no_claim_is_kept() -> None:
    doi = _sized("urls.doi", MAX_DOI)
    r = record(urls=Urls(doi=doi))
    assert cap_record(r) is r


def test_a_cut_url_that_named_another_paper_does_not_name_this_one() -> None:
    other = "https://proceedings.mlr.press/v235/" + "k" * (MAX_URL + 10) + ".html"
    r = _pmlr("https://proceedings.mlr.press/v235/own24a.html", claim("urls.pdf", other, source="pmlr"))
    [c] = cap_record(r).claims("urls.pdf")
    assert unread_identifier(c) and not names_own_record(c)


def test_a_cut_iclr_archive_target_never_reads_as_its_id() -> None:
    # its id hashes the whole canonical URL, so any cut names another id
    whole = "https://arxiv.org/abs/1412.6980?" + "q" * MAX_URL
    r = record(provenance=(claim("urls.proceedings", whole, source="iclr_archive", evidence="archive"),))
    [c] = cap_record(r).claims("urls.proceedings")
    assert unread_identifier(c) and proceedings_ids((c,)) == set()


def test_an_ojs_url_past_the_int_digit_limit_is_cut_without_error() -> None:
    whole = "https://ojs.aaai.org/index.php/AAAI/article/view/" + "7" * 5_000
    r = record(provenance=(claim("urls.proceedings", whole, source="ojs", evidence="dc:identifier"),))
    [c] = cap_record(r).claims("urls.proceedings")
    assert unread_identifier(c) and len(str(c.value)) <= MAX_URL


_CREATIVE = "NeurIPS.cc/2024/Creative_AI_Track"


def _creative(*provenance: Claim) -> PaperRecord:
    return record(
        id="op:neurips:2024:iilhN2MycO", venue="NeurIPS", track="other", venue_id_raw=None, keywords=(),
        provenance=(claim("track", "other", evidence="content.venueid"), *provenance),
    )  # fmt: skip


def test_a_cut_venue_id_is_never_creative_ai_evidence() -> None:
    # the whole id isn't Creative AI; cut before its last space it is exactly the Creative AI id
    r = _creative(claim("venue_id_raw", _CREATIVE + " " + "x" * MAX_VENUE_ID))
    out = cap_record(r)
    assert out.claims("venue_id_raw")[0].value == _CREATIVE
    assert not is_creative_ai(r) and not is_creative_ai(out)


def test_a_cut_proceedings_url_that_names_another_page_is_never_creative_ai_evidence() -> None:
    # the whole URL names no page (its path ends past `.html`); the cut falls before the first letter past the cap,
    # exactly after `.html`, so the cut text is a Creative AI page (a hash of any length parses) the whole never was
    head = "https://proceedings.neurips.cc/paper_files/paper/2024/hash/"
    tail = "-Abstract-Creative_AI_Track.html"
    page = head + "a" * (MAX_URL - len(head) - len(tail)) + tail
    r = _creative(claim("urls.proceedings", page + "xyz", evidence="content.pdf"))
    out = cap_record(r)
    [c] = out.claims("urls.proceedings")
    assert c.value == page and urls.proceedings_parts(page) is not None and unread_identifier(c)
    assert not is_creative_ai(r) and not is_creative_ai(out)  # the cut page is no evidence


@pytest.mark.parametrize(
    ("evidence", "flagged"),
    [
        (f"{CUT} value cut from 2,049 to 2,048 characters", True),
        (f"citation ({CUT} value cut from 2,049 to 2,048 characters)", True),
        (
            f"citation {CUT} value cut from 2,049 to 2,048 characters",
            False,
        ),  # mid-evidence, not the note's form
        (f"citation ({CUT} value cut) and more", False),  # not at the end
    ],
)
def test_only_the_cut_notes_own_form_flags_a_record_or_a_cut_identifier(evidence: str, flagged: bool) -> None:
    r = record(provenance=(claim("urls.doi", "10.1234/x", evidence=evidence),))
    assert is_trimmed(r) is flagged and cut_identifier(r.provenance[0]) is flagged


_TEXT = st.text(st.sampled_from("ab ́ﬁ.\u00a0-/"), max_size=60)


@given(_TEXT, st.integers(min_value=1, max_value=40))
def test_a_cut_never_passes_its_cap_and_text_within_it_is_unchanged(text: str, most: int) -> None:
    kept = cut(text, most)
    length = len(unicodedata.normalize("NFKD", text))
    if length <= most:
        assert kept is None  # within the cap: the value itself, never touched
    else:
        assert kept is not None and len(unicodedata.normalize("NFKD", kept)) <= most
        assert text.lstrip().startswith(kept)  # a prefix of the text, stripped: nothing added or moved


@given(
    st.lists(st.text(st.sampled_from("ab ́"), max_size=12), max_size=4).map(tuple),
    st.text(st.sampled_from("ab/"), max_size=12),
    st.integers(min_value=0, max_value=3),
)
def test_a_capped_record_is_within_every_cap_and_capping_it_again_changes_nothing(
    names: tuple[str, ...], tail: str, scale: int
) -> None:
    # values within a few characters of each cap, so some are within it and some past it
    author = "n" * (MAX_AUTHOR - 6 + scale) + "".join(names)
    doi = "10.1234/" + "d" * (MAX_DOI - 10 + scale) + tail
    r = record(
        authors=(author, *names),
        urls=Urls(doi=doi),
        provenance=(claim("authors", (author, *names)), claim("urls.doi", doi, evidence="citation_doi")),
    )
    out = cap_record(r)
    assert all(len(unicodedata.normalize("NFKD", a)) <= MAX_AUTHOR for a in out.authors)
    assert out.urls.doi is None or len(out.urls.doi) <= MAX_DOI
    assert cap_record(out) is out
    assert (out is r) is (not is_trimmed(out))


def test_a_snapshot_cuts_a_long_author_name_and_names_its_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="openproceedings.ingest.snapshot")
    long_name = "N" * (MAX_AUTHOR + 50)
    ingest_ris(
        [source(tmp_path, edit=lambda t: t.replace("AU  - Noe, N", f"AU  - Noe, {long_name}"))],
        tmp_path / "c",
    )
    result = build(tmp_path / "c", tmp_path / "snapshots", BUILT)
    trimmed = load_records(result.path)[REJECTED]
    assert all(len(a) <= MAX_AUTHOR for a in trimmed.authors)
    assert all(CUT in (c.evidence or "") for c in trimmed.claims("authors"))
    assert long_name not in (result.path / "records.jsonl").read_text(encoding="utf-8")
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trimmed"] == [REJECTED]
    # the build says so once, as a count: never the record's id or the name
    logged = [(r.message, r.levelname, getattr(r, "trimmed", None)) for r in caplog.records]
    assert [x for x in logged if x[0].startswith("snapshot_")] == [
        ("snapshot_trimmed", "WARNING", 1), ("snapshot_built", "INFO", 1),
    ]  # fmt: skip
    assert not any(REJECTED in str(r.__dict__) or long_name in str(r.__dict__) for r in caplog.records)
