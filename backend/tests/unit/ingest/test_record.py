"""PaperRecord, Claim and content_hash (spec 01 §Record schema; record-schema skill; task-018)."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from openproceedings.ingest.record import (
    DBLP_YEARS,
    DERIVED,
    DOI_YEARS,
    RECORD_SCHEMA_VERSION,
    Claim,
    PaperRecord,
    Urls,
    abstract_text,
    content_hash,
    controls_evidence,
    title_text,
)
from openproceedings.ingest.snapshot import record_line
from openproceedings.query.normalize import normalize
from pydantic import ValidationError

FETCHED = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def claim(field: str, value: Any, source: str = "openreview_v2", **kw: Any) -> Claim:
    return Claim(
        field=field,
        value=value,
        source=source,
        url=kw.get("url"),
        fetched_at=FETCHED,
        evidence=kw.get("evidence"),
    )  # type: ignore[arg-type]


def record(**overrides: Any) -> PaperRecord:
    fields: dict[str, Any] = {
        "id": "op:iclr:2024:iilhN2MycO",
        "title": "Trust Calibration in LLMs",
        "abstract": "We study trust.",
        "authors": ("A. Author", "B. Author"),
        "venue": "ICLR",
        "year": 2024,
        "track": "main",
        "status": "accepted",
        "presentation": None,
        "venue_id_raw": "ICLR.cc/2024/Conference",
        "urls": Urls(forum="https://openreview.net/forum?id=iilhN2MycO"),
        "keywords": ("trust",),
        "provenance": (claim("status", "accepted", evidence="venueid=ICLR.cc/2024/Conference"),),
    }
    fields.update(overrides)
    return PaperRecord.build(**fields)


def test_build_computes_the_hash() -> None:
    r = record()
    assert r.content_hash == content_hash(
        title=r.title, abstract=r.abstract, venue=r.venue, year=r.year, track=r.track, status=r.status
    )


def test_hash_is_sha256_of_canonical_json_of_the_searchable_and_filterable_fields() -> None:
    r = record(title="Trüst", abstract=None)
    body = {
        "abstract": None,
        "status": "accepted",
        "title": "Trüst",
        "track": "main",
        "venue": "ICLR",
        "year": 2024,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert r.content_hash == hashlib.sha256(canonical).hexdigest()


def test_hash_ignores_provenance_urls_keywords_presentation_authors_and_venue_id_raw() -> None:
    base = record()
    other = record(
        authors=("Someone Else",),
        venue_id_raw=None,
        provenance=(claim("status", "accepted"), claim("title", "x", "neurips_proceedings")),
        urls=Urls(pdf="https://x.pdf"),
        keywords=("other",),
        presentation="oral",
    )
    assert base.content_hash == other.content_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Other"),
        ("abstract", "Other."),
        ("track", "workshop"),
        ("status", "rejected"),
        ("year", 2023),
    ],
)
def test_hash_changes_with_every_covered_field(field: str, value: Any) -> None:
    changed = {field: value}
    if field == "year":
        changed["id"] = "op:iclr:2023:iilhN2MycO"
    assert record(**changed).content_hash != record().content_hash


def test_a_stale_hash_is_rejected_on_load() -> None:
    data = record().model_dump(exclude={*DERIVED})
    data["title"] = "Tampered"
    with pytest.raises(ValidationError, match="content_hash"):
        PaperRecord.model_validate(data)


@pytest.mark.parametrize("fake", ["pending", "0" * 64, "", "ABC"])
def test_stored_data_can_never_ask_for_a_new_hash(fake: str) -> None:
    line = (
        record()
        .model_dump_json(exclude={*DERIVED})
        .replace(record().content_hash, fake)
        .replace("Trust Calibration", "Tampered")
    )
    with pytest.raises(ValidationError):
        PaperRecord.model_validate_json(line)


def test_a_four_character_native_id_is_a_forum_id() -> None:
    assert record(id="op:iclr:2024:abcd").forum_id == "abcd"


def test_round_trips_through_json() -> None:
    r = record()
    assert PaperRecord.model_validate_json(r.model_dump_json(exclude={*DERIVED})) == r


INVALID: list[tuple[str, dict[str, Any]]] = [
    ("id scheme", {"id": "iclr:2024:x"}),
    ("id venue must match", {"id": "op:icml:2024:iilhN2MycO"}),
    ("id year must match", {"id": "op:iclr:2023:iilhN2MycO"}),
    ("id venue is lower-case", {"id": "op:ICLR:2024:iilhN2MycO"}),
    ("scholar snippet in abstract", {"abstract": "We study trust in large …"}),
    ("empty abstract (use None)", {"abstract": ""}),
    ("empty title", {"title": " "}),
    ("title not whitespace-collapsed", {"title": "Trust  in\nAI"}),
    ("unknown venue", {"venue": "ACL"}),
    ("unknown track", {"track": "tutorial"}),
    ("unknown status", {"status": "maybe"}),
    ("unknown presentation", {"presentation": "keynote"}),
    ("year out of range", {"year": 99, "id": "op:iclr:99:iilhN2MycO"}),
    ("id year zero-padded", {"id": "op:iclr:02024:iilhN2MycO"}),
    ("native id with a space", {"id": "op:iclr:2024:iilh N2MycO"}),
    ("native id with a colon", {"id": "op:iclr:2024:a:b"}),
    ("native id too short", {"id": "op:iclr:2024:ab"}),
    ("pmlr id on a non-ICML record", {"id": "op:iclr:2024:pmlr-v202-foo"}),
    ("nips id that isn't a hash", {"id": "op:neurips:2023:nips-zzz", "venue": "NeurIPS", "year": 2023}),
    (
        "iclr id on a NeurIPS record",
        {"id": "op:neurips:2024:iclr-0123456789abcdef0123456789abcdef", "venue": "NeurIPS"},
    ),
    ("whitespace abstract", {"abstract": "  "}),
    ("empty title", {"title": ""}),
    ("snippet at the start", {"abstract": "… we study trust"}),
    ("year below 1000", {"year": 999, "id": "op:iclr:0999:iilhN2MycO"}),
    ("year as a string", {"year": "2024"}),
    ("lone surrogate", {"title": "Trust \ud800"}),
    ("lone surrogate in authors", {"authors": ("a\ud800",)}),
    ("lone surrogate in keywords", {"keywords": ("a\ud800",)}),
    ("lone surrogate in venue_id_raw", {"venue_id_raw": "a\ud800"}),
    ("control character in the title", {"title": "Trust\x00AI"}),
    ("abstract with trailing whitespace", {"abstract": "We study trust.\n"}),
    ("snippet ending before whitespace", {"abstract": "We study …\n"}),
    (
        "nips hash with a tail",
        {"id": "op:neurips:2024:nips-0123456789abcdef0123456789abcdefx", "venue": "NeurIPS"},
    ),
    (
        "nips hash of 31 digits",
        {"id": "op:neurips:2024:nips-0123456789abcdef0123456789abcde", "venue": "NeurIPS"},
    ),
    ("iclr id that isn't a hash", {"id": "op:iclr:2024:iclr-zzz"}),
    ("pmlr id without a volume number", {"id": "op:icml:2024:pmlr-vX-foo", "venue": "ICML"}),
    ("native id of three characters", {"id": "op:iclr:2024:abc"}),
    ("native id of only punctuation", {"id": "op:iclr:2024:----"}),
    ("native id over 64 characters", {"id": "op:iclr:2024:" + "a" * 65}),
    ("full-width year digits", {"id": "op:iclr:２０２４:iilhN2MycO"}),
]


@pytest.mark.parametrize(("why", "overrides"), INVALID, ids=[w for w, _ in INVALID])
def test_invalid_records_cannot_be_built(why: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        record(**overrides)


def test_an_extra_field_is_rejected() -> None:
    data = record().model_dump(exclude={*DERIVED})
    data["source"] = "x"
    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


def test_valid_native_id_forms() -> None:
    assert record(id="op:iclr:2024:Ab_c-12").forum_id == "Ab_c-12"
    icml = record(id="op:icml:2024:pmlr-v235-smith24a", venue="ICML")
    assert icml.forum_id is None and icml.native == "pmlr-v235-smith24a"
    assert record(id="op:neurips:2024:nips-" + "a" * 32, venue="NeurIPS").forum_id is None
    assert record(id="op:iclr:2024:iclr-" + "0" * 32).forum_id is None


def test_a_real_abstract_may_contain_an_ellipsis() -> None:
    assert record(abstract="for inputs x₁, …, x_n we show").abstract == "for inputs x₁, …, x_n we show"


@pytest.mark.parametrize(
    "missing", ["id", "title", "abstract", "authors", "venue", "year", "track", "status"]
)
def test_every_required_field_is_required(missing: str) -> None:
    data = record().model_dump(exclude={*DERIVED})
    del data[missing]
    with pytest.raises(ValidationError) as err:
        PaperRecord.model_validate(data)
    assert any(e["loc"] == (missing,) and e["type"] == "missing" for e in err.value.errors())


def test_defaults_for_optional_fields() -> None:
    minimal = PaperRecord.build(
        id="op:iclr:2024:iilhN2MycO", title="T", abstract=None, authors=(), venue="ICLR", year=2024,
        track="main", status="accepted",
    )  # fmt: skip
    assert (
        minimal.urls,
        minimal.venue_id_raw,
        minimal.presentation,
        minimal.keywords,
        minimal.provenance,
    ) == (Urls(), None, None, (), ())


def test_model_copy_revalidates_and_rehashes() -> None:
    r = record()
    changed = r.model_copy(update={"title": "Other"})
    assert changed.content_hash == record(title="Other").content_hash != r.content_hash
    with pytest.raises(ValidationError):
        r.model_copy(update={"venue": "ACL", "id": "garbage"})


def test_records_are_hashable() -> None:
    assert len({record(), record()}) == 1


def test_records_are_frozen() -> None:
    with pytest.raises(ValidationError):
        record().title = "x"  # type: ignore[misc]


def test_claims_and_urls_forbid_extras_and_are_frozen() -> None:
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="ris", fetched_at=FETCHED, extra=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Urls(foo="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Urls().pdf = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "source", ["openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "ris"]
)
def test_every_source_can_claim(source: str) -> None:
    assert claim("title", "x", source).source == source


@pytest.mark.parametrize(
    ("field", "value"),
    [("year", "2024"), ("year", True), ("authors", "A. Author"), ("keywords", "trust"), ("title", 5), ("title", None),
     ("title", ("a",)), ("title", "a\ud800")],
)  # fmt: skip
def test_a_claim_value_must_fit_its_field(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        claim(field, value)


def test_claim_text_must_be_valid_unicode_and_times_real_datetimes() -> None:
    with pytest.raises(ValidationError):
        claim("title", "x", url="https://x/\ud800")
    with pytest.raises(ValidationError):
        claim("title", "x", evidence="\ud800")
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="ris", fetched_at="2026-09-20T12:00:00Z")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Urls(pdf="\ud800")


def test_claim_fields_and_values_are_strict() -> None:
    with pytest.raises(ValidationError):
        claim("titel", "x")  # a misspelt field would silently match nothing
    with pytest.raises(ValidationError):
        claim("year", True)  # no bool -> int coercion
    with pytest.raises(ValidationError):
        claim("year", 1.0)


def test_one_claim_per_field_and_source_in_a_fixed_order() -> None:
    a, b = claim("title", "A"), claim("status", "accepted", url="https://x")
    assert record(provenance=(a, b)) == record(provenance=(b, a))  # order never matters
    with pytest.raises(ValidationError):
        record(provenance=(claim("title", "A"), claim("title", "B")))  # same field and source twice
    mixed = record(provenance=(claim("title", "A", url="https://x"), claim("title", "B", "pmlr")))
    assert [c.source for c in mixed.provenance] == ["openreview_v2", "pmlr"]  # None and str urls sort


def test_claims_are_frozen_hashable_and_need_an_aware_fetch_time() -> None:
    c = claim("title", "Trust")
    assert {c, claim("title", "Trust")} == {c}  # hashable, equal by value
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="openreview_v2", fetched_at=datetime(2026, 1, 1))  # naive
    with pytest.raises(ValidationError):
        Claim(field="title", value="x", source="scholar", fetched_at=FETCHED)  # type: ignore[arg-type]
    assert claim("authors", ("A", "B")).value == ("A", "B")


def test_fetch_times_are_normalised_to_utc() -> None:
    est = timezone(timedelta(hours=-4))
    c = Claim(field="title", value="x", source="pmlr", fetched_at=datetime(2026, 9, 20, 8, 0, tzinfo=est))
    assert c.fetched_at == FETCHED and c.fetched_at.utcoffset() == timedelta(0)


def test_claims_for_a_field() -> None:
    r = record(provenance=(claim("title", "A"), claim("status", "accepted"), claim("title", "B", "pmlr")))
    assert [c.value for c in r.claims("title")] == ["A", "B"]
    assert isinstance(r.claims("title"), tuple)


@pytest.mark.parametrize(
    "bad",
    [
        *("\n", "\r", "\x85", "\u2028", "\u2029", "\x00", " ", "\t", "\x9b"),  # line breaks, controls
        *("\xa0", "\u1680", "\u2000", "\u3000"),  # whitespace that isn't a plain space
        *("\u202e", "\u2066", "\u061c", "\u200b", "\u2060", "\ufeff", "\xad", "\U000e0001"),  # format (Cf)
    ],
)
@pytest.mark.parametrize("field", ["forum", "pdf", "proceedings", "doi"])
def test_a_url_with_a_line_break_or_control_char_is_refused(field: str, bad: str) -> None:
    # a newline in a URL would be written into an RIS/BibTeX line and could forge a record, and a format
    # character could make it read as another (security gate); the value holds nothing else to refuse
    from openproceedings.ingest.record import Urls, is_url

    value = f"10.1234/ab{bad}cd" if field == "doi" else f"https://example.org/a{bad}b"
    with pytest.raises(ValueError):
        Urls(**{field: value})
    assert field == "doi" or not is_url(value)


def test_a_url_carrying_an_ris_line_is_refused() -> None:
    from openproceedings.ingest.record import is_url

    assert not is_url("https://example.org/a\nER  - ")


def test_urls_must_be_http_and_dois_well_formed() -> None:
    from openproceedings.ingest.record import Urls

    assert Urls(forum="https://openreview.net/forum?id=AbCd", doi="10.1000.10/x.y").forum
    for bad in (
        {"pdf": "javascript:alert(1)"},
        {"proceedings": "ftp://x/y"},
        {"doi": "doi:10.1/x"},
        {"forum": "https://"},
        {"forum": "https://@"},
        {"forum": "https://:80"},
    ):
        with pytest.raises(ValueError):
            Urls(**bad)  # type: ignore[arg-type]


# TASK-112: `venue_name`, the conference's full name the paper page shows (spec 04 §Exports, venue string), pinned
# by hand for every venue-year the corpus can hold (decision-013: every venue crawled from 2013), apart from
# `vocab.CONFERENCES`. NeurIPS was NIPS until 2017.
VENUE_NAMES: dict[tuple[str, int], str] = {
    ("NeurIPS", 2013): "Conference on Neural Information Processing Systems (NIPS 2013)",
    ("NeurIPS", 2014): "Conference on Neural Information Processing Systems (NIPS 2014)",
    ("NeurIPS", 2015): "Conference on Neural Information Processing Systems (NIPS 2015)",
    ("NeurIPS", 2016): "Conference on Neural Information Processing Systems (NIPS 2016)",
    ("NeurIPS", 2017): "Conference on Neural Information Processing Systems (NIPS 2017)",
    ("NeurIPS", 2018): "Conference on Neural Information Processing Systems (NeurIPS 2018)",
    ("NeurIPS", 2019): "Conference on Neural Information Processing Systems (NeurIPS 2019)",
    ("NeurIPS", 2020): "Conference on Neural Information Processing Systems (NeurIPS 2020)",
    ("NeurIPS", 2021): "Conference on Neural Information Processing Systems (NeurIPS 2021)",
    ("NeurIPS", 2022): "Conference on Neural Information Processing Systems (NeurIPS 2022)",
    ("NeurIPS", 2023): "Conference on Neural Information Processing Systems (NeurIPS 2023)",
    ("NeurIPS", 2024): "Conference on Neural Information Processing Systems (NeurIPS 2024)",
    ("NeurIPS", 2025): "Conference on Neural Information Processing Systems (NeurIPS 2025)",
    ("NeurIPS", 2026): "Conference on Neural Information Processing Systems (NeurIPS 2026)",
    ("ICLR", 2013): "International Conference on Learning Representations (ICLR 2013)",
    ("ICLR", 2014): "International Conference on Learning Representations (ICLR 2014)",
    ("ICLR", 2015): "International Conference on Learning Representations (ICLR 2015)",
    ("ICLR", 2016): "International Conference on Learning Representations (ICLR 2016)",
    ("ICLR", 2017): "International Conference on Learning Representations (ICLR 2017)",
    ("ICLR", 2018): "International Conference on Learning Representations (ICLR 2018)",
    ("ICLR", 2019): "International Conference on Learning Representations (ICLR 2019)",
    ("ICLR", 2020): "International Conference on Learning Representations (ICLR 2020)",
    ("ICLR", 2021): "International Conference on Learning Representations (ICLR 2021)",
    ("ICLR", 2022): "International Conference on Learning Representations (ICLR 2022)",
    ("ICLR", 2023): "International Conference on Learning Representations (ICLR 2023)",
    ("ICLR", 2024): "International Conference on Learning Representations (ICLR 2024)",
    ("ICLR", 2025): "International Conference on Learning Representations (ICLR 2025)",
    ("ICLR", 2026): "International Conference on Learning Representations (ICLR 2026)",
    ("ICML", 2013): "International Conference on Machine Learning (ICML 2013)",
    ("ICML", 2014): "International Conference on Machine Learning (ICML 2014)",
    ("ICML", 2015): "International Conference on Machine Learning (ICML 2015)",
    ("ICML", 2016): "International Conference on Machine Learning (ICML 2016)",
    ("ICML", 2017): "International Conference on Machine Learning (ICML 2017)",
    ("ICML", 2018): "International Conference on Machine Learning (ICML 2018)",
    ("ICML", 2019): "International Conference on Machine Learning (ICML 2019)",
    ("ICML", 2020): "International Conference on Machine Learning (ICML 2020)",
    ("ICML", 2021): "International Conference on Machine Learning (ICML 2021)",
    ("ICML", 2022): "International Conference on Machine Learning (ICML 2022)",
    ("ICML", 2023): "International Conference on Machine Learning (ICML 2023)",
    ("ICML", 2024): "International Conference on Machine Learning (ICML 2024)",
    ("ICML", 2025): "International Conference on Machine Learning (ICML 2025)",
    ("ICML", 2026): "International Conference on Machine Learning (ICML 2026)",
    ("AAAI", 1980): "AAAI Conference on Artificial Intelligence (AAAI 1980)",
    ("AAAI", 2026): "AAAI Conference on Artificial Intelligence (AAAI 2026)",
    ("AIES", 2018): "AAAI/ACM Conference on AI, Ethics, and Society (AIES 2018)",
    ("FAccT", 2018): "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2018)",
    ("FAccT", 2020): "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2020)",
    ("FAccT", 2021): "ACM Conference on Fairness, Accountability, and Transparency (FAccT 2021)",
    ("IASEAI", 2026): "International Association for Safe and Ethical AI Conference (IASEAI 2026)",
}


@pytest.mark.parametrize(("venue", "year"), sorted(VENUE_NAMES))
def test_venue_name_per_venue_year(venue: str, year: int) -> None:
    native = {"NeurIPS": "nips-" + "a" * 32, "ICML": "pmlr-v1-x", "ICLR": "iilhN2MycO"}.get(
        venue, "iilhN2MycO" if venue == "FAccT" else "ojs-28000"
    )  # FAccT has no ojs source: its ids are OpenReview-style until its own source lands
    r = record(id=f"op:{venue.lower()}:{year}:{native}", venue=venue, year=year)
    assert r.venue_name == VENUE_NAMES[venue, year]
    assert r.model_dump(mode="json")["venue_name"] == VENUE_NAMES[venue, year]  # sent with the record


def test_venue_name_is_derived_never_stored_or_hashed() -> None:
    """Computed from `venue` and `year` (`DERIVED`): a snapshot line never holds it, so snapshots, their hashes and
    the record schema version are unchanged. It is output only: stored data that names it is refused, as any
    other extra field is, so it can never disagree with the record's venue and year."""
    r = record()
    assert "venue_name" not in json.loads(record_line(r))
    assert PaperRecord.model_validate_json(record_line(r)) == r
    assert r.model_copy(update={"title": "Other"}).venue_name == r.venue_name
    moved = r.model_copy(update={"year": 2025, "id": "op:iclr:2025:iilhN2MycO"})  # recomputed, not carried
    assert moved.venue_name == "International Conference on Learning Representations (ICLR 2025)"
    assert "venue_name" not in PaperRecord.model_fields and frozenset({"venue_name"}) == DERIVED
    with pytest.raises(ValidationError, match="venue_name"):
        PaperRecord.model_validate(r.model_dump())


