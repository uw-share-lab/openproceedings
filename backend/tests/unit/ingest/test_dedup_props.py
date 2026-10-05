"""Dedup properties over small colliding pools (dedup-rules skill §Property tests).

The pools are small on purpose (four titles, three forum ids, two proceedings papers per venue, two
years), so records collide often: every source, venue, track and status appears, OpenReview records
sometimes carry a proceedings URL, any record may link a forum id (its own or another: the forum link,
TASK-105), and the fetch times tie.
"""

from __future__ import annotations

import random
from collections import Counter

from hypothesis import event, example, given
from hypothesis import strategies as st
from openproceedings.ingest import urls
from openproceedings.ingest.dedup import (
    IMPORTED,
    PROCEEDINGS_TRACKS,
    DedupResult,
    abstract_key,
    dedup,
    is_creative_ai,
    is_listing,
    resolve,
    shown_key,
)
from openproceedings.ingest.record import PaperRecord

from tests.unit.ingest.test_dedup import LONG, OTHER, T0, T1, T2, H, archive, imported, nips, own_page, paper

TITLES = ["Trust in AI", "trust in AI!", "Trust in Machines", "—"]
FORUMS = ["AbCd1234", "EfGh5678", "IjKl9012"]
PROCEEDINGS = {  # native id → its venue
    **{f"nips-{H[n]}": "NeurIPS" for n in (1, 2)},
    **{f"iclr-{H[n]}": "ICLR" for n in (1, 2)},
    **{f"pmlr-v202-key{n}": "ICML" for n in (1, 2)},
}
SOURCE_NATIVES = {
    "openreview_v2": FORUMS,
    "openreview_v1": FORUMS,
    "iclr_archive": [n for n in PROCEEDINGS if n.startswith("iclr-")],
    "neurips_proceedings": [n for n in PROCEEDINGS if n.startswith(("nips-", "iclr-"))],
    "pmlr": [n for n in PROCEEDINGS if n.startswith("pmlr-")],
    "ris": [*FORUMS, *PROCEEDINGS],
}


@st.composite
def records(draw: st.DrawFn) -> PaperRecord:
    source = draw(st.sampled_from(sorted(SOURCE_NATIVES)))
    native = draw(st.sampled_from(SOURCE_NATIVES[source]))
    venue = PROCEEDINGS.get(native) or draw(st.sampled_from(["NeurIPS", "ICLR", "ICML"]))
    extra = {}
    if native in FORUMS and draw(st.booleans()):
        extra["urls_proceedings"] = nips(draw(st.sampled_from([1, 2])))  # an OpenReview note linking a paper
    if native in FORUMS and draw(st.booleans()):  # an old-style NeurIPS PDF link
        extra["urls_pdf"] = (
            f"https://papers.nips.cc/paper/2021/file/{H[draw(st.sampled_from([1, 2]))]}-Paper.pdf"
        )
    if (
        draw(st.integers(0, 3)) == 0
    ):  # a forum link: a listing's (PMLR v235), a note's own, or a contradicting one
        extra["urls_forum"] = forum_url(draw(st.sampled_from(FORUMS)))
    year = draw(st.sampled_from([2023, 2024]))
    return paper(
        native,
        draw(st.sampled_from(TITLES)),
        source=source,
        venue=venue,
        year=year,
        abstract_evidence=own_page(native, year) if source == "ris" else None,
        track=draw(
            st.sampled_from(["main", "workshop", "position", "datasets_benchmarks", "unknown", "other"])
        ),
        status=draw(st.sampled_from(["accepted", "rejected", "unknown"])),
        # two abstracts long enough to be step 3's evidence (TASK-179), and two that never are
        abstract=draw(st.sampled_from([None, "An abstract.", "Another abstract.", LONG, OTHER])),
        fetched=draw(st.sampled_from([T0, T1, T2])),
        **extra,
    )


