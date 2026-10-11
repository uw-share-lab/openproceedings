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


def test_a_non_ascii_capture_is_cached_byte_for_byte(tmp_path: Path) -> None:
    """The harvest keeps the exact bytes of a capture with UTF-8 and Windows-1252 bytes, whatever the response names."""
    real = row_for("conf/aaai/Araya84")
    data = body(FIXTURES[real.key]).replace(b"synthetic3 ", "café “q” ".encode() + b"\x92 ", 1)
    row = aaai_library_table.Page(real.key, real.url, real.timestamp, a.digest(data), real.length)
    script = {row.capture: Response(200, {"content-type": "text/html; charset=UTF-8"}, data)}
    f = a.fetcher(tmp_path, offline=False, transport=FakeTransport(script))
    f.clock = Clock()
    a.harvest(table_of(row), f)
    cached = PageCache(tmp_path / a.CACHE_DIR).get(row.capture)
    assert cached is not None and a.body_of(cached) == data


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
    assert not f.is_cached(
        good.capture
    )  # verified before it is stored: one bad answer never poisons the cache
    assert PageCache(tmp_path / a.CACHE_DIR).get(good.capture) is None
    done = a.harvest(table_of(good, gone), f)
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
    # the text's date is the capture's (gate C round 1): the manifest's `capture_window`, not the harvest's fetch
    captured = datetime.strptime(row.timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    assert report.captured() == [captured]
    from openproceedings.ingest.sources.common import sources_manifest

    entry = sources_manifest([report])["aaai_library"]
    assert entry["capture_window"] == {"from": captured.isoformat(), "to": captured.isoformat()}
    assert entry["crawl_window"] == {"from": T.isoformat(), "to": T.isoformat()}


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
    assert marker["table"] == table.sha256
    result = DedupResult(
        (record("conf/aaai/Araya84"), record("conf/aaai/KimuraSN07", "Wrong", year=2007)), (), ()
    )
    with caplog.at_level(logging.INFO):
        filled, (report,) = a.apply(result, tmp_path)
    assert [r.abstract is not None for r in filled.records] == [True, False]
    assert report.to_manifest() == {"pages": 2, "candidates": 2, "no_page": 0, "attached": 1, "replaced": 0,
                                    "official_won": 0, "rows_unmatched": 0, "title_near": 0, "near": [],
                                    "refused": {"title_mismatch": 1}}  # fmt: skip
    events = {r.getMessage(): r for r in caplog.records}
    assert events["aaai_library_filled"].__dict__["refused"] == {"title_mismatch": 1}
    assert events["aaai_library_attention"].levelno == logging.WARNING
    assert events["aaai_library_attention"].__dict__["title_mismatch"] == 1
    assert not any("synthetic" in r.getMessage() for r in caplog.records)


def test_the_shipped_table_carries_the_sha256_of_its_toml() -> None:
    import hashlib
    from importlib.resources import files

    text = files("openproceedings.ingest").joinpath("aaai_library.toml").read_text(encoding="utf-8")
    assert aaai_library_table.TABLE.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert aaai_library_table.load(text + "\n").sha256 != aaai_library_table.TABLE.sha256


@pytest.mark.parametrize("named", ["0" * 64, None])
def test_a_marker_for_another_table_or_none_is_a_stale_harvest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, named: str | None
) -> None:
    """A marker naming another table's sha256, or none (one written before the field existed), is `harvest_stale`."""
    table = _cache_with(tmp_path, "conf/aaai/Araya84")
    monkeypatch.setattr(aaai_library_table, "TABLE", table)
    body_ = {"source": "aaai_library", "format": a.MARKER_FORMAT, "pages": 1}
    if named is not None:
        body_["table"] = named
    (tmp_path / "aaai_library" / "crawls").mkdir(parents=True)
    (tmp_path / "aaai_library" / "crawls" / "aaai_library.json").write_text(json.dumps(body_))
    with pytest.raises(CrawlError, match="re-run op ingest aaai-library") as e:
        a.apply(DedupResult((record("conf/aaai/Araya84"),), (), ()), tmp_path)
    assert e.value.reason == "harvest_stale"


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
        ("op:aaai:2020:dblp-Late20", "AAAI", 2020, "abstract"),  # a dblp-shaped id past 2008
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
    assert out == {"dry_run": False, "pages": 2, "fetched": 0, "missing": 0, "redirect": 0, "redirected_same": 0,
                   "requests": 0, "cached": 2}  # fmt: skip
    assert json.loads(marker.read_text())["pages"] == 2
    assert crawl.ingest_aaai_library(tmp_path, dry_run=True, table=table)["to_fetch"] == 0


