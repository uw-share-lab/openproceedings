"""The Python pin (TASK-208): one CPython patch release everywhere, and never one with CVE-2025-6069.

CVE-2025-6069 is quadratic time in the standard library's `html.parser.HTMLParser` on malformed input
(python/cpython#135462), the parser every proceedings crawler reads pages with (`ingest/sources/html.py`).
The fix was merged on 2025-06-13 (3.13, 3.14) and 2025-07-03 (3.12); the first releases that hold it are
3.12.12, 3.13.6 and 3.14.0 (each backport commit compared against the release tags on GitHub). `.python-version`
pins the patch release that uv installs for development and CI, `requires-python` refuses a 3.12 before the
fix, and `deploy/api.Dockerfile`'s base image names the same patch release as `.python-version`.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# The first release of each minor that holds the CVE-2025-6069 fix; a later minor than the last row has it.
CVE_2025_6069_FIXED = {(3, 12): (3, 12, 12), (3, 13): (3, 13, 6), (3, 14): (3, 14, 0)}


def html_parser_fixed(version: tuple[int, int, int]) -> bool:
    """Whether CPython `version`'s HTMLParser has the CVE-2025-6069 fix."""
    first = CVE_2025_6069_FIXED.get(version[:2])
    if first is None:
        return version[:2] > max(CVE_2025_6069_FIXED)
    return version >= first


def _pinned() -> tuple[int, int, int]:
    text = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    assert match, f".python-version must pin an exact patch release, not {text!r}"
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def test_the_fixed_releases_table() -> None:
    assert not html_parser_fixed((3, 12, 9)) and not html_parser_fixed((3, 12, 11))
    assert html_parser_fixed((3, 12, 12)) and html_parser_fixed((3, 12, 15))
    assert not html_parser_fixed((3, 13, 5)) and html_parser_fixed((3, 13, 6))
    assert html_parser_fixed((3, 14, 0)) and html_parser_fixed((3, 15, 0))
    assert not html_parser_fixed((3, 11, 13))  # below the supported range: never fixed here


def test_the_interpreter_running_the_suite_has_the_fix() -> None:
    running = sys.version_info[:3]
    assert html_parser_fixed(running), (
        f"Python {'.'.join(map(str, running))} has CVE-2025-6069 (HTMLParser); uv sync installs the pinned "
        f"{'.'.join(map(str, _pinned()))} from .python-version (uv 0.12.22 or later knows it)"
    )


def test_python_version_pins_a_fixed_release() -> None:
    assert html_parser_fixed(_pinned())


def test_requires_python_refuses_a_3_12_without_the_fix() -> None:
    floor = ">={}.{}.{}".format(*CVE_2025_6069_FIXED[(3, 12)])
    for manifest in (ROOT / "pyproject.toml", ROOT / "backend" / "pyproject.toml"):
        project = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]
        assert project["requires-python"] == floor, manifest
    assert f'requires-python = "{floor}"' in (ROOT / "uv.lock").read_text(encoding="utf-8")


def test_the_api_image_runs_the_pinned_release() -> None:
    """Both `FROM python:` lines name `.python-version`'s release, so a Dependabot patch bump of the image fails
    here until `.python-version` moves with it (spec 08 §Monorepo layout, "Python pin")."""
    dockerfile = (ROOT / "deploy" / "api.Dockerfile").read_text(encoding="utf-8")
    tags = re.findall(r"^FROM python:(\S+?)-slim-bookworm@sha256:[0-9a-f]{64}\b", dockerfile, re.MULTILINE)
    assert tags == [".".join(map(str, _pinned()))] * 2