@st.composite
def chains(draw: st.DrawFn) -> list[PaperRecord]:
    """One paper under two titles (two sources share its forum id), each title matching a different
    record from one proceedings source, plus noise: the shape that must never fold two papers."""
    venue, prefix, source = draw(
        st.sampled_from([("NeurIPS", "nips", "neurips_proceedings"), ("ICLR", "iclr", "iclr_archive")])
    )
    year = draw(st.sampled_from([2023, 2024]))
    a, b = draw(st.permutations(TITLES[:3]))[:2]
    forum = draw(st.sampled_from(FORUMS))
    base = [
        paper(
            forum, a, venue=venue, year=year, source=draw(st.sampled_from(["openreview_v2", "openreview_v1"]))
        ),
        paper(forum, b, venue=venue, year=year, source="ris", fetched=draw(st.sampled_from([T0, T1]))),
        paper(f"{prefix}-{H[1]}", a, venue=venue, year=year, source=source),
        paper(f"{prefix}-{H[2]}", b, venue=venue, year=year, source=source),
    ]
    return base + draw(st.lists(records(), max_size=3))


@st.composite
def links(draw: st.DrawFn) -> list[PaperRecord]:
    """One OpenReview paper and the listings that link its forum, under any title, sometimes from another
    venue-year or track, sometimes two listings for one forum, plus noise: the forum link's shapes."""
    fid = draw(st.sampled_from(FORUMS))
    year = draw(st.sampled_from([2023, 2024]))
    base = [  # weighted towards the listings' venue-year, so most links can hold
        paper(
            fid, draw(st.sampled_from(TITLES)), venue=draw(st.sampled_from(["ICML", "ICML", "ICLR"])),
            year=draw(st.sampled_from([year, year, 2023, 2024])),
            source=draw(st.sampled_from(["openreview_v2", "openreview_v1", "ris"])),
            track=draw(st.sampled_from(["main", "main", "position", "workshop"])), urls_forum=forum_url(fid),
        ),
    ]  # fmt: skip
    for key in draw(st.lists(st.sampled_from(["key1", "key2"]), min_size=1, max_size=2, unique=True)):
        base.append(
            paper(
                f"pmlr-v202-{key}", draw(st.sampled_from(TITLES)), venue="ICML", year=year,
                source=draw(st.sampled_from(["pmlr", "ris"])), track=draw(st.sampled_from(["main", "unknown"])),
                urls_forum=forum_url(draw(st.sampled_from([fid, fid, *FORUMS]))),
            )
        )  # fmt: skip
    return base + draw(st.lists(records(), max_size=3))


@st.composite
def imports(draw: st.DrawFn) -> list[PaperRecord]:
    """An imported record (RIS only) whose title is not its paper's, and the records its abstract may or may not
    tie it to (TASK-179): its note, sometimes with the note's own RIS row, a second note, a crawled listing, each
    with the import's abstract or another, in its venue-year or not, plus noise."""
    venue, prefix = draw(st.sampled_from([("NeurIPS", "nips"), ("ICLR", "iclr")]))
    year = draw(st.sampled_from([2023, 2024]))
    abstracts = st.sampled_from([LONG, LONG, OTHER, "An abstract.", None])
    # sometimes a forum-id import, sometimes an abstract that is not its own page's (never evidence)
    native = draw(st.sampled_from([f"{prefix}-{H[1]}", f"{prefix}-{H[1]}", FORUMS[2]]))
    evidence = draw(
        st.sampled_from([None, None, None, "scholarmend:proceedings_page https://example.org/x", ""])
    )
    statuses = st.sampled_from(["accepted", "accepted", "rejected", "withdrawn"])
    xs = [imported(native, "Trust in Machines", venue=venue, year=year, abstract=LONG,
                track=draw(st.sampled_from(["main", "main", "unknown"])), abstract_evidence=evidence,
                status=draw(statuses) if native in FORUMS else "accepted")]  # fmt: skip
    for fid in draw(st.lists(st.sampled_from(FORUMS), min_size=1, max_size=2, unique=True)):
        where = dict(venue=venue, year=draw(st.sampled_from([year, year, year, 2023, 2024])))
        title = draw(st.sampled_from(["Trust in AI", "Trust in AI", "Trust in Machines"]))
        crawled = draw(st.sampled_from([True, True, False]))  # else only the forum's RIS row, no note crawled
        if crawled:
            xs.append(paper(fid, title, source=draw(st.sampled_from(["openreview_v2", "openreview_v1"])),
                            track=draw(st.sampled_from(["main", "main", "workshop", "unknown"])),
                            status=draw(statuses), abstract=draw(abstracts), **where))  # fmt: skip
        if not crawled or draw(st.booleans()):  # the RIS row of the note's forum id, with a status of its own
            xs.append(imported(fid, title, abstract=draw(abstracts), fetched=draw(st.sampled_from([T0, T1, T2])),
                               status=draw(statuses), **where))  # fmt: skip
    if draw(
        st.booleans()
    ):  # a crawled listing: never joined by its abstract unless the import is in the group
        source = "neurips_proceedings" if venue == "NeurIPS" else "iclr_archive"
        xs.append(paper(f"{prefix}-{H[draw(st.sampled_from([1, 2]))]}", draw(st.sampled_from(TITLES)), source=source,
                        venue=venue, year=year, abstract=draw(abstracts)))  # fmt: skip
    return xs + draw(st.lists(records(), max_size=3))