def test_the_command_warns_when_captures_are_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from openproceedings.ingest.sources import crawl

    row, gone = row_for("conf/aaai/Araya84"), row_for("conf/aaai/KimuraSN07")
    seed(tmp_path, row, body(FIXTURES[row.key]))
    seed(tmp_path, gone, b"", status=404)
    with caplog.at_level(logging.INFO):
        out = crawl.ingest_aaai_library(tmp_path, offline=True, table=table_of(row, gone))
    assert out["missing"] == 1
    (warning,) = [r for r in caplog.records if r.getMessage() == "aaai_library_attention"]
    assert warning.levelno == logging.WARNING and warning.__dict__["capture_missing"] == 1


# --- the title guard (controller ruling, fix round 1) ------------------------------------------------------------


def test_title_similarity_is_one_minus_levenshtein_over_the_longer_key() -> None:
    assert (
        a.levenshtein("kitten", "sitting") == 3
        and a.levenshtein("", "abc") == 3
        and a.levenshtein("ab", "ab") == 0
    )
    assert a.title_similarity("Abcdefghijklmnopqrst", "abcdefghijklmnopqrst") == 1.0
    assert a.title_similarity("abcdefghijklmnopqrst", "abcdefghijklmnopqrsX") == pytest.approx(0.95)
    assert a.title_similarity("abcdefghi", "abcdefghX") == pytest.approx(1 - 1 / 9)


@pytest.mark.parametrize(
    ("record_title", "page_title", "verdict"),
    [
        ("An Optimization Approach", "An optimization approach", ("exact", 1.0)),
        ("abcdefghijklmnopqrst", "abcdefghijklmnopqrsX", ("near", 0.95)),
        ("abcdefghi", "abcdefghX", (None, 0.889)),  # 0.89 < 0.9: refused
        (
            "Learning Control Policies Part 1",
            "Learning Control Policies Part 2",
            (None, 0.969),
        ),  # digits differ
        ("Planning in 1987 Domains", "Planning in 1987 Domain", ("near", 0.958)),
        ("abcdefghij", "abcdefghiX", ("near", 0.9)),  # exactly the bound: kept (`>=`)
        # a token holding a digit among letters is a digit token too: `2a` is never `2b`, `3rd` never `4th`
        ("Planning Part 2a", "Planning Part 2b", (None, 0.938)),
        (
            "Planning Under Uncertainty: the 3rd Study",
            "Planning Under Uncertainty: the 4th Study",
            (None, 0.925),
        ),
    ],
)
def test_the_title_verdict(record_title: str, page_title: str, verdict: tuple[str | None, float]) -> None:
    how, score = a.title_verdict(record_title, page_title)
    assert (how, round(score, 3)) == verdict


def _page_with(title: str) -> bytes:
    return (f'<html><head><meta charset="utf-8"></head><body><div id="abstract"><h1><a href="x.pdf">{title}</a></h1>'
            '<p class="left"><i>An Author</i></p><p>An abstract long enough to be kept by the shared cleaning.</p>'
            "</div></body></html>").encode()  # fmt: skip


def test_a_near_title_attaches_counted_with_its_score_and_logged_without_titles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    keys = ("conf/aaai/Araya84", "conf/aaai/DetermanB98")
    pages = {keys[0]: _page_with("An Optimization Approach for Using Contextual Information In Computer Vision"),
             keys[1]: _page_with("Learning Control Policies Part 2")}  # fmt: skip
    rows = [row_for(k, pages[k]) for k in keys]
    for r in rows:
        seed(tmp_path, r, pages[r.key])
    table = table_of(*rows)
    monkeypatch.setattr(aaai_library_table, "TABLE", table)
    a.write_done(tmp_path, table, a.Harvest(pages=2))
    records = (record(keys[0], "An Optimisation Approach for Using Contextual Information in Conputer Vision"),
               record(keys[1], "Learning Control Policies Part 1", year=1998))  # fmt: skip
    with caplog.at_level(logging.INFO):
        filled, (report,) = a.apply(DedupResult(records, (), ()), tmp_path)
    assert [r.abstract is not None for r in filled.records] == [True, False]
    near = filled.records[0].claims("abstract")[0]
    assert "title near" in (near.evidence or "")
    manifest = report.to_manifest()
    assert manifest["attached"] == 1 and manifest["title_near"] == 1
    assert manifest["near"] == [{"id": records[0].id, "score": 0.974}]
    assert manifest["refused"] == {"title_mismatch": 1}
    events = {r.getMessage(): r for r in caplog.records}
    assert events["aaai_library_filled"].__dict__["title_near"] == 1
    assert events["aaai_library_attention"].__dict__["title_near"] == 1
    logged = " ".join(str(r.__dict__) for r in caplog.records)
    assert "Optimi" not in logged and "Learning" not in logged


