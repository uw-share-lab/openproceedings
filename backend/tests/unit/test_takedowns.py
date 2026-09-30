"""The takedown list and log (`openproceedings.takedowns`; TASK-136, decision-022, spec 08 §Deploy)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings import takedowns
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
        f"{B} is listed but log.jsonl has no `withheld` entry for it"
    ]


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