# --- control characters in a title (TASK-180) ----------------------------------------------------------------

TITLE_TEXT = [
    # raw, stored, control characters replaced
    ("A SPEC\x02TRUM FROM LOGIC", "A SPEC TRUM FROM LOGIC", 1),  # ICLR 2026 `xHMNX3l8rx`: U+0002, twice in it
    ("Aquifers in Ibadan, Nigeria\x00", "Aquifers in Ibadan, Nigeria", 1),  # NeurIPS 2026 `KlvYZ17FPi`
    ("INDUC\x02TIVE \x02 KNOWLEDGE", "INDUC TIVE KNOWLEDGE", 2),  # a run of spaces and controls is one space
    ("a\x7fb\x85c\x9fd", "a b c d", 2),  # DEL and C1 too; U+0085 is whitespace, which always became a space
    ("Details  through\x0b Chain\tof\nManipulations", "Details through Chain of Manipulations", 0),
    ("Trust in AI", "Trust in AI", 0),
    ("café​—τ $x^2$", "café​—τ $x^2$", 0),  # nothing but controls and whitespace is touched
    ("\x00\x02", "", 2),  # nothing left: the importer has no title
]


@pytest.mark.parametrize(("raw", "stored", "replaced"), TITLE_TEXT)
def test_a_control_character_in_a_title_becomes_a_space(raw: str, stored: str, replaced: int) -> None:
    assert title_text(raw) == (stored, replaced)
    assert title_text(stored) == (stored, 0)  # idempotent
    if stored:
        assert record(title=stored).title == stored  # the record model accepts it


