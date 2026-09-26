"""Dedup: merge order, never-merge rules, precedence and the audit rows (dedup-rules skill)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from openproceedings.ingest.dedup import Conflict, Merge, dedup, resolve, title_key
from openproceedings.ingest.record import Claim, PaperRecord

T0 = datetime(2026, 9, 1, tzinfo=UTC)
T1 = datetime(2026, 9, 2, tzinfo=UTC)
H = {n: f"{n:x}" * 32 for n in range(1, 6)}


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
) -> PaperRecord:
    """A record whose fields are exactly what its claims say (as every importer builds them)."""
    values = {
        "title": title,
        "venue": venue,
        "year": year,
        "track": track,
        "status": status,
        "abstract": abstract,
    }
    claims = [
        Claim(field=f, value=v, source=source, fetched_at=fetched) for f, v in values.items() if v is not None
    ]  # type: ignore[arg-type]
    record, _ = resolve(f"op:{venue.lower()}:{year}:{native}", claims)
    return record


def test_title_key_is_the_token_contract() -> None:
    assert title_key("Trust in AI!") == title_key("trust  in ai") == "trust in ai"
    assert title_key("—") == ""


def test_same_forum_id_merges_across_the_two_searches_newest_claim_wins() -> None:
    old = paper("AbCd1234", source="ris", status="unknown", fetched=T0)
    new = paper("AbCd1234", source="ris", status="accepted", fetched=T1)
    result = dedup([new, old])
    [r] = result.records
    assert r.status == "accepted"
    assert result.merges == (Merge(r.id, r.id, "forum_id", "AbCd1234", "NeurIPS", 2024, "ris"),)
    assert Conflict(r.id, "status", "accepted", "ris", "unknown", "ris", "newest:ris") in result.conflicts


def test_same_proceedings_id_merges() -> None:
    a = paper(f"nips-{H[1]}", source="ris", fetched=T0)
    b = paper(f"nips-{H[1]}", source="ris", fetched=T1)
    result = dedup([a, b])
    assert len(result.records) == 1
    assert [m.rule for m in result.merges] == ["native_id"]


def test_same_forum_id_in_different_years_is_not_merged() -> None:
    result = dedup([paper("AbCd1234", year=2023), paper("AbCd1234", year=2024)])
    assert len(result.records) == 2 and not result.merges
    assert [c.resolution for c in result.conflicts] == ["venue_year_not_merged"]


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
    assert result.merges == (  # markup tokenizes like plain text, so the keys agree
        Merge(orv.id, proc.id, "title_venue_year", "trust in ai", "NeurIPS", 2024, "neurips_proceedings"),
    )
    fields = {c.field: c.resolution for c in result.conflicts}
    assert fields == {"title": "precedence:openreview_v2", "status": "precedence:neurips_proceedings"}


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


def test_two_openreview_submissions_with_one_title_both_survive() -> None:
    result = dedup([paper("AbCd1234"), paper("EfGh5678")])  # e.g. a paper and its workshop version
    assert len(result.records) == 2 and not result.merges
    assert [c.resolution for c in result.conflicts] == ["ambiguous_not_merged"]


def test_different_forum_ids_never_merge_even_across_sources() -> None:
    result = dedup([paper("AbCd1234"), paper("EfGh5678", source="ris")])
    assert len(result.records) == 2
    assert [c.resolution for c in result.conflicts] == ["ambiguous_not_merged"]


def test_a_workshop_paper_never_merges_into_proceedings() -> None:
    result = dedup([paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="neurips_proceedings")])
    assert len(result.records) == 2
    assert [c.resolution for c in result.conflicts] == ["track_not_merged"]


def test_two_candidates_from_one_source_are_ambiguous() -> None:
    result = dedup(
        [
            paper("AbCd1234"),
            paper(f"nips-{H[1]}", source="neurips_proceedings"),
            paper(f"nips-{H[2]}", source="neurips_proceedings"),
        ]
    )
    assert len(result.records) == 3 and not result.merges
    assert {c.resolution for c in result.conflicts} == {"ambiguous_not_merged"}


def test_three_sources_merge_into_one() -> None:
    result = dedup(
        [
            paper("AbCd1234"),
            paper(f"nips-{H[1]}", source="neurips_proceedings"),
            paper(f"nips-{H[1]}", source="ris"),
        ]
    )
    [r] = result.records
    assert r.id == "op:neurips:2024:AbCd1234"
    assert sorted(m.merged_id for m in result.merges) == [f"op:neurips:2024:nips-{H[1]}"] * 2


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
    assert "ambiguous_not_merged" in {c.resolution for c in result.conflicts}


def test_records_must_match_their_claims() -> None:
    r = paper("AbCd1234")
    with pytest.raises(ValueError, match="own claims"):
        dedup([r.model_copy(update={"track": "workshop"})])
    with pytest.raises(ValueError, match="no claim for"):
        dedup([PaperRecord.build(id=r.id, title="T", abstract=None, authors=(), venue="NeurIPS", year=2024,
                                 track="main", status="accepted")])  # fmt: skip
