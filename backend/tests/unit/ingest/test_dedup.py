"""Dedup: merge order, never-merge rules, precedence and the audit rows (dedup-rules skill)."""

from __future__ import annotations

import random
import unicodedata
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from openproceedings.ingest import urls
from openproceedings.ingest.dedup import (
    AS_SUBMITTED,
    CONFLICT_FIELDS,
    MIN_ABSTRACT_TOKENS,
    PRECEDENCE,
    SUBMISSION_NOTE,
    Attribution,
    Conflict,
    Merge,
    abstract_claim,
    abstract_key,
    attribution,
    dedup,
    is_creative_ai,
    resolve,
    shown_key,
    title_key,
)
from openproceedings.ingest.record import Claim, PaperRecord

T0 = datetime(2026, 9, 1, tzinfo=UTC)
T1 = datetime(2026, 9, 2, tzinfo=UTC)
T2 = datetime(2026, 9, 3, tzinfo=UTC)
H = {n: f"{n:x}" * 32 for n in range(1, 6)}


def nips(n: int) -> str:
    return f"https://proceedings.neurips.cc/paper_files/paper/2024/hash/{H[n]}-Abstract-Conference.html"


def self_url(native: str, year: int) -> str | None:
    """The proceedings URL a proceedings-id record names itself by (dedup requires one)."""
    prefix, _, rest = native.partition("-")
    if prefix == "nips" and rest.endswith(("-round1", "-round2")):  # the 2021 D&B host (TASK-118)
        sha, _, rnd = rest.partition("-")
        host = "https://datasets-benchmarks-proceedings.neurips.cc"
        return f"{host}/paper_files/paper/{year}/hash/{sha}-Abstract-{rnd}.html"
    if prefix in ("nips", "iclr"):
        host = "neurips" if prefix == "nips" else "iclr"
        return f"https://proceedings.{host}.cc/paper_files/paper/{year}/hash/{rest}-Abstract-Conference.html"
    if prefix == "pmlr":
        volume, _, key = rest.partition("-")
        return f"https://proceedings.mlr.press/{volume}/{key}.html"
    if prefix == "dblp":
        return f"https://dblp.org/rec/conf/icml/{rest}"
    return None


def paper(
    native: str,
    title: str = "Trust in AI",
    *,
    source: str = "openreview_v2",
    venue: str = "NeurIPS",
    year: int = 2024,
    track: str = "main",
    status: str = "accepted",
    abstract: str | None = None,
    fetched: datetime = T0,
    abstract_evidence: str
    | None = None,  # the abstract claim's evidence (`imported` gives a RIS row its own)
    **extra: Any,  # further claim fields, e.g. `urls_proceedings=nips(1)`
) -> PaperRecord:
    """A record whose fields are exactly what its claims say (as every importer builds them); a
    proceedings-id record names itself in `urls.proceedings` unless the caller says otherwise."""
    extra.setdefault("urls_proceedings", self_url(native, year))
    values: dict[str, Any] = {"title": title, "venue": venue, "year": year, "track": track, "status": status,
                              "abstract": abstract, **{k.replace("urls_", "urls.", 1): v for k, v in extra.items()}}  # fmt: skip
    claims = [
        Claim(field=f, value=v, source=source, fetched_at=fetched,
              evidence=abstract_evidence if f == "abstract" else None)
        for f, v in values.items() if v is not None
    ]  # type: ignore[arg-type]  # fmt: skip
    record, _ = resolve(f"op:{venue.lower()}:{year}:{native}", claims)
    return record


def own_page(native: str, year: int) -> str:
    """A RIS abstract claim's evidence as `ingest/ris.py` writes it when scholarmend read the abstract from the
    record's own page: its proceedings page, or its forum."""
    page = self_url(native, year)
    return (
        f"scholarmend:proceedings_page {page}" if page else f"scholarmend:openreview_api openreview:{native}"
    )