# a rival that can never be the listed paper (TASK-126): a track the proceedings don't host, or not accepted
SET_ASIDE = [("workshop", "accepted"), ("workshop", "rejected"), ("main", "rejected"), ("main", "withdrawn"),
             ("datasets_benchmarks", "desk_rejected")]  # fmt: skip
# … and one that may be: another accepted submission, or a status or track nobody knows yet
REAL_RIVALS = [
    ("main", "accepted"),
    ("datasets_benchmarks", "accepted"),
    ("main", "unknown"),
    ("unknown", "accepted"),
]


@st.composite
def rivals(draw: st.DrawFn) -> tuple[list[PaperRecord], list[str], bool, int]:
    """A listing, its OpenReview note and same-title rivals (NeurIPS 2023/2024's workshop papers, 2021 D&B's
    rejected round-1 notes), sometimes one that may be the listed paper, plus noise from other venue-years:
    (records, the set-aside rivals' ids, whether a real rival is present, the year)."""
    year, track = draw(st.sampled_from([2023, 2024])), draw(st.sampled_from(["main", "datasets_benchmarks"]))
    title = lambda: draw(st.sampled_from(TITLES[:2]))  # noqa: E731  (one key, two spellings)
    note = lambda: draw(st.sampled_from(["openreview_v2", "openreview_v1", "ris"]))  # noqa: E731
    base = [
        paper("AbCd1234", title(), year=year, track=track, source=draw(st.sampled_from(["openreview_v2", "openreview_v1"]))),
        paper(f"nips-{H[1]}", title(), year=year, track=track, source=draw(st.sampled_from(["neurips_proceedings", "ris"]))),
    ]  # fmt: skip
    aside = [
        paper(fid, title(), year=year, track=t, status=s, source=note())
        for fid, (t, s) in zip(
            FORUMS[1:], draw(st.lists(st.sampled_from(SET_ASIDE), min_size=1, max_size=2)), strict=False
        )
    ]
    real = draw(st.booleans())
    if real:
        t, s = draw(st.sampled_from(REAL_RIVALS))
        base.append(paper("MnOp3456", title(), year=year, track=t, status=s, source=note()))
    noise = draw(st.lists(records().filter(lambda r: (r.venue, r.year) != ("NeurIPS", year)), max_size=3))
    return base + aside + noise, [r.id for r in aside], real, year


# same-title records that can never be a Creative AI listing's paper (TASK-137), by kind; `main_note` only while no
# main-track listing shares the title (then it may be that listing's paper, and stays a rival)
CREATIVE_ASIDE = ["education", "bare_other", "workshop", "main_note"]
# … and ones that keep the listing and its note apart: another Creative AI candidate, or a second listing
CREATIVE_BLOCKERS = ["creative_rival", "main_listing"]