_CONTROLS = "\x00\x02\x08\x0b\x1c\x7f\x85\x9f\n"


@given(st.text(alphabet=st.sampled_from([*"abAB12 -\\{}^_.,é́​", *_CONTROLS]), max_size=20))
def test_the_stored_title_keeps_the_raw_titles_tokens(raw: str) -> None:
    """The tokenizer reads a control character as a separator, so replacing it with a space changes no token
    (token-contract). `$` is left out of the alphabet: the one exception is below."""
    stored, _ = title_text(raw)
    assert normalize(stored) == normalize(raw)
    assert not any(unicodedata.category(c) == "Cc" for c in stored) and stored == " ".join(stored.split())


@given(st.text(alphabet=st.sampled_from([*"abAB12 -\\{}^_.,é́​$", *_CONTROLS]), max_size=20))
def test_with_math_the_stored_title_keeps_the_raw_titles_tokens_unless_a_control_touches_a_dollar(
    raw: str,
) -> None:
    """The property above with `$` in the alphabet: the tokens are the raw title's whenever no control character
    is next to a `$` (the exception below is the only one)."""
    controls = {i for i, c in enumerate(raw) if unicodedata.category(c) == "Cc" and not c.isspace()}
    assume(not any(raw[j] == "$" for i in controls for j in (i - 1, i + 1) if 0 <= j < len(raw)))
    stored, _ = title_text(raw)
    assert normalize(stored) == normalize(raw)


