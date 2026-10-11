"""The aaai_library source (TASK-232, decision-051): archived aaai.org paper pages, each pinned to one Internet Archive
capture, read only from web.archive.org; the digest checked on every read; the parser over the recorded layouts;
the post-dedup fill by dblp key, before OpenAlex's; the record guard."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest import aaai_library_table
from openproceedings.ingest.dedup import DedupResult, attribution, resolve
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.sources import aaai_library as a
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import CacheMiss, FetchError, Page, PageCache, Response

from tests.unit.ingest.proceedings_helpers import Clock, FakeTransport, fixture

T = datetime(2026, 10, 10, tzinfo=UTC)
FIXTURES = {
    "conf/aaai/Araya84": "aaai_library/aaai84-047.json",  # 1984, the old layout
    "conf/aaai/DetermanB98": "aaai_library/iaai98-014.json",  # IAAI 1998
    "conf/aaai/KimuraSN07": "aaai_library/aaai07-217.json",  # 2007: line breaks inside the abstract
    "conf/aaai/TaylorS06": "aaai_library/aaai06-329.json",  # the `None - …` placeholder
    "conf/aaai/Lifschitz08": "aaai_library/aaai08-270.json",  # 2008
}


def body(rel: str) -> bytes:
    return str(fixture(rel)["response"]["text"]).encode("utf-8")


def row_for(key: str, data: bytes | None = None) -> aaai_library_table.Page:
    """The shipped row with its digest set to the scrubbed fixture's bytes (the real digest is in `_recorded`)."""
    real = aaai_library_table.TABLE.pages[key]
    rel = FIXTURES[key]
    assert real.digest in fixture(rel)["_recorded"]["run"] and real.capture == fixture(rel)["request"]["url"]
    return aaai_library_table.Page(
        real.key, real.url, real.timestamp, a.digest(data or body(rel)), real.length
    )


def table_of(*rows: aaai_library_table.Page) -> aaai_library_table.Table:
    return aaai_library_table.Table(T.date(), "test", {r.key: r for r in rows})


def seed(cache: Path, row: aaai_library_table.Page, data: bytes, *, status: int = 200) -> None:
    text = data.decode("latin-1") if status == 200 else ""
    PageCache(cache / a.CACHE_DIR).put(Page(row.capture, status, text, T))


def record(key: str, title: str = "Synthetic title 1", *, year: int = 1984,
           abstract: tuple[str, str] | None = None) -> PaperRecord:  # fmt: skip
    tail = key.removeprefix("conf/aaai/")
    fields = [("title", title), ("venue", "AAAI"), ("year", year), ("track", "main"), ("status", "accepted"),
              ("urls.proceedings", f"https://dblp.org/rec/{key}")]  # fmt: skip
    claims = [Claim(field=f, value=v, source="dblp", fetched_at=T, evidence="t") for f, v in fields]
    if abstract:
        claims.append(
            Claim(field="abstract", value=abstract[0], source=abstract[1], fetched_at=T, evidence="t")
        )  # type: ignore[arg-type]
    return resolve(f"op:aaai:{year}:dblp-{tail}", claims)[0]


# --- the page ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_each_recorded_capture_parses(key: str) -> None:
    parsed = a.parse_page(body(FIXTURES[key]).decode("utf-8"))
    assert parsed.refused is None and parsed.title == "Synthetic title 1"
    cleaned, why = a.abstract_of(parsed)
    if key == "conf/aaai/TaylorS06":
        assert parsed.abstract == "None - 2 page paper is an abstract"
        assert cleaned is None and why == "no_abstract"
        return
    assert why is None and cleaned is not None and cleaned.text is not None
    assert cleaned.text.startswith("synthetic") and "\n" not in cleaned.text and "  " not in cleaned.text
    assert (
        "Subjects" not in cleaned.text and "Submitted" not in cleaned.text and "copyright" not in cleaned.text
    )


def test_the_2007_abstract_keeps_every_word_across_its_line_breaks() -> None:
    parsed = a.parse_page(body(FIXTURES["conf/aaai/KimuraSN07"]).decode("utf-8"))
    assert parsed.abstract is not None
    words = parsed.abstract.split(" ")
    assert words == [f"synthetic{n}" for n in range(3, 149)]