def imported(native: str, title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """A RIS row whose abstract is its own page's (step 3's evidence, TASK-179) unless the caller says otherwise."""
    if kw.get("abstract_evidence") is None:
        kw["abstract_evidence"] = own_page(native, kw.get("year", 2024))
    return paper(native, title, source="ris", **kw)


def resolutions(result: Any) -> list[str]:
    return [c.resolution for c in result.conflicts]


def test_title_key_is_the_token_contract() -> None:
    assert (
        title_key("Trust in AI!")
        == title_key("trust  in ai")
        == title_key("Trust in \\textbf{AI}")
        == "trust in ai"
    )
    assert title_key("—") == ""


# TASK-168: the pieces that split a title's NFC and NFD keys before the fix (a backslash, so LaTeX reads a command
# name, before a letter whose NFD starts with an ASCII one; an accent macro's braces around one), among letters
# whose canonical forms differ, marks in any order (U+0345 reorders), and plain text
_SPLITTERS = ["\\", "\\H{", "\\'{", "{", "}", "$", " ", "-"]
_ACCENTED = [chr(c) for c in range(0xC0, 0x250) if unicodedata.decomposition(chr(c))] + list("ḡǘṩẫệőŉǰ가각")
_MARKS = ["\u0301", "\u0308", "\u030b", "\u0323", "\u0345", "\u05b7", "\u0e48", "\u3099"]
_FORM_PIECES = st.one_of(
    st.sampled_from(_SPLITTERS), st.sampled_from(_ACCENTED), st.sampled_from(_MARKS), st.characters()
)


@given(st.lists(_FORM_PIECES, max_size=30).map("".join))
@example("Caf\\é")  # NFD dropped the e: `\e` was a command
@example("Erd\\H{ő}s")  # NFD's `{o\u030b}` was no accent macro
@example("\\ḡx")
@example("x \u5d69\u0345\U00010376y")  # U+0345 (ypogegrammeni, NFKC ι) before a letter
# two marks: the swapped order is canonically equivalent, so it is checked too
@example("Caf\\e\u0301\u0323 x")
@example("\u0301\u0301\ud800")  # nightly Unicode seed regression: two marks and a lone surrogate
def test_every_canonically_equivalent_title_has_one_key(title: str) -> None:
    """TASK-168: two copies of one paper that differ only in Unicode form (NFC, NFD, or marks stored in another
    canonical order) share a dedup title key, so they merge."""
    marks = [i for i, ch in enumerate(title) if unicodedata.combining(ch)]
    reordered = list(title)
    if len(marks) >= 2:  # swap two marks: canonically equivalent only when NFC says so
        # Random encodes string seeds with strict UTF-8; keep arbitrary Unicode, including surrogates.
        i, j = random.Random(title.encode("utf-8", "surrogatepass")).sample(marks, 2)
        reordered[i], reordered[j] = reordered[j], reordered[i]
    forms = {title, unicodedata.normalize("NFC", title), unicodedata.normalize("NFD", title)}
    if unicodedata.normalize("NFC", "".join(reordered)) == unicodedata.normalize("NFC", title):
        forms.add("".join(reordered))
    assert len({title_key(f) for f in forms}) == 1


@pytest.mark.parametrize(
    ("title", "key"),
    [("Caf\\é", "caf e"), ("Erd\\H{ő}s", "erdos"), ('Na\\"ive', "naive")],
)
def test_a_decomposed_title_keys_as_its_composed_form(title: str, key: str) -> None:
    assert title_key(title) == title_key(unicodedata.normalize("NFD", title)) == key


def test_the_precedence_table_is_decision_005() -> None:
    text = ("openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site",
            "ris")  # fmt: skip
    assert PRECEDENCE["status"] == (
        "iclr_archive",
        "neurips_proceedings",
        "pmlr",
        "dblp",  # decision-047: ICML 1988-2012, where no other source holds the venue-year
        "openreview_v2",
        "openreview_v1",
        "ris",
    )
    assert all(PRECEDENCE[f] == text for f in PRECEDENCE if f != "status")
    assert CONFLICT_FIELDS == ("title", "track", "status")


# --- step 1: identical ids ---------------------------------------------------------------------------


def test_same_forum_id_merges_across_the_two_searches_newest_claim_wins() -> None:
    old = paper("AbCd1234", source="ris", status="unknown", abstract="Old.", fetched=T0)
    new = paper("AbCd1234", source="ris", status="accepted", abstract="New.", fetched=T1)
    result = dedup([new, old])
    [r] = result.records
    assert (r.status, r.abstract) == ("accepted", "New.")
    assert result.merges == (Merge(r.id, r.id, "forum_id", "AbCd1234", "NeurIPS", 2024, "ris"),)
    # every field that changed between the searches is visible, not just the conflict fields
    assert set(result.conflicts) == {
        Conflict(r.id, "status", "accepted", "ris", "unknown", "ris", "newest:ris"),
        Conflict(r.id, "abstract", "New.", "ris", "Old.", "ris", "newest:ris"),
    }


def test_same_moment_disagreement_is_a_tie_not_newest() -> None:
    result = dedup(
        [
            paper("AbCd1234", source="ris", status="accepted"),
            paper("AbCd1234", source="ris", status="unknown"),
        ]
    )
    assert resolutions(result) == ["tie:ris"]


def test_newest_is_by_fetch_time_not_by_claim_url() -> None:
    base = paper("AbCd1234", source="ris")
    old = Claim(field="urls.pdf", value="https://x/old.pdf", source="ris", url="https://z", fetched_at=T0)
    new = Claim(field="urls.pdf", value="https://x/new.pdf", source="ris", url="https://a", fetched_at=T1)
    merged, rows = resolve(base.id, [*base.provenance, old, new])
    assert merged.urls.pdf == "https://x/new.pdf"
    assert [r.resolution for r in rows] == ["newest:ris"]


def test_a_tie_between_values_that_print_alike_is_still_a_tie() -> None:
    a = paper("AbCd1234", source="ris", authors=("Smith; J",))
    b = paper("AbCd1234", source="ris", authors=("Smith", "J"))
    result = dedup([a, b])
    assert [(c.field, c.resolution) for c in result.conflicts] == [("authors", "tie:ris")]
    assert dedup([b, a]) == result


def test_newest_is_by_fetch_time_not_by_url() -> None:
    old = paper("AbCd1234", source="ris", fetched=T0, urls_pdf="https://z.example/old.pdf")
    new = paper("AbCd1234", source="ris", fetched=T1, urls_pdf="https://a.example/new.pdf")
    [r] = dedup([old, new]).records
    assert r.urls.pdf == "https://a.example/new.pdf"


def test_same_proceedings_id_merges() -> None:
    result = dedup(
        [paper(f"nips-{H[1]}", source="ris", fetched=T0), paper(f"nips-{H[1]}", source="ris", fetched=T1)]
    )
    assert len(result.records) == 1
    assert [(m.rule, m.key) for m in result.merges] == [("native_id", f"nips-{H[1]}")]


def test_same_forum_id_in_different_years_is_not_merged() -> None:
    result = dedup([paper("AbCd1234", year=2023), paper("AbCd1234", year=2024), paper("AbCd1234", year=2025)])
    assert len(result.records) == 3 and not result.merges
    assert [(c.field, c.value_b, c.resolution) for c in result.conflicts] == [
        ("forum_id", "op:neurips:2024:AbCd1234", "venue_year_not_merged"),
        ("forum_id", "op:neurips:2025:AbCd1234", "venue_year_not_merged"),
    ]


# --- step 2: title, venue, year across sources --------------------------------------------------------


def test_openreview_and_proceedings_merge_on_title_with_precedence() -> None:
    orv = paper("AbCd1234", "Trust in AI", status="rejected", abstract="OpenReview abstract.")
    proc = paper(
        f"nips-{H[1]}", "Trust in \\textbf{AI}", source="neurips_proceedings", abstract="Proc abstract."
    )
    result = dedup([proc, orv])
    [r] = result.records
    assert r.id == orv.id  # the forum id survives
    assert (r.title, r.abstract) == ("Trust in AI", "OpenReview abstract.")  # OpenReview first for text
    assert r.status == "accepted"  # the proceedings decide acceptance
    assert {c.source for c in r.provenance} == {"openreview_v2", "neurips_proceedings"}  # every claim kept
    assert result.merges == (
        Merge(orv.id, proc.id, "title_venue_year", "trust in ai", "NeurIPS", 2024, "neurips_proceedings"),
    )
    # the titles differ only in markup (same key): no title row, per decision-005
    assert [(c.field, c.resolution) for c in result.conflicts] == [
        ("status", "precedence:neurips_proceedings")
    ]


def test_a_real_title_difference_is_a_conflict_row() -> None:
    orv = paper("AbCd1234", "Trust in AI")
    result = dedup([orv, paper("AbCd1234", "Trust in Machines", source="ris")])
    expected = Conflict(
        orv.id,
        "title",
        "Trust in AI",
        "openreview_v2",
        "Trust in Machines",
        "ris",
        "precedence:openreview_v2",
    )
    assert expected in result.conflicts


def test_openreview_track_beats_the_proceedings_track() -> None:
    result = dedup([paper("AbCd1234", track="position"), paper(f"nips-{H[1]}", source="neurips_proceedings")])
    [r] = result.records
    assert r.track == "position"
    assert ("track", "precedence:openreview_v2") in [(c.field, c.resolution) for c in result.conflicts]


def test_datasets_track_merges_into_proceedings() -> None:
    result = dedup([paper("AbCd1234", track="datasets_benchmarks"),
                    paper(f"nips-{H[1]}", source="neurips_proceedings", track="datasets_benchmarks")])  # fmt: skip
    assert len(result.records) == 1


# --- decision-005 §Track: "on OpenReview" is per track (owner, 2026-09-29; TASK-130) --------------------------

ARXIV = "https://arxiv.org/abs/1511.06644"


def archive(year: int = 2016, title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """An ICLR archive main-track listing, named as the archive names it (an arXiv target's `iclr-` id)."""
    target = urls.iclr_archive_target(ARXIV)
    assert target is not None
    return paper(
        target[0], title, source="iclr_archive", venue="ICLR", year=year, urls_proceedings=ARXIV, **kw
    )


def test_iclr_2016_main_from_the_archive_keeps_main() -> None:
    # OpenReview holds only ICLR 2016's workshop track: its notes carry no decision (status unknown)
    ws = dict(venue="ICLR", year=2016, source="openreview_v1", track="workshop", status="unknown")
    listing, same_title, other = (
        archive(),
        paper("AbCd1234", **ws),
        paper("EfGh5678", "A workshop paper", **ws),
    )
    result = dedup([listing, same_title, other])
    got = {r.id: (r.track, r.status) for r in result.records}
    assert got == {listing.id: ("main", "accepted"), same_title.id: ("workshop", "unknown"),
                   other.id: ("workshop", "unknown")}  # fmt: skip
    assert result.merges == () and "track_not_merged" in resolutions(result)
    assert not [
        c for c in result.conflicts if c.field == "track"
    ]  # no track claim competes with the archive's


@pytest.mark.parametrize(
    ("or_source", "venue", "year", "or_track", "listing", "listing_track"),
    [
        ("openreview_v2", "NeurIPS", 2023, "datasets_benchmarks", "neurips_proceedings", "main"),
        ("openreview_v1", "NeurIPS", 2022, "main", "neurips_proceedings", "datasets_benchmarks"),
        ("openreview_v2", "ICML", 2025, "position", "pmlr", "unknown"),  # a mixed volume says no track
        ("openreview_v1", "ICLR", 2014, "main", "iclr_archive", "main"),  # the archive agrees: no row
    ],
)
def test_where_openreview_holds_the_track_its_claim_beats_the_proceedings(
    or_source: str, venue: str, year: int, or_track: str, listing: str, listing_track: str
) -> None:
    note = paper("AbCd1234", source=or_source, venue=venue, year=year, track=or_track)
    if listing == "iclr_archive":
        proc = archive(year)
    else:
        native = "pmlr-v267-key1" if listing == "pmlr" else f"nips-{H[1]}"
        proc = paper(native, source=listing, venue=venue, year=year, track=listing_track)
    result = dedup([proc, note])
    [r] = result.records
    assert (r.id, r.track, r.status) == (note.id, or_track, "accepted")
    rows = [
        (c.value_a, c.source_a, c.value_b, c.source_b, c.resolution)
        for c in result.conflicts
        if c.field == "track"
    ]
    expected = [(or_track, or_source, listing_track, listing, f"precedence:{or_source}")]
    assert rows == (expected if or_track != listing_track else [])
    assert dedup(result.records) == dedup(result.records[::-1])
    assert dedup(result.records).records == result.records  # idempotent


def test_a_listing_openreview_does_not_hold_keeps_its_own_track_in_a_track_openreview_holds() -> None:
    # NeurIPS 2025: OpenReview holds Creative AI (`other`) and D&B, but not these two papers (one renamed for the
    # camera-ready): the listings answer their own track; the note under the old title stays a record of its own
    db = dict(venue="NeurIPS", year=2025, track="datasets_benchmarks")
    creative = creative_listing(title="A Creative AI piece")
    renamed = paper(f"nips-{H[2]}", "The camera-ready title", source="neurips_proceedings", **db)
    note = paper("AbCd1234", "The submitted title", **db)
    result = dedup([creative, renamed, note])
    assert {r.id: r.track for r in result.records} == {
        creative.id: "other",
        renamed.id: "datasets_benchmarks",
        note.id: "datasets_benchmarks",
    }
    assert result.merges == () and result.conflicts == ()


def test_an_openreview_note_with_no_track_never_merges_into_a_listing() -> None:
    # `unknown` names no track OpenReview holds; dedup keeps the note apart, so it never overrules the listing
    listing = paper(f"nips-{H[1]}", source="neurips_proceedings")
    note = paper("AbCd1234", track="unknown")
    result = dedup([listing, note])
    assert {r.id: r.track for r in result.records} == {listing.id: "main", note.id: "unknown"}
    assert resolutions(result) == ["track_not_merged"]


OLD_PDF = f"https://papers.nips.cc/paper/2021/file/{H[2]}-Paper.pdf"


@pytest.mark.parametrize(
    "bridge",
    [
        [
            paper("AbCd1234", source="openreview_v1", track="unknown"),
            paper("AbCd1234", source="ris", urls_pdf=OLD_PDF),
        ],
        [paper("AbCd1234", source="openreview_v1", track="unknown", urls_pdf=OLD_PDF)],
        [paper("AbCd1234", source="openreview_v2", track="unknown", urls_proceedings=nips(2))],
    ],
    ids=["ris-row-names-it", "note-names-it-v1", "note-names-it-v2"],
)
def test_a_note_with_no_track_never_merges_into_a_listing_it_names(bridge: list[PaperRecord]) -> None:
    """TASK-174: a same-id RIS row, or the note itself, naming the listing's paper makes the note's cluster a
    listing, but its `unknown` is still the note's (OpenReview's track claim), not a listing's own: it stays apart."""
    listing = paper(f"nips-{H[2]}", source="neurips_proceedings")
    result = dedup([listing, *bridge])
    note = bridge[0].id
    assert {r.id: r.track for r in result.records} == {listing.id: "main", note: "unknown"}
    assert [(m.rule, m.merged_id) for m in result.merges] == [("forum_id", note)] * (len(bridge) - 1)
    assert ("title_key", note, listing.id, "track_not_merged") in {
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts
    }


def test_a_main_note_bridged_by_a_ris_row_still_merges_into_its_listing() -> None:
    """The other side of TASK-174: OpenReview's `main` is a proceedings track, so the bridge merges and keeps it."""
    listing = paper(f"nips-{H[2]}", source="neurips_proceedings")
    note = paper("AbCd1234", source="openreview_v1")
    ris = paper("AbCd1234", source="ris", track="unknown", urls_pdf=OLD_PDF)
    (merged,) = dedup([listing, note, ris]).records
    assert (merged.id, merged.track) == (note.id, "main")


@pytest.mark.parametrize(
    ("why", "a", "b"),
    [
        ("different year", paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings", year=2023)),
        (
            "different venue",
            paper("AbCd1234", venue="ICLR"),
            paper(f"nips-{H[1]}", source="neurips_proceedings"),
        ),
        (
            "different title",
            paper("AbCd1234", "Trust"),
            paper(f"nips-{H[1]}", "Reliance", source="neurips_proceedings"),
        ),
        ("empty title key", paper("AbCd1234", "—"), paper(f"nips-{H[1]}", "—", source="neurips_proceedings")),
    ],
)
def test_no_shared_key_never_merges(why: str, a: PaperRecord, b: PaperRecord) -> None:
    result = dedup([a, b])
    assert len(result.records) == 2 and not result.merges and not result.conflicts


@pytest.mark.parametrize(
    ("why", "records", "resolution"),
    [
        (
            "two OpenReview submissions with one title",
            [paper("AbCd1234"), paper("EfGh5678")],
            "ambiguous_not_merged",
        ),
        (
            "different forum ids across sources",
            [paper("AbCd1234"), paper("EfGh5678", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "two proceedings ids across sources",
            [paper(f"nips-{H[1]}", source="neurips_proceedings"), paper(f"nips-{H[2]}", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "a proceedings URL on the OpenReview side names another paper",
            [paper("AbCd1234", urls_proceedings=nips(1)), paper(f"nips-{H[2]}", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "a workshop paper into a proceedings source",
            [paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="neurips_proceedings")],
            "track_not_merged",
        ),
        (
            "a workshop paper into a RIS proceedings listing",
            [paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="ris")],
            "track_not_merged",
        ),
        (
            "an unknown track waits for evidence",
            [
                paper("AbCd1234", source="ris", track="unknown"),
                paper(f"nips-{H[1]}", source="neurips_proceedings"),
            ],
            "track_not_merged",
        ),
    ],
)
def test_never_merge(why: str, records: list[PaperRecord], resolution: str) -> None:
    result = dedup(records)
    assert len(result.records) == len(records) and not result.merges
    assert set(resolutions(result)) == {resolution}


def db21(native: str, title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """A NeurIPS 2021 Datasets and Benchmarks record (TASK-118: its D&B-host ids carry the round)."""
    kw.setdefault("source", "neurips_proceedings")
    return paper(native, title, year=2021, track=kw.pop("track", "datasets_benchmarks"), **kw)


def test_a_round_qualified_db_listing_merges_with_its_openreview_submission() -> None:
    result = dedup([db21("AbCd1234", source="openreview_v1"), db21(f"nips-{H[1]}-round1")])
    [r] = result.records
    assert r.id == "op:neurips:2021:AbCd1234" and len(result.merges) == 1


# equal titles: main↔round1 and main↔round2 each refused; different titles: only the two rounds (whose
# titles still match each other) are refused
@pytest.mark.parametrize(("title_b", "refused"), [("Trust in AI", 2), ("Reliance on AI", 1)])
def test_one_hash_on_the_main_host_and_in_each_db_round_is_three_papers(title_b: str, refused: int) -> None:
    """md5 of a per-site paper number: the same hash names a main-track paper and one paper per D&B round.
    The sources differ, so the title step does run; it refuses each title match (two proceedings ids)."""
    records = [
        db21(f"nips-{H[1]}", track="main", source="ris"),
        db21(f"nips-{H[1]}-round1", title_b),
        db21(f"nips-{H[1]}-round2", title_b),
    ]
    result = dedup(records)
    assert sorted(r.id for r in result.records) == sorted(r.id for r in records) and not result.merges
    assert [(c.field, c.resolution) for c in result.conflicts] == [
        ("title_key", "ambiguous_not_merged")
    ] * refused


def test_an_openreview_record_naming_the_main_host_hash_is_not_merged_into_the_db_paper() -> None:
    main_url = f"https://proceedings.neurips.cc/paper_files/paper/2021/hash/{H[1]}-Abstract.html"
    result = dedup([db21("AbCd1234", source="openreview_v1", urls_proceedings=main_url),
                    db21(f"nips-{H[1]}-round1")])  # fmt: skip
    assert len(result.records) == 2 and not result.merges
    assert set(resolutions(result)) == {"ambiguous_not_merged"}


def test_three_way_with_two_proceedings_ids_is_refused() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[2]}", source="ris")])  # fmt: skip
    assert len(result.records) == 3 and not result.merges


def test_two_candidates_from_one_source_are_ambiguous() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[2]}", source="neurips_proceedings")])  # fmt: skip
    assert len(result.records) == 3 and not result.merges
    assert set(resolutions(result)) == {"ambiguous_not_merged"}


def test_three_sources_merge_into_one_and_merges_csv_shows_each_rule() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[1]}", source="ris")])  # fmt: skip
    [r] = result.records
    assert r.id == "op:neurips:2024:AbCd1234"
    proc = f"op:neurips:2024:nips-{H[1]}"
    assert [(m.survivor_id, m.merged_id, m.rule) for m in result.merges] == [
        (r.id, proc, "title_venue_year"),  # the proceedings cluster joins the OpenReview record
        (proc, proc, "native_id"),  # its two copies (proceedings crawl and RIS) were one id first
    ]


# --- TASK-126: a cluster that cannot be the listed paper is no rival -----------------------------------


def test_a_same_title_workshop_paper_does_not_block_the_main_track_merge() -> None:
    """NeurIPS 2023/2024: a proceedings listing, its main-track note and an accepted workshop note of the
    same title. The workshop note can never be the listed paper (the track rule), so the pair merges."""
    orv, proc = paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings")
    workshop = paper("EfGh5678", track="workshop")
    result = dedup([workshop, proc, orv])
    assert sorted(r.id for r in result.records) == sorted([orv.id, workshop.id])
    assert result.merges == (
        Merge(orv.id, proc.id, "title_venue_year", "trust in ai", "NeurIPS", 2024, "neurips_proceedings"),
    )
    assert [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        ("title_key", orv.id, workshop.id, "track_not_merged")
    ]
    again = dedup(result.records)
    assert (again.records, again.conflicts, again.merges) == (result.records, result.conflicts, ())


def test_a_rejected_round_one_note_does_not_block_its_accepted_resubmission() -> None:
    """NeurIPS 2021 D&B: a round-1 rejection resubmitted (another forum, another pdf) and accepted in round
    2. Proceedings list only accepted papers, so the rejected note is no rival for the listing."""
    accepted = db21("AbCd1234", source="openreview_v1")
    rejected = db21("EfGh5678", source="openreview_v1", status="rejected")
    listing = db21(f"nips-{H[1]}-round2")
    result = dedup([rejected, listing, accepted])
    assert sorted(r.id for r in result.records) == sorted([accepted.id, rejected.id])
    assert [(m.survivor_id, m.merged_id) for m in result.merges] == [(accepted.id, listing.id)]
    assert [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        ("title_key", accepted.id, rejected.id, "ambiguous_not_merged")
    ]
    assert dedup(result.records).records == result.records


@pytest.mark.parametrize("status", ["rejected", "withdrawn", "desk_rejected"])
def test_every_not_accepted_status_is_no_rival(status: str) -> None:
    result = dedup([paper("AbCd1234"), paper("EfGh5678", status=status),
                    paper(f"nips-{H[1]}", source="neurips_proceedings")])  # fmt: skip
    assert [(m.survivor_id, m.rule) for m in result.merges] == [
        ("op:neurips:2024:AbCd1234", "title_venue_year")
    ]


@pytest.mark.parametrize(
    ("why", "rival"),
    [
        ("two accepted main-track submissions", paper("EfGh5678")),
        (
            "an accepted D&B submission",
            paper("EfGh5678", source="openreview_v1", track="datasets_benchmarks"),
        ),
        ("a status nobody knows yet: it may be the listed paper", paper("EfGh5678", status="unknown")),
        ("a track nobody knows yet: it may be the listed paper", paper("EfGh5678", track="unknown")),
        ("a rejected note that is itself a listing", paper(f"nips-{H[2]}", source="ris", status="rejected")),
    ],
)
def test_a_rival_that_may_be_the_listed_paper_still_refuses(why: str, rival: PaperRecord) -> None:
    records = [paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"), rival]
    result = dedup(records)
    assert len(result.records) == 3 and not result.merges
    assert result.conflicts and all(c.resolution.endswith("_not_merged") for c in result.conflicts)


def test_a_rejected_note_alone_still_merges_with_its_listing() -> None:
    """Only a rival is set aside: a lone OpenReview note the proceedings list merges, and the proceedings
    decide its status (decision-005)."""
    result = dedup(
        [paper("EfGh5678", status="rejected"), paper(f"nips-{H[1]}", source="neurips_proceedings")]
    )
    [r] = result.records
    assert r.status == "accepted"


def test_without_a_listing_nothing_is_set_aside() -> None:
    main, workshop, rejected = (
        paper("AbCd1234"),
        paper("EfGh5678", track="workshop"),
        paper("IjKl9012", status="rejected", source="ris"),
    )
    result = dedup([main, workshop, rejected])
    assert len(result.records) == 3 and not result.merges
    assert [(c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        (main.id, workshop.id, "ambiguous_not_merged"),
        (main.id, rejected.id, "ambiguous_not_merged"),
    ]


def test_a_rejected_note_chained_back_in_by_a_second_key_splits_the_chain() -> None:
    """The rejected note is set aside on "Trust in AI" but shares "Trust in Machines" with the listing,
    where it would merge alone (status is no bar to `_mergeable`). The chain re-check refuses the whole
    chain on forum ids (every non-listing record has its own; here a shared source too), so nothing merges: the safe direction."""
    accepted = paper("AbCd1234", "Trust in AI")
    listing = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
               paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    rejected = [paper("EfGh5678", "Trust in AI", source="openreview_v1", status="rejected"),
                paper("EfGh5678", "Trust in Machines", status="rejected")]  # fmt: skip
    result = dedup([*rejected, *listing, accepted])
    lid, rid = listing[0].id, rejected[0].id
    assert sorted(r.id for r in result.records) == sorted([accepted.id, lid, rid])
    assert sorted(m.rule for m in result.merges) == ["forum_id", "native_id"]  # step 1 only
    rows = {(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts}
    assert ("title_key", lid, rid, "ambiguous_not_merged") in rows  # the set-aside note keeps its row
    assert dedup(result.records).records == result.records


def test_a_workshop_note_set_aside_on_one_key_never_chains_in_on_another() -> None:
    """The workshop note is set aside on "Trust in AI" and also shares "Trust in Machines" with the
    listing; that key's group meets the same track rule, so it never chains in and the pair still merges."""
    accepted = paper("AbCd1234", "Trust in AI")
    listing = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
               paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    workshop = [paper("EfGh5678", "Trust in AI", source="openreview_v1", track="workshop"),
                paper("EfGh5678", "Trust in Machines", track="workshop")]  # fmt: skip
    result = dedup([*workshop, *listing, accepted])
    wid = workshop[0].id
    assert sorted(r.id for r in result.records) == sorted([accepted.id, wid])
    assert (accepted.id, listing[0].id, "title_venue_year") in [
        (m.survivor_id, m.merged_id, m.rule) for m in result.merges
    ]
    assert [
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts if c.field == "title_key"
    ] == [("title_key", accepted.id, wid, "track_not_merged")]  # one row, though the two share both keys
    assert dedup(result.records).records == result.records


def test_keys_that_chain_forbidden_clusters_merge_nothing() -> None:
    # One paper known under two titles (OpenReview and RIS share its forum id); each title matches a
    # different proceedings record. Each pair is fine alone, but together two proceedings records would
    # fold into one paper.
    orv = paper("AbCd1234", "Trust in AI")
    ris = paper("AbCd1234", "Trust in Machines", source="ris")
    p1 = paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings")
    p2 = paper(f"nips-{H[2]}", "Trust in Machines", source="neurips_proceedings")
    result = dedup([orv, ris, p1, p2])
    assert sorted(r.id for r in result.records) == sorted({orv.id, p1.id, p2.id})
    assert [m.rule for m in result.merges] == ["forum_id"]
    assert ("title_key_chain", "ambiguous_not_merged") in [(c.field, c.resolution) for c in result.conflicts]


def test_a_merge_row_names_the_first_shared_key() -> None:
    # both clusters carry both titles, so they share two keys; merges.csv names the first, in key order
    orv = [paper("AbCd1234", "Trust in Machines"), paper("AbCd1234", "Trust in AI", source="openreview_v1")]
    proc = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
            paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    result = dedup([*orv, *proc])
    [title] = [m for m in result.merges if m.rule == "title_venue_year"]
    assert title.key == "trust in ai"


def test_a_superseded_title_is_reported_not_matched() -> None:
    # Matching on the older title would merge here but not on a second run (the merged record no longer
    # carries it), so it stays a duplicate, the safe direction, with the old title in conflicts.csv.
    old = paper(f"nips-{H[1]}", "Old Title", source="ris", fetched=T0)
    new = paper(f"nips-{H[1]}", "New Title", source="ris", fetched=T1)
    result = dedup([old, new, paper("AbCd1234", "Old Title")])
    assert len(result.records) == 2
    assert ("title", "New Title", "Old Title", "newest:ris") in [
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts
    ]


def test_conflicts_survive_a_rerun() -> None:
    once = dedup([paper("AbCd1234", status="rejected"), paper(f"nips-{H[1]}", source="neurips_proceedings")])
    twice = dedup(once.records)
    precedence = [c for c in once.conflicts if c.resolution.startswith("precedence:")]
    assert precedence and [c for c in twice.conflicts if c.resolution.startswith("precedence:")] == precedence


def test_a_proceedings_record_must_name_itself() -> None:
    with pytest.raises(ValueError, match="name itself"):
        dedup([paper(f"nips-{H[1]}", source="neurips_proceedings", urls_proceedings=None)])
    with pytest.raises(ValueError, match="name itself"):
        dedup([paper(f"nips-{H[1]}", source="neurips_proceedings", urls_proceedings=nips(2))])


def test_a_merged_record_remembers_the_listing_it_absorbed() -> None:
    # nips-1 merges into the forum record; on a second run the merged record must still refuse nips-2
    xs = [
        paper("AbCd1234", "Trust in AI"),
        paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
        paper(f"nips-{H[1]}", "Trust in Machines", source="ris"),
        paper(f"nips-{H[2]}", "Trust in Machines", source="openreview_v1"),
    ]
    once = dedup(xs)
    assert dedup(once.records).records == once.records
    assert len(once.records) == 2


def test_icml_papers_merge_with_a_mixed_pmlr_volume() -> None:
    orv = paper("AbCd1234", venue="ICML", track="main")
    pmlr = paper("pmlr-v235-smith24a", venue="ICML", source="pmlr", track="unknown")
    [r] = dedup([orv, pmlr]).records
    assert (r.id, r.track) == (orv.id, "main")  # OpenReview's track, the volume's unknown overruled
    workshop = paper("AbCd1234", venue="ICML", track="workshop")
    assert len(dedup([workshop, pmlr]).records) == 2  # but a workshop paper still never joins it


def test_an_old_style_proceedings_url_names_its_paper() -> None:
    old = "https://proceedings.neurips.cc/paper/2021/file/" + H[2].upper() + "-Paper.pdf"
    orv = paper("AbCd1234", year=2021, urls_pdf=old)
    proc = paper(f"nips-{H[1]}", source="neurips_proceedings", year=2021)
    assert len(dedup([orv, proc]).records) == 2  # the forum's PDF is another NeurIPS paper
    hexed = "abcdef" * 5 + "ab"
    upper = f"https://proceedings.neurips.cc/paper/2021/file/{hexed.upper()}-Paper.pdf"
    listing = paper(f"nips-{hexed}", source="neurips_proceedings", year=2021)
    same = paper("AbCd1234", year=2021, urls_pdf=upper)
    assert len(dedup([same, listing]).records) == 1  # upper-case hex names the same paper


# --- TASK-137: a NeurIPS Creative AI listing merges with its own Creative AI note ------------------------


def creative_url(n: int = 1, year: int = 2025, token: str = "Creative_AI_Track") -> str:
    return f"https://proceedings.neurips.cc/paper_files/paper/{year}/hash/{H[n]}-Abstract-{token}.html"


def creative_listing(n: int = 1, title: str = "Trust in AI", source: str = "neurips_proceedings",
                     **kw: Any) -> PaperRecord:  # fmt: skip
    """A NeurIPS 2025 Creative AI listing, as the proceedings crawler (or the RIS importer) builds one."""
    kw.setdefault("urls_proceedings", creative_url(n))
    return paper(f"nips-{H[n]}", title, source=source, year=2025, track="other", **kw)


def creative_note(fid: str = "AbCd1234", title: str = "Trust in AI", status: str = "unknown",
                  venueid: str = "NeurIPS.cc/2025/Creative_AI_Track", **kw: Any) -> PaperRecord:  # fmt: skip
    """A Creative AI OpenReview note: a bare-path `other` venueid is status `unknown` (openreview-venueids)."""
    kw.setdefault("track", "other")
    return paper(fid, title, year=2025, status=status, venue_id_raw=venueid, **kw)


def test_a_creative_ai_listing_merges_with_its_own_note() -> None:
    listing, note = creative_listing(), creative_note()
    assert is_creative_ai(listing) and is_creative_ai(note)
    result = dedup([listing, note])
    [r] = result.records
    assert (r.id, r.track, r.status) == (note.id, "other", "accepted")  # the proceedings decide acceptance
    assert r.venue_id_raw == "NeurIPS.cc/2025/Creative_AI_Track" and is_creative_ai(r)
    assert result.merges == (
        Merge(note.id, listing.id, "title_venue_year", "trust in ai", "NeurIPS", 2025, "neurips_proceedings"),
    )
    assert [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        ("status", "accepted", "unknown", "precedence:neurips_proceedings")
    ]
    assert dedup(result.records).records == result.records
    assert dedup([note, listing]) == result


def test_a_creative_ai_listing_its_ris_copy_and_its_note_are_one_record() -> None:
    xs = [creative_listing(), creative_listing(source="ris", fetched=T1), creative_note()]
    [r] = dedup(xs).records
    assert r.track == "other" and r.status == "accepted"


def test_a_rejected_creative_ai_note_alone_merges_and_the_proceedings_decide() -> None:
    venueid = "NeurIPS.cc/2025/Creative_AI_Track/Rejected_Submission"
    [r] = dedup([creative_listing(), creative_note(status="rejected", venueid=venueid)]).records
    assert r.status == "accepted"  # as for a main-track note (decision-005)


@pytest.mark.parametrize(
    ("why", "records"),
    [
        (
            "an Education_Program note (the other NeurIPS 2025 `other`) into a Creative AI listing",
            [creative_listing(), creative_note(venueid="NeurIPS.cc/2025/Education_Program")],
        ),
        ("an `other` note with no venueid into a Creative AI listing",
         [creative_listing(), paper("AbCd1234", year=2025, track="other", status="unknown")]),
        ("a note whose venueid names another year",
         [creative_listing(), creative_note(venueid="NeurIPS.cc/2024/Creative_AI_Track")]),
        ("a Creative AI note into a main-track listing",
         [paper(f"nips-{H[1]}", source="neurips_proceedings", year=2025), creative_note()]),
        ("a main-track note into a Creative AI listing",
         [creative_listing(), paper("AbCd1234", year=2025)]),
        ("a Creative AI listing whose URL is from another year",
         [creative_listing(urls_proceedings=creative_url(year=2024)), creative_note()]),
        ("a note whose own evidence disagrees: a Creative AI URL but an Education_Program venueid",
         [creative_listing(),
          creative_note(venueid="NeurIPS.cc/2025/Education_Program", urls_pdf=creative_url(1).replace("Abstract", "Paper").replace(".html", ".pdf"))]),
        ("an `other` listing whose URL names the main conference",
         [creative_listing(urls_proceedings=creative_url(token="Conference")), creative_note()]),
        ("a workshop note into a Creative AI listing", [creative_listing(), creative_note(track="workshop")]),
        ("a note of unknown track into a Creative AI listing", [creative_listing(), creative_note(track="unknown")]),
        ("a Creative AI note and a listing from ICLR",
         [paper(f"iclr-{H[1]}", source="iclr_archive", venue="ICLR", year=2025, track="other"),
          paper("AbCd1234", venue="ICLR", year=2025, track="other", status="unknown",
                venue_id_raw="NeurIPS.cc/2025/Creative_AI_Track")]),
    ],
)  # fmt: skip
def test_creative_ai_never_merges_across_the_track_rule(why: str, records: list[PaperRecord]) -> None:
    result = dedup(records)
    assert len(result.records) == 2 and not result.merges
    assert resolutions(result) == ["track_not_merged"]


@pytest.mark.parametrize("track", ["workshop", "tiny_papers", "blogpost", "competition", "other", "unknown"])
@pytest.mark.parametrize("listing", ["main", "creative_ai"])
def test_no_other_track_merges_into_a_listing(track: str, listing: str) -> None:
    """Every other never-merge rule stands: only Creative AI evidence admits `other`, and only beside Creative AI."""
    lst = (
        creative_listing()
        if listing == "creative_ai"
        else paper(f"nips-{H[1]}", source="neurips_proceedings", year=2025)
    )
    note = paper("AbCd1234", year=2025, track=track, status="accepted")
    result = dedup([lst, note])
    assert len(result.records) == 2 and resolutions(result) == ["track_not_merged"]


def test_same_title_rivals_of_another_family_are_set_aside_both_ways() -> None:
    """A Creative AI listing beside a main listing's title (TASK-126's set-aside, per family): each listing merges
    with its own family's note; a workshop, Education_Program or other-family note stays apart with its row."""
    listing, note = creative_listing(), creative_note()
    main_note = paper("EfGh5678", year=2025)
    workshop = paper("IjKl9012", year=2025, track="workshop")
    education = creative_note("MnOp3456", venueid="NeurIPS.cc/2025/Education_Program")
    result = dedup([listing, note, main_note, workshop, education])
    assert [(m.survivor_id, m.merged_id) for m in result.merges] == [(note.id, listing.id)]
    rows = [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts if c.field == "title_key"]
    assert rows == [
        ("title_key", note.id, x.id, "track_not_merged") for x in (main_note, workshop, education)
    ]
    again = dedup(result.records)
    assert (again.records, again.conflicts, again.merges) == (result.records, result.conflicts, ())
    # and the other way round: a main listing and its note merge past a same-title Creative AI note
    main_listing = paper(f"nips-{H[2]}", source="neurips_proceedings", year=2025)
    result = dedup([main_listing, main_note, note])
    assert [(m.survivor_id, m.merged_id) for m in result.merges] == [(main_note.id, main_listing.id)]
    assert [(c.value_b, c.resolution) for c in result.conflicts if c.field == "title_key"] == [
        (note.id, "track_not_merged")
    ]


def test_two_creative_ai_notes_for_one_listing_are_ambiguous() -> None:
    result = dedup([creative_listing(), creative_note(), creative_note("EfGh5678")])
    assert len(result.records) == 3 and not result.merges
    assert set(resolutions(result)) == {"ambiguous_not_merged"}


# --- the forum link (TASK-105): a proceedings listing that names its OpenReview forum ------------------


def forum(fid: str) -> str:
    return f"https://openreview.net/forum?id={fid}"


def linked(key: str = "key1", fid: str = "AbCd1234", title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """A PMLR v235 listing whose index links the OpenReview forum `fid` (track unknown: v235 mixes tracks)."""
    kw.setdefault("track", "unknown")
    return paper(
        f"pmlr-v235-{key}", title, source="pmlr", venue="ICML", year=2024, urls_forum=forum(fid), **kw
    )


def icml(fid: str = "AbCd1234", title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    kw.setdefault("venue", "ICML")
    return paper(fid, title, urls_forum=forum(fid), **kw)


@pytest.mark.parametrize(
    ("url", "fid"),
    [
        (forum("AbCd1234"), "AbCd1234"),
        ("http://OpenReview.net/forum?id=AbCd1234", "AbCd1234"),  # any host case, http
        ("https://openreview.net/forum?id=AbCd1234&noteId=XyZ9876", "AbCd1234"),  # a reply anchor
        ("https://openreview.net/forum?id=false", "false"),  # the shape is all a URL can check
        ("https://openreview.net/pdf?id=AbCd1234", None),  # the PDF, not the forum
        ("https://openreview.net/forum?id=AbCd1234&id=EfGh5678", None),  # two ids: which one?
        ("https://openreview.net/forum?id=a", None),  # too short for a forum id
        ("https://openreview.net/forum", None),
        ("https://api2.openreview.net/forum?id=AbCd1234", None),
        ("https://example.org/forum?id=AbCd1234", None),
        ("ftp://openreview.net/forum?id=AbCd1234", None),
    ],
)
def test_forum_id_from_a_url(url: str, fid: str | None) -> None:
    assert urls.forum_id(url) == fid


def test_the_link_merges_whatever_the_titles_say() -> None:
    orv, listing = icml(title="Trust in AI", status="rejected"), linked(title="Reliance on machines")
    result = dedup([listing, orv])
    [r] = result.records
    assert r.id == orv.id  # the forum id survives
    assert (r.title, r.track, r.status) == ("Trust in AI", "main", "accepted")  # decision-005 precedence
    assert r.urls.proceedings == "https://proceedings.mlr.press/v235/key1.html"
    assert result.merges == (Merge(orv.id, listing.id, "forum_link", "AbCd1234", "ICML", 2024, "pmlr"),)
    assert set(resolutions(result)) == {"precedence:openreview_v2", "precedence:pmlr"}  # title, status
    again = dedup(result.records)
    assert again.records == result.records and not again.merges


def test_the_link_comes_before_the_title_and_joins_every_copy() -> None:
    """The OpenReview note, its RIS copy and the linked listing: one record, every step in merges.csv."""
    orv = icml()
    result = dedup(
        [orv, paper("AbCd1234", "Trust in AI!", source="ris", venue="ICML"), linked(title="Other")]
    )
    assert [r.id for r in result.records] == [orv.id]
    assert [(m.survivor_id, m.merged_id, m.rule) for m in result.merges] == [
        (orv.id, orv.id, "forum_id"),  # the RIS copy of the same id
        (orv.id, "op:icml:2024:pmlr-v235-key1", "forum_link"),
    ]


@pytest.mark.parametrize(
    ("why", "records", "field", "resolution"),
    [
        (
            "the link names another year",
            [icml(year=2023), linked()],
            "forum_id",
            "venue_year_not_merged",
        ),
        (
            "the link names another venue",
            [icml(venue="ICLR"), linked()],
            "forum_id",
            "venue_year_not_merged",
        ),
        (
            "the linked note is a workshop paper",
            [icml(track="workshop"), linked(title="Reliance")],
            "forum_id",
            "track_not_merged",
        ),
        (
            "two listings link one forum",
            [icml(title="A"), linked("key1", title="B"), linked("key2", title="C")],
            "forum_id",
            "ambiguous_not_merged",
        ),
        (
            "the title matches but the link names another forum",
            [icml("AbCd1234"), linked(fid="EfGh5678")],
            "title_key",
            "ambiguous_not_merged",
        ),
    ],
)
def test_a_contradicted_link_never_merges(
    why: str, records: list[PaperRecord], field: str, resolution: str
) -> None:
    result = dedup(records)
    assert len(result.records) == len(records) and not result.merges
    assert {(c.field, c.resolution) for c in result.conflicts} == {(field, resolution)}
    assert dedup(result.records).conflicts == result.conflicts


def test_a_link_to_a_forum_that_is_absent_changes_nothing() -> None:
    listing = linked()
    assert dedup([listing]).records == (listing,)
    other = paper("EfGh5678", "Unrelated", venue="ICML")
    result = dedup([listing, other])
    assert len(result.records) == 2 and not result.merges and not result.conflicts


def test_records_must_match_their_claims() -> None:
    r = paper("AbCd1234")
    with pytest.raises(ValueError, match="own claims"):
        dedup([r.model_copy(update={"track": "workshop"})])
    with pytest.raises(ValueError, match="no claim for"):
        dedup([PaperRecord.build(id=r.id, title="T", abstract=None, authors=(), venue="NeurIPS", year=2024,
                                 track="main", status="accepted")])  # fmt: skip


@pytest.mark.parametrize(
    ("status", "presentation"),
    [
        ("accepted", "oral"),
        ("unknown", None),
        ("rejected", None),
        ("withdrawn", None),
        ("desk_rejected", None),
    ],
)
def test_presentation_holds_only_while_the_resolved_status_is_accepted(
    status: str, presentation: str | None
) -> None:
    record = paper("AbCd1234", status=status, presentation="oral")
    assert (record.status, record.presentation) == (status, presentation)
    assert any(
        c.field == "presentation" and c.value == "oral" for c in record.provenance
    )  # the claim is kept


def test_a_proceedings_status_that_outranks_openreview_accepted_drops_the_presentation() -> None:
    claims = [
        *paper("AbCd1234", presentation="spotlight").provenance,
        Claim(field="status", value="unknown", source="neurips_proceedings", fetched_at=T1),
    ]
    record, _ = resolve("op:neurips:2024:AbCd1234", claims)
    assert (record.status, record.presentation) == ("unknown", None)
    same = paper("AbCd1234")  # content_hash doesn't cover presentation
    assert record.content_hash == same.model_copy(update={"status": "unknown"}).content_hash


def _abstract(source: Any, value: str, url: str | None = None, evidence: str | None = None) -> Claim:
    return Claim(field="abstract", value=value, source=source, url=url, fetched_at=T0, evidence=evidence)


def test_abstract_claim_is_the_one_precedence_took_the_abstract_from() -> None:
    """TASK-134 (decision-018): the results list attributes an abstract to the claim `resolve` took it from."""
    pmlr = _abstract("pmlr", "Same text.", "https://proceedings.mlr.press/v162/a22a.html")
    ris = _abstract("ris", "Same text.")
    orv = _abstract("openreview_v2", "Same text.", "https://api2.openreview.net/notes?offset=0")
    assert abstract_claim("Same text.", [ris, pmlr]) == pmlr  # pmlr outranks ris
    assert abstract_claim("Same text.", [ris, pmlr, orv]) == orv  # OpenReview first (decision-005)
    scope = {"title": "Trust in AI", "venue": "ICML", "year": 2022, "track": "main", "status": "accepted"}
    base = [Claim(field=f, value=v, source="pmlr", fetched_at=T0) for f, v in scope.items()]  # type: ignore[arg-type]
    record, _ = resolve("op:icml:2022:pmlr-v162-a22a", [*base, pmlr, ris])
    assert abstract_claim(record.abstract, record.claims("abstract")) == pmlr  # the claim `resolve` chose


def test_abstract_claim_holds_the_abstracts_own_text() -> None:
    other = _abstract("openreview_v2", "A different abstract.")
    pmlr = _abstract("pmlr", "Shown text.", "https://proceedings.mlr.press/v162/a22a.html")
    # a better-ranked claim with other text is not the source of the text shown
    assert abstract_claim("Shown text.", [other, pmlr]) == pmlr
    assert abstract_claim("Shown text.", [other]) is None  # no claim holds it: unknown, never guessed
    assert abstract_claim("Shown text.", []) is None  # no provenance (a synthetic record)
    assert abstract_claim(None, [pmlr]) is None  # no abstract, nothing to attribute


FORUM = "https://openreview.net/forum?id=AbCd1234"
NIPS_PAGE = nips(1)
ICLR_PAGE = f"https://proceedings.iclr.cc/paper_files/paper/2024/hash/{H[2]}-Abstract-Conference.html"
PMLR_PAGE = "https://proceedings.mlr.press/v162/a22a.html"
NIPS_CUT = NIPS_PAGE.split("-Abstract")[0]  # a page cut after its hash, as 4 served RIS claims record it
NATIVE = f"nips-{H[1]}"  # the record whose page NIPS_PAGE is


@pytest.mark.parametrize(
    ("claim", "forum", "proceedings", "expected"),
    [
        # a direct claim: OpenReview's page is the forum (its claim url is the API listing)
        (_abstract("openreview_v1", "T", "https://api.openreview.net/notes"), FORUM, None,
         Attribution("openreview_v1", "openreview", FORUM)),
        (_abstract("pmlr", "T", PMLR_PAGE), None, PMLR_PAGE, Attribution("pmlr", "pmlr", PMLR_PAGE)),
        (_abstract("neurips_proceedings", "T", NIPS_PAGE), None, NIPS_PAGE,
         Attribution("neurips_proceedings", "neurips_proceedings", NIPS_PAGE)),
        # an `ris` claim: its evidence names the route, and the record's url the page
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {NIPS_PAGE}"), None, NIPS_PAGE,
         Attribution("ris", "neurips_proceedings", NIPS_PAGE)),
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {ICLR_PAGE}"), None, ICLR_PAGE,
         Attribution("ris", "iclr_proceedings", ICLR_PAGE)),
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {PMLR_PAGE}"), None, PMLR_PAGE,
         Attribution("ris", "pmlr", PMLR_PAGE)),
        (_abstract("ris", "T", evidence="scholarmend:openreview_api openreview:AbCd1234"), FORUM, None,
         Attribution("ris", "openreview", FORUM)),
        # a route that names no known site, or a proceedings route with no proceedings url: named, not linked
        (_abstract("ris", "T", evidence="scholarmend:semantic_scholar s2:1"), FORUM, NIPS_PAGE,
         Attribution("ris", None, None)),
        (_abstract("ris", "T", evidence="scholarmend:proceedings_page"), None, None, Attribution("ris", None, None)),
        # no proceedings link: the evidence's url names the site, and is linked as this paper's page (below)
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {NIPS_CUT}"), None,
         None, Attribution("ris", "neurips_proceedings", NIPS_CUT)),
        (_abstract("ris", "T", evidence="scholarmend:proceedings_page https://example.org/p"), None,
         "https://example.org/p", Attribution("ris", None, None)),
        (_abstract("ris", "T"), FORUM, NIPS_PAGE, Attribution("ris", None, None)),
    ],
)  # fmt: skip
def test_attribution_names_the_site_and_its_page(
    claim: Claim, forum: str | None, proceedings: str | None, expected: Attribution
) -> None:
    assert attribution("T", [claim], forum=forum, proceedings=proceedings, native=NATIVE) == expected
    assert attribution(None, [claim], forum=forum, proceedings=proceedings, native=NATIVE) is None


def _via(page: str) -> Claim:
    return _abstract("ris", "T", evidence=f"scholarmend:proceedings_page {page}")


def test_an_evidence_url_is_linked_only_as_this_records_own_page() -> None:
    """With no proceedings link, the evidence's url is the page when it names the record's native id: in full,
    or cut after its hash (the 4 served NeurIPS records); another paper's page, or a bare hash on the 2021 D&B
    host (which names up to three papers), is named but not linked."""

    def got(page: str, native: str) -> Attribution | None:
        return attribution("T", [_via(page)], forum=None, proceedings=None, native=native)

    assert got(NIPS_CUT, NATIVE) == Attribution("ris", "neurips_proceedings", NIPS_CUT)
    assert got(NIPS_PAGE, NATIVE) == Attribution("ris", "neurips_proceedings", NIPS_PAGE)
    assert got(NIPS_CUT, f"nips-{H[2]}") == Attribution("ris", "neurips_proceedings", None)
    assert got(PMLR_PAGE, "pmlr-v162-a22a") == Attribution("ris", "pmlr", PMLR_PAGE)
    assert got(PMLR_PAGE, "pmlr-v162-b22b") == Attribution("ris", "pmlr", None)
    db = f"https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/hash/{H[1]}"
    assert got(db, NATIVE) == Attribution("ris", "neurips_proceedings", None)
    assert got(ICLR_PAGE.split("-Abstract")[0], f"iclr-{H[2]}") == Attribution(
        "ris", "iclr_proceedings", ICLR_PAGE.split("-Abstract")[0]
    )


def test_when_the_evidence_and_the_proceedings_link_name_different_sites_the_evidence_wins_unlinked() -> None:
    both = attribution("T", [_via(NIPS_PAGE)], forum=None, proceedings=ICLR_PAGE, native=NATIVE)
    assert both == Attribution("ris", "neurips_proceedings", None)
    agree = attribution("T", [_via(NIPS_CUT)], forum=None, proceedings=NIPS_PAGE, native=NATIVE)
    assert agree == Attribution("ris", "neurips_proceedings", NIPS_PAGE)  # same site: the record's link


# --- a submission-time abstract (TASK-210) ----------------------------------------------------------------------
CAPTURE_98 = (
    "https://web.archive.org/web/19991009084141id_/http://www.cs.wisc.edu:80/icml98/papers/paper2.html"
)
SUBMITTED_EVIDENCE = (
    "official ICML 1998 page http://www.cs.wisc.edu:80/icml98/papers/paper2.html, Internet Archive capture "
    f"{CAPTURE_98}: {AS_SUBMITTED}; the page's contact details are not kept"
)


def test_an_icml_submission_pages_abstract_says_it_is_as_submitted() -> None:
    """The claim's evidence (as `icml_sites._evidence` writes it for 1997 and 1998) is read when the snapshot is
    loaded: the attribution says so, and its note is the one sentence the API and every export carry."""
    got = attribution("T", [_abstract("icml_site", "T", CAPTURE_98, SUBMITTED_EVIDENCE)], forum=None,
                      proceedings=None, native="dblp-X98")  # fmt: skip
    assert got == Attribution("icml_site", "icml_site", CAPTURE_98, as_submitted=True)
    assert got.note == SUBMISSION_NOTE
    assert SUBMISSION_NOTE.startswith("Submission-time abstract: ") and "published paper's" in SUBMISSION_NOTE


@pytest.mark.parametrize(
    "claim",
    [
        # another year's official page (2001-2007): as published, no note
        _abstract("icml_site", "T", CAPTURE_98, "official ICML 2003 page http://example.org/a.html"),
        _abstract("icml_site", "T", CAPTURE_98),  # no evidence at all
        # the words in another source's evidence don't make its abstract a submission's: only `icml_site` says so
        _abstract("pmlr", "T", PMLR_PAGE, SUBMITTED_EVIDENCE),
        _abstract("ris", "T", evidence=f"scholarmend:proceedings_page {PMLR_PAGE} {AS_SUBMITTED}"),
    ],
)
def test_any_other_abstract_has_no_note(claim: Claim) -> None:
    got = attribution("T", [claim], forum=None, proceedings=PMLR_PAGE, native="pmlr-v162-a22a")
    assert got is not None and not got.as_submitted and got.note is None


def test_the_note_follows_the_claim_precedence_took_the_abstract_from() -> None:
    """A submission page's claim beside a higher-ranked one with the same text: the abstract is credited to the
    higher one, so no note; with different text, the record's abstract decides which claim is credited."""
    submitted = _abstract("icml_site", "T", CAPTURE_98, SUBMITTED_EVIDENCE)
    pmlr = _abstract("pmlr", "T", PMLR_PAGE)
    both = attribution("T", [submitted, pmlr], forum=None, proceedings=PMLR_PAGE, native="pmlr-v162-a22a")
    assert both == Attribution("pmlr", "pmlr", PMLR_PAGE) and both.note is None
    other = _abstract("pmlr", "Other text.", PMLR_PAGE)
    credited = attribution(
        "T", [submitted, other], forum=None, proceedings=PMLR_PAGE, native="pmlr-v162-a22a"
    )
    assert credited is not None and credited.note == SUBMISSION_NOTE


# --- imported copies (TASK-179) -------------------------------------------------------------------------------
# Snapshot 2026-10-05-47d4e190ca81 held 7 accepted records that were only the Trust-Evals import's second copy of a
# crawled ICLR paper: the RIS row under the paper's proceedings.iclr.cc id, beside the note (and, for two of them,
# the RIS row under its forum id).

LONG = " ".join(f"word{n}" for n in range(MIN_ABSTRACT_TOKENS))  # an abstract just long enough to be evidence
OTHER = " ".join(f"term{n}" for n in range(MIN_ABSTRACT_TOKENS))
ICLR = {"venue": "ICLR", "year": 2025}


def rules(result: Any) -> list[tuple[str, str, str]]:
    return [(m.survivor_id, m.merged_id, m.rule) for m in result.merges]


def not_merged(result: Any) -> list[tuple[str, str]]:
    return [(c.field, c.resolution) for c in result.conflicts if c.resolution.endswith("_not_merged")]


def test_abstract_key_is_the_title_keys_normalisation_hashed_and_needs_enough_tokens() -> None:
    key = abstract_key(LONG)
    assert (
        key.startswith("sha256:") and len(key) == len("sha256:") + 64
    )  # the whole digest is what is matched
    assert shown_key(key) == key[:23] and len(shown_key(key)) == len("sha256:") + 16  # merges.csv's form
    assert abstract_key(LONG.upper().replace(" ", ",  ")) == key  # case, punctuation, spacing: one key
    assert abstract_key(LONG + " more") != key
    assert abstract_key(" ".join(LONG.split()[1:])) == ""  # one token short
    assert abstract_key("") == abstract_key("— …") == ""
    nfd = unicodedata.normalize("NFD", "café " + LONG)
    assert abstract_key(nfd) == abstract_key(unicodedata.normalize("NFC", nfd)) != ""


def test_a_papers_two_ris_rows_do_not_make_it_ambiguous() -> None:
    """ICLR 2024 `QHROe7Mfcb`: the note, the RIS row of its forum id, and the RIS row of its proceedings id, all
    under one title key. Sharing `ris` is not two candidates from one source: each RIS row names its paper by id."""
    xs = [
        paper("QHROe7Mfcb", "Less is More: One-shot Subgraph Reasoning", **ICLR),
        imported("QHROe7Mfcb", "Less is more: One-shot subgraph reasoning", **ICLR),
        imported(f"iclr-{H[1]}", "Less is more: One-shot subgraph reasoning", fetched=T1, **ICLR),
    ]
    result = dedup(xs)
    [r] = result.records
    assert r.id == "op:iclr:2025:QHROe7Mfcb" and r.title == "Less is More: One-shot Subgraph Reasoning"
    assert r.urls.proceedings == self_url(f"iclr-{H[1]}", 2025)
    assert rules(result) == [
        (r.id, r.id, "forum_id"),
        (r.id, f"op:iclr:2025:iclr-{H[1]}", "title_venue_year"),
    ]
    assert not_merged(result) == [] and dedup(result.records).records == result.records


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (f"iclr-{H[1]}", f"iclr-{H[2]}"),  # two proceedings papers
        ("AbCd1234", "EfGh5678"),  # two submissions
    ],
)
def test_two_ris_rows_naming_different_papers_still_never_merge(a: str, b: str) -> None:
    xs = [imported(a, abstract=LONG, **ICLR), imported(b, abstract=LONG, **ICLR)]
    result = dedup(xs)
    assert len(result.records) == 2 and rules(result) == []
    # one row: the pair's title key reported it, so its shared abstract adds none
    assert not_merged(result) == [("title_key", "ambiguous_not_merged")]
    titled = [imported(a, "One", abstract=LONG, **ICLR), imported(b, "Two", abstract=LONG, **ICLR)]
    assert not_merged(dedup(titled)) == [
        ("abstract_key", "ambiguous_not_merged")
    ]  # the abstract alone ties them


LOST_SYMBOL = [  # crawled title, the title Google Scholar gave the import
    ("$R^2$-Guard: Robust Reasoning Enabled LLM Guardrail", "-Guard: Robust Reasoning Enabled LLM Guardrail"),
    ("{$\\tau$}-bench: A Benchmark for Tool-Agent-User Interaction", "{}-bench: A Benchmark for Tool-Agent-User Interaction"),
    ("Adapt-$\\infty$: Scalable Continual Multimodal Instruction Tuning", "Adapt-: Scalable Continual Multimodal Instruction Tuning"),
    ("RobotArena $\\infty$: Scalable Robot Benchmarking", "RobotArena : Scalable Robot Benchmarking"),
    ("A$^2$Search: Ambiguity-Aware Question Answering", "ASearch: Ambiguity-Aware Question Answering"),
    # ICLR 2026 `CwoM9T55lG`: the import holds the paper's earlier title
    ("Computational Barriers to Filtering for AI Alignment", "On the impossibility of separating intelligence from judgment"),
]  # fmt: skip


@pytest.mark.parametrize(("crawled", "scholar"), LOST_SYMBOL)
def test_an_imported_copy_whose_title_lost_its_math_merges_on_its_abstract(
    crawled: str, scholar: str
) -> None:
    assert title_key(crawled) != title_key(scholar)
    note = paper("CkgKSqZbuC", crawled, abstract=LONG, **ICLR)
    copy = imported(f"iclr-{H[1]}", scholar, abstract=LONG.upper(), **ICLR)
    result = dedup([copy, note])
    [r] = result.records
    assert (r.id, r.title, r.abstract) == (note.id, crawled, LONG)
    assert result.merges == (
        Merge(note.id, copy.id, "abstract_venue_year", shown_key(abstract_key(LONG)), "ICLR", 2025, "ris"),
    )
    assert result.conflicts == (
        Conflict(note.id, "title", crawled, "openreview_v2", scholar, "ris", "precedence:openreview_v2"),
    )
    assert dedup(result.records).records == result.records


def test_the_retitled_import_merges_with_a_note_that_holds_its_own_ris_row() -> None:
    """ICLR 2026 `CwoM9T55lG`: the note's cluster holds the RIS row of its forum id, so the merge needs both
    rules: the abstract (the titles differ) and `ris` on both sides being no ambiguity."""
    crawled, scholar = LOST_SYMBOL[-1]
    xs = [
        paper("CwoM9T55lG", crawled, abstract=LONG, **ICLR),
        imported("CwoM9T55lG", crawled, abstract=LONG, **ICLR),
        imported(f"iclr-{H[1]}", scholar, abstract=LONG, fetched=T1, **ICLR),
    ]
    result = dedup(xs)
    [r] = result.records
    assert (r.id, r.title) == ("op:iclr:2025:CwoM9T55lG", crawled)
    assert [m.rule for m in result.merges] == ["forum_id", "abstract_venue_year"]


def test_two_papers_whose_titles_differ_only_by_a_symbol_are_not_merged() -> None:
    """The rule is the abstract, never a looser title key: `A$^2$Search` and an imported `ASearch` with another
    abstract, a short one, or none stay two records, with no row (nothing ties them)."""
    note = paper("3CPzUWIoNf", "A$^2$Search: Ambiguity-Aware Question Answering", abstract=LONG, **ICLR)
    for abstract in (OTHER, "Ambiguity-aware question answering.", None):
        copy = imported(f"iclr-{H[1]}", "ASearch: Ambiguity-Aware Question Answering", abstract=abstract, **ICLR)  # fmt: skip
        result = dedup([note, copy])
        assert [r.id for r in result.records] == [note.id, copy.id]
        assert result.merges == () and result.conflicts == ()


def test_a_short_shared_abstract_is_never_merge_evidence() -> None:
    short = " ".join(LONG.split()[1:])
    xs = [paper("AbCd1234", "One", abstract=short, **ICLR), imported(f"iclr-{H[1]}", "Two", abstract=short, **ICLR)]  # fmt: skip
    assert len(dedup(xs).records) == 2


@pytest.mark.parametrize("other", [{"venue": "ICLR", "year": 2024}, {"venue": "NeurIPS", "year": 2025}])
def test_an_abstract_never_merges_across_venue_or_year(other: dict[str, Any]) -> None:
    prefix = "nips" if other["venue"] == "NeurIPS" else "iclr"
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        imported(f"{prefix}-{H[1]}", "Two", abstract=LONG, **other),
    ]
    result = dedup(xs)
    assert len(result.records) == 2 and result.merges == () and result.conflicts == ()


@pytest.mark.parametrize("source", ["neurips_proceedings", "pmlr", "iclr_archive"])
def test_a_crawled_listing_is_never_joined_by_its_abstract(source: str) -> None:
    """Step 3 is for imported records only: a crawled listing's title is the publisher's own, and a retitled
    paper there (NeurIPS 2023 D&B `3sRR2u72oQ`, the one such pair on the 2026-10-05 snapshot) stays two records."""
    venue, native = {"neurips_proceedings": ("NeurIPS", f"nips-{H[1]}"), "pmlr": ("ICML", "pmlr-v202-key1"),
                     "iclr_archive": ("ICLR", f"iclr-{H[1]}")}[source]  # fmt: skip
    xs = [
        paper("AbCd1234", "One", abstract=LONG, venue=venue),
        paper(native, "Two", source=source, abstract=LONG, venue=venue),
    ]
    result = dedup(xs)
    assert len(result.records) == 2 and result.merges == () and result.conflicts == ()


def test_an_import_beside_two_accepted_notes_with_its_abstract_is_ambiguous() -> None:
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        paper("EfGh5678", "Two", abstract=LONG, **ICLR),
        imported(f"iclr-{H[1]}", "Three", abstract=LONG, **ICLR),
    ]
    result = dedup(xs)
    assert len(result.records) == 3 and result.merges == ()
    assert not_merged(result) == [("abstract_key", "ambiguous_not_merged")] * 2
    assert dedup(result.records).conflicts == result.conflicts


@pytest.mark.parametrize(
    ("rival", "row"),
    [
        ({"track": "workshop"}, "track_not_merged"),  # the paper's workshop version, same abstract
        ({"status": "rejected"}, "ambiguous_not_merged"),  # an earlier, rejected submission
    ],
)
def test_a_rival_that_cannot_be_the_listed_paper_is_set_aside_on_an_abstract_too(
    rival: dict[str, Any], row: str
) -> None:
    """As on a title (TASK-126): the import and its note merge, the rival stays its own record, and its row is
    written against the record that now holds the listing, on this run and on the next."""
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        paper("EfGh5678", "Two", abstract=LONG, **ICLR, **rival),
        imported(f"iclr-{H[1]}", "Three", abstract=LONG, **ICLR),
    ]
    result = dedup(xs)
    assert [r.id for r in result.records] == ["op:iclr:2025:AbCd1234", "op:iclr:2025:EfGh5678"]
    assert rules(result) == [("op:iclr:2025:AbCd1234", f"op:iclr:2025:iclr-{H[1]}", "abstract_venue_year")]
    rows = [c for c in result.conflicts if c.resolution.endswith("_not_merged")]
    assert rows == [
        Conflict("op:iclr:2025:AbCd1234", "abstract_key", "op:iclr:2025:AbCd1234", "openreview_v2+ris",
                 "op:iclr:2025:EfGh5678", "openreview_v2", row)
    ]  # fmt: skip
    again = dedup(result.records)
    assert again.records == result.records
    assert [c for c in again.conflicts if c.resolution.endswith("_not_merged")] == rows


def test_a_rival_is_reported_when_a_newer_ris_row_replaced_the_abstract_the_import_merged_on() -> None:
    """The note's own RIS row (abstract OTHER, fetched last) keeps the merged record's one `ris` abstract claim, so
    the import's LONG is gone from it; the note's own claim still holds LONG, and the workshop rival sharing it is
    reported on this run and the next."""
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        imported("AbCd1234", "One", abstract=OTHER, fetched=T2, **ICLR),
        imported(f"iclr-{H[1]}", "Three", abstract=LONG, fetched=T1, **ICLR),
        paper("EfGh5678", "Two", abstract=LONG, track="workshop", **ICLR),
    ]
    result = dedup(xs)
    assert [r.id for r in result.records] == ["op:iclr:2025:AbCd1234", "op:iclr:2025:EfGh5678"]
    assert rules(result)[-1] == ("op:iclr:2025:AbCd1234", f"op:iclr:2025:iclr-{H[1]}", "abstract_venue_year")
    [kept] = [c.value for c in result.records[0].provenance if c.field == "abstract" and c.source == "ris"]
    assert kept == OTHER
    rows = [c for c in result.conflicts if c.resolution.endswith("_not_merged")]
    assert rows == [
        Conflict("op:iclr:2025:AbCd1234", "abstract_key", "op:iclr:2025:AbCd1234", "openreview_v2+ris",
                 "op:iclr:2025:EfGh5678", "openreview_v2", "track_not_merged")
    ]  # fmt: skip
    again = dedup(result.records)
    assert [c for c in again.conflicts if c.resolution.endswith("_not_merged")] == rows