def test_a_control_character_beside_a_math_delimiter_is_the_one_token_exception() -> None:
    """A space just inside `$…$` stops it reading as math, so there the stored title's tokens differ from the raw
    title's: stated in spec 01, pinned here so a tokenizer change that moves it is seen."""
    raw = "$\\tau\x02$-bench"
    stored, replaced = title_text(raw)
    assert (stored, replaced) == ("$\\tau $-bench", 1)
    assert (normalize(raw), normalize(stored)) == (["τ", "bench"], ["bench"])


# --- control characters in an abstract (TASK-188, decision-044) -----------------------------------------------

ABSTRACT_TEXT = [
    # raw, stored, control characters replaced
    (
        "the LiDAR modal\x02ity is quanti\x02fying",
        "the LiDAR modal ity is quanti fying",
        2,
    ),  # a line-break hyphen
    ("500x\x02 longer and 6\x02x over", "500x longer and 6 x over", 2),  # U+0002 for a lost `×`
    ("such as\x0f-greedy, \u2200\x0f > 0", "such as -greedy, \u2200 > 0", 2),  # U+000F for a lost `ε`
    ("back\x08space\x00", "back space", 2),
    ("a\x7fb\x85c\x9fd", "a b c d", 2),  # DEL and C1; U+0085 is whitespace, which always became a space
    ("We study  trust.\nIn\tdepth.", "We study trust. In depth.", 0),  # whitespace collapsed, as importers do
    ("caf\u00e9\u200b\u2014$x^2$ \u2026 done", "caf\u00e9\u200b\u2014$x^2$ \u2026 done", 0),
    ("\x00\x02 ", "", 2),  # nothing left: the importer has no abstract
]