@st.composite
def creative(draw: st.DrawFn) -> tuple[list[PaperRecord], list[str], bool, int]:
    """A NeurIPS Creative AI listing (the proceedings', its RIS copy, or both), its Creative AI note (bare path
    or a status suffix) and same-title others, plus noise from other venue-years: (records, the set-aside ids,
    whether a blocker is present, the year)."""
    year = draw(st.sampled_from([2023, 2024]))
    title = lambda: draw(st.sampled_from(TITLES[:2]))  # noqa: E731  (one key, two spellings)
    url = (
        f"https://proceedings.neurips.cc/paper_files/paper/{year}/hash/{H[1]}-Abstract-Creative_AI_Track.html"
    )
    venueid = f"NeurIPS.cc/{year}/Creative_AI_Track"
    listed_by = draw(
        st.lists(st.sampled_from(["neurips_proceedings", "ris"]), min_size=1, max_size=2, unique=True)
    )
    xs = [
        paper(f"nips-{H[1]}", title(), source=src, year=year, track="other", urls_proceedings=url,
              fetched=draw(st.sampled_from([T0, T1])))
        for src in listed_by
    ]  # fmt: skip
    suffix, status = draw(st.sampled_from([("", "unknown"), ("/Rejected_Submission", "rejected")]))
    xs.append(
        paper("AbCd1234", title(), year=year, track="other", status=status, venue_id_raw=venueid + suffix,
              source=draw(st.sampled_from(["openreview_v2", "openreview_v1"])))
    )  # fmt: skip
    kinds = draw(st.lists(st.sampled_from(CREATIVE_ASIDE + CREATIVE_BLOCKERS), max_size=3, unique=True))
    others = {
        "education": dict(
            track="other", status="unknown", venue_id_raw=f"NeurIPS.cc/{year}/Education_Program"
        ),
        "bare_other": dict(track="other", status="unknown"),
        "workshop": dict(track="workshop"),
        "main_note": dict(track="main"),
        "creative_rival": dict(track="other", status="unknown", venue_id_raw=venueid),
    }
    aside = []
    for fid, kind in zip(["EfGh5678", "IjKl9012", "MnOp3456"], kinds, strict=False):
        if kind == "main_listing":
            xs.append(paper(f"nips-{H[2]}", title(), source="neurips_proceedings", year=year))
            continue
        xs.append(paper(fid, title(), year=year, source=draw(st.sampled_from(["openreview_v2", "ris"])),
                        **others[kind]))  # fmt: skip
        if kind in CREATIVE_ASIDE and not (kind == "main_note" and "main_listing" in kinds):
            aside.append(xs[-1].id)
    blocked = (
        any(k in CREATIVE_BLOCKERS for k in kinds)
        or (
            "main_note" in kinds and "main_listing" in kinds
        )  # a main note beside a main listing: a candidate
        # a rejected note merges with its listing only alone (TASK-126): beside any rival it is set aside too
        or (status == "rejected" and bool(kinds))
        # … and only with a crawled listing: beside the RIS copy alone it would keep its status (`ris` ranks last)
        or (status == "rejected" and listed_by == ["ris"])
    )
    noise = draw(st.lists(records().filter(lambda r: (r.venue, r.year) != ("NeurIPS", year)), max_size=3))
    return xs + noise, aside, blocked, year


pools = st.one_of(
    st.lists(records(), max_size=10),
    chains(),
    links(),
    links(),
    rivals().map(lambda t: t[0]),
    creative().map(lambda t: t[0]),
    imports(),
)  # links() twice: weighted

# the reviewer's two over-merges, pinned
TWO_PROCEEDINGS_IDS = [
    paper(f"nips-{H[1]}", source="neurips_proceedings"),
    paper(f"nips-{H[2]}", source="ris"),
]
WORKSHOP_INTO_RIS_LISTING = [paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="ris")]
CHAIN = [
    paper("AbCd1234", "Trust in AI"),
    paper("AbCd1234", "Trust in Machines", source="ris"),
    paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
    paper(f"nips-{H[2]}", "Trust in Machines", source="neurips_proceedings"),
]


def forum_url(fid: str) -> str:
    return f"https://openreview.net/forum?id={fid}"


# the forum link's pinned cases: a listing linking the note under another title; the same across years
LINK_OTHER_TITLE = [
    paper("AbCd1234", "Trust in AI", venue="ICML", year=2023, urls_forum=forum_url("AbCd1234")),
    paper("pmlr-v202-key1", "Trust in Machines", source="pmlr", venue="ICML", year=2023, track="unknown",
          urls_forum=forum_url("AbCd1234")),
]  # fmt: skip
LINK_OTHER_YEAR = [
    paper("AbCd1234", "Trust in AI", venue="ICML", year=2024, urls_forum=forum_url("AbCd1234")),
    LINK_OTHER_TITLE[1],
]
# the title matches one note, the link names another: neither merge may happen by title
LINK_AGAINST_TITLE = [
    paper("AbCd1234", "Trust in AI", venue="ICML", year=2023),
    paper("EfGh5678", "Other", venue="ICML", year=2023),
    paper("pmlr-v202-key1", "Trust in AI", source="pmlr", venue="ICML", year=2023, urls_forum=forum_url("EfGh5678")),
]  # fmt: skip