def test_a_pair_a_title_key_reported_gets_no_second_row_for_its_abstract() -> None:
    """A listing holding a `ris` claim and its same-title workshop version, which share the abstract too: one
    `title_key` row says it all."""
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR),
        paper("EfGh5678", "One", abstract=LONG, track="workshop", **ICLR),
    ]
    result = dedup(xs)
    assert len(result.records) == 2
    assert not_merged(result) == [("title_key", "track_not_merged")]
    assert not_merged(dedup(result.records)) == not_merged(result)


def test_an_imported_listing_never_merges_with_a_workshop_note_on_its_abstract() -> None:
    xs = [
        paper("AbCd1234", "One", abstract=LONG, track="workshop", **ICLR),
        imported(f"iclr-{H[1]}", "Two", abstract=LONG, **ICLR),
    ]
    result = dedup(xs)
    assert len(result.records) == 2 and result.merges == ()
    assert not_merged(result) == [("abstract_key", "track_not_merged")]


def test_an_import_that_matched_by_title_is_not_matched_again_by_abstract() -> None:
    """Step 3 is for an imported record that matched nothing: one whose title found its paper is no longer an
    imported record, so a second note sharing its abstract is left alone. (Its title partner keeps the abstract
    too: when only the second note did, the import would yield to it, decision-045, tested below.)"""
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR),
        paper("EfGh5678", "Two", abstract=LONG, track="workshop", **ICLR),
    ]
    result = dedup(xs)
    assert [r.id for r in result.records] == ["op:iclr:2025:AbCd1234", "op:iclr:2025:EfGh5678"]
    assert [m.rule for m in result.merges] == ["title_venue_year"]
    # the workshop note shares the listing's abstract: a rival's row (as a title's would be), never a merge
    assert not_merged(result) == [("abstract_key", "track_not_merged")]


