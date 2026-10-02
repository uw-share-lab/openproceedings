"""The ingest caps on indexed text (TASK-155, decision-026; spec 01 §Pipeline 2): a run of combining marks keeps
at most 8 marks per base character, an abstract at most 20,000 characters, and whatever is trimmed is flagged in
the claim's evidence and the snapshot manifest, never silently."""

from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import pytest
from openproceedings.ingest.caps import MAX_ABSTRACT, MAX_MARKS, TRIMMED, cap, cap_marks, cap_records, is_mark
from openproceedings.ingest.dedup import attribution
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
    assert cap_marks(HOSTILE) == ("a" + (ACUTE + SLASH) * 4, 92)


def test_each_base_starts_a_new_run() -> None:
    text = ("x" + ACUTE * MAX_MARKS) * 3
    assert cap_marks(text) == (text, 0)  # eight per base is within the cap, however many bases
    assert cap_marks("x" + ACUTE * 9 + "y" + ACUTE * 10) == ("x" + ACUTE * 8 + "y" + ACUTE * 8, 3)


def test_a_run_at_the_start_of_the_text_is_capped_too() -> None:
    assert cap_marks(ACUTE * 12 + "x") == (ACUTE * 8 + "x", 4)


def test_ordinary_text_is_returned_as_it_is() -> None:
    for text in ("Trust in LLMs", "Gödel, Erdős and Đặng", "ป่า ภาษา", "がぎ", "x₁, …, x_n", "a" + ACUTE * 8):
        out, dropped = cap_marks(text)
        assert out is text and dropped == 0
        assert cap("abstract", text) == (text, None)


def test_cap_notes_the_marks_it_dropped() -> None:
    assert cap("title", HOSTILE) == (
        "a" + (ACUTE + SLASH) * 4,
        f"{TRIMMED} 92 combining marks dropped past 8 per base character",
    )


def test_a_long_abstract_is_cut_and_noted() -> None:
    text = "word " * 5_000 + "end"  # 25,003 characters
    out, note = cap("abstract", text)
    assert len(out) <= MAX_ABSTRACT and text.startswith(out) and out == out.strip()
    assert note == f"{TRIMMED} cut from 25,003 to 20,000 characters"


def test_a_cut_abstract_never_ends_in_whitespace_or_an_ellipsis() -> None:
    # a record refuses either: whitespace is stripped by importers, a trailing `…` reads as a Scholar snippet
    text = "x" * (MAX_ABSTRACT - 3) + " … …" + "y" * 10
    out, note = cap("abstract", text)
    assert out == "x" * (MAX_ABSTRACT - 3) and note is not None


def test_a_title_has_no_length_cap() -> None:
    title = "word " * 5_000 + "end"
    assert cap("title", title) == (title, None)


def test_both_caps_are_noted_together() -> None:
    _, note = cap("abstract", HOSTILE + " x" * MAX_ABSTRACT)
    assert note == (
        f"{TRIMMED} 92 combining marks dropped past 8 per base character; cut from 40,009 to 20,000 characters"
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
    assert out.title == "Trust a" + (ACUTE + SLASH) * 4
    assert out.abstract is not None and len(out.abstract) <= MAX_ABSTRACT
    [title] = out.claims("title")
    [abstract] = out.claims("abstract")
    assert title.value == out.title and abstract.value == out.abstract
    assert title.evidence == f"content.title ({TRIMMED} 92 combining marks dropped past 8 per base character)"
    assert abstract.evidence == f"{TRIMMED} cut from 39,999 to 20,000 characters"
    assert out.claims("status") == r.claims("status")  # nothing else changes
    assert out.content_hash != r.content_hash  # rehashed for the trimmed text
    # the abstract's attribution still finds the claim that holds its text
    assert attribution(out.abstract, out.claims("abstract"), forum=None, proceedings=None, native=out.native)


def test_a_record_under_both_caps_is_the_same_object() -> None:
    r = record()
    assert cap_records([r])[0] is r


def test_a_proceedings_page_evidence_keeps_its_url_first() -> None:
    # dedup.attribution reads the url after `scholarmend:proceedings_page `: the note goes after it
    ev = "scholarmend:proceedings_page https://proceedings.neurips.cc/paper/2024/hash/x-Abstract.html"
    r = record(provenance=(claim("abstract", HOSTILE, source="ris", evidence=ev),), abstract=HOSTILE)
    [out] = cap_records([r])
    assert (
        out.claims("abstract")[0].evidence
        == f"{ev} ({TRIMMED} 92 combining marks dropped past 8 per base character)"
    )


@pytest.fixture
def hostile_cache(tmp_path: Path) -> Path:
    edit = lambda t: t.replace(RIS_ABSTRACT, RIS_ABSTRACT[:-1] + HOSTILE)  # noqa: E731
    ingest_ris([source(tmp_path, edit=edit)], tmp_path / "cache")
    return tmp_path / "cache"


def test_a_snapshot_trims_a_hostile_abstract_and_names_its_record(
    hostile_cache: Path, tmp_path: Path
) -> None:
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


def test_a_snapshot_with_nothing_to_trim_has_no_trimmed_key(tmp_path: Path) -> None:
    ingest_ris([source(tmp_path)], tmp_path / "cache")
    result = build(tmp_path / "cache", tmp_path / "snapshots", BUILT)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert "trimmed" not in manifest  # an untouched corpus keeps the manifest it had


def test_tokenizing_the_largest_capped_abstract_stays_linear() -> None:
    # TASK-155 AC #3: the worst text the caps allow (8 alternating marks on every base, 20,000 characters)
    # costs about what plain text of that length does, while the uncapped run it came from is superlinear
    worst = ("a" + (ACUTE + SLASH) * 4) * (MAX_ABSTRACT // 9)
    assert cap("abstract", worst) == (worst, None)
    plain = "a" * len(worst)

    def secs(text: str) -> float:
        t = time.thread_time()
        tokenize(text)
        return time.thread_time() - t

    secs(plain)
    capped, base = min(secs(worst) for _ in range(5)), min(secs(plain) for _ in range(5))
    assert capped < max(base, 0.002) * 20
    assert capped < 0.5  # the budget: a stored abstract at the cap tokenizes in well under half a second