@pytest.mark.parametrize(("raw", "stored", "replaced"), ABSTRACT_TEXT)
def test_a_control_character_in_an_abstract_becomes_a_space(raw: str, stored: str, replaced: int) -> None:
    assert abstract_text(raw) == (stored, replaced)
    assert abstract_text(stored) == (stored, 0)  # idempotent
    if stored:
        assert record(abstract=stored).abstract == stored  # the record model accepts it


def test_an_abstract_with_a_line_break_control_keeps_its_tokens_and_still_misses_the_whole_word() -> None:
    """decision-044: the tokenizer already split `quanti\x02fying`, so the stored abstract's tokens are the raw
    one's and no search result changes; a search for `quantifying` still misses it (spec 01 states it)."""
    raw = "Quanti\x02fying the LiDAR modal\x02ity of 500x\x02 longer runs"
    stored, replaced = abstract_text(raw)
    assert replaced == 3 and normalize(stored) == normalize(raw)
    assert normalize(stored) == [
        "quanti",
        "fying",
        "the",
        "lidar",
        "modal",
        "ity",
        "of",
        "500x",
        "longer",
        "runs",
    ]
    assert "quantifying" not in normalize(stored)


@given(st.text(alphabet=st.sampled_from([*"abAB12 -\\{}^_.,\u00e9\u0301\u200b", *_CONTROLS]), max_size=40))
def test_the_stored_abstract_keeps_the_raw_abstracts_tokens(raw: str) -> None:
    """The title property, for abstracts (decision-044): no token changes, no control character is left."""
    stored, replaced = abstract_text(raw)
    assert normalize(stored) == normalize(raw)
    assert not any(unicodedata.category(c) == "Cc" for c in stored) and stored == " ".join(stored.split())
    assert replaced == sum(unicodedata.category(c) == "Cc" and not c.isspace() for c in raw)