# --- step 3's own refusals (TASK-179 review) ------------------------------------------------------------------


@pytest.mark.parametrize("status", ["withdrawn", "rejected", "desk_rejected"])
def test_an_accepted_import_never_merges_into_a_lone_note_that_is_not_accepted(status: str) -> None:
    """`_mergeable` ignores status, so without step 3's own rule the accepted import would merge into the note
    and take its status (RIS ranks last for status), and the paper would leave every accepted-only result."""
    note = paper("AbCd1234", "One", abstract=LONG, status=status, **ICLR)
    copy = imported(f"iclr-{H[1]}", "Two", abstract=LONG, **ICLR)
    result = dedup([note, copy])
    assert [(r.id, r.status) for r in result.records] == [(note.id, status), (copy.id, "accepted")]
    assert result.merges == ()
    assert result.conflicts == (
        Conflict(copy.id, "abstract_key", copy.id, "ris", note.id, "openreview_v2", "ambiguous_not_merged"),
    )
    assert dedup(result.records) == result


@pytest.mark.parametrize("status", ["withdrawn", "rejected", "desk_rejected"])
@pytest.mark.parametrize(
    ("titles", "field"), [(("One", "Two"), "abstract_key"), (("One", "One"), "title_key")]
)
@pytest.mark.parametrize("fetched", [(T1, T0), (T0, T1)])
def test_an_imported_listing_never_merges_with_an_import_only_submission_that_is_not_accepted(
    status: str, titles: tuple[str, str], field: str, fetched: tuple[Any, Any]
) -> None:
    """A forum id's RIS row alone (no note crawled) saying withdrawn, and the paper's proceedings-id RIS row: both
    claims are `ris`, so the merged record's status would be whichever row was fetched last. Apart, by abstract as
    by title, whatever the fetch order, with the row against the listing."""
    own = imported("AbCd1234", titles[0], abstract=LONG, status=status, fetched=fetched[0], **ICLR)
    listing = imported(f"iclr-{H[1]}", titles[1], abstract=LONG, fetched=fetched[1], **ICLR)
    result = dedup([own, listing])
    assert [(r.id, r.status) for r in result.records] == [(own.id, status), (listing.id, "accepted")]
    assert result.merges == ()
    assert [c for c in result.conflicts if c.resolution.endswith("_not_merged")] == [
        Conflict(listing.id, field, listing.id, "ris", own.id, "ris", "ambiguous_not_merged")
    ]
    assert dedup(result.records) == result


