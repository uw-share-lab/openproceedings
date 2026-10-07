"""Reading one stream's entries out of a dblp snapshot release (spec 01 §Sources, dblp row; TASK-205).

The release (`dblp-<date>.xml.gz`, about 1.1 GB compressed and several GB of XML) is never loaded whole. It is
read line by line through gzip, and only the records whose `key` starts with the wanted prefix
(`conf/icml/`) are handed to expat, one record at a time, with the release's DTD supplying its character
entities (`&uuml;` and the rest). A record runs from its start tag
(`<inproceedings mdate="…" key="conf/icml/…">`, anywhere in a line: dblp writes `</incollection><inproceedings …>`
on one line) to its end tag. That framing is checked rather than trusted: every `key="conf/icml/` in the file must
be inside a record start tag, and every such record must parse as one element of a known record type, or the read
is refused (`DblpFormatError`), never a silently smaller extract. The release must name the pinned DTD.

Only what the ingest uses is kept, verbatim (no cleaning here; `dblp.py` decides): the record type, key, mdate,
`publtype`, title text (inline markup such as `<i>` and `<sub>` flattened to its text), authors in order, year,
booktitle, crossref, pages, every `ee`, and for a `proceedings` record its title, volume and publisher.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.parsers import expat

# dblp's record elements (the DTD's `%rec` entity)
RECORD_TYPES = frozenset(
    {"article", "inproceedings", "proceedings", "book", "incollection", "phdthesis", "mastersthesis", "www",
     "data"}
)  # fmt: skip
_TEXT_FIELDS = ("title", "year", "booktitle", "crossref", "pages", "volume", "publisher", "series")
_LIST_FIELDS = ("author", "editor", "ee")


class DblpFormatError(ValueError):
    """The release isn't framed or formed as this reader expects: the message says where."""


@dataclass
class DblpEntry:
    """One record of the wanted stream, as the release states it."""

    type: str
    key: str
    mdate: str
    publtype: str | None
    fields: dict[str, str] = field(default_factory=dict)  # each `_TEXT_FIELDS` element's text (the first)
    lists: dict[str, list[str]] = field(default_factory=dict)  # each `_LIST_FIELDS` element's texts, in order

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type, "key": self.key, "mdate": self.mdate, "publtype": self.publtype,
                "fields": dict(sorted(self.fields.items())), "lists": dict(sorted(self.lists.items()))}  # fmt: skip

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> DblpEntry:
        return cls(type=str(raw["type"]), key=str(raw["key"]), mdate=str(raw["mdate"]),
                   publtype=raw["publtype"] if raw["publtype"] is None else str(raw["publtype"]),
                   fields={str(k): str(v) for k, v in raw["fields"].items()},
                   lists={str(k): [str(x) for x in v] for k, v in raw["lists"].items()})  # fmt: skip


def _start_tag(prefix: str) -> re.Pattern[bytes]:
    types = "|".join(sorted(RECORD_TYPES)).encode()
    return re.compile(rb"<(" + types + rb')\s[^<>]*?\bkey="' + re.escape(prefix.encode()) + rb'[^"]*"[^<>]*>')


def doctype_system_id(path: Path) -> str:
    """The DTD the release names in its `<!DOCTYPE dblp SYSTEM "…">` (the file's second line), after checking its
    first declares ISO-8859-1 (the encoding `_parse` gives each record)."""
    with gzip.open(path, "rb") as fh:
        head = fh.read(4096)
    if not head.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>'):
        raise DblpFormatError("the release doesn't declare ISO-8859-1, the encoding each record is parsed in")
    m = re.search(rb'<!DOCTYPE dblp SYSTEM "([^"]+)">', head)
    if m is None:
        raise DblpFormatError("the release has no <!DOCTYPE dblp SYSTEM ...> line")
    return m.group(1).decode("ascii")


PROGRESS_LINES = 1_000_000  # how often `_records` reports its progress (the caller rate-limits the lines)


