"""PMLR volume → ICML year and track (spec 01 §Sources, PMLR row): `ICML_PMLR_VOLUMES`, pinned by `test_ris.py`;
a config file with verification columns comes with the PMLR adapter (task-053). Shared by the RIS importer and the PMLR adapter (task-053).

A volume that holds more than one track gives `unknown`: ICML added position papers in 2024, and they sit
in the same volume as the main conference, so a PMLR URL alone can't say which track a paper is in.
"""

from __future__ import annotations

ICML_PMLR_VOLUMES: dict[int, tuple[int, str]] = {
    119: (2020, "main"),
    139: (2021, "main"),
    162: (2022, "main"),
    202: (2023, "main"),
    235: (2024, "unknown"),  # main + position papers
    267: (2025, "unknown"),  # main + position papers
}