def test_paragraphs_up_to_the_subjects_line_join_and_entities_decode() -> None:
    page = ('<html><body><div id="abstract"><h1><a href="x.pdf">A &amp; B</a></h1><p class="left"><i>An Author</i>'
            "</p><p>First paragraph of the abstract, long enough.</p><p>Second &ldquo;one&rdquo;.</p>"
            "<p><i>Subjects:</i> 1. AI</p><p>Not read.</p></div></body></html>")  # fmt: skip
    parsed = a.parse_page(page)
    assert parsed.title == "A & B"
    assert parsed.abstract == "First paragraph of the abstract, long enough. Second “one”."


@pytest.mark.parametrize(
    "page",
    [
        "<html><body><p>No abstract div.</p></body></html>",
        '<html><div id="abstract"><p><i>A</i></p><p>Text</p></div><div id="abstract"><h1>T</h1></div></html>',
        '<html><div id="abstract"><p><i>No heading</i></p><p>Text</p></div></html>',
        '<html><div id="abstract"><h1>T</h1><p>Authors without italics</p><p>Text</p></div></html>',
        '<html><div id="abstract"><h1>T</h1></div></html>',
    ],
)
def test_another_layout_is_refused(page: str) -> None:
    assert a.parse_page(page).refused == "layout_unknown"
    assert a.abstract_of(a.parse_page(page)) == (None, "layout_unknown")


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("None - 2 page paper is an abstract", "no_abstract"),
        ("None: this two-page paper is an extended abstract of the talk given", "no_abstract"),
        ("Too short to be an abstract.", "no_abstract"),
        ("", "no_abstract"),
        ("A text with a lone surrogate \ud800 that is otherwise long enough to keep.", "abstract_surrogate"),
    ],
)
def test_placeholders_short_texts_and_surrogates_are_refused(text: str, why: str) -> None:
    assert a.abstract_of(a.Parsed("T", text or None)) == (None, why)


def test_none_of_as_the_first_words_is_an_abstract() -> None:
    text = "None of the existing planners handle this domain; we present one that does, and evaluate it."
    cleaned, why = a.abstract_of(a.Parsed("T", text))
    assert why is None and cleaned is not None and cleaned.text == text


def test_the_bytes_decode_by_the_pages_own_meta_charset() -> None:
    latin = b'<meta http-equiv="content-type" content="text/html; charset=iso-8859-1" /><p>it\x92s \xe9</p>'
    assert (
        a.decode(latin)
        == '<meta http-equiv="content-type" content="text/html; charset=iso-8859-1" /><p>it’s \xe9</p>'
    )
    assert a.decode(b'<meta charset="utf-8"><p>caf\xc3\xa9</p>') == '<meta charset="utf-8"><p>caf\xe9</p>'
    assert a.decode("<p>caf\xe9 with no meta</p>".encode()) == "<p>caf\xe9 with no meta</p>"
    assert a.decode(b"<p>caf\xe9 not utf-8, no meta</p>") is None
    assert a.decode(b'<meta charset="shift_jis"><p>x</p>') is None
    assert a.decode(b'<meta charset="iso-8859-1"><p>\x81</p>') == '<meta charset="iso-8859-1"><p>\x81</p>'


# --- the digest -------------------------------------------------------------------------------------------------


def test_a_capture_reads_only_when_its_bytes_hash_to_the_rows_digest(tmp_path: Path) -> None:
    key = "conf/aaai/Araya84"
    row = row_for(key)
    data = body(FIXTURES[key])
    page = Page(row.capture, 200, data.decode("latin-1"), T)
    assert a.check_digest(page, row) == data
    assert a.read(page, row).title == "Synthetic title 1"
    edited = Page(row.capture, 200, data.replace(b"synthetic", b"Synthetic", 1).decode("latin-1"), T)
    with pytest.raises(CrawlError, match="not the capture") as e:
        a.read(edited, row)
    assert e.value.reason == "digest_mismatch" and "synthetic" not in str(e.value)
    with pytest.raises(CrawlError) as e:  # a text no byte gives: never this source's entry
        a.check_digest(Page(row.capture, 200, "’", T), row)
    assert e.value.reason == "digest_mismatch"


def test_the_digest_is_the_archives_base32_sha1() -> None:
    assert a.digest(b"") == "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ"  # SHA-1 of nothing, base32
    assert len(a.digest(b"x")) == 32


# --- the harvest --------------------------------------------------------------------------------------------------


