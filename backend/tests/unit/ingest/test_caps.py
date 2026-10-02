"""The ingest caps on indexed text (TASK-155, decision-026; spec 01 §Pipeline 2): a run of combining marks keeps
at most 8 marks, an abstract at most 20,000 characters, and whatever is trimmed is flagged in
the claim's evidence and the snapshot manifest, never silently."""

from __future__ import annotations

import json
import logging
import random
import sys
import time
import unicodedata
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest.caps import (
    CAPPED,
    MAX_ABSTRACT,
    MAX_MARKS,
    MAX_TITLE,
    TRIMMED,
    cap,
    cap_marks,
    cap_records,
    is_mark,
    is_trimmed,
)
from openproceedings.ingest.dedup import attribution, title_key
from openproceedings.ingest.snapshot import build, ingest_ris, load_records
from openproceedings.query.normalize import tokenize

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
    abstract = title.strip("…").strip()
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


def test_a_length_cap_counts_and_cuts_the_nfc_form() -> None:
    # the dedup review's Nit: counted in code points as sent, an NFD title was cut where its NFC twin was not
    nfc = "Title " + "\u00e9" * 600  # 606 characters
    nfd = unicodedata.normalize("NFD", nfc)  # 1,206
    assert cap("title", nfc) == (nfc, None) and cap("title", nfd) == (nfd, None)
    long_nfc, long_nfd = nfc + "\u00e9" * 900, nfd + "e\u0301" * 900
    assert cap("title", long_nfc)[0] == cap("title", long_nfd)[0] == ("Title " + "\u00e9" * 994)
    assert cap("title", long_nfd)[1] == f"{TRIMMED} cut from 1,506 to 1,000 characters"


def test_a_long_title_is_cut_collapsed_and_noted() -> None:
    title = "word " * 300 + "end"  # 1,503 characters
    out, note = cap("title", title)
    assert out == ("word " * 200).strip() and len(out) == 999  # cut at 1,000, then the trailing space
    assert note == f"{TRIMMED} cut from 1,503 to 999 characters"
    assert cap("title", "x" * MAX_TITLE) == ("x" * MAX_TITLE, None)  # at the cap: unchanged


def test_both_caps_are_noted_together() -> None:
    _, note = cap("abstract", HOSTILE + " x" * MAX_ABSTRACT)
    assert note == (
        f"{TRIMMED} 92 combining marks dropped past 8 in a run; cut from 40,009 to 19,999 characters"
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
        t = time.thread_time()
        tokenize(text)
        return time.thread_time() - t

    secs(plain)
    capped, base = min(secs(worst) for _ in range(5)), min(secs(plain) for _ in range(5))
    assert capped < max(base, 0.002) * 20
    assert capped < 0.5  # the budget: a stored abstract at the cap tokenizes in well under half a second
