"""The OpenReview API v1 author splitter (decision-019, TASK-113): `content.authors` is split into names only when
the pieces match the note's author ids, against recorded, scrubbed notes (the scrub keeps an authors value's
separators and an email string's count), plus Hypothesis properties of `split_authors`. No network (conftest)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import openreview_v1 as v1

from tests.unit.ingest.openreview_fakes import FakeOpenReviewV1, v1_clone, v1_note, v1_notes
from tests.unit.ingest.test_openreview_v1 import BLIND, claim, run

NAMES = tuple(f"Synthetic Author {n}" for n in range(1, 40))


def crawled(
    tmp_path: Path, year: int, listing: str, fixture: str
) -> tuple[dict[str, PaperRecord], v1.CrawlReport]:
    crawl = run(FakeOpenReviewV1({listing: v1_notes(fixture)}), tmp_path, "ICLR", year)
    return {r.native: r for r in crawl.records}, crawl.report


# (fixture, year, listing, note id, the authors a record gets, how): every case recorded from the 2026-09-29 crawl
CASES = [
    # early ICLR 2017: one string, counted against the `author_emails` string
    ("iclr-2017/notes-conference-authors-string.json", 2017, "ICLR.cc/2017/conference/-/submission", "S1HEBe_Jl",
     ("Synthetic Author 6", "Synthetic Author 7"), "split"),
    # a list whose last entry starts with `and `
    ("iclr-2017/notes-workshop-authors-and.json", 2017, "ICLR.cc/2017/workshop/-/submission", "HkXKUTVFl",
     tuple(f"Synthetic Author {n}" for n in range(8, 13)), "split"),
    # `A and B` in one entry
    ("iclr-2017/notes-workshop-authors-and.json", 2017, "ICLR.cc/2017/workshop/-/submission", "Hynn8SHOx",
     ("Synthetic Author 35", "Synthetic Author 36"), "split"),
    # the title in `authors`: three pieces for two ids, refused
    ("iclr-2017/notes-workshop-authors-and.json", 2017, "ICLR.cc/2017/workshop/-/submission", "H1JBMVpdx",
     (), "refused"),
    ("iclr-2018/notes-blind-authors-and.json", 2018, BLIND.format(y=2018), "r1ISxGZRb",
     ("Synthetic Author 6", "Synthetic Author 7", "Synthetic Author 8"), "split"),
    ("iclr-2018/notes-blind-authors-and.json", 2018, BLIND.format(y=2018), "BJij4yg0Z",
     ("Synthetic Author 27", "Synthetic Author 28"), "split"),
    # a clean list is untouched even when it has fewer ids than names (two names, one id)
    ("iclr-2018/notes-blind-authors-and.json", 2018, BLIND.format(y=2018), "Hy3MvSlRW",
     ("Synthetic Author 15", "Synthetic Author 16"), "listed"),
    # `A and B` joined in the first entry of a longer list
    ("iclr-2020/notes-blind-authors-and.json", 2020, BLIND.format(y=2020), "HklCmaVtPS",
     tuple(f"Synthetic Author {n}" for n in range(8, 12)), "split"),
    # profile ids count as ids (live, the second is `~and_<Name>1`: the `and` is in the id too)
    ("iclr-2021/notes-blind-authors-and.json", 2021, BLIND.format(y=2021), "RepN5K31PT3",
     ("Synthetic Author 5", "Synthetic Author 6"), "split"),
]  # fmt: skip


@pytest.mark.parametrize(("fixture", "year", "listing", "nid", "authors", "how"), CASES)
def test_recorded_author_shapes(
    tmp_path: Path, fixture: str, year: int, listing: str, nid: str, authors: tuple[str, ...], how: str
) -> None:
    got, _ = crawled(tmp_path, year, listing, fixture)
    record = got[nid]
    assert record.authors == authors
    evidence = claim(record, "authors").evidence
    assert claim(record, "authors").value == authors
    raw = next(n for n in v1_notes(fixture) if n["id"] == nid)["content"]["authors"]
    if how == "listed":
        assert evidence == "content.authors"
    else:  # the raw value is kept in the evidence, whichever way the rule went
        assert evidence.endswith(f"(raw: {json.dumps(raw, ensure_ascii=False)})")
        assert evidence.startswith("content.authors split" if how == "split" else "content.authors not split")


@pytest.mark.parametrize(
    ("fixture", "year", "listing", "counts"),
    [
        ("iclr-2017/notes-workshop-authors-and.json", 2017, "ICLR.cc/2017/workshop/-/submission", (2, 1)),
        ("iclr-2018/notes-blind-authors-and.json", 2018, BLIND.format(y=2018), (2, 0)),
    ],
)
def test_the_report_counts_splits_and_refusals(
    tmp_path: Path, fixture: str, year: int, listing: str, counts: tuple[int, int]
) -> None:
    _, report = crawled(tmp_path, year, listing, fixture)
    manifest = report.to_manifest()
    assert (manifest["authors_split"], manifest["authors_unsplit"]) == counts
    refused = manifest.get("authors_unsplit_ids")  # present only when a split was refused
    assert refused == (["H1JBMVpdx"] if counts[1] else None)


def test_a_string_with_nothing_to_count_against_is_refused(tmp_path: Path) -> None:
    note = v1_note("iclr-2017/note-authors-string-live.json")  # one string, one email
    bare = v1_clone(note, "NoEmails2017x", 3, author_emails=None)
    # another title: two refused notes would otherwise be one paper's two notes (rule 5)
    fewer = v1_clone(
        note, "TwoNamesOneX", 4, authors="Synthetic Author 1, Synthetic Author 2", title="Other."
    )
    server = FakeOpenReviewV1({"ICLR.cc/2017/conference/-/submission": [note, bare, fewer]})
    crawl = run(server, tmp_path, "ICLR", 2017)
    got = {r.native: r for r in crawl.records}
    assert got[note["id"]].authors == ("Synthetic Author 4",)
    assert got["NoEmails2017x"].authors == () and got["TwoNamesOneX"].authors == ()
    assert "no content.authorids or author_emails to count" in claim(got["NoEmails2017x"], "authors").evidence
    assert "its 1 author ids" in claim(got["TwoNamesOneX"], "authors").evidence
    assert (crawl.report.authors_split, crawl.report.authors_unsplit) == (1, 2)


@pytest.mark.parametrize(
    ("content", "count"),
    [
        ({"authorids": ["~A1", "~B1"], "author_emails": "a@x"}, 2),  # ids win over emails
        ({"author_emails": ["a@x", "b@y", "c@z"]}, 3),
        ({"author_emails": "a@x, b@y,"}, 2),  # a trailing comma is no email
        ({"author_emails": "  "}, None),
        ({}, None),
    ],
)
def test_author_count(content: dict[str, object], count: int | None) -> None:
    assert v1.author_count(content) == count


@pytest.mark.parametrize(
    ("raw", "count", "expected"),
    [
        ("A, B, and C", 3, (("A", "B", "C"), "split")),  # an Oxford comma is one separator
        ("A and B", 2, (("A", "B"), "split")),
        ("and A", 1, (("A",), "split")),
        (
            "Synthetic Ferdinand, Anand Synthetic",
            2,
            (("Synthetic Ferdinand", "Anand Synthetic"), "split"),
        ),  # `and` inside a name
        (["A", "B and C", "and D"], 4, (("A", "B", "C", "D"), "split")),
        (["A", "B and C"], 2, ((), "refused")),
        (["A", "B", "and"], 2, (("A", "B"), "split")),  # a bare trailing `and` entry is no name
        (["A and"], 1, (("A",), "split")),  # nor is a dangling ` and`
        (["A and"], 2, ((), "refused")),
        ("A And B", 1, (("A And B",), "split")),  # only lowercase `and` separates (documented, decision-019)
        (["A", "B AND C"], 5, (("A", "B AND C"), "listed")),
        ("A, and and B", 2, ((), "refused")),  # a piece still starting with `and `
        (["A", " ", 3], 5, (("A",), "listed")),  # a clean list: blanks and non-strings dropped, never counted
        (None, 1, ((), "listed")),
        ("", 1, ((), "listed")),
    ],
)
def test_split_authors_table(raw: object, count: int | None, expected: tuple[tuple[str, ...], str]) -> None:
    assert v1.split_authors(raw, count) == expected


# --- properties -------------------------------------------------------------------------------------------------

_SEPARATORS = st.sampled_from([", ", ",", ", and ", " and ", ",  and  ", " , "])
_names = st.lists(st.sampled_from(NAMES), min_size=1, max_size=8)


@st.composite
def raw_authors(draw: st.DrawFn) -> object:
    """An authors value as v1 writes one: a joined string, a list with `and`-joined or `and`-prefixed entries, or
    arbitrary text."""
    names = draw(_names)
    kind = draw(st.sampled_from(["string", "list", "text"]))
    if kind == "text":
        return draw(st.one_of(st.text(max_size=40), st.lists(st.text(max_size=12), max_size=5)))
    joined = names[0]
    for name in names[1:]:
        joined += draw(_SEPARATORS) + name
    if draw(st.booleans()):
        joined = "and " + joined
    if kind == "string":
        return joined
    return [p for p in joined.split(", ") if p] or [joined]


@given(raw_authors(), st.one_of(st.none(), st.integers(min_value=0, max_value=10)))
def test_a_split_always_has_the_id_count(raw: object, count: int | None) -> None:
    names, how = v1.split_authors(raw, count)
    if how == "split":
        assert len(names) == count
        assert all(n.strip() == n and n for n in names)
    if how == "refused":
        assert names == ()


@given(raw_authors(), st.integers(min_value=0, max_value=10))
def test_the_output_taken_again_is_listed_unchanged(raw: object, count: int) -> None:
    names, _ = v1.split_authors(raw, count)
    assert v1.split_authors(list(names), len(names)) == (names, "listed")


@given(_names)
def test_a_correct_list_is_untouched_whatever_the_count(names: list[str]) -> None:
    for count in (None, 0, len(names), len(names) + 1):
        assert v1.split_authors(names, count) == (tuple(names), "listed")