def test_the_harvest_fetches_each_exact_capture_from_the_archive_only_and_paced(tmp_path: Path) -> None:
    rows = [row_for(k) for k in ("conf/aaai/Araya84", "conf/aaai/KimuraSN07")]
    script = {r.capture: Response(200, {"content-type": "text/html; charset=UTF-8"}, body(FIXTURES[r.key]))
              for r in rows}  # fmt: skip
    transport = FakeTransport(script)
    f = a.fetcher(tmp_path, offline=False, transport=transport, min_interval=0.5)
    f.clock = clock = Clock()
    done = a.harvest(table_of(*rows), f)
    assert (done.pages, done.fetched, done.missing) == (2, 2, 0)
    assert transport.calls == [r.capture for r in rows]  # in key order
    assert all(
        c.startswith("https://web.archive.org/web/") and "id_/http://www.aaai.org/" in c
        for c in transport.calls
    )
    assert clock.sleeps == [a.MIN_INTERVAL]  # never under the archive's pace, whatever was asked
    sent = transport.requests[0].headers
    assert "openproceedings/" in sent["User-Agent"] and "@" not in sent["User-Agent"]
    again = a.harvest(table_of(*rows), a.fetcher(tmp_path, offline=True))  # from the cache alone
    assert (again.pages, again.fetched) == (2, 0)


def test_the_fetcher_refuses_aaai_org_itself(tmp_path: Path) -> None:
    f = a.fetcher(tmp_path, offline=False, transport=FakeTransport({}))
    with pytest.raises(FetchError) as e:
        f.get("http://www.aaai.org/Library/AAAI/1984/aaai84-047.php")
    assert e.value.reason == "off_host"
    assert frozenset({"web.archive.org"}) == a.HOSTS


def test_a_digest_mismatch_stops_the_harvest_and_a_missing_capture_is_counted(tmp_path: Path) -> None:
    good, gone = row_for("conf/aaai/Araya84"), row_for("conf/aaai/KimuraSN07")
    wrong = aaai_library_table.Page(good.key, good.url, good.timestamp, "A" * 32, good.length)
    script = {good.capture: Response(200, {}, body(FIXTURES[good.key])), gone.capture: Response(404, {}, b"")}
    f = a.fetcher(tmp_path, offline=False, transport=FakeTransport(script))
    f.clock = Clock()
    with pytest.raises(CrawlError) as e:
        a.harvest(table_of(wrong), f)
    assert e.value.reason == "digest_mismatch"
    done = a.harvest(table_of(good, gone), f, refresh=True)
    assert (done.pages, done.missing) == (2, 1)
    with pytest.raises(CacheMiss):
        a.harvest(table_of(row_for("conf/aaai/Lifschitz08")), a.fetcher(tmp_path, offline=True))


# --- the fill -----------------------------------------------------------------------------------------------------


def _cache_with(tmp_path: Path, *keys: str) -> aaai_library_table.Table:
    rows = [row_for(k) for k in keys]
    for r in rows:
        seed(tmp_path, r, body(FIXTURES[r.key]))
    return table_of(*rows)


def test_the_fill_attaches_the_page_abstract_by_dblp_key_credited_to_the_aaai_page(tmp_path: Path) -> None:
    table = _cache_with(tmp_path, "conf/aaai/Araya84")
    (out,), report = a.fill([record("conf/aaai/Araya84")], a.fetcher(tmp_path, offline=True), table)
    row = table.pages["conf/aaai/Araya84"]
    assert (
        out.abstract is not None and out.abstract.startswith("synthetic") and out.abstract_kind == "official"
    )
    (claim,) = out.claims("abstract")
    assert claim.source == "aaai_library" and claim.url == row.capture and claim.fetched_at == T
    assert row.url in (claim.evidence or "") and row.timestamp in (claim.evidence or "")
    assert row.digest in (claim.evidence or "")
    att = attribution(out.abstract, out.claims("abstract"), forum=None, proceedings=out.urls.proceedings,
                      native="dblp-Araya84")  # fmt: skip
    assert att is not None and (att.source, att.origin, att.url) == ("aaai_library", "aaai_library", row.url)
    assert (report.candidates, report.attached, report.no_page, report.rows_unmatched) == (1, 1, 0, 0)
    assert report.fetched == [T]


