"""Shared pytest configuration: Hypothesis profiles (property-testing skill).

Select with HYPOTHESIS_PROFILE or `--hypothesis-profile`: `dev` (local default), `ci` (2,000 examples, the
`test` workflow) and `nightly` (50,000, the `nightly` workflow). `print_blob=True` so a CI failure prints a
`@reproduce_failure` blob; the example database (`.hypothesis/`) is gitignored.
"""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=200, deadline=500, print_blob=True)
settings.register_profile("ci", max_examples=2_000, deadline=2_000, print_blob=True)
settings.register_profile("nightly", max_examples=50_000, deadline=None, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