def final_ids(result: DedupResult) -> dict[str, str]:
    """Every input id → the output record it ended in, following forum_link and title rows (each points from
    a cluster id to its survivor)."""
    step = {m.merged_id: m.survivor_id for m in result.merges if m.merged_id != m.survivor_id}
    ids = {m.merged_id for m in result.merges} | {r.id for r in result.records}

    def end(i: str) -> str:
        while i in step:
            i = step[i]
        return i

    return {i: end(i) for i in ids}


def linked_forums(records: list[PaperRecord]) -> set[str]:
    """Every forum id the records name, as their id or in a `urls.forum` claim dedup would keep."""
    kept = [c for r in dedup(records).records for c in r.provenance]
    own = {f for r in records if (f := r.forum_id)}
    return own | {
        f
        for c in kept
        if c.field == "urls.forum" and isinstance(c.value, str) and (f := urls.forum_id(c.value))
    }


def note(result: DedupResult) -> None:
    for c in result.conflicts:
        event(f"{c.field}:{c.resolution.split(':')[0]}")
    for m in result.merges:
        event(f"merge:{m.rule}")


# the same title and native id at another venue: a key without venue and year would merge these
SAME_TITLE_OTHER_VENUE = [
    paper("AbCd1234", "Trust in AI", source="openreview_v2", venue="ICLR", year=2023),
    paper("AbCd1234", "Trust in AI", source="ris", venue="NeurIPS", year=2023),
]
# … and at the same venue in another year
SAME_TITLE_OTHER_YEAR = [
    paper("AbCd1234", "Trust in AI", source="openreview_v2", venue="ICLR", year=2023),
    paper("AbCd1234", "Trust in AI", source="ris", venue="ICLR", year=2024),
]


# ICLR 2016 (TASK-130): OpenReview holds only the workshop track; the archive's main listing and a same-title note
ICLR_2016 = [
    archive(2016),
    paper("AbCd1234", venue="ICLR", year=2016, source="openreview_v1", track="workshop", status="unknown"),
]
# TASK-174 (nightly 37017691575): a RIS row with the note's id and the listing's PDF hash must not carry the note's
# `unknown` track into the listing as if it were a listing's own
RIS_BRIDGE = [
    paper("AbCd1234", source="openreview_v1", track="unknown"),
    paper("AbCd1234", source="ris", urls_pdf=f"https://papers.nips.cc/paper/2021/file/{H[2]}-Paper.pdf"),
    paper(f"nips-{H[2]}", source="neurips_proceedings"),
]
# the same where the note itself names the listed paper (no crawler emits this; the generator draws it)
NOTE_BRIDGE = [
    paper("AbCd1234", source="openreview_v2", track="unknown", urls_proceedings=nips(2)),
    paper(f"nips-{H[2]}", source="neurips_proceedings"),
]


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
@example(CHAIN)
@example(LINK_OTHER_TITLE)
@example(LINK_OTHER_YEAR)
@example(LINK_AGAINST_TITLE)
@example(ICLR_2016)
@example(RIS_BRIDGE)
@example(NOTE_BRIDGE)
def test_idempotent(xs: list[PaperRecord]) -> None:
    once = dedup(xs)
    note(once)
    twice = dedup(once.records)
    assert twice.records == once.records
    # every row but the superseded-claim ones (the merged record no longer holds those claims) repeats
    stable = [c for c in once.conflicts if not c.resolution.startswith(("newest:", "tie:"))]
    assert [c for c in twice.conflicts if not c.resolution.startswith(("newest:", "tie:"))] == stable


