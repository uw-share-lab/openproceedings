"""The deploy smoke test's data directory (TASK-065): what `deploy/smoke-test.sh` relies on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings.engine.index import verify_index

from tests.deploy.fixture_data import write


def test_writes_three_verified_indexes_current_and_an_empty_list(tmp_path: Path) -> None:
    data = tmp_path / "data"
    versions = write(data)
    assert set(versions) == {"big", "small", "spare"}
    assert len(set(versions.values())) == 3  # three distinct index_versions to promote and retire
    for name, version in versions.items():
        manifest = json.loads((data / "indexes" / version / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["doc_count"] == {"big": 5000, "small": 300, "spare": 100}[name]
        verify_index(data / "indexes" / version)
    assert (data / "indexes" / "current").readlink() == Path(versions["big"])
    assert (data / "takedowns" / "withheld.txt").read_text(encoding="utf-8") == ""
    assert sorted(p.name for p in (data / "takedowns").iterdir()) == ["withheld.txt"]  # never a log beside it


def test_refuses_a_directory_that_is_not_empty(tmp_path: Path) -> None:
    (tmp_path / "keep").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="is not empty"):
        write(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep"]