def _records(path: Path, prefix: str, progress: Callable[[int, int], None] | None = None) -> Iterator[bytes]:
    """Each wanted record's bytes, from its start tag through its end tag, in file order. dblp writes a record's
    end tag and the next record's start tag on one line (`</incollection><incollection …>`), so a record is found
    by its start tag anywhere in a line, and every occurrence of `key="<prefix>` must be inside one."""
    wanted = f'key="{prefix}'.encode()
    start = _start_tag(prefix)
    block: list[bytes] = []
    end: bytes | None = None
    with gzip.open(path, "rb") as fh:
        kept = 0
        for n, line in enumerate(fh, 1):
            if progress is not None and n % PROGRESS_LINES == 0:
                progress(n, kept)
            if end is None and wanted not in line:
                continue
            pos = 0
            while True:
                if end is None:
                    m = start.search(line, pos)
                    rest = line[pos:] if m is None else line[pos : m.start()]
                    if wanted in rest:
                        raise DblpFormatError(f"line {n}: a {prefix} key outside a record start tag")
                    if m is None:
                        break
                    end, pos = b"</" + m.group(1) + b">", m.start()
                    block = []
                stop = line.find(end, pos)
                inside = line[pos:] if stop < 0 else line[pos : stop + len(end)]
                if start.search(inside, 0 if block else 1):  # a second wanted start tag before this one ends
                    raise DblpFormatError(f"line {n}: a {prefix} record inside another")
                block.append(inside)
                if stop < 0:
                    break
                kept += 1
                yield b"".join(block)
                pos, end = stop + len(end), None
    if end is not None:
        raise DblpFormatError(f"the file ends inside a {prefix} record")


def _parse(record: bytes, dtd: bytes, dtd_name: str) -> DblpEntry:
    """One record through expat, its entities from the DTD."""
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_ALWAYS)

    def external(context: str | None, base: str | None, system_id: str | None, public_id: str | None) -> int:
        if system_id != dtd_name:
            raise DblpFormatError(f"an external entity other than the DTD: {system_id!r}")
        sub = parser.ExternalEntityParserCreate(context)
        sub.Parse(dtd, True)
        return 1

    entry: DblpEntry | None = None
    stack: list[str] = []
    text: list[str] = []

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal entry, text
        stack.append(name)
        if len(stack) == 2:
            if name not in RECORD_TYPES or entry is not None:
                raise DblpFormatError(f"not one dblp record: <{name}>")
            entry = DblpEntry(name, attrs.get("key", ""), attrs.get("mdate", ""), attrs.get("publtype"))
        elif len(stack) == 3:
            text = []

    def end(name: str) -> None:
        stack.pop()
        if len(stack) == 2 and entry is not None:
            value = " ".join("".join(text).split())
            if name in _LIST_FIELDS:
                entry.lists.setdefault(name, []).append(value)
            elif name in _TEXT_FIELDS:
                entry.fields.setdefault(name, value)

    def chars(data: str) -> None:
        if len(stack) >= 3:
            text.append(data)

    def skipped(name: str, is_parameter_entity: bool) -> None:
        raise DblpFormatError(f"an entity the DTD doesn't define: &{name};")  # never dropped silently

    parser.ExternalEntityRefHandler = external
    parser.SkippedEntityHandler = skipped
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    doc = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>\n<!DOCTYPE dblp SYSTEM "'
        + dtd_name.encode("ascii")
        + b'">\n<dblp>'
        + record
        + b"</dblp>"
    )
    try:
        parser.Parse(doc, True)
    except expat.ExpatError as e:
        raise DblpFormatError(f"a record doesn't parse ({expat.ErrorString(e.code)})") from None
    if entry is None or not entry.key:
        raise DblpFormatError("a record without a key")
    return entry


def read_stream(
    path: Path, dtd: bytes, dtd_name: str, prefix: str, progress: Callable[[int, int], None] | None = None
) -> list[DblpEntry]:
    """Every record of the release at `path` whose key starts with `prefix`, in file order. The release must
    name `dtd_name` as its DTD (the pinned one); `dtd` is that file's bytes."""
    if (named := doctype_system_id(path)) != dtd_name:
        raise DblpFormatError(f"the release names DTD {named!r}, not the pinned {dtd_name!r}")
    entries = [_parse(block, dtd, dtd_name) for block in _records(path, prefix, progress)]
    for e in entries:
        if not e.key.startswith(prefix):
            raise DblpFormatError(f"record {e.key!r} isn't in {prefix}")
    return entries