def test_a_crawled_note_that_is_not_accepted_never_merges_with_an_imported_listing_by_title() -> None:
    """The title step's form of the same rule: the note's OpenReview status outranks `ris`, so merged with the
    import alone the accepted paper would be withdrawn. A crawled listing outranks it, so beside one it may merge."""
    note = paper("AbCd1234", "One", status="withdrawn", **ICLR)
    copy = imported(f"iclr-{H[1]}", "One", **ICLR)
    result = dedup([note, copy])
    assert [(r.id, r.status) for r in result.records] == [(note.id, "withdrawn"), (copy.id, "accepted")]
    assert result.conflicts == (
        Conflict(copy.id, "title_key", copy.id, "ris", note.id, "openreview_v2", "ambiguous_not_merged"),
    )
    crawled = paper(f"iclr-{H[1]}", "One", source="iclr_archive", **ICLR)
    [r] = dedup([note, copy, crawled]).records
    assert (r.id, r.status) == (note.id, "accepted")


# --- a listing by RIS evidence alone (TASK-198, decision-040) ----------------------------------------------------


def ris_listed_note(title: str, status: str = "rejected") -> list[PaperRecord]:
    """TASK-174's shape: a note that is not accepted and its forum id's RIS row naming a proceedings paper, which
    makes the note's cluster a listing by RIS evidence alone."""
    return [
        paper("AbCd1234", title, abstract=LONG, status=status, **ICLR),
        paper("AbCd1234", title, source="ris", abstract=LONG, urls_proceedings=self_url(f"iclr-{H[1]}", 2025),
              **ICLR),
    ]  # fmt: skip


