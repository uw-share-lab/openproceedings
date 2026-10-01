"""The Hypothesis profiles' wall-clock rule (decision-024, TASK-146; profiles in `backend/tests/conftest.py`).

`dev` has no deadline and suppresses only `too_slow`, so local load can't fail a property; `pr`, `ci` and
`nightly` suppress nothing, so a slow strategy still fails on a CI runner (shown below with a strategy that
sleeps), and no test suppresses a health check itself. Case table:
`.claude/scripts/tests/test-hypothesis-profiles.sh` (mutants in `mutants/gates.json`).
"""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.errors import FailedHealthCheck


@st.composite
def slow_integers(draw: st.DrawFn) -> int:
    """0.15 s a draw: past a 1 s `too_slow` limit by the 7th of the 10 draws the health check times."""
    time.sleep(0.15)
    return draw(st.integers())


def run_slow_strategy(profile: str) -> None:
    # the profile's health checks, with a 200 ms deadline so the too_slow limit is 1 s (Hypothesis allows the
    # larger of 1 s and 5 deadlines; at pr's 2 s deadline this test would take 10 s). The profiles' own
    # deadlines are pinned by the tests below.
    @settings(settings.get_profile(profile), deadline=200, max_examples=10, database=None)
    @given(slow_integers())
    def prop(n: int) -> None:
        pass

    prop()


def test_dev_has_no_deadline_and_suppresses_only_too_slow() -> None:
    dev = settings.get_profile("dev")
    assert dev.deadline is None
    assert list(dev.suppress_health_check) == [HealthCheck.too_slow]


@pytest.mark.parametrize("profile", ["pr", "ci", "nightly"])
def test_the_ci_profiles_suppress_no_health_check(profile: str) -> None:
    assert list(settings.get_profile(profile).suppress_health_check) == []


@pytest.mark.parametrize(
    ("profile", "deadline"), [("pr", timedelta(seconds=2)), ("ci", timedelta(seconds=2)), ("nightly", None)]
)
def test_the_ci_profiles_keep_their_deadlines(profile: str, deadline: timedelta | None) -> None:
    # nightly has none, so its too_slow limit is Hypothesis's 30 s
    assert settings.get_profile(profile).deadline == deadline


@pytest.mark.parametrize(
    ("profile", "derandomized"), [("dev", False), ("pr", True), ("ci", False), ("nightly", False)]
)
def test_only_the_pr_gate_is_derandomized(profile: str, derandomized: bool) -> None:
    # pr runs the same examples on every PR; the others explore. With CI set, Hypothesis loads its built-in `ci`
    # profile (derandomized, too_slow suppressed); the case table also runs this file with CI=true, where a
    # profile registered without its parent would inherit that
    assert settings.get_profile(profile).derandomize is derandomized


def test_no_test_suppresses_a_health_check_itself() -> None:
    # nor borrows dev's suppression by loading or deriving from a profile itself
    tests = Path(__file__).resolve().parents[1]
    found = [
        str(f.relative_to(tests))
        for f in sorted(tests.rglob("*.py"))
        if f not in (tests / "conftest.py", Path(__file__).resolve())
        and any(
            s in f.read_text()
            for s in ("suppress_health_check", "HealthCheck", "get_profile(", "load_profile(")
        )
    ]
    assert found == []


def test_a_slow_strategy_fails_the_pr_profile() -> None:
    with pytest.raises(FailedHealthCheck, match="Input generation is slow"):
        run_slow_strategy("pr")


def test_a_slow_strategy_passes_the_dev_profile() -> None:
    run_slow_strategy("dev")
