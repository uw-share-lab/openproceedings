"""Serve the synthetic 5k fixture index for Playwright (TASK-046; spec 05 §Testing). Its records carry authors
and each abstract's source claim (`attributed`, TASK-134), so the results list's attribution is exercised. The
first two results of the default `trust` search are made twins (a `twin` claim each, decision-029; TASK-162),
so the "See also" line is drawn on the first results page and the first result's paper page: a claim is
provenance only, so the ranking that picks them is the final index's. One ICML paper of the `trust venue:ICML`
results page, off the default `trust` page (so that baseline is unchanged), takes its abstract from an ICML
submission page (an `icml_site` claim whose evidence says it is as submitted, as TASK-207's are), so its
result and paper page draw the submission-time note (TASK-210). Comparisons are on (`POST /compare`,
TASK-177), as on a local instance, so the search page's "Compare with your records" panel is exercised.

The ports are 8000 (API) and 3000 (web) unless `OP_E2E_API_PORT` / `OP_E2E_WEB_PORT` say otherwise
(`frontend/playwright.config.ts` reads the same two), so a run can sit beside an instance already on them.

Three instances serve the one index, so a spec reaches states only another configuration gives without mocking
an answer in the browser (TASK-182; `frontend/e2e/instances.ts` sends a page's API calls to one of them):

- the API port: the default, as a local instance (no rate limit, comparisons on);
- port + 1, `tight`: at most 2 concept groups and 5 terms counted (`too_many_groups`, `too_costly`), the rate
  limit on with a comparison cooldown of 200 times the slot time used (a fixture comparison takes hundredths
  of a second, so the default factor of 3 would be over before a second click; at 200 the 429 and its
  countdown last a few seconds), and a 2,048-byte comparison file cap (an over-cap file);
- port + 2, `plain`: comparisons off, as a public instance is by default (the panel is not offered)."""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from openproceedings.api import ApiConfig, RateLimit
from openproceedings.api.server import serve, uvicorn_config
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.dedup import AS_SUBMITTED
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.query.parser import parse
from openproceedings.search import run

from tests.contract.conftest import attributed, build
from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import records

BUILT = datetime(2026, 9, 26, tzinfo=UTC)  # the twin claims' fetch time (the fixture's build time)
TWINNED_QUERY = "trust"  # frontend/e2e/accessibility.spec.ts searches it and opens its first result
SUBMITTED_QUERY = "trust venue:ICML"  # accessibility.spec.ts finds the submission-time note there
PAGE = 50  # the web app's results page
# the ICML-98 submission page a TASK-207 claim names (`icml_sites.toml`), as the claim's url and evidence give it
SUBMISSION_PAGE = "http://www.cs.wisc.edu:80/icml98/papers/paper2.html"
SUBMISSION_CAPTURE = f"https://web.archive.org/web/19991009084141id_/{SUBMISSION_PAGE}"


def _chosen(data: Path) -> tuple[dict[str, str], str]:
    """From a scratch build: the first two hits of the default `TWINNED_QUERY` search, each → the other; and the
    first hit of `SUBMITTED_QUERY`'s first page that the default search's first page doesn't show."""
    version = build(
        list(records()), data / "scratch-snapshots", "fixture", data / "scratch-indexes", attributed
    )
    engine = TantivyEngine(data / "scratch-indexes" / version)
    shown = [h.id for h in run(engine, parse(TWINNED_QUERY), limit=PAGE).hits]
    first, second = shown[:2]
    submitted = next(h.id for h in run(engine, parse(SUBMITTED_QUERY), limit=PAGE).hits if h.id not in shown)
    return {first: second, second: first}, submitted


def _with_claims(twins: dict[str, str], submitted: str) -> Callable[[Rec], PaperRecord]:
    def paper(r: Rec) -> PaperRecord:
        p = attributed(r)
        if p.id == submitted:  # precedence ranks `pmlr` over `icml_site` over `ris`: so it replaces `pmlr`'s
            kept = tuple(c for c in p.provenance if not (c.field == "abstract" and c.source == "pmlr"))
            claim = Claim(
                field="abstract", value=p.abstract, source="icml_site", url=SUBMISSION_CAPTURE, fetched_at=BUILT,
                evidence=f"official ICML 1998 page {SUBMISSION_PAGE}, Internet Archive capture "
                f"{SUBMISSION_CAPTURE}: {AS_SUBMITTED}; the page's contact details are not kept",
            )  # fmt: skip
            return p.model_copy(update={"provenance": (*kept, claim)})
        if p.id not in twins:
            return p
        claim = Claim(field="twin", value=(twins[p.id],), source="openreview_v1", fetched_at=BUILT)
        return p.model_copy(update={"provenance": (*p.provenance, claim)})

    return paper


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="openproceedings-e2e-") as raw:
        data = Path(raw)
        twins, submitted = _chosen(data)
        version = build(
            list(records()), data / "snapshots", "fixture", data / "indexes", _with_claims(twins, submitted)
        )
        (data / "indexes" / "current").symlink_to(version)
        config = ApiConfig(
            data_dir=data,
            cors_origins=(f"http://127.0.0.1:{int(os.environ.get('OP_E2E_WEB_PORT', '3000'))}",),
            rate_limit=RateLimit(enabled=False),
            load_in_background=False,
            handle_sighup=False,
            records_min_free_bytes=0,
            compare_enabled=True,
            # a search's group counts get 30 s, not production's 50 ms grace and 2 s wait: the browser tests
            # assert the counts arrive, on a machine other suites may load (the defaults are held by
            # tests/unit and tests/contract test_group_counts.py)
            group_count_grace_seconds=30.0,
            group_count_wait_seconds=30.0,
        )
        port = int(os.environ.get("OP_E2E_API_PORT", "8000"))
        others = {
            port + 1: config.model_copy(  # `tight`
                update={
                    "max_counted_groups": 2,
                    "max_counted_terms": 5,
                    "rate_limit": RateLimit(capacity=10_000, compare_cooldown_factor=200),
                    "compare_max_body_bytes": 2_048,
                }
            ),
            port + 2: config.model_copy(update={"compare_enabled": False}),  # `plain`
        }
        for other_port, other in others.items():
            import uvicorn

            server = uvicorn.Server(
                uvicorn_config(ApiConfig.model_validate(other.model_dump()), "127.0.0.1", other_port)
            )
            threading.Thread(target=server.run, name=f"e2e-api-{other_port}", daemon=True).start()
        serve(config, "127.0.0.1", port, log_level="WARNING", log_format="text")


if __name__ == "__main__":
    main()