@pytest.mark.parametrize("status", ["withdrawn", "rejected", "desk_rejected"])
@pytest.mark.parametrize(
    ("titles", "field"), [(("One", "Two"), "abstract_key"), (("One", "One"), "title_key")]
)
def test_a_listing_by_ris_evidence_alone_never_takes_an_import_by_abstract_or_title(
    status: str, titles: tuple[str, str], field: str
) -> None:
    """decision-040: the note's cluster names `iclr-<H1>` only through its RIS row, so it is no listing for
    decision-037's exemption. The import of that paper stays apart and accepted, by abstract as by title, with one
    not-merged row."""
    xs = [*ris_listed_note(titles[0], status), imported(f"iclr-{H[1]}", titles[1], abstract=LONG, **ICLR)]
    note, copy = xs[0], xs[2]
    result = dedup(xs)
    assert [(r.id, r.status) for r in result.records] == [(note.id, status), (copy.id, "accepted")]
    assert rules(result) == [(note.id, note.id, "forum_id")]
    pair = [(copy.id, "ris"), (note.id, "openreview_v2+ris")]
    if field == "title_key":  # both are listings, so neither is set aside: the pair in id order
        pair.reverse()
    (a, sa), (b, sb) = pair
    assert [c for c in result.conflicts if c.resolution.endswith("_not_merged")] == [
        Conflict(a, field, a, sa, b, sb, "ambiguous_not_merged")
    ]
    again = dedup(result.records)
    assert (again.records, again.conflicts) == (result.records, result.conflicts)