@pytest.mark.parametrize(
    ("evidence", "replaced", "said"),
    [
        ("content.abstract", 0, "content.abstract"),
        ("content.abstract", 1, "content.abstract (1 control character replaced by a space)"),
        ("p.paper-abstract", 3, "p.paper-abstract (3 control characters replaced by a space)"),
    ],
)
def test_a_claims_evidence_says_how_many_control_characters_were_replaced(
    evidence: str, replaced: int, said: str
) -> None:
    assert controls_evidence(evidence, replaced) == said


# --- the `ojs` source, the `ojs-<article id>` native id, AAAI-only tracks, schema 6 (decision-049) ---


def _ojs(
    venue: str = "AAAI", year: int = 2024, track: str = "main", native: str = "ojs-28000"
) -> PaperRecord:
    return PaperRecord.build(
        id=f"op:{venue.lower()}:{year}:{native}", title="A paper", abstract=None, authors=("A. Author",),
        venue=venue, year=year, track=track, status="accepted",
    )  # fmt: skip


@pytest.mark.parametrize(("venue", "year"), [("AAAI", 2010), ("AIES", 2024), ("IASEAI", 2026)])
def test_ojs_native_id_is_valid_for_its_venues(venue: str, year: int) -> None:
    assert _ojs(venue, year).native == "ojs-28000"