def test_refusals_are_counted_and_never_attached(tmp_path: Path) -> None:
    table = _cache_with(tmp_path, "conf/aaai/Araya84", "conf/aaai/TaylorS06", "conf/aaai/KimuraSN07")
    gone = row_for("conf/aaai/Lifschitz08")
    seed(tmp_path, gone, b"", status=404)
    table = table_of(*table.pages.values(), gone, row_for("conf/aaai/DetermanB98"))
    records = [
        record("conf/aaai/Araya84", "Another Paper Altogether"),  # the page is not this paper
        record("conf/aaai/TaylorS06", year=2006),  # the placeholder
        record("conf/aaai/Lifschitz08", year=2008),  # the archive answered 404
        record("conf/aaai/NoPage99", year=1999),  # no row
    ]
    out, report = a.fill(records, a.fetcher(tmp_path, offline=True), table)
    assert all(r.abstract is None for r in out) and out == sorted(records, key=lambda r: r.id)
    assert report.refused == {"title_mismatch": 1, "no_abstract": 1, "capture_missing": 1}
    assert (report.candidates, report.attached, report.no_page) == (4, 0, 1)
    assert report.rows_unmatched == 2  # KimuraSN07 and DetermanB98 name no record here


def test_a_row_not_in_the_cache_stops_the_fill(tmp_path: Path) -> None:
    table = table_of(row_for("conf/aaai/Araya84"))
    with pytest.raises(CrawlError) as e:
        a.fill([record("conf/aaai/Araya84")], a.fetcher(tmp_path, offline=True), table)
    assert e.value.reason == "not_cached" and "op ingest aaai-library" in str(e.value)


def test_a_cached_capture_edited_since_stops_the_fill(tmp_path: Path) -> None:
    row = row_for("conf/aaai/Araya84")
    seed(tmp_path, row, body(FIXTURES[row.key]) + b" ")
    with pytest.raises(CrawlError) as e:
        a.fill([record(row.key)], a.fetcher(tmp_path, offline=True), table_of(row))
    assert e.value.reason == "digest_mismatch"


def test_only_aaai_1980_2008_dblp_records_are_candidates(tmp_path: Path) -> None:
    table = _cache_with(tmp_path, "conf/aaai/Araya84")
    others = [
        resolve("op:aaai:2020:ojs-1", [Claim(field=f, value=v, source="ojs", fetched_at=T, evidence="t")
                                       for f, v in (("title", "Synthetic title 1"), ("venue", "AAAI"), ("year", 2020),
                                                    ("track", "main"), ("status", "accepted"))])[0],
        resolve("op:icml:1990:dblp-Araya84", [Claim(field=f, value=v, source="dblp", fetched_at=T, evidence="t")
                                              for f, v in (("title", "Synthetic title 1"), ("venue", "ICML"),
                                                           ("year", 1990), ("track", "main"),
                                                           ("status", "accepted"))])[0],
    ]  # fmt: skip
    out, report = a.fill(others, a.fetcher(tmp_path, offline=True), table)
    assert out == sorted(others, key=lambda r: r.id) and report.candidates == 0 and report.rows_unmatched == 1


def test_an_abstract_ranked_before_it_stays_and_one_ranked_after_it_is_replaced(tmp_path: Path) -> None:
    table = _cache_with(tmp_path, "conf/aaai/Araya84")
    f = a.fetcher(tmp_path, offline=True)
    official = record("conf/aaai/Araya84", abstract=("An abstract dblp somehow gave.", "dblp"))
    (kept,), report = a.fill([official], f, table)
    assert kept == official and report.official_won == 1 and report.attached == 0
    ris = record("conf/aaai/Araya84", abstract=("An abstract a RIS import gave.", "ris"))
    (taken,), report = a.fill([ris], f, table)
    assert taken.abstract is not None and taken.abstract.startswith("synthetic")
    assert {c.source for c in taken.claims("abstract")} == {"ris", "aaai_library"}
    assert (report.attached, report.replaced) == (1, 1)


def test_the_openalex_fill_after_it_never_displaces_the_page_abstract(tmp_path: Path) -> None:
    """The build runs this fill first (`snapshot.build`); OpenAlex then finds the abstract held, counts it
    `official_won` and leaves it."""
    table = _cache_with(tmp_path, "conf/aaai/Araya84")
    (filled,), _ = a.fill([record("conf/aaai/Araya84")], a.fetcher(tmp_path, offline=True), table)
    extract = openalex.Extract("0" * 64, ())
    (after,), report = openalex.fill([filled], extract)
    assert after == filled and after.abstract_kind == "official" and report.candidates == 0


def test_apply_without_a_harvest_changes_nothing(tmp_path: Path) -> None:
    result = DedupResult((record("conf/aaai/Araya84"),), (), ())
    assert a.apply(result, tmp_path) == (result, [])


