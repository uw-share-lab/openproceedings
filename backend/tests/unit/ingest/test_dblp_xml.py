"""The dblp release reader (TASK-205) and the pinned-file download it rests on.

The XML here is a synthetic excerpt in the release's own framing (decision-004: real keys, crossrefs, element
names and line layout; titles and authors synthetic): dblp writes a record's end tag and the next record's start
tag on one line, names its DTD by file name, and spells non-ASCII characters as the DTD's entities. The DTD is
the pinned file itself (`fixtures/dblp/dblp-2023-06-28.dtd`, CC0). Scripted transports only; no network.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest.sources.dblp_xml import DblpFormatError, doctype_system_id, read_stream
from openproceedings.ingest.sources.http import (
    CacheError,
    CacheMiss,
    FetchError,
    HTTPRefused,
    PinnedFile,
    Request,
    RetriesExhausted,
    StreamResponse,
    TransportError,
    fetch_file,
)

from tests.unit.ingest.openreview_fakes import FakeClock

FIXTURES = Path(__file__).parents[2] / "fixtures" / "dblp"
DTD_NAME = "dblp-2023-06-28.dtd"
DTD = (FIXTURES / DTD_NAME).read_bytes()
HEAD = f'<?xml version="1.0" encoding="ISO-8859-1"?>\n<!DOCTYPE dblp SYSTEM "{DTD_NAME}">\n<dblp>\n'
# One line holds an end tag and the next start tag, as the release does; `&uuml;` comes from the DTD; `<i>` is
# inline markup in a title; `0001` is a homonym number; the withdrawn and workshop papers are kept by the reader
# (the miner decides).
BODY = """<article mdate="2020-01-01" key="journals/ml/Other90">
<author>Synthetic Author 1</author>
<title>Not an ICML paper.</title>
<year>1990</year>
</article><inproceedings mdate="2017-05-20" key="conf/icml/Synthetic90">
<author>Synthetic Author 2 0001</author>
<author>Synth&uuml;tic Author 3</author>
<title>Synthetic title with <i>markup</i> 1.</title>
<pages>1-8</pages>
<year>1990</year>
<booktitle>ML</booktitle>
<ee>https://doi.org/10.1016/b978-1-55860-141-3.50001-0</ee>
<ee type="oa">https://www.wikidata.org/entity/Q1</ee>
<crossref>conf/icml/1990</crossref>
<url>db/conf/icml/icml1990.html#Synthetic90</url>
</inproceedings><proceedings mdate="2017-05-20" key="conf/icml/1990">
<editor>Synthetic Editor 1</editor>
<title>Machine Learning, Proceedings of the Seventh International Conference on Machine Learning</title>
<publisher>Morgan Kaufmann</publisher>
<year>1990</year>
</proceedings>
<proceedings mdate="2019-01-01" key="conf/icml/2009"><title>ICML 2009</title><year>2009</year></proceedings>
<inproceedings mdate="2019-01-01" key="conf/icml/Withdrawn09" publtype="withdrawn">
<author>Synthetic Author 4</author>
<title>Synthetic title 2?</title>
<year>2009</year>
<crossref>conf/icml/2009</crossref>
</inproceedings><inproceedings mdate="2019-01-01" key="conf/icml/Workshop06"><author>Synthetic Author 5</author><title>Synthetic title 3.</title><year>2006</year><crossref>conf/icml/2006sna</crossref></inproceedings>
<proceedings mdate="2019-01-01" key="conf/icml/2006sna"><title>Synthetic workshop</title><year>2007</year></proceedings>
</dblp>
"""


def release(tmp_path: Path, body: str = BODY, head: str = HEAD) -> Path:
    path = tmp_path / "dblp.xml.gz"
    path.write_bytes(gzip.compress((head + body).encode("latin-1")))
    return path


def test_reads_only_the_stream_across_shared_lines_with_entities_and_markup(tmp_path: Path) -> None:
    entries = read_stream(release(tmp_path), DTD, DTD_NAME, "conf/icml/")
    assert [e.key for e in entries] == [
        "conf/icml/Synthetic90", "conf/icml/1990", "conf/icml/2009", "conf/icml/Withdrawn09", "conf/icml/Workshop06",
        "conf/icml/2006sna",
    ]  # fmt: skip
    paper = entries[0]
    assert (paper.type, paper.mdate, paper.publtype) == ("inproceedings", "2017-05-20", None)
    assert (
        paper.fields["title"] == "Synthetic title with markup 1."
    )  # markup flattened; dblp's period kept here
    assert paper.lists["author"] == ["Synthetic Author 2 0001", "Synthütic Author 3"]  # entity from the DTD
    assert paper.fields["crossref"] == "conf/icml/1990" and len(paper.lists["ee"]) == 2
    assert entries[1].type == "proceedings" and entries[1].fields["publisher"] == "Morgan Kaufmann"
    assert entries[3].publtype == "withdrawn"


def test_the_release_must_declare_the_encoding_records_are_parsed_in(tmp_path: Path) -> None:
    path = release(tmp_path, head=HEAD.replace("ISO-8859-1", "UTF-8"))
    with pytest.raises(DblpFormatError, match="ISO-8859-1"):
        read_stream(path, DTD, DTD_NAME, "conf/icml/")


def test_the_release_must_name_the_pinned_dtd(tmp_path: Path) -> None:
    path = release(tmp_path, head=HEAD.replace(DTD_NAME, "dblp-2019-11-22.dtd"))
    assert doctype_system_id(path) == "dblp-2019-11-22.dtd"
    with pytest.raises(DblpFormatError, match="not the pinned"):
        read_stream(path, DTD, DTD_NAME, "conf/icml/")


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ('<www key="homepages/x">\n<note>key="conf/icml/X90"</note>\n</www>\n', "outside a record start tag"),
        # another spelling of the attribute: never read as no record at all
        ("<inproceedings mdate=\"1\" key='conf/icml/A90'>\n<title>T.</title>\n</inproceedings>\n",
         "outside a record start tag"),
        ('<inproceedings mdate="1" key = "conf/icml/A90">\n<title>T.</title>\n</inproceedings>\n',
         "outside a record start tag"),
        ('<inproceedings mdate="1" key="conf/icml/A90">\n<title>T.</title>\n', "ends inside"),
        ('<inproceedings mdate="1" key="conf/icml/A90">\n<title>T &nosuchentity; .</title>\n</inproceedings>\n',
         "the DTD doesn.t define"),
        ('<inproceedings mdate="1" key="conf/icml/A90">\n<title>T</x>.</title>\n</inproceedings>\n', "doesn.t parse"),
        ('<inproceedings mdate="1" key="conf/icml/A90">\n<title>T.</title>\n<inproceedings mdate="1" '
         'key="conf/icml/B90"></inproceedings>\n</inproceedings>\n', "inside another"),
    ],
)  # fmt: skip
def test_a_release_the_framing_does_not_hold_for_is_refused(tmp_path: Path, body: str, why: str) -> None:
    with pytest.raises(DblpFormatError, match=why):
        read_stream(release(tmp_path, body + "</dblp>\n"), DTD, DTD_NAME, "conf/icml/")


# --- fetch_file: the pinned release through the shared HTTP layer ----------------------------------------------

BYTES = b"x" * 3000
PIN = PinnedFile("https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/f.xml.gz", len(BYTES),
                 hashlib.sha256(BYTES).hexdigest())  # fmt: skip
HOSTS = frozenset({"drops.dagstuhl.de"})


class Stream:
    """Scripted streaming transport: each call serves the next answer (a status with a body, or an exception)."""

    def __init__(self, *answers: tuple[int, bytes] | Exception) -> None:
        self.answers, self.sent = list(answers), []  # type: list[tuple[int, bytes] | Exception]

    def __call__(self, request: Request, timeout: float) -> StreamResponse:
        self.sent.append(request.url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer

        def chunks() -> Iterator[bytes]:
            for i in range(0, len(body), 1000):
                yield body[i : i + 1000]

        return StreamResponse(status, {"retry-after": "1"} if status == 503 else {}, chunks())


def test_a_pinned_file_is_downloaded_once_verified_and_then_read_from_disk(tmp_path: Path) -> None:
    clock = FakeClock()
    t = Stream((503, b""), (200, BYTES))
    first = fetch_file(PIN, tmp_path / "f.xml.gz", t, hosts=HOSTS, clock=clock)
    assert (first.path.read_bytes(), first.cached, len(t.sent)) == (BYTES, False, 2)  # the 503 waited out
    assert clock.sleeps == [1.0]  # for as long as its Retry-After said, not the back-off
    side = json.loads((tmp_path / "f.xml.gz.json").read_text())
    assert (side["sha256"], side["url"]) == (PIN.sha256, PIN.url)
    again = fetch_file(PIN, tmp_path / "f.xml.gz", None, hosts=HOSTS)  # offline: the verified copy
    assert (again.cached, again.fetched_at) == (True, first.fetched_at)
    assert not list(tmp_path.glob(".tmp-*"))


def test_a_download_that_is_not_the_pin_is_refused_and_not_kept(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="not the pinned") as e:
        fetch_file(PIN, tmp_path / "f.xml.gz", Stream((200, b"y" * 3000)), hosts=HOSTS, clock=FakeClock())
    assert e.value.reason == "pin_mismatch" and not list(tmp_path.iterdir())
    longer = Stream(*[(200, BYTES + b"z")] * 3)
    with pytest.raises(FetchError, match="over the pinned") as e:  # longer than the pin: cut off at once
        fetch_file(PIN, tmp_path / "f.xml.gz", longer, hosts=HOSTS, clock=FakeClock())
    assert e.value.reason == "pin_mismatch" and len(longer.sent) == 1  # never fetched again in full
    assert not list(tmp_path.iterdir())


def test_a_changed_copy_on_disk_is_fetched_again_or_refused_offline(tmp_path: Path) -> None:
    fetch_file(PIN, tmp_path / "f.xml.gz", Stream((200, BYTES)), hosts=HOSTS, clock=FakeClock())
    (tmp_path / "f.xml.gz").write_bytes(b"y" * 3000)
    with pytest.raises(CacheMiss):
        fetch_file(PIN, tmp_path / "f.xml.gz", None, hosts=HOSTS)
    again = fetch_file(PIN, tmp_path / "f.xml.gz", Stream((200, BYTES)), hosts=HOSTS, clock=FakeClock())
    assert again.cached is False and again.path.read_bytes() == BYTES


def test_off_host_refusals_and_spent_retries(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="is not on"):
        fetch_file(PinnedFile("https://dblp.org/xml/dblp.xml.gz", 1, "0" * 64), tmp_path / "f", Stream(),
                   hosts=HOSTS)  # fmt: skip
    for status in (404, 403):  # any 4xx but 429 is refused at once, never retried
        refused = Stream((status, b""), (200, BYTES))
        with pytest.raises(HTTPRefused):
            fetch_file(PIN, tmp_path / "f.xml.gz", refused, hosts=HOSTS, clock=FakeClock())
        assert len(refused.sent) == 1
    with pytest.raises(RetriesExhausted):
        fetch_file(PIN, tmp_path / "f.xml.gz", Stream(*[TransportError("ConnectionResetError")] * 3),
                   hosts=HOSTS, clock=FakeClock())  # fmt: skip
    assert not (tmp_path / "f.xml.gz").exists()


@pytest.mark.parametrize(
    ("sidecar", "why"),
    [("not json", "unreadable"), ('{"url": "u", "sha256": "s"}', "unreadable"),
     (json.dumps({"url": PIN.url, "sha256": PIN.sha256, "fetched_at": "2026-10-06T00:00:00"}), "naive fetched_at")],
)  # fmt: skip
def test_a_sidecar_that_cant_say_when_the_file_was_fetched_is_refused(
    tmp_path: Path, sidecar: str, why: str
) -> None:
    (tmp_path / "f.xml.gz").write_bytes(BYTES)
    (tmp_path / "f.xml.gz.json").write_text(sidecar)
    with pytest.raises(CacheError, match=why):
        fetch_file(PIN, tmp_path / "f.xml.gz", None, hosts=HOSTS)


def test_the_fetch_time_is_the_clocks_utc(tmp_path: Path) -> None:
    clock = FakeClock()
    got = fetch_file(PIN, tmp_path / "f.xml.gz", Stream((200, BYTES)), hosts=HOSTS, clock=clock)
    assert got.fetched_at == clock.now().astimezone(UTC) and isinstance(got.fetched_at, datetime)


def test_a_dtd_name_that_is_not_ascii_is_a_format_error(tmp_path: Path) -> None:
    path = tmp_path / "x.xml.gz"
    path.write_bytes(gzip.compress(HEAD.replace(DTD_NAME, "dblp-\u00e9.dtd").encode("latin-1") + b"</dblp>"))
    with pytest.raises(DblpFormatError, match="not ASCII"):
        doctype_system_id(path)


def test_a_retry_after_past_the_bound_aborts_rather_than_waits(tmp_path: Path) -> None:
    class Slow(Stream):
        def __call__(self, request: Request, timeout: float) -> StreamResponse:
            self.sent.append(request.url)
            return StreamResponse(503, {"retry-after": "7200"}, ())

    with pytest.raises(FetchError, match="asked to wait") as e:
        fetch_file(PIN, tmp_path / "f.xml.gz", Slow(), hosts=HOSTS, clock=FakeClock())
    assert e.value.reason == "wait_too_long"


def test_a_download_says_when_it_starts_how_far_it_has_got_and_why_a_copy_was_not_used(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    class Ticking(FakeClock):  # every read of the monotonic clock is 31 s on: each progress check is due
        def monotonic(self) -> float:
            self.t += 31
            return self.t

    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources.http"):
        fetch_file(PIN, tmp_path / "f.xml.gz", Stream((200, BYTES)), hosts=HOSTS, clock=Ticking())
    events = [r.getMessage() for r in caplog.records]
    assert events[0] == "pinned_file_fetch_started" and "pinned_file_progress" in events
    assert events[-1] == "pinned_file_fetched"
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources.http"):
        fetch_file(PIN, tmp_path / "f.xml.gz", None, hosts=HOSTS)  # a verified copy: hashed, and said so
    assert [r.getMessage() for r in caplog.records] == ["pinned_file_verify_started", "pinned_file_verified"]
    side = tmp_path / "f.xml.gz.json"
    meta = json.loads(side.read_text())
    for change, reason in (
        (lambda: side.write_text(json.dumps(meta | {"sha256": "0" * 64})), "sidecar_mismatch"),
        (lambda: (tmp_path / "f.xml.gz").write_bytes(BYTES + b"!"), "size_mismatch"),
        (lambda: (tmp_path / "f.xml.gz").write_bytes(b"y" * len(BYTES)), "hash_mismatch"),
    ):
        side.write_text(json.dumps(meta))
        (tmp_path / "f.xml.gz").write_bytes(BYTES)
        change()
        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="openproceedings.ingest.sources.http"),
            pytest.raises(CacheMiss),
        ):
            fetch_file(PIN, tmp_path / "f.xml.gz", None, hosts=HOSTS)
        [mismatch] = [r for r in caplog.records if r.getMessage() == "pinned_file_mismatch"]
        assert mismatch.reason == reason  # type: ignore[attr-defined]
