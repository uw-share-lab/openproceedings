"""Dedup properties over small colliding pools (dedup-rules skill §Property tests)."""

from __future__ import annotations

from collections import Counter

from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import PaperRecord

from tests.unit.ingest.test_dedup import T0, T1, H, paper

TITLES = ["Trust in AI", "trust in AI!", "Trust in Machines", "—"]
FORUMS = ["AbCd1234", "EfGh5678", "IjKl9012"]


@st.composite
def records(draw: st.DrawFn) -> PaperRecord:
    source = draw(st.sampled_from(["openreview_v2", "openreview_v1", "neurips_proceedings", "ris"]))
    if source.startswith("openreview"):
        native = draw(st.sampled_from(FORUMS))
    elif source == "neurips_proceedings":
        native = f"nips-{draw(st.sampled_from(sorted(H.values())[:3]))}"
    else:
        native = draw(st.sampled_from([*FORUMS, *(f"nips-{h}" for h in sorted(H.values())[:3])]))
    return paper(
        native,
        draw(st.sampled_from(TITLES)),
        source=source,
        year=draw(st.sampled_from([2023, 2024])),
        track=draw(st.sampled_from(["main", "workshop"])),
        status=draw(st.sampled_from(["accepted", "rejected"])),
        fetched=draw(st.sampled_from([T0, T1])),
    )


pools = st.lists(records(), max_size=8)


@given(pools)
def test_idempotent(xs: list[PaperRecord]) -> None:
    once = dedup(xs).records
    assert dedup(once).records == once


@given(pools, st.randoms())
def test_order_independent(xs: list[PaperRecord], rnd: object) -> None:
    shuffled = list(xs)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert dedup(shuffled) == dedup(xs)


@given(pools)
def test_conservation_and_no_cross_venue_year_merges(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    survivors = Counter(r.id for r in result.records)
    merged = Counter(m.merged_id for m in result.merges)
    assert Counter(r.id for r in xs) == survivors + merged  # each input survives or is merged, once
    assert all(n == 1 for n in survivors.values())  # one record per id
    by_id = {r.id: r for r in result.records}
    for m in result.merges:
        s = by_id[m.survivor_id]
        assert (m.venue, m.year) == (s.venue, s.year)


@given(pools)
def test_distinct_forum_ids_never_share_a_record(xs: list[PaperRecord]) -> None:
    result = dedup(xs)
    for r in result.records:
        forums = {m.merged_id.rsplit(":", 1)[1] for m in result.merges if m.survivor_id == r.id} | {r.native}
        assert len(forums & set(FORUMS)) <= 1