def test_apply_after_a_harvest_fills_reports_and_logs_its_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    table = _cache_with(tmp_path, "conf/aaai/Araya84", "conf/aaai/KimuraSN07")
    monkeypatch.setattr(aaai_library_table, "TABLE", table)
    a.write_done(tmp_path, table, a.Harvest(pages=2))
    marker = json.loads((tmp_path / "aaai_library" / "crawls" / "aaai_library.json").read_text())
    assert marker["source"] == "aaai_library" and marker["format"] == a.MARKER_FORMAT
    result = DedupResult(
        (record("conf/aaai/Araya84"), record("conf/aaai/KimuraSN07", "Wrong", year=2007)), (), ()
    )
    with caplog.at_level(logging.INFO):
        filled, (report,) = a.apply(result, tmp_path)
    assert [r.abstract is not None for r in filled.records] == [True, False]
    assert report.to_manifest() == {"pages": 2, "candidates": 2, "no_page": 0, "attached": 1, "replaced": 0,
                                    "official_won": 0, "rows_unmatched": 0, "refused": {"title_mismatch": 1}}  # fmt: skip
    events = {r.getMessage(): r for r in caplog.records}
    assert events["aaai_library_filled"].__dict__["refused"] == {"title_mismatch": 1}
    assert events["aaai_library_attention"].levelno == logging.WARNING
    assert events["aaai_library_attention"].__dict__["title_mismatch"] == 1
    assert not any("synthetic" in r.getMessage() for r in caplog.records)


def test_an_unreadable_marker_stops_the_build(tmp_path: Path) -> None:
    (tmp_path / "aaai_library" / "crawls").mkdir(parents=True)
    (tmp_path / "aaai_library" / "crawls" / "aaai_library.json").write_text('{"source": "other"}')
    with pytest.raises(CrawlError) as e:
        a.apply(DedupResult((), (), ()), tmp_path)
    assert e.value.reason == "crawl_file_invalid"


# --- the record guard -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rid", "venue", "year", "field"),
    [
        ("op:aaai:1984:dblp-Araya84", "AAAI", 1984, "title"),  # not an abstract
        ("op:icml:1990:dblp-Araya84", "ICML", 1990, "abstract"),  # not AAAI
        ("op:aaai:2020:ojs-1", "AAAI", 2020, "abstract"),  # not a dblp record
    ],
)
def test_the_record_refuses_an_aaai_library_claim_outside_its_scope(
    rid: str, venue: str, year: int, field: str
) -> None:
    base = [("title", "A Paper"), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted")]
    claims = [Claim(field=f, value=v, source="dblp", fetched_at=T, evidence="t") for f, v in base]  # type: ignore[arg-type]
    claims.append(Claim(field=field, value="A long enough text from the page.", source="aaai_library",  # type: ignore[arg-type]
                        fetched_at=T, evidence="t"))  # fmt: skip
    with pytest.raises(ValueError, match="aaai_library"):
        resolve(rid, claims)


# --- the command (`op ingest aaai-library`) ---------------------------------------------------------------------


def test_the_command_caches_every_capture_then_marks_the_harvest_and_a_dry_run_writes_nothing(
    tmp_path: Path,
) -> None:
    from openproceedings.ingest.sources import crawl

    rows = [row_for(k) for k in ("conf/aaai/Araya84", "conf/aaai/DetermanB98")]
    table = table_of(*rows)
    marker = tmp_path / "aaai_library" / "crawls" / "aaai_library.json"
    dry = crawl.ingest_aaai_library(tmp_path, dry_run=True, table=table)
    assert dry == {
        "dry_run": True,
        "pages": 2,
        "cached": 0,
        "to_fetch": 2,
        "requests": 0,
        "seconds_at_least": 6,
    }
    assert not marker.exists()
    with pytest.raises(CacheMiss):  # offline, nothing cached: no marker
        crawl.ingest_aaai_library(tmp_path, offline=True, table=table)
    assert not marker.exists()
    seed(tmp_path, rows[0], body(FIXTURES[rows[0].key]))
    seed(tmp_path, rows[1], body(FIXTURES[rows[1].key]))
    out = crawl.ingest_aaai_library(tmp_path, offline=True, table=table)
    assert out == {"dry_run": False, "pages": 2, "fetched": 0, "missing": 0, "requests": 0, "cached": 2}
    assert json.loads(marker.read_text())["pages"] == 2
    assert crawl.ingest_aaai_library(tmp_path, dry_run=True, table=table)["to_fetch"] == 0
