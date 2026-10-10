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
    check_native(native, ok, 2021)


def test_a_round_qualified_id_is_2021_only() -> None:
    check_native(f"nips-{H}-round1", False, 2022)
    check_native(f"nips-{H}", True, 2022)


def check_native(native: str, ok: bool, year: int) -> None:
    venue = "ICLR" if native.startswith("iclr") else "NeurIPS"

    def build() -> PaperRecord:
        return PaperRecord.build(
            id=f"op:{venue.lower()}:{year}:{native}", title="A title", abstract=None, authors=("A. Author",),
            venue=venue, year=year, track="datasets_benchmarks" if venue == "NeurIPS" else "main",
            status="accepted",
        )  # fmt: skip

    if ok:
        assert build().native == native
    else:
        with pytest.raises(ValueError, match="not a valid"):
            build()


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://dblp.org/rec/conf/icml/SzitaL09", "SzitaL09"),
        ("http://dblp.org/rec/conf/icml/SzitaL09.html", "SzitaL09"),
        ("https://DBLP.org/rec/conf/icml/Ng04", "Ng04"),
        ("https://dblp.uni-trier.de/rec/conf/icml/SzitaL09", None),  # another host: no dblp key
        ("https://example.org/rec/conf/icml/SzitaL09", None),
        ("https://dblp.org/rec/conf/nips/SzitaL09", None),  # not the ICML stream
        ("https://dblp.org/rec/conf/icml/bad key", None),
        ("ftp://dblp.org/rec/conf/icml/SzitaL09", None),
    ],
)
def test_a_dblp_record_page_names_its_icml_key(url: str, key: str | None) -> None:
    """decision-047: a dblp record's `urls.proceedings` is its dblp page, which `urls.native` reads back as
    `dblp-<key>` (dedup's proceedings-id check); only dblp.org's ICML pages name one."""
    assert urls.dblp_icml(url) == key
    assert urls.native(url) == (f"dblp-{key}" if key else None)
    assert urls.dblp_record_url("conf/icml/SzitaL09") == "https://dblp.org/rec/conf/icml/SzitaL09"


@pytest.mark.parametrize(
    ("url", "article"),
    [
        ("https://ojs.aaai.org/index.php/AAAI/article/view/28000", 28000),
        ("https://OJS.aaai.org/index.php/AIES/article/view/31600/33767", 31600),
        ("http://ojs.aaai.org/index.php/IASEAI/article/view/43010?x=1", 43010),
        ("https://ojs.aaai.org/index.php/AAAI/article/view/28000/", 28000),
        ("https://ojs.aaai.org/index.php/AAAI/article/view/28000/35000/", 28000),
        ("https://ojs.aaai.org/index.php/AAAI/issue/view/741", None),
        ("https://example.org/index.php/AAAI/article/view/1", None),
    ],
)
def test_ojs_article(url: str, article: int | None) -> None:
    assert urls.ojs_article(url) == article
    assert urls.native(url) == (None if article is None else f"ojs-{article}")


def test_ojs_article_names_exactly_the_tables_journals() -> None:
    """The URL pattern's journals are the table's: a journal added to `ojs_sections.toml` names its articles."""
    from openproceedings.ingest import ojs_table

    for journal in ojs_table.TABLE.journals:
        assert urls.ojs_article(f"https://ojs.aaai.org/index.php/{journal}/article/view/7") == 7
    assert (
        urls.ojs_article("https://ojs.aaai.org/index.php/AIMAG/article/view/7") is None
    )  # not a table journal
