"""OP_EARLY_FAILURES=1 prints a failed test's report when it fails (`_EarlyFailures` in `backend/tests/conftest.py`;
TASK-057): the nightly workflow's long steps are interrupted at their time limit, which drops pytest's
end-of-session FAILURES section. Each case runs a scratch session in a subprocess with the repo's conftest hooks.
Case table: `.claude/scripts/tests/test-early-failures.sh` (mutants in `mutants/gates.json`).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ERROR = re.compile(r"^::error::\S*test_fails failed \(call\); its report follows$", re.MULTILINE)


def session(tmp_path: Path, early: bool, *args: str) -> str:
    (tmp_path / "conftest.py").write_text("from tests.conftest import pytest_configure  # noqa: F401\n")
    (tmp_path / "test_scratch.py").write_text(
        "def test_passes():\n    pass\n\n\ndef test_fails():\n    assert 1 == 2, 'the scratch failure'\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "OP_EARLY_FAILURES"}
    env["PYTHONPATH"] = str(BACKEND)
    if early:
        env["OP_EARLY_FAILURES"] = "1"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly", "--rootdir", str(tmp_path),
         *args, str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    assert run.returncode == 1, run.stdout + run.stderr  # the scratch failure, and nothing else
    return run.stdout


@pytest.mark.parametrize("args", [("-v", "-n", "2"), ("-q", "-n", "2"), ("-v",), ("-q",)])
def test_a_failure_is_reported_once_before_the_summary(tmp_path: Path, args: tuple[str, ...]) -> None:
    out = session(tmp_path, True, *args)
    found = ERROR.findall(out)
    assert len(found) == 1, out  # on its own line, and once: xdist workers don't print it again
    report = out.index(found[0])
    assert "the scratch failure" in out[report : out.index("= FAILURES =")], out


def test_nothing_is_printed_early_without_the_variable(tmp_path: Path) -> None:
    out = session(tmp_path, False, "-v", "-n", "2")
    assert "::error::" not in out, out