@given(pools, st.randoms(use_true_random=False))
@example(CHAIN, random.Random(0))
@example(LINK_AGAINST_TITLE, random.Random(0))
def test_order_independent(xs: list[PaperRecord], rnd: random.Random) -> None:
    shuffled = list(xs)
    rnd.shuffle(shuffled)
    assert dedup(shuffled) == dedup(xs)


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
@example(SAME_TITLE_OTHER_VENUE)
@example(SAME_TITLE_OTHER_YEAR)
@example(LINK_OTHER_YEAR)
def test_conservation_and_no_cross_venue_year_merges(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    outputs = Counter(r.id for r in result.records)
    assert all(n == 1 for n in outputs.values())  # one record per id
    assert Counter(r.id for r in xs) == outputs + Counter(m.merged_id for m in result.merges)
    by_id = {r.id: r for r in result.records}
    ends = final_ids(result)
    for x in xs:  # each input against the record it ended in: never merged across a venue or a year
        final = by_id[ends.get(x.id, x.id)]
        assert (x.venue, x.year) == (final.venue, final.year)


@given(rivals(), st.randoms(use_true_random=False))
def test_a_set_aside_rival_is_never_merged_and_blocks_nothing(
    shape: tuple[list[PaperRecord], list[str], bool, int], rnd: random.Random
) -> None:
    xs, aside, real, year = shape
    rnd.shuffle(xs)
    result = dedup(xs)
    note(result)
    outputs = Counter(r.id for r in result.records)
    assert all(n == 1 for n in outputs.values())
    assert Counter(r.id for r in xs) == outputs + Counter(m.merged_id for m in result.merges)
    ends = final_ids(result)
    orv, listing = f"op:neurips:{year}:AbCd1234", f"op:neurips:{year}:nips-{H[1]}"
    assert all(ends[i] == i for i in aside)  # never merged into anything, nor anything into them
    assert all(i in outputs and i not in {m.survivor_id for m in result.merges} for i in aside)
    assert (ends[listing] == ends[orv]) is not real  # the pair merges unless a real rival makes it ambiguous
    reported = {(c.value_a, c.value_b) for c in result.conflicts if c.field == "title_key"}
    assert all((ends[listing], i) in reported for i in aside)  # each set-aside rival has its row, always


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
@example(CHAIN)
@example(LINK_AGAINST_TITLE)
def test_never_folds_two_papers(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    ends = final_ids(result)
    by_id = {r.id: r for r in result.records}
    groups: dict[str, set[str]] = {}
    for x in xs:
        groups.setdefault(ends[x.id], set()).add(x.native)
    for out, natives in groups.items():
        assert len(natives & set(FORUMS)) <= 1  # distinct forum ids never share a record
        if len(natives) > 1:  # a merge across ids: every id's own and linked forum ids name one submission
            members = [x for x in xs if ends[x.id] == out]
            copies_of = {i: [x for x in members if x.id == i] for i in {x.id for x in members}}
            assert len(set().union(*(linked_forums(copies) for copies in copies_of.values()))) <= 1
        assert len(natives & set(PROCEEDINGS)) <= 1  # nor do distinct proceedings papers
        if len(natives) > 1 and natives & set(PROCEEDINGS):  # merged into a proceedings listing
            # a proceedings track, or unknown when every side was a listing without one (a mixed PMLR volume),
            # or `other` only where every input is NeurIPS Creative AI (TASK-137)
            members = [x for x in xs if ends[x.id] == out]
            if by_id[out].track == "other":
                assert is_creative_ai(by_id[out]) and all(is_creative_ai(x) for x in members)
            else:
                assert by_id[out].track in {"main", "datasets_benchmarks", "position", "unknown"}
                assert not any(is_creative_ai(x) for x in members)


@given(creative(), st.randoms(use_true_random=False))
def test_a_creative_ai_listing_merges_with_its_own_note_and_nothing_else(
    shape: tuple[list[PaperRecord], list[str], bool, int], rnd: random.Random
) -> None:
    """TASK-137: the listing and its Creative AI note merge unless another candidate blocks them; every
    same-title record of another family is set aside with its row, and never merges."""
    xs, aside, blocked, year = shape
    rnd.shuffle(xs)
    result = dedup(xs)
    note(result)
    outputs = Counter(r.id for r in result.records)
    assert Counter(r.id for r in xs) == outputs + Counter(m.merged_id for m in result.merges)
    ends = final_ids(result)
    orv, listing = f"op:neurips:{year}:AbCd1234", f"op:neurips:{year}:nips-{H[1]}"
    assert (ends[listing] == ends[orv]) is not blocked
    assert all(ends[i] == i and i not in {m.survivor_id for m in result.merges} for i in aside)
    if not blocked:
        merged = {r.id: r for r in result.records}[orv]
        assert merged.track == "other" and is_creative_ai(merged)
        if any(c.source == "neurips_proceedings" for c in merged.provenance):  # RIS alone is outranked
            assert merged.status == "accepted"
        reported = {(c.value_a, c.value_b) for c in result.conflicts if c.field == "title_key"}
        assert all((orv, i) in reported for i in aside)
    for x in xs:  # nothing but Creative AI ever shares a record with the Creative AI listing
        if ends[x.id] == ends[listing]:
            assert is_creative_ai(x)


OPENREVIEW, OFFICIAL = ("openreview_v2", "openreview_v1"), ("iclr_archive", "neurips_proceedings", "pmlr")


@given(pools)
@example(ICLR_2016)
@example(LINK_OTHER_TITLE)
@example(RIS_BRIDGE)
@example(NOTE_BRIDGE)
def test_track_is_openreview_where_it_holds_the_paper_else_the_proceedings(xs: list[PaperRecord]) -> None:
    """decision-005 §Track, per track (owner, 2026-09-29; TASK-130): a record carrying an OpenReview track claim
    is on a track OpenReview holds, and takes it; one without takes the proceedings' track; RIS only alone."""
    for r in dedup(xs).records:
        claims = {c.source: c.value for c in r.provenance if c.field == "track"}
        orv = [claims[s] for s in OPENREVIEW if s in claims]
        official = [claims[s] for s in OFFICIAL if s in claims]
        assert r.track == (orv or official or [claims["ris"]])[0]
        event("track:" + ("openreview" if orv else "proceedings" if official else "ris"))
        # a note merges into a listing only on a track in PROCEEDINGS_TRACKS, or as NeurIPS Creative AI beside a
        # Creative AI listing (TASK-137), even where it, or a same-id RIS row, names the listed paper (TASK-174)
        if orv and official:
            event("track:openreview-over-proceedings")
            assert orv[0] in PROCEEDINGS_TRACKS or (is_creative_ai(r) and set(official) == {"other"})


# TASK-179: the six pairs and the retitled seventh of snapshot 2026-10-05-47d4e190ca81, as shapes
LOST_SYMBOL = [
    paper("AbCd1234", "A$^2$Search", venue="ICLR", abstract=LONG),
    imported(f"iclr-{H[1]}", "ASearch", venue="ICLR", abstract=LONG),
]
TWO_RIS_ROWS = [
    paper("AbCd1234", venue="ICLR", abstract=LONG),
    imported("AbCd1234", "Trust in Machines", venue="ICLR", abstract=LONG),
    imported(f"iclr-{H[1]}", "Trust in Machines", venue="ICLR", abstract=LONG, fetched=T1),
]
SAME_ABSTRACT_OTHER_YEAR = [
    paper("AbCd1234", "A$^2$Search", venue="ICLR", year=2023, abstract=LONG),
    imported(f"iclr-{H[1]}", "ASearch", venue="ICLR", year=2024, abstract=LONG),
]
# a rejected note that is a listing by its own `urls.proceedings` claim, and the import of that paper
LISTED_REJECTED_NOTE = [
    paper(
        "AbCd1234", "Trust in AI", venue="NeurIPS", status="rejected", abstract=LONG, urls_proceedings=nips(1)
    ),
    imported(f"nips-{H[1]}", "Trust in Machines", venue="NeurIPS", abstract=LONG),
]
# TASK-174's shape: a rejected note, its forum id's RIS row naming a proceedings paper, and the import of that paper
REJECTED_NOTE_RIS_LISTING = [
    paper("AbCd1234", "Trust in AI", venue="NeurIPS", status="rejected", abstract=LONG),
    paper("AbCd1234", "Trust in AI", source="ris", venue="NeurIPS", abstract=LONG, urls_proceedings=nips(1)),
    imported(f"nips-{H[1]}", "Trust in Machines", venue="NeurIPS", abstract=LONG),
]


@given(pools)
@example(LOST_SYMBOL)
@example(TWO_RIS_ROWS)
@example(SAME_ABSTRACT_OTHER_YEAR)
@example(TWO_PROCEEDINGS_IDS)
@example(LISTED_REJECTED_NOTE)
@example(REJECTED_NOTE_RIS_LISTING)
def test_an_abstract_merge_always_holds_an_imported_record_and_its_abstract(xs: list[PaperRecord]) -> None:
    """Step 3 (TASK-179): every `abstract_venue_year` row joins two clusters of one venue and year that both keep
    an abstract with the row's key, into a group that held an imported record (sources `ris` alone) before the
    step; and a pool with no imported record has no such row."""
    result = dedup(xs)
    note(result)
    rows = [m for m in result.merges if m.rule == "abstract_venue_year"]
    if not any({c.source for c in x.provenance} == IMPORTED for x in xs):
        assert rows == []
    ends = final_ids(result)
    by_id = {r.id: r for r in result.records}
    for m in rows:
        out = by_id[ends[m.merged_id]]
        assert (out.venue, out.year) == (m.venue, m.year) and m.key.startswith("sha256:")
        members = [x for x in xs if ends[x.id] == out.id]
        assert {(x.venue, x.year) for x in members} == {(m.venue, m.year)}
        # both sides held the abstract: the merged cluster's inputs, and the rest of the group
        mine = [x for x in members if x.id == m.merged_id or final_before(result, x.id) == m.merged_id]
        rest = [x for x in members if x not in mine]
        for side in (mine, rest):
            assert any(x.abstract is not None and shown_key(abstract_key(x.abstract)) == m.key for x in side)
        # an imported record: some cluster in the group whose every input, before step 3, came from `ris` alone;
        # and at most one cluster that isn't one (an abstract never joins two crawled records)
        before = {final_before(result, x.id) for x in members}
        inputs = {cid: [x for x in members if final_before(result, x.id) == cid] for cid in before}
        crawled = [
            cid
            for cid, ins in inputs.items()
            if any({c.source for c in x.provenance} != IMPORTED for x in ins)
        ]
        assert len(crawled) <= 1 < len(before)
        for cid in (
            crawled
        ):  # the cluster's resolved status is one a listing can have, unless it is a listing itself
            # (decision-037 refuses only a record that is no listing; whether a listing by RIS evidence alone should
            # count is TASK-198), and its forum id survives
            status = dedup(inputs[cid]).records
            assert all(r.status in {"accepted", "unknown"} or is_listing(r) for r in status)
            if any(x.forum_id is not None and x.id == cid for x in inputs[cid]):
                assert out.id == cid
        if any(x.forum_id is not None for x in members):  # a forum id in the group is always the survivor's
            assert out.forum_id is not None


IMPORT_ONLY_WITHDRAWN = [  # the forum id's RIS row says withdrawn and was fetched last; no note crawled
    imported("AbCd1234", "One", venue="ICLR", abstract=LONG, status="withdrawn", fetched=T1),
    imported(f"iclr-{H[1]}", "Two", venue="ICLR", abstract=LONG),
]
WITHDRAWN_NOTE_IMPORTED_LISTING = [
    paper("AbCd1234", venue="ICLR", status="withdrawn"),
    imported(f"iclr-{H[1]}", venue="ICLR"),
]


@given(pools)
@example(IMPORT_ONLY_WITHDRAWN)
@example(WITHDRAWN_NOTE_IMPORTED_LISTING)
def test_a_status_no_listing_has_is_never_kept_by_merging_with_imports_alone(xs: list[PaperRecord]) -> None:
    """Steps 2 and 3 (decision-037): when a title or an abstract joins clusters, one that is no listing and is
    rejected, withdrawn or desk-rejected (a note, or a forum id's RIS row) has a companion that is no import, a
    crawled listing whose status outranks it. Merged with imports alone, `ris` ranking last, the record would keep
    that status, and an accepted paper would leave every accepted-only result."""
    result = dedup(xs)
    note(result)
    ends = final_ids(result)
    for out in result.records:
        members = [x for x in xs if ends[x.id] == out.id]
        inputs: dict[str, list[PaperRecord]] = {}
        for x in members:
            inputs.setdefault(linked_before(result, x.id), []).append(x)
        if len(inputs) < 2:
            continue
        for cid, ins in inputs.items():
            alone, _ = resolve(cid, [c for x in ins for c in x.provenance])
            if not is_listing(alone) and alone.status not in {"accepted", "unknown"}:
                assert any(
                    {c.source for c in x.provenance} != IMPORTED
                    for other, rest in inputs.items() if other != cid for x in rest
                )  # fmt: skip


def linked_before(result: DedupResult, rid: str) -> str:
    """The cluster an input id was in before step 2: follow only step 1's and the forum link's rows."""
    step = {
        m.merged_id: m.survivor_id
        for m in result.merges
        if m.merged_id != m.survivor_id and m.rule in {"forum_id", "native_id", "forum_link"}
    }
    while rid in step:
        rid = step[rid]
    return rid


def final_before(result: DedupResult, rid: str) -> str:
    """The cluster an input id was in before step 3: follow every row but the `abstract_venue_year` ones."""
    step = {
        m.merged_id: m.survivor_id
        for m in result.merges
        if m.merged_id != m.survivor_id and m.rule != "abstract_venue_year"
    }
    while rid in step:
        rid = step[rid]
    return rid
