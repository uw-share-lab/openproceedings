"""Serve the synthetic 5k fixture index for Playwright (TASK-046; spec 05 §Testing). Its records carry authors
and each abstract's source claim (`attributed`, TASK-134), so the results list's attribution is exercised."""

from __future__ import annotations

import tempfile
from pathlib import Path

from openproceedings.api import ApiConfig, RateLimit
from openproceedings.api.server import serve

from tests.contract.conftest import attributed, build
from tests.fixtures.corpus.synthetic_5k import records


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="openproceedings-e2e-") as raw:
        data = Path(raw)
        version = build(list(records()), data / "snapshots", "fixture", data / "indexes", attributed)
        (data / "indexes" / "current").symlink_to(version)
        config = ApiConfig(
            data_dir=data,
            cors_origins=("http://127.0.0.1:3000",),
            rate_limit=RateLimit(enabled=False),
            load_in_background=False,
            handle_sighup=False,
            records_min_free_bytes=0,
        )
        serve(config, "127.0.0.1", 8000, log_level="WARNING", log_format="text")


if __name__ == "__main__":
    main()
