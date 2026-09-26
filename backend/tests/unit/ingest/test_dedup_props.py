"""Dedup properties over small colliding pools (dedup-rules skill §Property tests).

The pools are small on purpose (four titles, three forum ids, two proceedings papers per venue, two
years), so records collide often: every source, venue, track and status appears, OpenReview records
sometimes carry a proceedings URL, and the fetch times tie.
"""

from __future__ import annotations

import random
from collections import Counter

from hypothesis import event, example, given
from hypothesis import strategies as st
from openproceedings.ingest.dedup import DedupResult, dedup
from openproceedings.ingest.record import PaperRecord

from tests.unit.ingest.test_dedup import T0, T1, T2, H, nips, paper

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
    return paper(
        native,
        draw(st.sampled_from(TITLES)),
        source=source,
        venue=venue,
        year=draw(st.sampled_from([2023, 2024])),
        track=draw(st.sampled_from(["main", "workshop", "position", "datasets_benchmarks", "unknown"])),
        status=draw(st.sampled_from(["accepted", "rejected", "unknown"])),
        abstract=draw(st.sampled_from([None, "An abstract.", "Another abstract."])),
        fetched=draw(st.sampled_from([T0, T1, T2])),
        **extra,
    )


@st.composite
def chains(draw: st.DrawFn) -> list[PaperRecord]:
    """One paper under two titles (two sources share its forum id), each title matching a different
    record from one proceedings source, plus noise: the shape that must never fold two papers."""
    venue, prefix, source = draw(
        st.sampled_from([("NeurIPS", "nips", "neurips_proceedings"), ("ICLR", "iclr", "neurips_proceedings")])
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


pools = st.one_of(st.lists(records(), max_size=10), chains())

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


def final_ids(result: DedupResult) -> dict[str, str]:
    """Every input id → the output record it ended in (title rows point from a cluster id to a survivor)."""
    title = {m.merged_id: m.survivor_id for m in result.merges if m.rule == "title_venue_year"}
    ids = {m.merged_id for m in result.merges} | {r.id for r in result.records}
    return {i: title.get(i, i) for i in ids}


def note(result: DedupResult) -> None:
    for c in result.conflicts:
        event(f"{c.field}:{c.resolution.split(':')[0]}")
    for m in result.merges:
        event(f"merge:{m.rule}")


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
@example(CHAIN)
def test_idempotent(xs: list[PaperRecord]) -> None:
    once = dedup(xs)
    note(once)
    twice = dedup(once.records)
    assert twice.records == once.records
    precedence = [c for c in once.conflicts if c.resolution.startswith("precedence:")]
    assert [c for c in twice.conflicts if c.resolution.startswith("precedence:")] == precedence


@given(pools, st.randoms(use_true_random=False))
@example(CHAIN, random.Random(0))
def test_order_independent(xs: list[PaperRecord], rnd: random.Random) -> None:
    shuffled = list(xs)
    rnd.shuffle(shuffled)
    assert dedup(shuffled) == dedup(xs)


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
def test_conservation_and_no_cross_venue_year_merges(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    outputs = Counter(r.id for r in result.records)
    assert all(n == 1 for n in outputs.values())  # one record per id
    assert Counter(r.id for r in xs) == outputs + Counter(m.merged_id for m in result.merges)
    by_id = {r.id: r for r in result.records}
    ends = final_ids(result)
    for m in result.merges:
        final = by_id[ends[m.merged_id]]
        assert (m.venue, m.year) == (final.venue, final.year)


@given(pools)
@example(TWO_PROCEEDINGS_IDS)
@example(WORKSHOP_INTO_RIS_LISTING)
@example(CHAIN)
def test_never_folds_two_papers(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    ends = final_ids(result)
    by_id = {r.id: r for r in result.records}
    groups: dict[str, set[str]] = {}
    for x in xs:
        groups.setdefault(ends[x.id], set()).add(x.native)
    for out, natives in groups.items():
        assert len(natives & set(FORUMS)) <= 1  # distinct forum ids never share a record
        assert len(natives & set(PROCEEDINGS)) <= 1  # nor do distinct proceedings papers
        if len(natives) > 1 and natives & set(PROCEEDINGS):  # merged into a proceedings listing
            assert by_id[out].track in {"main", "datasets_benchmarks", "position"}
