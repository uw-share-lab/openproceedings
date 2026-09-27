"""The RIS file a person imports into Covidence by hand (task-004 AC#1; checklist in
`docs/results/2026-09-27-covidence-check.md`) is exactly what the RIS writer produces today: six synthetic
records, one per venue and naming era, a multi-author record with non-ASCII names, an astral-plane title, a
record with no abstract, and proceedings-only records with no forum URL. If the writer changes, this test
fails, and the hand import has to be redone before the fixture is regenerated:

    uv run python -c "from tests.unit.test_covidence_fixture import regenerate; regenerate()"

(run from `backend/`). Records are invented (decision-004): no real paper, author or forum id.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from openproceedings.export import Provenance, write

FIXTURE = Path(__file__).resolve().parents[3] / "docs" / "results" / "2026-09-27-covidence-fixture.ris"
PROVENANCE = Provenance("fixture0000a", "0" * 64, "2026-09-27")
NIPS_HASH = "3f9a1c0d5e7b2a4c6d8e0f1a2b3c4d5e"

RECORDS: list[dict[str, Any]] = [
    {
        "id": "op:iclr:2024:Xq7Lm2Pz9A",
        "title": "𝒪(log n) Regret for 𝔽-Divergence Bandits",  # U+1D4AA and U+1D53D: outside the BMP
        "abstract": None,
        "authors": ["Varga, Eszter", "Mensah, Kofi"],
        "venue": "ICLR",
        "year": 2024,
        "track": "main",
        "urls": {
            "forum": "https://openreview.net/forum?id=Xq7Lm2Pz9A",
            "pdf": "https://openreview.net/pdf?id=Xq7Lm2Pz9A",
        },
    },
    {
        "id": "op:iclr:2025:bT4kR8sW1n",
        "title": "Calibrated Trust in Language-Model Assistants Under Distribution Shift",
        "abstract": (
            "People rely on language-model assistants more when the assistant sounds confident, whether or not "
            "it is right. We study how that reliance changes under distribution shift, where the assistant's "
            "accuracy drops but its stated confidence does not. In three preregistered experiments "
            "(N = 1,204) we find that verbalised uncertainty reduces over-reliance by 23% without reducing "
            "appropriate reliance, and that the effect survives a shift in task domain."
        ),
        "authors": ["Lindqvist, Maja", "Okonkwo, Adaeze", "Park, Joon-ho"],
        "venue": "ICLR",
        "year": 2025,
        "track": "main",
        "urls": {
            "forum": "https://openreview.net/forum?id=bT4kR8sW1n",
            "pdf": "https://openreview.net/pdf?id=bT4kR8sW1n",
        },
    },
    {
        "id": "op:icml:2023:pmlr-v202-okafor23a",
        "title": "Sample-Efficient Evaluation of Human-AI Teams",
        "abstract": (
            "Evaluating a human-AI team is expensive because every data point needs a person. We propose an "
            "adaptive design that chooses which items to show next, and prove that it estimates team accuracy "
            "within $\\epsilon$ using $O(\\log(1/\\delta)/\\epsilon^2)$ items. On two crowdsourced tasks it "
            "matches the full evaluation with 38% of the annotations."
        ),
        "authors": ["Okafor, Chidi", "Brennan, Siobhán"],
        "venue": "ICML",
        "year": 2023,
        "track": "main",
        "urls": {
            "pdf": "https://proceedings.mlr.press/v202/okafor23a/okafor23a.pdf",
            "proceedings": "https://proceedings.mlr.press/v202/okafor23a.html",
        },
    },
    {
        "id": f"op:neurips:2017:nips-{NIPS_HASH}",
        "title": "Learning When to Defer to an Expert",
        "abstract": (
            "A classifier that may defer a decision to a human expert should do so when the expert is more "
            "likely to be right. We give a consistent surrogate loss for learning the classifier and the "
            "deferral rule jointly, and show on three medical imaging tasks that the joint system is more "
            "accurate than either the classifier or the expert alone."
        ),
        "authors": ["Moreau, Élodie", "Tanaka, Hiroshi"],
        "venue": "NeurIPS",
        "year": 2017,
        "track": "main",
        "urls": {
            "proceedings": f"https://proceedings.neurips.cc/paper_files/paper/2017/hash/{NIPS_HASH}-Abstract.html",
        },
    },
    {
        "id": "op:neurips:2023:Hn3vQ6eYt0",
        "title": "Explanations That Help: A Benchmark for Appropriate Reliance",
        "abstract": (
            "Explanations are meant to help people decide when to follow an AI's advice.\nWe release a "
            "benchmark of 14 decision tasks with ground truth, human baselines and a protocol for measuring "
            "appropriate reliance, and evaluate nine explanation methods. None improves appropriate reliance "
            "over showing the model's confidence alone."
        ),
        "authors": [
            "Şahin, Elif",
            "Nguyễn, Thị Hương",
            "Zhang, Yíhán",
            "O'Neill, Aoife",
            "García-López, Mateo",
            "Van der Berg, Pieter",
            "Kowalczyk, Łukasz",
        ],
        "venue": "NeurIPS",
        "year": 2023,
        "track": "main",
        "urls": {
            "forum": "https://openreview.net/forum?id=Hn3vQ6eYt0",
            "pdf": "https://openreview.net/pdf?id=Hn3vQ6eYt0",
        },
    },
    {
        "id": "op:neurips:2024:Rk2wP5dLx8",
        "title": "TrustBench: Measuring Over-Reliance on AI Advice at Scale",
        "abstract": (
            "We introduce TrustBench, a dataset of 52,000 human decisions made with and without AI advice "
            "across 11 domains, and use it to compare six measures of over-reliance."
        ),
        "authors": ["Adeyemi, Tolu", "Fischer, Lena"],
        "venue": "NeurIPS",
        "year": 2024,
        "track": "datasets_benchmarks",
        "urls": {
            "forum": "https://openreview.net/forum?id=Rk2wP5dLx8",
            "pdf": "https://openreview.net/pdf?id=Rk2wP5dLx8",
            "doi": "10.5555/trustbench.2024.001",
        },
    },
]


def render() -> str:
    out = io.StringIO()
    assert write("ris", sorted(RECORDS, key=lambda r: r["id"]), PROVENANCE, out) == len(RECORDS)
    return out.getvalue()


def regenerate() -> None:
    FIXTURE.write_bytes(render().encode("utf-8"))


def test_the_covidence_fixture_is_what_the_writer_writes() -> None:
    assert FIXTURE.read_bytes() == render().encode("utf-8"), "writer changed: redo the Covidence import"


def test_the_covidence_fixture_reads_back_with_the_reference_parser() -> None:
    from scholarmend.parse import parse_ris

    parsed = {r.first("ID"): r for r in parse_ris(FIXTURE.read_text(encoding="utf-8"), FIXTURE.name)}
    assert sorted(parsed) == sorted(r["id"] for r in RECORDS)
    for r in RECORDS:
        got = parsed[r["id"]].fields
        assert got["TY"] == ["CPAPER"] and got["TI"] == [r["title"]] and got["AU"] == r["authors"]
        assert got["PY"] == [str(r["year"])] and got.get("AB", []) == (
            [" ".join(r["abstract"].split())] if r["abstract"] else []
        )
    t2 = {r["id"].split(":")[1] + r["id"].split(":")[2]: parsed[r["id"]].fields["T2"][0] for r in RECORDS}
    assert t2["neurips2017"] == "Conference on Neural Information Processing Systems (NIPS 2017)"
    assert t2["neurips2023"] == "Conference on Neural Information Processing Systems (NeurIPS 2023)"
    assert t2["icml2023"] == "International Conference on Machine Learning (ICML 2023)"
    assert t2["iclr2025"] == "International Conference on Learning Representations (ICLR 2025)"