@pytest.mark.parametrize(("venue", "year"), [("ICML", 2024), ("FAccT", 2024)])
def test_ojs_native_id_is_refused_for_another_venue(venue: str, year: int) -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _ojs(venue, year)


@pytest.mark.parametrize("native", ["ojs-", "ojs-12a", "ojs-1-2"])
def test_malformed_ojs_native_id_is_refused(native: str) -> None:
    with pytest.raises(ValidationError):
        _ojs(native=native)


@pytest.mark.parametrize("track", ["iaai", "eaai"])
def test_iaai_and_eaai_are_aaai_only(track: str) -> None:
    assert _ojs(track=track).track == track
    with pytest.raises(ValidationError, match="only an AAAI track"):
        _ojs("AIES", 2024, track=track)


@pytest.mark.parametrize("track", ["student_abstract", "consortium", "demo"])
def test_other_new_tracks_are_open_to_every_venue(track: str) -> None:
    assert _ojs("AIES", 2025, track=track).track == track


def _rec(rid: str, venue: str, year: int, track: str = "main") -> PaperRecord:
    return PaperRecord.build(id=rid, title="A paper", abstract=None, authors=("A. Author",), venue=venue,
                             year=year, track=track, status="accepted")  # fmt: skip


def test_schema_is_7() -> None:
    assert RECORD_SCHEMA_VERSION == "7"


