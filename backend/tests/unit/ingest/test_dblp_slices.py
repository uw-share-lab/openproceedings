"""One read of the pinned release writes each venue's slice (decision-049, milestone B); ICML's extract keeps its path
and its bytes (guarantee 4). Synthetic records in the release's framing (decision-004)."""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest import dblp_table
from openproceedings.ingest.sources import dblp
from openproceedings.ingest.sources.dblp_xml import DblpFormatError, read_stream, read_streams

from tests.unit.ingest import test_dblp
from tests.unit.ingest.test_dblp_xml import BODY, DTD, DTD_NAME, HEAD, Stream, release

AAAI_BODY = """<inproceedings mdate="2020-01-01" key="conf/aaai/Synthetic86a">
<author>Synthetic Author 1 0001</author>
<author>Synth&uuml;tic Author 2</author>
<title>Synthetic AAAI title 1.</title>
<year>1986</year>
<ee>https://doi.org/10.5555/synthetic.1</ee>
<crossref>conf/aaai/1986-1</crossref>
</inproceedings><inproceedings mdate="2020-01-01" key="conf/aaai/Synthetic86b"><author>Synthetic Author 3</author><title>Synthetic AAAI title 2?</title><year>1986</year><crossref>conf/aaai/1986-2</crossref></inproceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Invited86"><author>Synthetic Author 4</author><title>Synthetic invited talk.</title><year>1986</year><crossref>conf/aaai/1986-1</crossref></inproceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Withdrawn86" publtype="withdrawn"><author>Synthetic Author 5</author><title>Synthetic title 3.</title><year>1986</year><crossref>conf/aaai/1986-2</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/1986-1"><title>Synthetic AAAI 1986, Volume 1</title><year>1986</year></proceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/1986-2"><title>Synthetic AAAI 1986, Volume 2</title><year>1986</year></proceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2006"><title>Synthetic AAAI 2006</title><year>2006</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Main06"><author>Synthetic Author 7</author><title>Synthetic main paper.</title><year>2006</year><crossref>conf/aaai/2006</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2006w"><title>Synthetic AAAI 2006 workshop</title><year>2006</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Workshop06"><author>Synthetic Author 6</author><title>Synthetic workshop paper.</title><year>2006</year><crossref>conf/aaai/2006w</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2024"><title>Synthetic AAAI 2024</title><year>2024</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Late24"><author>Synthetic Author 8</author><title>Never read.</title><year>2024</year><crossref>conf/aaai/2024</crossref></inproceedings>
"""
FULL = BODY.replace("</dblp>\n", "") + AAAI_BODY + "</dblp>\n"
GZ_FULL = gzip.compress((HEAD + FULL).encode("latin-1"), mtime=0)


def pins(gz: bytes) -> dblp_table.Table:
    """test_dblp's ICML table, pinned to `gz` instead of its own release."""
    text = test_dblp.table_text(sha=hashlib.sha256(gz).hexdigest())
    return dblp_table.load(text.replace(f"size = {len(test_dblp.GZ)}", f"size = {len(gz)}", 1))


def on_disk(tmp_path: Path, gz: bytes = GZ_FULL) -> tuple[dblp_table.Table, object, object]:
    table = pins(gz)
    release, dtd = dblp.fetch_release(tmp_path, Stream((200, DTD), (200, gz)), table)
    return table, release, dtd


def test_read_streams_splits_one_pass_by_prefix(tmp_path: Path) -> None:
    path = release(tmp_path, FULL)
    both = read_streams(path, DTD, DTD_NAME, ("conf/icml/", "conf/aaai/"))
    assert [e.key for e in both["conf/icml/"]] == [
        e.key for e in read_stream(path, DTD, DTD_NAME, "conf/icml/")
    ]
    assert {e.key for e in both["conf/aaai/"]} >= {
        "conf/aaai/Synthetic86a",
        "conf/aaai/1986-1",
        "conf/aaai/Late24",
    }
    assert all(e.key.startswith("conf/aaai/") for e in both["conf/aaai/"])


@pytest.mark.parametrize("prefixes", [("conf/icml/", "conf/icml/"), ("conf/", "conf/aaai/")])
def test_overlapping_prefixes_are_refused(tmp_path: Path, prefixes: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="distinct"):
        read_streams(release(tmp_path, FULL), DTD, DTD_NAME, prefixes)


