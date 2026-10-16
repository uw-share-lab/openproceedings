"""The smoke test's comparison file (TASK-183): `compare_probe.ris` writes exactly the bytes asked for, and the
file passes the API's own caps, so `deploy/smoke-test.sh --compare` measures the proxy, not a refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings.api.compare import check_caps
from openproceedings.api.config import ApiConfig

from tests.deploy.compare_probe import MAX_LINE, MAX_LINES, _padding, ris

MIB = 1024 * 1024


def _records(path: Path, n: int) -> Path:
    rows = [
        {"title": f"A  title\nnumber {i}", "venue": "ICLR", "year": 2019, "abstract": "x"} for i in range(n)
    ]
    rows.append({"title": "no abstract", "venue": "ICLR", "year": 2019, "abstract": None})  # left out
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("size", [16 * MIB, 16 * MIB - 1, MIB + 7, 200_000])
def test_writes_exactly_the_size_asked_within_the_apis_caps(tmp_path: Path, size: int) -> None:
    out = tmp_path / "file.ris"
    assert ris(_records(tmp_path / "records.jsonl", 300), size, out) == 300
    data = out.read_bytes()
    assert len(data) == size
    config = ApiConfig(data_dir=tmp_path)  # the defaults: what `/meta` states and compare.yml leaves
    assert len(data) <= config.compare_max_body_bytes
    text = data.decode("utf-8")
    records = check_caps(
        text, max_records=config.compare_max_records, max_line_chars=config.compare_max_line_chars
    )
    assert records == 300
    assert "TI  - A title number 0\n" in text  # a title on one line, as the index's title key reads it


@pytest.mark.parametrize("n", [0, 8, 9, MAX_LINE, MAX_LINE + 1, MAX_LINE + 7, MAX_LINE + 8, 3 * MAX_LINE + 3])
def test_padding_is_exact_and_within_the_line_caps(n: int) -> None:
    pad = _padding(n)
    assert len(pad) == n
    lines = pad.splitlines(keepends=True)
    assert len(lines) <= MAX_LINES
    assert all(
        line.startswith(b"N1  - ") and line.endswith(b"\n") and 8 <= len(line) <= MAX_LINE for line in lines
    )


@pytest.mark.parametrize("n", [1, 7])
def test_padding_too_short_for_a_line_is_refused(n: int) -> None:
    with pytest.raises(SystemExit, match="too short"):
        _padding(n)


def test_a_size_too_small_for_the_records_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="too small"):
        ris(_records(tmp_path / "records.jsonl", 300), 1_000, tmp_path / "file.ris")
