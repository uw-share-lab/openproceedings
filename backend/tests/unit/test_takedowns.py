"""The takedown list and log (`openproceedings.takedowns`; TASK-136, decision-022, spec 08 §Deploy)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings import takedown_check, takedowns
from openproceedings.takedowns import LOG_FIELDS, TakedownError, check_log, load, parse

A, B = "op:iclr:2024:Rej_ected-1", "op:neurips:2025:nips-0123456789abcdef0123456789abcdef"


def test_the_list_is_ids_with_comments_and_blank_lines() -> None:
    text = f"# withheld abstracts\n\n{A}\n  {B}   # 2026-09-30, see the log\n{A}\n"
    assert parse(text) == {A, B}


@pytest.mark.parametrize(
    "line",
    ["Rej_ected-1", "op:iclr:24:x", "op:acl:2024:Abcd1234", f"{A} {B}", "https://openreview.net/forum?id=x"],
)
def test_a_line_that_is_not_one_record_id_is_refused(line: str) -> None:
    with pytest.raises(TakedownError, match=r"line 2: .* is not a record id") as e:
        parse(f"{A}\n{line}\n")
    assert e.value.reason == "takedowns_invalid"


def test_a_missing_list_is_empty_and_an_unreadable_one_is_refused(tmp_path: Path) -> None:
    assert load(tmp_path / "withheld.txt") == frozenset()
    (tmp_path / "withheld.txt").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(TakedownError) as e:
        load(tmp_path / "withheld.txt")
    assert e.value.reason == "takedowns_unreadable"


def test_the_paths_are_under_the_data_dir(tmp_path: Path) -> None:
    assert takedowns.list_path(tmp_path) == tmp_path / "takedowns" / "withheld.txt"
    assert takedowns.log_path(tmp_path) == tmp_path / "takedowns" / "log.jsonl"


def entry(rid: str = A, decision: str = "withheld", **over: object) -> str:
    row: dict[str, object] = {
        "record_id": rid,
        "received": "2026-09-30",
        "requester": "Rights Holder <rights@example.org>",
        "basis": "copyright in the abstract",
        "decision": decision,
        "applied": "2026-10-01",
        "first_index_version": None,
    }
    row.update(over)
    return json.dumps(row)


def log_file(tmp_path: Path, *lines: str, mode: int = 0o600) -> Path:
    path = tmp_path / "log.jsonl"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    path.chmod(mode)
    return path


def test_a_complete_private_log_has_no_problems(tmp_path: Path) -> None:
    path = log_file(tmp_path, entry(), entry(B, "declined"), entry(B, "withheld"))
    assert check_log(path, frozenset({A, B})) == []
    assert set(LOG_FIELDS) == set(json.loads(entry()))


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660])
def test_a_log_others_can_read_is_a_problem(tmp_path: Path, mode: int) -> None:
    [problem] = check_log(log_file(tmp_path, entry(), mode=mode), frozenset({A}))
    assert "readable by others" in problem.message and "chmod 600" in problem.message


def test_a_listed_id_without_a_withheld_entry_is_a_problem(tmp_path: Path) -> None:
    path = log_file(tmp_path, entry(B, "declined"))
    assert [p.message for p in check_log(path, frozenset({B}))] == [
        f"{B} is listed but its latest entry in log.jsonl is not `withheld`"
    ]


def test_the_latest_entry_for_an_id_is_the_one_that_counts(tmp_path: Path) -> None:
    lifted = log_file(tmp_path, entry(), entry(decision="lifted"))
    assert [p.message for p in check_log(lifted, frozenset({A}))] == [
        f"{A} is listed but its latest entry in log.jsonl is not `withheld`"
    ]
    again = log_file(tmp_path, entry(), entry(decision="lifted"), entry())
    assert check_log(again, frozenset({A})) == []


def test_a_log_owned_by_another_account_is_a_problem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = log_file(tmp_path, entry())
    monkeypatch.setattr(takedowns.os, "getuid", lambda: path.stat().st_uid + 1)
    [problem] = check_log(path, frozenset({A}))
    assert "owned by another account" in problem.message


def test_a_named_list_that_is_missing_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TakedownError) as e:
        load(tmp_path / "withheld.txt", required=True)
    assert e.value.reason == "takedowns_missing"


def test_a_missing_log_is_a_problem_only_when_something_is_listed(tmp_path: Path) -> None:
    assert check_log(tmp_path / "log.jsonl", frozenset()) == []
    [problem] = check_log(tmp_path / "log.jsonl", frozenset({A}))
    assert "missing" in problem.message


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[1]",
        json.dumps({"record_id": A}),
        entry(decision="maybe"),
        entry("nope"),
        entry(extra="x"),
    ],
)
def test_a_malformed_entry_is_named_by_line_never_quoted(tmp_path: Path, line: str) -> None:
    problems = check_log(log_file(tmp_path, entry(), line), frozenset({A}))
    assert [p.message.split(":")[0] for p in problems] == ["log.jsonl line 2"]
    assert all("Rights Holder" not in p.message and "example.org" not in p.message for p in problems)


# --- op takedown check's pure parts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "phrase"),
    [
        ("Calibrated Trust in Agents", "calibrated trust in agents"),
        ("Learning with 日本語 data", "learning with"),  # a phrase has no gaps: the leading run only
        ("α-divergence bounds", None),  # no usable leading word
    ],
)
def test_the_title_query_is_the_leading_run_of_plain_words(title: str, phrase: str | None) -> None:
    got = takedown_check.title_query(title, A)
    if phrase is None:
        assert got is None
    else:
        assert got == f'title:"{phrase}" {takedown_check.cell_query(A)}'


def test_the_cell_query_names_the_ids_venue_and_year_and_every_track_and_status() -> None:
    q = takedown_check.cell_query(A)
    assert q.startswith("venue:ICLR year:2024 track:(") and "status:(accepted" in q


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        (None, 1.0),
        ("3", 3.0),
        ("600", 60.0),
        ("Wed, 21 Oct 2026 07:28:00 GMT", 1.0),
        ("-1", 1.0),
        ("٣", 1.0),
        ("²", 1.0),
    ],
)
def test_retry_after_reads_whole_seconds_only(header: str | None, seconds: float) -> None:
    assert takedown_check.retry_after(header) == seconds


# --- the same paper under another id (TASK-067) ------------------------------------------------------------------

OLD, NEW = "op:icml:2023:Abcd1234", "op:icml:2024:Abcd1234"  # one native id: a rekey (a corrected year)
DUP = "op:icml:2024:pmlr-v235-smith24a"  # a duplicate some build merged into NEW (PMLR's native id form)


def test_a_listed_paper_is_withheld_under_its_other_ids_in_any_version() -> None:
    merges = [(NEW, DUP)]  # (survivor, merged)
    assert takedowns.same_paper(frozenset({NEW}), merges, [OLD, DUP, B]) == {OLD, DUP}
    assert takedowns.same_paper(frozenset({NEW}), (), [OLD, DUP, B]) == {
        OLD
    }  # no merge known: the rekey only
    assert takedowns.same_paper(frozenset({OLD}), merges, [NEW, DUP]) == {NEW, DUP}  # forward too
    assert takedowns.same_paper(frozenset({DUP}), merges, [OLD]) == {OLD}  # merged, then rekeyed
    assert takedowns.same_paper(frozenset({NEW}), merges, [NEW]) == {NEW}
    assert takedowns.same_paper(frozenset(), merges, [OLD, NEW, DUP]) == frozenset()


def test_merges_chain_and_other_papers_are_left_alone() -> None:
    far = "op:icml:2024:pmlr-v235-jones24b"
    merges = [(NEW, DUP), (DUP, far), (A, "op:iclr:2024:Other-99")]
    assert takedowns.same_paper(frozenset({far}), merges, [NEW, OLD, A, B]) == {NEW, OLD}


def test_an_id_the_log_withholds_but_the_list_dropped_is_a_problem(tmp_path: Path) -> None:
    """TASK-067: a line deleted from the list lifts a takedown the log still records as `withheld`."""
    path = log_file(tmp_path, entry(), entry(B), entry(B, "lifted"))
    assert [p.message for p in check_log(path, frozenset())] == [
        f"{A}'s latest entry in log.jsonl is `withheld`, but the list doesn't name it: list it again, or log it lifted"
    ]
    assert check_log(path, frozenset({A})) == []


def test_a_byte_order_mark_is_read_and_an_invisible_character_is_refused(tmp_path: Path) -> None:
    (tmp_path / "withheld.txt").write_text(f"﻿{A}\n", encoding="utf-8")
    assert load(tmp_path / "withheld.txt") == {A}
    with pytest.raises(TakedownError, match=r"line 1: .* is not a record id"):
        parse(f"{A}​\n")


H = "nips-0266e33d3f546cb5436a10798e657d97"


def test_a_proceedings_hash_links_no_two_years() -> None:
    """TASK-067 review: a NeurIPS or ICLR proceedings hash is md5 of a per-year paper number, so the same hash in
    two years is two papers (one NeurIPS hash names four, 2013 to 2019, in the 2026-09-29 snapshot). Only
    globally unique native ids (OpenReview forum ids, PMLR volume keys) link ids; a merge still does."""
    listed = f"op:neurips:2019:{H}"
    others = [f"op:neurips:{y}:{H}" for y in (2013, 2015, 2016)]
    assert takedowns.same_paper(frozenset({listed}), (), [listed, *others]) == {listed}
    # nor through a merge: the listed forum id's merged listing shares a hash with another year's listing
    forum, survivor = "op:neurips:2022:-3Pg7QNIF1S", "op:neurips:2024:h0rbjHyWoa"
    merges = [(forum, f"op:neurips:2022:{H}"), (survivor, f"op:neurips:2024:{H}")]
    held = [forum, f"op:neurips:2022:{H}", survivor, f"op:neurips:2024:{H}"]
    assert takedowns.same_paper(frozenset({forum}), merges, held) == {forum, f"op:neurips:2022:{H}"}
    iclr = "iclr-0123456789abcdef0123456789abcdef"
    assert (
        takedowns.same_paper(frozenset({f"op:iclr:2024:{iclr}"}), (), [f"op:iclr:2026:{iclr}"]) == frozenset()
    )


@pytest.mark.parametrize(
    ("rid", "linked"),
    [("op:iclr:2024:Abcd1234", True), ("op:icml:2024:pmlr-v235-smith24a", True), (f"op:neurips:2019:{H}", False),
     (f"op:neurips:2021:{H}-round1", False), ("op:iclr:2015:iclr-0123456789abcdef0123456789abcdef", False)],
)  # fmt: skip
def test_only_globally_unique_native_ids_link(rid: str, linked: bool) -> None:
    assert (takedowns.global_native(rid) is not None) is linked
