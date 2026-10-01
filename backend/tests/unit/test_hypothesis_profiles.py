"""The Hypothesis profiles' wall-clock rule (decision-024, TASK-146; profiles in `backend/tests/conftest.py`).

`dev` has no deadline and suppresses only `too_slow`, so local load can't fail a property; `pr`, `ci` and
`nightly` suppress nothing, so a slow strategy still fails on a CI runner (shown below with a strategy that
sleeps). Case table: `.claude/scripts/tests/test-hypothesis-profiles.sh` (mutants in `mutants/gates.json`).
"""

from __future__ import annotations

import time

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
    # larger of 1 s and 5 deadlines; at pr's 2 s deadline this test would take 10 s)
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


@pytest.mark.parametrize("profile", ["pr", "ci"])
def test_the_pr_and_ci_profiles_keep_a_deadline(profile: str) -> None:
    assert settings.get_profile(profile).deadline is not None


def test_a_slow_strategy_fails_the_pr_profile() -> None:
    with pytest.raises(FailedHealthCheck, match="Input generation is slow"):
        run_slow_strategy("pr")


def test_a_slow_strategy_passes_the_dev_profile() -> None:
    run_slow_strategy("dev")