def test_a_listing_by_ris_evidence_alone_is_still_a_listing_for_reconcile() -> None:
    """decision-040 narrows only decision-037's exemption: `is_listing` keeps its meaning (reconcile, the track
    rule), so the note's merged record is still one."""
    from openproceedings.ingest.dedup import is_listing

    [r] = dedup(ris_listed_note("One")).records
    assert is_listing(r)


def test_a_ris_listed_note_and_its_import_merge_once_the_proceedings_listing_is_crawled() -> None:
    """With the crawled listing present, its status outranks the note's: the three merge, accepted."""
    xs = [
        *ris_listed_note("One"),
        imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR),
        paper(f"iclr-{H[1]}", "One", source="iclr_archive", abstract=LONG, **ICLR),
    ]
    [r] = dedup(xs).records
    assert (r.id, r.status) == ("op:iclr:2025:AbCd1234", "accepted")


@pytest.mark.parametrize("title", ["One", "Two"])
def test_a_note_that_names_its_proceedings_paper_itself_is_crawled_evidence(title: str) -> None:
    """decision-040: a crawled note's own `urls.proceedings` claim is crawled evidence (no crawler emits one
    today), so the exemption holds and the import merges into it, by title or abstract (the note's status
    stays OpenReview's)."""
    note = paper("AbCd1234", "One", abstract=LONG, status="rejected",
                 urls_proceedings=self_url(f"iclr-{H[1]}", 2025), **ICLR)  # fmt: skip
    copy = imported(f"iclr-{H[1]}", title, abstract=LONG, **ICLR)
    result = dedup([note, copy])
    assert [(r.id, r.status) for r in result.records] == [(note.id, "rejected")]
    assert [m.rule for m in result.merges] == [
        "title_venue_year" if title == "One" else "abstract_venue_year"
    ]


@pytest.mark.parametrize(
    "evidence",
    [
        f"scholarmend:proceedings_page {self_url(f'iclr-{H[2]}', 2025)}",  # another paper's page
        "scholarmend:proceedings_page",  # no page named
        "scholarmend:openreview_api openreview:EfGh5678",  # a forum's abstract on a proceedings-id row
        "scholarmend:semanticscholar x",  # a route this code doesn't know
        "",
    ],
)
def test_an_abstract_that_is_not_the_imports_own_page_is_no_evidence(evidence: str) -> None:
    """The import "Reward Shaping in Bandits" with the abstract of "Graph Transformers for Chemistry": only an
    abstract scholarmend read from the import's own page says which paper the import is."""
    note = paper("AbCd1234", "Graph Transformers for Chemistry", abstract=LONG, **ICLR)
    copy = imported(f"iclr-{H[1]}", "Reward Shaping in Bandits", abstract=LONG,
                 abstract_evidence=evidence, **ICLR)  # fmt: skip
    result = dedup([note, copy])
    assert len(result.records) == 2 and result.merges == () and result.conflicts == ()


def test_a_forum_id_imports_openreview_abstract_counts_only_for_its_own_forum() -> None:
    listing = paper(f"iclr-{H[1]}", "One", source="iclr_archive", abstract=LONG, **ICLR)
    own = imported("AbCd1234", "Two", abstract=LONG, **ICLR)
    result = dedup([listing, own])
    [r] = result.records
    assert r.id == own.id and rules(result) == [
        (own.id, listing.id, "abstract_venue_year")
    ]  # the forum id survives
    other = imported("AbCd1234", "Two", abstract=LONG, **ICLR,
                  abstract_evidence="scholarmend:openreview_api openreview:EfGh5678")  # fmt: skip
    assert len(dedup([listing, other]).records) == 2