# --- a pinned capture the archive redirects (the controller's ruling, 2026-10-10) ------------------------------------
#
# The CDX can list a capture as a 200 that `id_` replay answers with a 302 to another timestamp (a revisit or
# warc-dedup record). At most one redirect is followed, only to another `id_` capture of the same page, and only its
# bytes hashing to the row's digest attach; anything else is recorded `capture_redirect`, and the harvest goes on.

PAGE = "www.aaai.org/Library/AAAI/1984/aaai84-047.php"
OTHER_TS = "20191209073055"


def _moved(location: str, status: int = 302) -> Response:
    return Response(status, {"location": location, "content-type": "text/plain"}, b"")


def _live(tmp_path: Path, script: dict[str, Response]) -> tuple[FakeTransport, a.Fetcher]:
    transport = FakeTransport(script)
    f = a.fetcher(tmp_path, offline=False, transport=transport)
    f.clock = Clock()
    return transport, f


def test_a_redirect_to_the_same_page_with_the_pinned_bytes_attaches_counted(tmp_path: Path) -> None:
    row = row_for("conf/aaai/Araya84")
    data = body(FIXTURES[row.key])
    target = f"https://web.archive.org/web/{OTHER_TS}id_/https://aaai.org/Library/AAAI/1984/aaai84-047.php"
    transport, f = _live(tmp_path, {row.capture: _moved(target), target: Response(200, {}, data)})
    done = a.harvest(table_of(row), f)
    assert (done.pages, done.redirected_same, done.redirect, done.missing) == (1, 1, 0, 0)
    assert transport.calls == [row.capture, target]
    cached = PageCache(tmp_path / a.CACHE_DIR).get(row.capture)  # under the row's own capture key
    assert cached is not None and cached.ok and a.body_of(cached) == data
    (out,), report = a.fill([record(row.key)], a.fetcher(tmp_path, offline=True), table_of(row))
    assert out.abstract is not None and report.attached == 1 and not report.refused


def test_a_redirect_to_the_same_page_with_other_bytes_is_capture_redirect(tmp_path: Path) -> None:
    row = row_for("conf/aaai/Araya84")
    target = f"https://web.archive.org/web/{OTHER_TS}id_/http://{PAGE}"
    other = body(FIXTURES[row.key]) + b"<!-- another capture -->"
    _, f = _live(tmp_path, {row.capture: _moved(target), target: Response(200, {}, other)})
    done = a.harvest(table_of(row), f)
    assert (done.pages, done.redirected_same, done.redirect) == (1, 0, 1)
    cached = PageCache(tmp_path / a.CACHE_DIR).get(row.capture)
    assert cached is not None and not cached.ok and cached.status == 302 and cached.text == ""
    assert PageCache(tmp_path / a.CACHE_DIR).get(target) is None  # the other bytes are never stored
    (out,), report = a.fill([record(row.key)], a.fetcher(tmp_path, offline=True), table_of(row))
    assert out.abstract is None and report.refused == {"capture_redirect": 1} and report.attached == 0


@pytest.mark.parametrize(
    "location",
    [
        f"https://web.archive.org/web/{OTHER_TS}id_/http://www.aaai.org/Library/AAAI/1984/aaai84-048.php",  # another page
        f"https://web.archive.org/web/{OTHER_TS}id_/http://www.aaai.org/Library/AAAI/1984/aaai84-047.php?x=1",
        f"https://web.archive.org/web/{OTHER_TS}id_/http://www.example.org/Library/AAAI/1984/aaai84-047.php",
        f"https://web.archive.org/web/{OTHER_TS}/http://{PAGE}",  # not an `id_` capture: a rewritten page
        f"https://web.archive.org/web/2019id_/http://{PAGE}",  # not a 14-digit timestamp
        f"https://example.org/web/{OTHER_TS}id_/http://{PAGE}",  # another host
        f"http://{PAGE}",  # aaai.org itself
        "",  # no Location at all
    ],
)
def test_a_redirect_anywhere_else_is_capture_redirect_and_never_followed(
    tmp_path: Path, location: str
) -> None:
    row = row_for("conf/aaai/Araya84")
    response = _moved(location) if location else Response(302, {}, b"")
    transport, f = _live(tmp_path, {row.capture: response})
    done = a.harvest(table_of(row), f)
    assert (done.redirected_same, done.redirect) == (0, 1)
    assert transport.calls == [row.capture]  # nothing else was fetched
    cached = PageCache(tmp_path / a.CACHE_DIR).get(row.capture)
    assert cached is not None and cached.status == 302


