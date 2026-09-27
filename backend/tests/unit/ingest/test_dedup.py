"""Dedup: merge order, never-merge rules, precedence and the audit rows (dedup-rules skill)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from openproceedings.ingest.dedup import (
    CONFLICT_FIELDS,
    PRECEDENCE,
    Conflict,
    Merge,
    dedup,
    resolve,
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
    if prefix in ("nips", "iclr"):
        host = "neurips" if prefix == "nips" else "iclr"
        return f"https://proceedings.{host}.cc/paper_files/paper/{year}/hash/{rest}-Abstract-Conference.html"
    if prefix == "pmlr":
        volume, _, key = rest.partition("-")
        return f"https://proceedings.mlr.press/{volume}/{key}.html"
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
    **extra: Any,  # further claim fields, e.g. `urls_proceedings=nips(1)`
) -> PaperRecord:
    """A record whose fields are exactly what its claims say (as every importer builds them); a
    proceedings-id record names itself in `urls.proceedings` unless the caller says otherwise."""
    extra.setdefault("urls_proceedings", self_url(native, year))
    values: dict[str, Any] = {"title": title, "venue": venue, "year": year, "track": track, "status": status,
                              "abstract": abstract, **{k.replace("urls_", "urls.", 1): v for k, v in extra.items()}}  # fmt: skip
    claims = [
        Claim(field=f, value=v, source=source, fetched_at=fetched) for f, v in values.items() if v is not None
    ]  # type: ignore[arg-type]
    record, _ = resolve(f"op:{venue.lower()}:{year}:{native}", claims)
    return record


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


def test_the_precedence_table_is_decision_005() -> None:
    text = ("openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris")
    assert PRECEDENCE["status"] == ("neurips_proceedings", "pmlr", "openreview_v2", "openreview_v1", "ris")
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


def test_records_must_match_their_claims() -> None:
    r = paper("AbCd1234")
    with pytest.raises(ValueError, match="own claims"):
        dedup([r.model_copy(update={"track": "workshop"})])
    with pytest.raises(ValueError, match="no claim for"):
        dedup([PaperRecord.build(id=r.id, title="T", abstract=None, authors=(), venue="NeurIPS", year=2024,
                                 track="main", status="accepted")])  # fmt: skip
