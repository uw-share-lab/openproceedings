"""Writes the synthetic scholarmend fixture (`mended.ris` + `resolved.json`) for test_ris.py.

Every title, author, forum id and hash is invented (decision-004). The claim shapes copy real scholarmend
0.1.3 output: a leading BOM, bare-URL evidence for `proceedings_url`/`pmlr_url` claims (twice when the
RIS has both the page and the PDF), `venueid=<id>` for `openreview_api`, `openreview:<forum>` for its
abstract, `clean.ris:TI=<title>` for Scholar. The `venue_string` rows (TASK-098, written to `v1/`) and the `invitation` rows (TASK-157) are written by
hand, since the real corpus has none: the claim copies scholarmend 0.1.4's shape (OpenReview's `content.venue` verbatim,
source `openreview_api`, tier 2, confidence 0.99, evidence `venueid=<id>`). Run `python backend/tests/fixtures/ris/generate.py` after
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


def v1(title: str, fid: str, vid: str, venue_string: str, evidence: str | None = None,
       also: tuple[str, str] | None = None, invitation: tuple[str, str] | None = None,
       also_invitation: tuple[str, str] | None = None) -> None:  # fmt: skip
    """An OpenReview record with scholarmend 0.1.4's `venue_string` claim (evidence: its venueid), plus
    optionally a second one (`also`: string, evidence), and optionally scholarmend 0.1.5's `invitation` claim
    (`invitation`: the note's top-level invitation verbatim, evidence)."""
    venue, year, track = vid.split("/", 2)
    venue = venue.removesuffix(".cc")
    add(title, ["Voe, V"], venue, [f"https://openreview.net/pdf?id={fid}"], int(year), "An OpenReview snippet …",
        [*orv(fid, vid, venue, int(year), track),
         c("venue_string", venue_string, "openreview_api", evidence or f"venueid={vid}"),
         *([c("venue_string", also[0], "openreview_api", also[1])] if also else []),
         *([c("invitation", invitation[0], "openreview_api", invitation[1])] if invitation else []),
         *([c("invitation", also_invitation[0], "openreview_api", also_invitation[1])] if also_invitation else [])],
        rows=V1_ROWS)  # fmt: skip


ROWS: list[dict[str, Any]] = []  # mended.ris + resolved.json
V1_ROWS: list[dict[str, Any]] = []  # v1/mended.ris + v1/resolved.json: the venue_string rows (TASK-098)


def add(title: str, authors: list[str], jf: str, urls: list[str], py: int, ab: str, claims: list[dict[str, Any]],
        m1: str | None = Q, extra: tuple[str, ...] = (), rows: list[dict[str, Any]] = ROWS) -> None:  # fmt: skip
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
    rows.append({"ris": ris, "title": title, "claims": claims})


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
# v1 venue-years (TASK-098): the venueid gives venue, year and track; the venue string gives status
v1("A Synthetic v1 Poster", "V1Poster01", "ICLR.cc/2022/Conference", "ICLR 2022 Poster")
v1("A Synthetic v1 Oral", "V1Oral0001", "NeurIPS.cc/2021/Conference", "NeurIPS 2021 Oral")
v1("A Synthetic v1 Rejection", "V1Submit01", "ICLR.cc/2022/Conference", "ICLR 2022 Submitted")
v1("A Synthetic v1 Withdrawal", "V1Withdr01", "ICLR.cc/2023/Conference", "")  # v1 withdrawn notes say ""
v1("A Synthetic Unmapped Venue String", "V1Unmapp01", "ICLR.cc/2023/Conference", "ICLR 2023 Synthetic Track")
v1(
    "A Synthetic v2 Venue String",
    "V2Ignore01",
    "ICLR.cc/2024/Conference/Rejected_Submission",
    "ICLR 2024 Poster",
)
v1("A Synthetic Venue String From Another Note", "V1Disagr01", "ICLR.cc/2022/Conference", "Submitted to ICLR 2023",
   evidence="venueid=ICLR.cc/2023/Conference")  # fmt: skip
# the string agrees with the venueid, but its evidence names another note's: still not used
v1("A Synthetic Agreeing String From Another Note", "V1Agree001", "ICLR.cc/2022/Conference", "ICLR 2022 Poster",
   evidence="venueid=ICLR.cc/2023/Conference")  # fmt: skip
# two claims with the same agreeing string, only one with bad evidence: every claim must name the venueid
v1("A Synthetic Pair With One Bad Claim", "V1OneBad01", "ICLR.cc/2022/Conference", "ICLR 2022 Poster",
   also=("ICLR 2022 Poster", "venueid=ICLR.cc/2023/Conference"))  # fmt: skip
# ICLR 2017's lower-case `conference` venueid is on every conference note, workshop invitations included, so it
# gives track `other` and the venue string gives track and status too (TASK-142)
v1("A Synthetic ICLR 2017 Poster", "V1Ic17Pos1", "ICLR.cc/2017/conference", "ICLR 2017 Poster")
v1("A Synthetic ICLR 2017 Oral", "V1Ic17Ora1", "ICLR.cc/2017/conference", "ICLR 2017 Oral")
v1(
    "A Synthetic ICLR 2017 Workshop Invitation",
    "V1Ic17Wks1",
    "ICLR.cc/2017/conference",
    "ICLR 2017 Invite to Workshop",
)
v1("A Synthetic ICLR 2017 Rejection", "V1Ic17Rej1", "ICLR.cc/2017/conference", "Submitted to ICLR 2017")
v1(
    "A Synthetic ICLR 2017 String Of Another Year",
    "V1Ic17Yr01",
    "ICLR.cc/2017/conference",
    "ICLR 2022 Poster",
)
# ICLR 2023 blog posts: the venueid's track is `blogpost`, and the string must name it
v1("A Synthetic ICLR 2023 Blog Post", "V1Blog2301", "ICLR.cc/2023/BlogPosts", "Blogposts @ ICLR 2023")
# scholarmend 0.1.5's `invitation` claim (TASK-157; appended, so earlier rows keep their index). rkB_5hEKe is the
# recorded workshop copy (http/openreview/v1/iclr-2017/note-workshop-submitted-to-iclr-live.json): its claims equal
# a real rejection's but for the invitation, which names the workshop listing
_IC17 = "ICLR.cc/2017/conference"
v1("A Synthetic ICLR 2017 Workshop Copy", "rkB_5hEKe", _IC17, "Submitted to ICLR 2017",
   invitation=("ICLR.cc/2017/workshop/-/submission", f"venueid={_IC17}"))  # fmt: skip
v1("A Synthetic ICLR 2017 Rejection With Its Invitation", "V1Ic17Inv1", _IC17, "Submitted to ICLR 2017",
   invitation=("ICLR.cc/2017/conference/-/submission", f"venueid={_IC17}"))  # fmt: skip
v1("A Synthetic Invitation Of Another Note", "V1Ic17Inv2", _IC17, "Submitted to ICLR 2017",
   invitation=("ICLR.cc/2017/workshop/-/submission", "venueid=ICLR.cc/2018/Conference"))  # fmt: skip
v1("A Synthetic Unlisted Invitation", "V1Ic17Inv3", _IC17, "Submitted to ICLR 2017",
   invitation=("ICLR.cc/2017/workshop/-/Synthetic", f"venueid={_IC17}"))  # fmt: skip
v1("A Synthetic Workshop Invitation Of A Poster", "V1Ic17Inv4", _IC17, "ICLR 2017 Poster",
   invitation=("ICLR.cc/2017/workshop/-/submission", f"venueid={_IC17}"))  # fmt: skip
# an invitation outside the v1 years is ignored (scholarmend emits none for v2 notes); two different invitations,
# or an empty one, are no evidence (review round 1)
v1("A Synthetic v2 Invitation", "V2Invite01", "ICLR.cc/2024/Conference/Rejected_Submission", "ICLR 2024 Poster",
   invitation=("ICLR.cc/2024/Conference/-/Submission", "venueid=ICLR.cc/2024/Conference/Rejected_Submission"))  # fmt: skip
v1("A Synthetic Pair Of Invitations", "V1Ic17Inv5", _IC17, "Submitted to ICLR 2017",
   invitation=("ICLR.cc/2017/workshop/-/submission", f"venueid={_IC17}"),
   also_invitation=("ICLR.cc/2017/conference/-/submission", f"venueid={_IC17}"))  # fmt: skip
v1(
    "A Synthetic Empty Invitation",
    "V1Ic17Inv6",
    _IC17,
    "Submitted to ICLR 2017",
    invitation=("", f"venueid={_IC17}"),
)


def write(rows: list[dict[str, Any]], out: Path) -> None:
    out.mkdir(exist_ok=True)
    (out / "mended.ris").write_text(
        "\ufeff" + "\n".join(line for r in rows for line in r["ris"]), encoding="utf-8"
    )
    resolved = [{"title": r["title"], "source_file": "clean.ris", "conflicts": [], "claims": r["claims"],
                 "fields": {cl["field"]: {k: cl[k] for k in ("confidence", "evidence", "source", "tier", "value")}
                            for cl in reversed(r["claims"])}} for r in rows]  # fmt: skip
    (out / "resolved.json").write_text(
        json.dumps(resolved, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{out.name}: {len(rows)} records")


if __name__ == "__main__":
    write(ROWS, HERE)
    write(V1_ROWS, HERE / "v1")
