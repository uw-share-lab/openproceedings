"""The RIS file a person imports into Covidence by hand (task-004 AC#1; checklist in
`docs/results/2026-09-27-covidence-check.md`) is exactly what the RIS writer produces today: seven synthetic
records covering each venue and naming era, a multi-author record with non-ASCII names, an astral-plane
title, a record with no abstract, proceedings-only records with no forum URL, and a rejected paper. The dedup
probe beside it is pinned too. If the writer changes, these tests fail, and the hand import has to be redone
after the fixture is regenerated:

    uv run python -c "from tests.unit.test_covidence_fixture import regenerate; regenerate()"

(run from `backend/`). Records are invented (decision-004): no real paper, author or forum id.
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

import pytest
from openproceedings.export import Provenance, write
from openproceedings.vocab import venue_name

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
        "status": "accepted",
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
        "status": "accepted",
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
        "status": "accepted",
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
        "status": "accepted",
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
        "status": "accepted",
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
        "status": "accepted",
        "urls": {
            "forum": "https://openreview.net/forum?id=Rk2wP5dLx8",
            "pdf": "https://openreview.net/pdf?id=Rk2wP5dLx8",
            "doi": "10.5555/trustbench.2024.001",
        },
    },
    {
        "id": "op:iclr:2024:Wd8nJ3cV5r",
        "title": "Do Confidence Displays Reduce Automation Bias? A Null Result",
        "abstract": (
            "We tested whether showing a model's confidence reduces automation bias in a loan-approval task "
            "(N = 312) and found no effect. We report the study as a null result."
        ),
        "authors": ["Haddad, Rania", "Kim, Seo-yeon"],
        "venue": "ICLR",
        "year": 2024,
        "track": "main",
        "status": "rejected",
        "urls": {
            "forum": "https://openreview.net/forum?id=Wd8nJ3cV5r",
            "pdf": "https://openreview.net/pdf?id=Wd8nJ3cV5r",
        },
    },
]

T2 = {  # every record's venue string, written out by hand
    "op:iclr:2024:Xq7Lm2Pz9A": "International Conference on Learning Representations (ICLR 2024)",
    "op:iclr:2024:Wd8nJ3cV5r": "International Conference on Learning Representations (ICLR 2024)",
    "op:iclr:2025:bT4kR8sW1n": "International Conference on Learning Representations (ICLR 2025)",
    "op:icml:2023:pmlr-v202-okafor23a": "International Conference on Machine Learning (ICML 2023)",
    f"op:neurips:2017:nips-{NIPS_HASH}": "Conference on Neural Information Processing Systems (NIPS 2017)",
    "op:neurips:2023:Hn3vQ6eYt0": "Conference on Neural Information Processing Systems (NeurIPS 2023)",
    "op:neurips:2024:Rk2wP5dLx8": "Conference on Neural Information Processing Systems (NeurIPS 2024)",
}

PROBE = FIXTURE.with_name("2026-09-27-covidence-dedup-probe.ris")
VL_ONLY = "op:neurips:2023:Hn3vQ6eYt0"  # probe 1 is this fixture record with `VL  - 36` added, nothing else
# probes 2 and 3: copies as another database might export them (title, authors and year unchanged)
OTHER_DATABASE = [
    [
        ("TY", "CONF"),
        ("TI", "Sample-Efficient Evaluation of Human-AI Teams"),
        ("AU", "Okafor, Chidi"),
        ("AU", "Brennan, Siobhán"),
        ("PY", "2023"),
        ("T2", "Proceedings of the 40th International Conference on Machine Learning"),
    ],
    [
        ("TY", "JOUR"),
        ("TI", "TrustBench: Measuring Over-Reliance on AI Advice at Scale"),
        ("AU", "Adeyemi, Tolu"),
        ("AU", "Fischer, Lena"),
        ("PY", "2024"),
        ("T2", "Advances in Neural Information Processing Systems"),
        ("VL", "37"),
    ],
]  # written as the writer writes RIS (`ER  - ` keeps its trailing space, which an editor would strip)
# probes 4 and 5: a fixture record with one field changed the way another database might write it
YEAR_EARLIER = "op:iclr:2025:bT4kR8sW1n"  # probe 4: fixture record 3 with `PY` one year earlier, nothing else
INITIALS = "op:neurips:2023:Hn3vQ6eYt0"  # probe 5: fixture record 6 with initials-only authors, nothing else
INITIALS_AUTHORS = [
    "Şahin, E.",
    "Nguyễn, T. H.",
    "Zhang, Y.",
    "O'Neill, A.",
    "García-López, M.",
    "Van der Berg, P.",
    "Kowalczyk, Ł.",
]
CHECK = FIXTURE.with_name("2026-09-27-covidence-check.md")
IMPORTED_SHA = re.compile(r"^- Fixture sha256 imported: `([0-9a-f]*)`$", re.MULTILINE)
TASK_DIRS = [FIXTURE.parents[2] / "backlog" / d for d in ("tasks", "completed")]


def render(records: list[dict[str, Any]] = RECORDS) -> str:
    out = io.StringIO()
    assert write("ris", sorted(records, key=lambda r: r["id"]), PROVENANCE, out) == len(records)
    return out.getvalue()


def fixture_record(record_id: str) -> dict[str, Any]:
    (record,) = [r for r in RECORDS if r["id"] == record_id]
    return record


def render_probe() -> str:
    t2 = f"T2  - {T2[VL_ONLY]}\n"
    others = "".join("".join(f"{t}  - {v}\n" for t, v in lines) + "ER  - \n\n" for lines in OTHER_DATABASE)
    earlier = fixture_record(YEAR_EARLIER)
    year = f"PY  - {earlier['year']}\n"
    initials = fixture_record(INITIALS)
    authors = "".join(f"AU  - {a}\n" for a in initials["authors"])
    return (
        render([fixture_record(VL_ONLY)]).replace(t2, t2 + "VL  - 36\n")
        + others
        + render([earlier]).replace(year, f"PY  - {earlier['year'] - 1}\n")
        + render([initials]).replace(authors, "".join(f"AU  - {a}\n" for a in INITIALS_AUTHORS))
    )


def probe_lines(n: int) -> list[str]:
    """Probe `n` (1-based) of the probe file, as lines."""
    return PROBE.read_text(encoding="utf-8").split("ER  - \n\n")[n - 1].splitlines()


def fixture_lines(record_id: str) -> list[str]:
    return render([fixture_record(record_id)]).split("ER  - \n\n")[0].splitlines()


def regenerate() -> None:
    FIXTURE.write_bytes(render().encode("utf-8"))
    PROBE.write_bytes(render_probe().encode("utf-8"))


def test_the_covidence_fixture_is_what_the_writer_writes() -> None:
    assert FIXTURE.read_bytes() == render().encode("utf-8"), "writer changed: redo the Covidence import"


def test_the_first_probe_differs_from_its_fixture_record_by_the_volume_alone() -> None:
    from scholarmend.parse import parse_ris

    assert PROBE.read_bytes() == render_probe().encode("utf-8")
    parsed = parse_ris(PROBE.read_text(encoding="utf-8"), PROBE.name)
    assert [r.fields["TY"] for r in parsed] == [["CPAPER"], ["CONF"], ["JOUR"], ["CPAPER"], ["CPAPER"]]
    assert [r.fields.get("VL") for r in parsed] == [["36"], None, ["37"], None, None]
    assert [line for line in probe_lines(1) if line != "VL  - 36"] == fixture_lines(VL_ONLY)


def test_probe_4_differs_from_fixture_record_3_by_a_year_earlier_alone() -> None:
    probe, record = probe_lines(4), fixture_lines(YEAR_EARLIER)
    assert [(a, b) for a, b in zip(probe, record, strict=True) if a != b] == [("PY  - 2024", "PY  - 2025")]


def test_probe_5_differs_from_fixture_record_6_by_initials_only_authors_alone() -> None:
    probe, record = probe_lines(5), fixture_lines(INITIALS)
    changed = [(a, b) for a, b in zip(probe, record, strict=True) if a != b]
    assert [a for a, _ in changed] == [f"AU  - {x}" for x in INITIALS_AUTHORS]
    assert [b for _, b in changed] == [f"AU  - {x}" for x in fixture_record(INITIALS)["authors"]]
    for short, full in zip(INITIALS_AUTHORS, fixture_record(INITIALS)["authors"], strict=True):
        family, given = full.split(", ")
        assert short == f"{family}, " + " ".join(f"{g[0]}." for g in given.split())  # the same person


def test_git_never_rewrites_the_line_endings_of_a_pinned_ris_file() -> None:
    """`.gitattributes` marks every `.ris` `-text`, so a checkout with `core.autocrlf` can't turn the LF
    fixture into CRLF (which would change its sha256 and the bytes the writer is compared with)."""
    import subprocess

    root = FIXTURE.parents[2]
    paths = [FIXTURE, PROBE, root / "backend" / "tests" / "fixtures" / "ris" / "mended.ris"]
    out = subprocess.run(
        ["git", "check-attr", "text", "--", *(str(p.relative_to(root)) for p in paths)],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert out.splitlines() == [f"{p.relative_to(root)}: text: unset" for p in paths]


def recorded_sha(check: str) -> str:
    """The sha256 the check's Outcome records ("" while the import is pending); a malformed line fails with
    the format it must have."""
    found = IMPORTED_SHA.findall(check)
    assert len(found) == 1, (
        f"{CHECK.name}'s Outcome needs exactly one line `- Fixture sha256 imported: `<64 lowercase hex>`` "
        f"(nothing between the backticks until the import is done); found {len(found)} such lines"
    )
    return str(found[0])


@pytest.mark.parametrize(
    "line",
    ["- Fixture sha256 imported: ABC123", "- Fixture sha256 imported: `ABCDEF`", "Fixture sha256: `00`", ""],
)
def test_a_malformed_sha_line_names_the_format_it_needs(line: str) -> None:
    with pytest.raises(AssertionError, match=r"- Fixture sha256 imported: `<64 lowercase hex>`"):
        recorded_sha(f"## Outcome (fill in)\n{line}\n")
    assert recorded_sha("- Fixture sha256 imported: ``\n") == ""


def test_the_hand_imported_fixture_is_the_pinned_one() -> None:
    """Active once the check records the sha256 of the file a person imported, or once TASK-004 AC#1 is
    ticked: the imported file must be this one, so the check still describes what the writer writes."""
    recorded = recorded_sha(CHECK.read_text(encoding="utf-8"))
    ticked = any(
        "- [x] #1 " in p.read_text(encoding="utf-8")
        for d in TASK_DIRS
        if d.is_dir()
        for p in d.glob("task-004 *")
    )
    if not recorded and not ticked:
        return  # the import is still pending: nothing to compare yet
    assert recorded, "TASK-004 AC#1 is ticked: record the imported fixture's sha256 in the check's Outcome"
    assert recorded == hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), "the imported fixture isn't this one"


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
        assert got["KW"] == [r["track"], f"status:{r['status']}"]
        status_note = f"Submitted to {venue_name(r['venue'], r['year'])}; status: {r['status']} (not in its proceedings)."
        assert got["N1"] == ([] if r["status"] == "accepted" else [status_note]) + [PROVENANCE.line()]
    assert PROVENANCE.line().endswith(" · exported 2026-09-27")
    assert {rid: r.fields["T2"] for rid, r in parsed.items()} == {rid: [t2] for rid, t2 in T2.items()}
