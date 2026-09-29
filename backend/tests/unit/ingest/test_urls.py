"""Proceedings URL → native id (`urls.native`), and the record's native-id pattern agreeing with it."""

from __future__ import annotations

import pytest
from openproceedings.ingest import urls
from openproceedings.ingest.record import PaperRecord

H = "0336dcbab05b9d5ad24f4333c7658a0e"
DB = "https://datasets-benchmarks-proceedings.neurips.cc"
MAIN = "https://proceedings.neurips.cc"


@pytest.mark.parametrize(
    ("url", "native"),
    [
        (f"{MAIN}/paper_files/paper/2021/hash/{H}-Abstract.html", f"nips-{H}"),
        (f"{MAIN}/paper_files/paper/2023/hash/{H}-Abstract-Datasets_and_Benchmarks.html", f"nips-{H}"),
        (f"https://papers.nips.cc/paper/2015/hash/{H}-Abstract.html", f"nips-{H}"),
        # the 2021 D&B host numbers each round separately, so its hash alone is not a paper (TASK-118)
        (f"{DB}/paper_files/paper/2021/hash/{H}-Abstract-round1.html", f"nips-{H}-round1"),
        (f"{DB}/paper_files/paper/2021/hash/{H}-Abstract-round2.html", f"nips-{H}-round2"),
        (f"{DB}/paper_files/paper/2021/file/{H}-Paper-round2.pdf", f"nips-{H}-round2"),
        (f"{DB.upper()}/paper_files/paper/2021/hash/{H.upper()}-Abstract-round1.html", f"nips-{H}-round1"),
        (f"{DB}/paper_files/paper/2021/hash/{H}-Abstract.html", None),  # no round: which paper is unknowable
        (f"{DB}/paper_files/paper/2021/hash/{H}-Abstract-round3.html", None),
        (f"{DB}/paper_files/paper/2022/hash/{H}-Abstract-round1.html", None),  # the host lists 2021 only
        (f"{DB}/paper_files/paper/2021/hash/{H}-Abstract-Round1.html", None),  # the host writes it lowercase
        (
            f"{MAIN}/paper_files/paper/2021/hash/{H}-Abstract-round1.html",
            f"nips-{H}",
        ),  # a round token off-host
        (f"{MAIN}/paper_files/paper/2021/hash/{H[:31]}-Abstract.html", None),
    ],
)
def test_native(url: str, native: str | None) -> None:
    assert urls.native(url) == native


@pytest.mark.parametrize(
    ("native", "ok"),
    [(f"nips-{H}", True), (f"nips-{H}-round1", True), (f"nips-{H}-round2", True), (f"nips-{H}-round3", False),
     (f"nips-{H}-Round1", False), (f"iclr-{H}-round1", False)],
)  # fmt: skip
def test_record_accepts_exactly_the_native_ids_urls_produce(native: str, ok: bool) -> None:
    venue = "ICLR" if native.startswith("iclr") else "NeurIPS"

    def build() -> PaperRecord:
        return PaperRecord.build(
            id=f"op:{venue.lower()}:2021:{native}", title="A title", abstract=None, authors=("A. Author",),
            venue=venue, year=2021, track="datasets_benchmarks" if venue == "NeurIPS" else "main",
            status="accepted",
        )  # fmt: skip

    if ok:
        assert build().native == native
    else:
        with pytest.raises(ValueError, match="not a valid"):
            build()