def test_a_chain_of_two_redirects_is_capture_redirect(tmp_path: Path) -> None:
    row = row_for("conf/aaai/Araya84")
    first = f"https://web.archive.org/web/{OTHER_TS}id_/http://{PAGE}"
    second = f"https://web.archive.org/web/20200101000000id_/http://{PAGE}"
    script = {row.capture: _moved(first), first: _moved(second, 301),
              second: Response(200, {}, body(FIXTURES[row.key]))}  # fmt: skip
    transport, f = _live(tmp_path, script)
    done = a.harvest(table_of(row), f)
    assert (done.redirected_same, done.redirect) == (0, 1)
    assert transport.calls == [row.capture, first]  # one hop at most: the second is never followed
    assert PageCache(tmp_path / a.CACHE_DIR).get(row.capture).status == 302  # type: ignore[union-attr]


def test_a_relative_location_resolves_against_the_archive(tmp_path: Path) -> None:
    row = row_for("conf/aaai/Araya84")
    target = f"https://web.archive.org/web/{OTHER_TS}id_/http://{PAGE}"
    transport, f = _live(tmp_path, {row.capture: _moved(f"/web/{OTHER_TS}id_/http://{PAGE}"),
                                    target: Response(200, {}, body(FIXTURES[row.key]))})  # fmt: skip
    assert a.harvest(table_of(row), f).redirected_same == 1 and transport.calls == [row.capture, target]


def test_the_harvest_goes_on_past_a_redirect_marks_and_replays_offline_with_the_same_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from openproceedings.ingest.sources import crawl

    keys = ("conf/aaai/Araya84", "conf/aaai/DetermanB98", "conf/aaai/KimuraSN07")
    same, moved, plain = rows = [row_for(k) for k in keys]
    same_to = f"https://web.archive.org/web/{OTHER_TS}id_/http://{PAGE}"
    script = {same.capture: _moved(same_to), same_to: Response(200, {}, body(FIXTURES[same.key])),
              moved.capture: _moved("https://web.archive.org/web/20190101000000id_/http://www.aaai.org/"),
              plain.capture: Response(200, {}, body(FIXTURES[plain.key]))}  # fmt: skip
    table = table_of(*rows)
    monkeypatch.setattr(aaai_library_table, "TABLE", table)
    with caplog.at_level(logging.INFO):
        out = crawl.ingest_aaai_library(
            tmp_path, transport=FakeTransport(script), min_interval=0, table=table
        )
    assert out == {"dry_run": False, "pages": 3, "fetched": 3, "missing": 0, "redirect": 1,
                   "redirected_same": 1, "requests": 4, "cached": 0}  # fmt: skip
    marker = json.loads((tmp_path / "aaai_library" / "crawls" / "aaai_library.json").read_text())
    assert (marker["pages"], marker["missing"], marker["redirect"]) == (3, 0, 1)
    events = {r.getMessage(): r for r in caplog.records}
    assert events["aaai_library_ingested"].__dict__["redirect"] == 1
    assert events["aaai_library_ingested"].__dict__["redirected_same"] == 1
    assert events["aaai_library_attention"].levelno == logging.WARNING
    assert events["aaai_library_attention"].__dict__["capture_redirect"] == 1
    records = DedupResult(
        (record(same.key), record(moved.key, year=1998), record(plain.key, year=2007)), (), ()
    )
    _, (live,) = a.apply(records, tmp_path)
    assert live.attached == 2 and live.refused == {"capture_redirect": 1}
    caplog.clear()
    # offline, from the cache alone: the harvest completes with the redirected row, and the fill is the same
    again = crawl.ingest_aaai_library(tmp_path, offline=True, table=table)
    assert (again["pages"], again["redirect"], again["requests"]) == (3, 1, 0)
    assert crawl.ingest_aaai_library(tmp_path, dry_run=True, table=table)["to_fetch"] == 0
    with caplog.at_level(logging.INFO):
        _, (replayed,) = a.apply(records, tmp_path)
    assert replayed.to_manifest() == live.to_manifest()
    events = {r.getMessage(): r for r in caplog.records}
    assert events["aaai_library_filled"].__dict__["refused"] == {"capture_redirect": 1}
    assert events["aaai_library_attention"].__dict__["capture_redirect"] == 1


def test_an_abstract_held_by_sources_on_both_sides_of_it_is_not_outranked() -> None:
    """`_outranked` asks that every claim holding the abstract rank after aaai_library: one ranked before it (dblp)
    beside one ranked after it (ris) keeps the abstract (gate C round 1: `all`, not `any`)."""
    text = "An abstract two sources gave."
    both = record("conf/aaai/Araya84", abstract=(text, "ris"))
    claim = Claim(field="abstract", value=text, source="dblp", fetched_at=T, evidence="t")
    mixed = resolve(both.id, [*both.provenance, claim])[0]
    assert {c.source for c in mixed.claims("abstract")} == {"ris", "dblp"}
    assert a._outranked(both) and not a._outranked(mixed)
