"""Writes the synthetic scholarmend fixture (`mended.ris` + `resolved.json`) for test_ris.py.

Every title, author, forum id and hash is invented (decision-004). The claim shapes copy real scholarmend
0.1.3 output: a leading BOM, bare-URL evidence for `proceedings_url`/`pmlr_url` claims (twice when the
RIS has both the page and the PDF), `venueid=<id>` for `openreview_api`, `openreview:<forum>` for its
abstract, `clean.ris:TI=<title>` for Scholar. Run `python backend/tests/fixtures/ris/generate.py` after
changing a row; the test module documents what each row is for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
H1, H2, H3, H4 = (
    "0123456789abcdef0123456789abcdef",
    "fedcba9876543210fedcba9876543210",
    "00112233445566778899aabbccddeeff",
    "ffeeddccbbaa99887766554433221100",
)
Q = "M1  - Query date: 2026-09-19 01:06:30"


def pu(host: str, year: int, sha: str, kind: str, track: str, query: str = "") -> str:
    part, doc = ("hash", "Abstract") if kind == "html" else ("file", "Paper")
    return f"https://{host}/paper_files/paper/{year}/{part}/{sha}-{doc}-{track}.{kind}{query}"


def c(
    field: str, value: str, source: str, evidence: str, tier: int = 2, conf: float = 0.99
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "source": source,
        "tier": tier,
        "confidence": conf,
        "evidence": evidence,
    }


def procs(venue: str, year: int, track: str, *urls: str) -> list[dict[str, Any]]:
    return [c(f, v, "proceedings_url", u) for u in urls for f, v in
            (("venue", venue), ("year", str(year)), ("track", track), ("version", "proceedings"))]  # fmt: skip


def orv(
    fid: str, vid: str, venue: str, year: int, track: str, abstract: str | None = None
) -> list[dict[str, Any]]:
    e = f"venueid={vid}"
    out = [c("forum_id", fid, "openreview_url", f"https://openreview.net/pdf?id={fid}")]
    out += [c(f, v, "openreview_api", e) for f, v in
            (("venue_id", vid), ("venue", venue), ("year", str(year)), ("track", track), ("version", "proceedings"))]  # fmt: skip
    if abstract:
        out.append(c("abstract", abstract, "openreview_api", f"openreview:{fid}"))
    return out


ROWS: list[dict[str, Any]] = []


def add(title: str, authors: list[str], jf: str, urls: list[str], py: int, ab: str, claims: list[dict[str, Any]],
        m1: str | None = Q, extra: tuple[str, ...] = ()) -> None:  # fmt: skip
    scholar = f"clean.ris:TI={title}"
    ris = ["TY  - PDF", *(f"AU  - {a}" for a in authors), f"TI  - {title}", f"JF  - {jf}"]
    ris += (
        [f"UR  - {u}" for u in urls] + [f"PY  - {py}///", f"AB  - {ab}"] + ([m1] if m1 else []) + list(extra)
    )
    ris += ["ER  - ", ""]
    claims = [
        *claims,
        c("abstract", ab, "scholar", scholar, 0, 0.3),
        c("authors", "; ".join(authors), "scholar", scholar, 0, 0.3),
    ]
    ROWS.append({"ris": ris, "title": title, "claims": claims})


NEURIPS = ("proceedings.neurips.cc", 2025, H1)
add("Synthetic Trust Benchmark for Language Models", ["Doe, J", "Roe, R", "..."], "NeurIPS",
    [pu(*NEURIPS, "html", "Conference"), pu(*NEURIPS, "pdf", "Conference")], 2025, "We introduce a synthetic … snippet",
    [*procs("NeurIPS", 2025, "Conference", pu(*NEURIPS, "html", "Conference"), pu(*NEURIPS, "pdf", "Conference")),
     c("abstract", "We introduce a synthetic benchmark for measuring trust calibration in language models.",
       "proceedings_page", pu(*NEURIPS, "html", "Conference"))],
    extra=("M1  - 3 cites: https://scholar.google.com/scholar?cites=1",))  # fmt: skip
add("An Imaginary Workshop Paper on Reliance", ["Poe, E"], "ICML", ["https://openreview.net/pdf?id=AbCdEf1234"], 2026,
    "A made-up abstract …", orv("AbCdEf1234", "ICML.cc/2026/Workshop/SyntheticWS", "ICML", 2026, "Workshop/SyntheticWS",
                              "A made-up abstract about human reliance on model outputs."),
    m1="M1  - Query date: 2026-09-18 10:03:05")  # fmt: skip
add("A Snippet-Only ICLR Record", ["Moe, M"], "ICLR", [pu("proceedings.iclr.cc", 2025, H2, "html", "Conference")], 2025,
    "… a truncated snippet about trust …",
    procs("ICLR", 2025, "Conference", pu("proceedings.iclr.cc", 2025, H2, "html", "Conference")))  # fmt: skip
add("An arXiv Preprint Out of Scope", ["Zoe, Z"], "arXiv.org", ["https://arxiv.org/abs/2601.00001"], 2026,
    "Not a paper from the three venues.",
    [c("venue", "arXiv.org", "semanticscholar", "s2:An arXiv Preprint"),
     c("abstract", "A full Semantic Scholar abstract.", "semanticscholar", "s2:An arXiv Preprint")])  # fmt: skip
add("No Identifier Anywhere", ["Koe, K"], "ICML", ["https://example.org/paper.pdf"], 2025,
    "A record whose only URL identifies nothing.",
    [c("venue", "ICML", "scholar", "clean.ris:TI=No Identifier Anywhere", 0, 0.3)])  # fmt: skip
PMLR_INDEX = "PMLR v267: International Conference on Machine Learning"
add("A Synthetic ICML Paper Reached Through PMC", ["Loe, L"], "ICML", ["https://pmc.ncbi.nlm.nih.gov/articles/PMC00000001/"],
    2025, "Only a PMC link …",
    [c("pmc_id", "PMC00000001", "pmc_url", "https://pmc.ncbi.nlm.nih.gov/articles/PMC00000001/"),
     c("pmlr_volume", "267", "pmc_api", "PMC esummary volume=267"), c("venue", "ICML", "pmlr_index", PMLR_INDEX),
     c("venue_id", "PMLR v267", "pmlr_index", PMLR_INDEX), c("year", "2025", "pmlr_index", PMLR_INDEX)])  # fmt: skip
PMLR = [
    "https://proceedings.mlr.press/v202/smith23a.html",
    "https://proceedings.mlr.press/v202/smith23a/smith23a.pdf",
]
add("A Synthetic PMLR Paper on Calibration", ["Smith, A", "Jones, B"], "ICML", PMLR, 2023, "A synthetic PMLR abstract …",
    [c("pmlr_volume", "202", "pmlr_url", u, 1, 1.0) for u in PMLR]
    + [c("venue", "ICML", "pmlr_index", "PMLR v202: International Conference on Machine Learning")],
    m1="M1  - Query date: 2026-09-20 08:00:00")  # fmt: skip
add("A Synthetic Rejected Submission", ["Noe, N"], "ICLR", ["https://openreview.net/pdf?id=Rej_ected-1"], 2024,
    "A rejected paper's snippet …",
    orv("Rej_ected-1", "ICLR.cc/2024/Conference/Rejected_Submission", "ICLR", 2024, "Conference/Rejected_Submission",
        "A synthetic abstract of a rejected submission."))  # fmt: skip
DB = pu("Papers.NIPS.cc", 2024, H3, "pdf", "Datasets_and_Benchmarks_Track", "?utm_source=chatgpt.com")
add("A Synthetic Datasets Track Paper", ["Hoe, H"], "NeurIPS", [DB], 2024, "A benchmark snippet …",
    [*procs("NeurIPS", 2024, "Datasets_and_Benchmarks_Track", DB),
     c("abstract", "", "openreview_api", "openreview:none"),
     c("abstract", "A synthetic datasets-track abstract with  extra   spaces.", "proceedings_page", DB)])  # fmt: skip
add("A Synthetic Paper With No Query Date", ["Qoe, Q"], "ICLR", [pu("proceedings.iclr.cc", 2024, H4, "html", "Conference")],
    2024, "No M1 line …", procs("ICLR", 2024, "Conference", pu("proceedings.iclr.cc", 2024, H4, "html", "Conference")),
    m1=None)  # fmt: skip
add("A Synthetic Hidden Forum", ["Roe, S"], "ICLR", ["https://openreview.net/pdf?id=HiDden0001"], 2025, "Hidden …",
    [c("forum_id", "HiDden0001", "openreview_url", "https://openreview.net/pdf?id=HiDden0001")])  # fmt: skip
add("A Synthetic NeurIPS Media Link", ["Soe, T"], "NeurIPS", ["https://neurips.cc/media/PosterPDFs/NeurIPS%202023/1.png"],
    2023, "Poster only …", [])  # fmt: skip

if __name__ == "__main__":
    (HERE / "mended.ris").write_text(
        "﻿" + "\n".join(line for r in ROWS for line in r["ris"]), encoding="utf-8"
    )
    resolved = [{"title": r["title"], "source_file": "clean.ris", "conflicts": [], "claims": r["claims"],
                 "fields": {cl["field"]: {k: cl[k] for k in ("confidence", "evidence", "source", "tier", "value")}
                            for cl in reversed(r["claims"])}} for r in ROWS]  # fmt: skip
    (HERE / "resolved.json").write_text(
        json.dumps(resolved, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(ROWS)} records")