def test_two_keys_chaining_two_imports_through_one_note_merge_nothing() -> None:
    """A note keeps its own abstract A and its RIS row's abstract B; one import holds A, another B. Each pair
    could merge alone, but the chain would hold two proceedings papers: all apart, two chain rows, stable."""
    xs = [
        paper("AbCd1234", "One", abstract=LONG, **ICLR),
        imported("AbCd1234", "One", abstract=OTHER, **ICLR),
        imported(f"iclr-{H[1]}", "Two", abstract=LONG, **ICLR),
        imported(f"iclr-{H[2]}", "Three", abstract=OTHER, **ICLR),
    ]
    result = dedup(xs)
    assert len(result.records) == 3 and [m.rule for m in result.merges] == ["forum_id"]
    assert not_merged(result) == [("abstract_key_chain", "ambiguous_not_merged")] * 2
    again = dedup(result.records)
    assert again.records == result.records and not_merged(again) == not_merged(result)


def test_an_import_never_bridges_a_listing_and_a_note_of_another_forum() -> None:
    xs = [
        imported("AbCd1234", "One", abstract=LONG, **ICLR),  # a forum-id import
        paper(f"iclr-{H[1]}", "Two", source="iclr_archive", abstract=LONG, **ICLR),
        paper("EfGh5678", "Three", abstract=LONG, **ICLR),
    ]
    result = dedup(xs)
    assert len(result.records) == 3 and result.merges == ()
    assert not_merged(result) == [("abstract_key", "ambiguous_not_merged")] * 2
    assert dedup(result.records) == result


def test_an_abstract_never_joins_two_crawled_records_even_beside_an_import() -> None:
    """A proceedings-id import, a crawled listing of another title and a note: the abstract alone never says the
    listing and the note are one paper (decision-037). Step 1 merges the import into its listing, so step 3 has
    no imported record here and never forms the group: this pins the end result, not step 3's rule (below)."""
    xs = [
        imported("pmlr-v202-key1", "One", venue="ICML", abstract=LONG),
        paper("pmlr-v202-key1", "One", source="pmlr", venue="ICML", abstract=LONG),
        paper("AbCd1234", "Two", venue="ICML", abstract=LONG),
    ]
    result = dedup(xs)
    assert len(result.records) == 2 and [m.rule for m in result.merges] == ["native_id"]


def test_step_threes_two_crawled_records_guard_refuses_a_group_mergeable_would_pass() -> None:
    """No dedup run reaches `_abstract_group`'s guard against two crawled clusters: an import that passes
    `_mergeable` beside two of them carries one's id, and step 1 has merged it there. A group built by hand,
    skipping steps 1 and 2, shows the guard alone refuses one: a note, a crawled listing linking its forum, and
    an import of the listing's id."""
    from openproceedings.ingest.dedup import _abstract_group, _cluster, _mergeable

    group = [
        _cluster([paper("AbCd1234", "One", venue="ICML", abstract=LONG)]),
        _cluster([paper("pmlr-v202-key1", "Two", source="pmlr", venue="ICML", abstract=LONG,
                        urls_forum="https://openreview.net/forum?id=AbCd1234")]),
        _cluster([imported("pmlr-v202-key1", "Three", venue="ICML", abstract=LONG)]),
    ]  # fmt: skip
    assert _mergeable(group) is None
    assert _abstract_group(group) == "ambiguous_not_merged"


def test_matching_is_on_the_whole_digest_not_the_sixteen_digits_merges_csv_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openproceedings.ingest import dedup as module

    fake = {LONG: "sha256:" + "a" * 16 + "0" * 48, OTHER: "sha256:" + "a" * 16 + "1" * 48}
    monkeypatch.setattr(module, "abstract_key", lambda text: fake.get(text, ""))
    xs = [paper("AbCd1234", "One", abstract=LONG, **ICLR), imported(f"iclr-{H[1]}", "Two", abstract=OTHER, **ICLR)]  # fmt: skip
    assert len(dedup(xs).records) == 2  # the two keys share their first 16 digits and are still two abstracts


# --- an import's title merge yields to its own abstract's crawled match (TASK-189, decision-045) -----------------
GUARD = "Guard: Robust Reasoning Enabled LLM Guardrail"


def test_an_import_whose_title_lost_a_symbol_joins_its_abstracts_note_not_the_other_title() -> None:
    """Shape A: Scholar's `-Guard` has the title key of a different note, `Guard`, but its own-page abstract is
    `$R^2$-Guard`'s. The title partner keeps no such abstract and a crawled record does: the import joins that
    record by its abstract, and the two notes stay apart with their title row."""
    r2 = paper("AbCd1234", "$R^2$-" + GUARD, abstract=LONG, **ICLR)
    guard = paper("EfGh5678", GUARD, abstract=OTHER, **ICLR)
    copy = imported(f"iclr-{H[1]}", "-" + GUARD, abstract=LONG, **ICLR)
    assert title_key(copy.title) == title_key(guard.title) != title_key(r2.title)
    result = dedup([guard, copy, r2])
    assert [r.id for r in result.records] == [r2.id, guard.id]
    assert rules(result) == [(r2.id, copy.id, "abstract_venue_year")]
    assert not_merged(result) == [("title_key", "ambiguous_not_merged")]  # two forum ids under one title key
    again = dedup(result.records)
    assert (again.records, again.conflicts) == (result.records, result.conflicts)


def test_an_import_whose_abstract_no_crawled_record_holds_still_merges_on_its_title() -> None:
    """Shape A without `$R^2$-Guard`'s note: nothing says the import is another paper, so the title decides."""
    guard = paper("EfGh5678", GUARD, abstract=OTHER, **ICLR)
    copy = imported(f"iclr-{H[1]}", "-" + GUARD, abstract=LONG, **ICLR)
    result = dedup([guard, copy])
    assert rules(result) == [(guard.id, copy.id, "title_venue_year")]


def test_two_ris_rows_with_one_title_and_different_abstracts_still_merge() -> None:
    """Shape B: OpenReview and camera-ready abstracts often differ; no crawled record holds either, so the title
    decides (decision-045)."""
    own = imported("AbCd1234", "One", abstract=LONG, **ICLR)
    listing = imported(f"iclr-{H[1]}", "One", abstract=OTHER, **ICLR)
    result = dedup([own, listing])
    assert rules(result) == [(own.id, listing.id, "title_venue_year")]


@pytest.mark.parametrize("workshop_title", ["One", "One (workshop version)"])
def test_an_import_beside_a_main_note_and_its_workshop_version_sharing_the_abstract_merges_with_the_main(
    workshop_title: str,
) -> None:
    """The 14 pairs of decision-037: a main note and its workshop version keep one abstract. The import's title
    partner (the main note) keeps its abstract too, so the title merge stands; the workshop note is a rival set
    aside, as before."""
    main = paper("AbCd1234", "One", abstract=LONG, **ICLR)
    workshop = paper("EfGh5678", workshop_title, abstract=LONG, track="workshop", **ICLR)
    copy = imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR)
    result = dedup([main, workshop, copy])
    assert [r.id for r in result.records] == [main.id, workshop.id]
    assert rules(result) == [(main.id, copy.id, "title_venue_year")]


def test_an_import_whose_abstracts_holder_cannot_take_it_stays_apart() -> None:
    """decision-045 reads the crawled holder as evidence the title partner is another paper, whether or not step 3
    can then merge the two: a workshop note keeps the import's abstract, so it stays its own record, with a row
    against each."""
    guard = paper("EfGh5678", GUARD, abstract=OTHER, **ICLR)
    workshop = paper("AbCd1234", "$R^2$-" + GUARD, abstract=LONG, track="workshop", **ICLR)
    copy = imported(f"iclr-{H[1]}", "-" + GUARD, abstract=LONG, **ICLR)
    result = dedup([guard, workshop, copy])
    assert len(result.records) == 3 and result.merges == ()
    assert sorted(not_merged(result)) == [
        ("abstract_key", "track_not_merged"),
        ("title_key", "ambiguous_not_merged"),
    ]
    again = dedup(result.records)
    assert (again.records, again.conflicts) == (result.records, result.conflicts)


def test_an_abstract_only_a_crawled_records_ris_row_holds_is_no_reason_to_yield() -> None:
    """decision-045 reads a crawler's abstract only: a RIS row's in a crawled cluster can be replaced by a merge in
    the same step (one claim per source), so a second run would judge the title group differently."""
    r2 = paper("AbCd1234", "$R^2$-" + GUARD, abstract=OTHER, **ICLR)
    its_row = imported("AbCd1234", "$R^2$-" + GUARD, abstract=LONG, **ICLR)
    guard = paper("EfGh5678", GUARD, abstract=OTHER, **ICLR)
    copy = imported(f"iclr-{H[1]}", "-" + GUARD, abstract=LONG, **ICLR)
    result = dedup([r2, its_row, guard, copy])
    assert (guard.id, copy.id, "title_venue_year") in rules(result)


def test_a_title_partner_set_aside_by_the_track_rule_still_keeps_the_title_merge() -> None:
    """decision-045 asks whether a title partner keeps the import's abstract, set-aside rivals included: a
    same-title workshop note holding it is the main paper's workshop version (the 14 pairs of decision-037), not a
    sign the title names another paper. The forum-id import merges on its title with the proceedings-id import
    (whose abstract is another page's, no evidence), and the workshop note stays apart with its title row
    (nightly run 37412309356)."""
    copy = imported(f"nips-{H[1]}", "Trust in Machines", year=2023, abstract=LONG,
                    abstract_evidence="scholarmend:proceedings_page https://example.org/x")  # fmt: skip
    workshop = paper("AbCd1234", "Trust in Machines", year=2023, track="workshop", abstract=LONG)
    own = imported("EfGh5678", "Trust in Machines", year=2023, abstract=LONG)
    result = dedup([copy, workshop, own])
    assert [r.id for r in result.records] == [workshop.id, own.id]
    assert rules(result) == [(own.id, copy.id, "title_venue_year")]
    assert not_merged(result) == [("title_key", "track_not_merged")]


# --- over-yielding (TASK-201): decision-045 asks that NO title partner keep the abstract --------------------------


def test_one_title_partner_keeping_the_abstract_keeps_the_title_merge_whatever_the_others_keep() -> None:
    """The main note keeps the import's abstract, a same-title workshop note of another forum keeps another: the
    import is the main paper's, merged on its title (the workshop note set aside). Yielding because some partner
    lacks the abstract would move the merge to step 3: the same record, by the wrong rule."""
    main = paper("AbCd1234", "One", abstract=LONG, **ICLR)
    workshop = paper("EfGh5678", "One", abstract=OTHER, track="workshop", **ICLR)
    copy = imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR)
    result = dedup([main, workshop, copy])
    assert [r.id for r in result.records] == [main.id, workshop.id]
    assert rules(result) == [(main.id, copy.id, "title_venue_year")]


def test_a_lone_title_partner_keeping_the_abstract_keeps_the_title_merge() -> None:
    """The partner is itself the crawled holder of the import's abstract: nothing names another paper."""
    note = paper("AbCd1234", "One", abstract=LONG, **ICLR)
    copy = imported(f"iclr-{H[1]}", "One", abstract=LONG, **ICLR)
    assert rules(dedup([note, copy])) == [(note.id, copy.id, "title_venue_year")]


def test_two_dblp_records_sharing_a_title_are_never_merged() -> None:
    """decision-047: two dblp papers of one ICML year with the same title key are two proceedings ids: kept apart,
    with a conflicts.csv row, never folded."""
    a = paper("dblp-Smith09", "Trust in AI", source="dblp", venue="ICML", year=2009)
    b = paper("dblp-Smith09b", "trust in AI!", source="dblp", venue="ICML", year=2009)
    result = dedup([a, b])
    assert sorted(r.id for r in result.records) == ["op:icml:2009:dblp-Smith09", "op:icml:2009:dblp-Smith09b"]
    assert not result.merges and result.conflicts