def test_an_aaai_key_outside_a_record_start_tag_is_refused(tmp_path: Path) -> None:
    body = FULL.replace("</dblp>", '<www key="x"><note>key="conf/aaai/Stray"</note></www></dblp>')
    with pytest.raises(DblpFormatError, match="conf/aaai/"):
        read_streams(release(tmp_path, body), DTD, DTD_NAME, ("conf/icml/", "conf/aaai/"))


def test_the_icml_extract_is_the_same_bytes_whether_or_not_aaai_shares_the_pass(tmp_path: Path) -> None:
    table, rel, dtd = on_disk(tmp_path)
    alone = dblp.write_extract(tmp_path, rel, dtd, table)
    first = dblp.extract_path(tmp_path, table).read_bytes()
    both = dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)
    assert dblp.extract_path(tmp_path, table).read_bytes() == first and both["ICML"] == alone
    assert (
        dblp.extract_path(tmp_path, table)
        == tmp_path / "dblp" / "extract" / f"{table.release.file.sha256}.json"
    )
    assert (
        dblp.AAAI_SLICE.path(tmp_path, table)
        == tmp_path / "dblp" / "extract" / "aaai" / f"{table.release.file.sha256}.json"
    )
    assert dblp.load_extract(tmp_path, table, dblp.AAAI_SLICE) == both["AAAI"]


# sha256 of the ICML extract origin/dev's writer (5f147e32, `write_extract` before slices existed) wrote from GZ_FULL
# and its DTD, with `fetched_at` 2026-10-10T00:00:00+00:00 and the release's sha256 replaced by 64 zeros: computed once
# from a `git archive 5f147e32` copy on 2026-10-10. The hash is normalized because the extract records
# `release_sha256`, the sha256 of `gzip.compress(...)`, and gzip/zlib output bytes differ between platforms' zlib
# builds (macOS vs Linux CI), so the raw extract's bytes are not portable. A change to the extract's format, keys or
# order still fails here (guarantee 4: ICML's bytes are unchanged).
PRE_SLICE_ICML_SHA256 = "fd19a9138bae87e2c45c3696cf40fea428573061d84e86481daf9efda3ced56f"
RELEASE_SHA256_PLACEHOLDER = "0" * 64


def test_the_icml_extract_is_byte_identical_to_the_pre_slice_writers(tmp_path: Path) -> None:
    table, rel, dtd = on_disk(tmp_path)
    fixed = dataclasses.replace(rel, fetched_at=datetime(2026, 10, 10, tzinfo=UTC))
    dblp.write_extracts(tmp_path, fixed, dtd, table, dblp.SLICES)
    path = dblp.extract_path(tmp_path, table)
    assert path == tmp_path / "dblp" / "extract" / f"{table.release.file.sha256}.json"
    raw = path.read_bytes()
    assert (
        raw.count(table.release.file.sha256.encode()) == 1
    )  # only `release_sha256` derives from the gzip bytes
    normalized = raw.replace(table.release.file.sha256.encode(), RELEASE_SHA256_PLACEHOLDER.encode())
    assert hashlib.sha256(normalized).hexdigest() == PRE_SLICE_ICML_SHA256


def test_prepare_slices_reads_the_release_once_for_every_missing_slice(tmp_path: Path, monkeypatch) -> None:
    table, _rel, _dtd = on_disk(tmp_path)
    reads: list[tuple[str, ...]] = []
    real = dblp.read_streams
    monkeypatch.setattr(dblp, "read_streams", lambda *a, **k: reads.append(a[3]) or real(*a, **k))
    out = dblp.prepare_slices(tmp_path, None, table, (dblp.AAAI_SLICE,))
    assert reads == [("conf/aaai/", "conf/icml/")] or reads == [
        ("conf/icml/", "conf/aaai/")
    ]  # one read, both
    assert set(out) == {"AAAI"} and dblp.extract_path(tmp_path, table).exists()
    dblp.prepare_slices(tmp_path, None, table, dblp.SLICES)
    assert len(reads) == 1  # both on disk: nothing is read again


def test_an_aaai_extract_holding_another_streams_entry_is_refused(tmp_path: Path) -> None:
    table, rel, dtd = on_disk(tmp_path)
    dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)
    path = dblp.AAAI_SLICE.path(tmp_path, table)
    path.write_text(path.read_text().replace('"conf/aaai/Main06"', '"conf/icml/Main06"'))
    with pytest.raises(dblp.CrawlError, match="malformed"):
        dblp.load_extract(tmp_path, table, dblp.AAAI_SLICE)