@pytest.mark.parametrize(
    ("venue", "year"), [("FAccT", 2019), ("FAccT", 2026), ("AIES", 2018), ("AIES", 2023)]
)
def test_doi_native_id_is_valid_for_the_acm_venue_years(venue: str, year: int) -> None:
    r = _rec(f"op:{venue.lower()}:{year}:doi-3593013.3594011", venue, year)
    assert r.native == "doi-3593013.3594011" and r.forum_id is None


@pytest.mark.parametrize(("venue", "year"), [("ICML", 2023), ("AAAI", 2023), ("AIES", 2024), ("FAccT", 2018)])
def test_doi_native_id_is_refused_outside_its_venue_years(venue: str, year: int) -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _rec(f"op:{venue.lower()}:{year}:doi-3593013.3594011", venue, year)


@pytest.mark.parametrize(
    "native",
    ["doi-", "doi-3593013", "doi-3593013.", "doi-3593013.3594011a", "doi-3593013.359.4011", "doi-x.1"],
)
def test_malformed_doi_native_id_is_refused(native: str) -> None:
    with pytest.raises(ValidationError):
        _rec(f"op:facct:2023:{native}", "FAccT", 2023)


@pytest.mark.parametrize(
    ("venue", "year", "ok"),
    [("AAAI", 1980, True), ("AAAI", 2008, True), ("AAAI", 2009, False), ("AAAI", 2010, False),
     ("ICML", 1988, True), ("ICML", 2012, True), ("ICML", 2013, False)],
)  # fmt: skip
def test_dblp_ids_are_icml_1988_2012_and_aaai_1980_2008(venue: str, year: int, ok: bool) -> None:
    rid = f"op:{venue.lower()}:{year}:dblp-Smith90"
    if ok:
        assert _rec(rid, venue, year).native == "dblp-Smith90"
    else:
        with pytest.raises(ValidationError, match="dblp ids are"):
            _rec(rid, venue, year)


def test_dblp_ids_are_refused_for_another_venue() -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _rec("op:aies:2018:dblp-Smith18", "AIES", 2018)


def test_the_year_tables_name_their_venues() -> None:
    assert set(DBLP_YEARS) == {"ICML", "AAAI"} and set(DOI_YEARS) == {"AIES", "FAccT"}
