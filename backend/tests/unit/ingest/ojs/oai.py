"""Synthetic OAI-PMH ListRecords pages in the shape ojs.aaai.org serves (checked live 2026-10-09)."""

from xml.sax.saxutils import escape

BASE = "https://ojs.aaai.org/index.php/{j}/oai"


def record(
    article: int,
    set_spec: str = "AAAI:AISI",
    *,
    title: str = "A Paper",
    creators=("Doe, Jane",),
    description: str | None = "An abstract.",
    volume: str = "Vol. 34 No. 01: AAAI-20 Technical Tracks 1",
    journal: str = "AAAI",
    extra: str = "",
    public_id: str | None = None,
) -> str:
    """`public_id` replaces the article id in the dc:identifier and dc:relation URLs (an OJS public id)."""
    seg = public_id or str(article)

    desc = (
        ""
        if description is None
        else f'<dc:description xml:lang="en-US">{escape(description)}</dc:description>'
    )
    names = "".join(f"<dc:creator>{escape(c)}</dc:creator>" for c in creators)
    return f"""<record><header><identifier>oai:ojs.aaai.org:article/{article}</identifier>
<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>{set_spec}</setSpec></header><metadata>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title xml:lang="en-US">{escape(title)}</dc:title>{names}{desc}{extra}
<dc:identifier>https://ojs.aaai.org/index.php/{journal}/article/view/{seg}</dc:identifier>
<dc:identifier>10.1609/{journal.lower()}.v34i01.{article}</dc:identifier>
<dc:source xml:lang="en-US">Proceedings of the AAAI Conference on Artificial Intelligence; {volume}; 1-8</dc:source>
<dc:source>2374-3468</dc:source>
<dc:relation>https://ojs.aaai.org/index.php/{journal}/article/view/{seg}{"" if public_id else f"/{article + 7000}"}</dc:relation>
</oai_dc:dc></metadata></record>"""


def deleted(article: int, set_spec: str = "AAAI:AISI") -> str:
    return f"""<record><header status="deleted"><identifier>oai:ojs.aaai.org:article/{article}</identifier>
<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>{set_spec}</setSpec></header></record>"""


def page(*records: str, token: str | None = None, size: int | None = None) -> str:
    rt = (
        ""
        if token is None
        else (
            f'<resumptionToken expirationDate="2026-10-10T22:01:20Z" completeListSize="{size or 0}" cursor="0">'
            f"{token}</resumptionToken>"
        )
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="ListRecords" metadataPrefix="oai_dc">https://ojs.aaai.org/index.php/AAAI/oai</request>
<ListRecords>{"".join(records)}{rt}</ListRecords></OAI-PMH>
"""


def error(code: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request>https://ojs.aaai.org/index.php/AAAI/oai</request><error code="{code}">message</error></OAI-PMH>
"""


def sets_page(*specs: str, token: str | None = None, names: dict[str, str] | None = None) -> str:
    """A ListSets page naming `specs` (names default to the spec)."""
    names = names or {}
    sets = "".join(
        f"<set><setSpec>{escape(s)}</setSpec><setName>{escape(names.get(s, s))}</setName></set>"
        for s in specs
    )
    rt = (
        "" if token is None else f'<resumptionToken completeListSize="0" cursor="0">{token}</resumptionToken>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="ListSets">https://ojs.aaai.org/index.php/AAAI/oai</request><ListSets>{sets}{rt}</ListSets></OAI-PMH>
"""


def identifiers_page(*headers: tuple[int, bool, str], token: str | None = None) -> str:
    """A ListIdentifiers page of (article, deleted, setSpec) headers."""
    body = "".join(
        f"<header{' status="deleted"' if d else ''}><identifier>oai:ojs.aaai.org:article/{a}</identifier>"
        f"<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>{s}</setSpec></header>"
        for a, d, s in headers
    )
    rt = (
        "" if token is None else f'<resumptionToken completeListSize="0" cursor="0">{token}</resumptionToken>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="ListIdentifiers">https://ojs.aaai.org/index.php/AAAI/oai</request>
<ListIdentifiers>{body}{rt}</ListIdentifiers></OAI-PMH>
"""


def get_record(record_xml: str) -> str:
    """A GetRecord response holding one `record(...)`."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="GetRecord">https://ojs.aaai.org/index.php/AAAI/oai</request><GetRecord>{record_xml}</GetRecord></OAI-PMH>
"""


def inventory_of(*pages: str) -> str:
    """The journal-wide ListIdentifiers page matching ListRecords `pages`: every header in order, a live article
    once (as the server lists it)."""
    from openproceedings.ingest.sources import ojs

    headers: list[tuple[int, bool, str]] = []
    live: set[int] = set()
    for text in pages:
        if "<ListRecords>" not in text:  # an error page lists nothing
            continue
        for r in ojs.parse_page(text)[0]:
            if r.deleted:
                headers.append((r.article, True, r.set_spec))
            elif r.article not in live:
                live.add(r.article)
                headers.append((r.article, False, r.set_spec))
    return identifiers_page(*headers)
