"""The one Diagnostic shape and the code registry (error-diagnostics skill, spec 04 §Error handling)."""

import re
from pathlib import Path

import pytest
from openproceedings.diagnostics import Diagnostic, DiagnosticCode, OpenProceedingsError, http_status
from pydantic import ValidationError

SPEC = Path(__file__).resolve().parents[3] / "docs" / "specs" / "04-backend-api.md"


def spec_04_table() -> dict[str, int]:
    """Spec 04 §Error handling, the only table of HTTP statuses and API codes, read from the spec itself (a
    hand copy here could drift from both): each row's status and every `API_…` code it names."""
    section = SPEC.read_text(encoding="utf-8").split("## Error handling", 1)[1].split("\n## ", 1)[0]
    table: dict[str, int] = {}
    for row in section.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1].isdigit():
            for code in re.findall(r"`(API_[A-Z_]+)`", cells[2]):
                assert code not in table, f"{code} is in two rows of spec 04's table"
                table[code] = int(cells[1])
    return table


SPEC_04 = spec_04_table()


def test_the_spec_table_is_read() -> None:
    assert SPEC_04["API_BAD_PARAM"] == 422 and SPEC_04["API_BODY_TOO_LARGE"] == 413 and len(SPEC_04) >= 13


@pytest.mark.parametrize(("code", "status"), sorted(SPEC_04.items()))
def test_api_codes_map_to_spec_04_statuses(code: str, status: int) -> None:
    assert http_status(DiagnosticCode(code)) == status


def test_every_http_api_code_is_in_spec_04s_table() -> None:
    """Both ways: a registry code with an HTTP status that the table doesn't name is undocumented."""
    registry = {c.value: http_status(c) for c in DiagnosticCode if c.startswith("API_") and http_status(c)}
    assert registry == SPEC_04


def test_every_parse_code_is_422() -> None:
    parse = [c for c in DiagnosticCode if c.startswith("PARSE_")]
    assert parse
    assert all(http_status(c) == 422 for c in parse)


def test_replay_mismatch_is_a_log_code_not_an_http_error() -> None:
    assert http_status(DiagnosticCode.API_REPLAY_MISMATCH) is None


def test_codes_follow_area_snake_name() -> None:
    prefixes = ("PARSE_", "WILDCARD_", "FIELD_", "WARN_", "COMPAT_", "API_")
    for c in DiagnosticCode:
        assert c.value == c.name
        assert c.startswith(prefixes), c
        assert c == c.upper()


def test_codes_named_by_the_specs_exist() -> None:
    for name in (
        "WARN_NESTED_FILTER",
        "WARN_MIXED_AND_OR",
        "WARN_LOWERCASE_OPERATOR",
        "COMPAT_SOURCE_ALIAS",
        "COMPAT_POP_DOLLAR",
        "WILDCARD_STEM_TOO_SHORT",
        "WILDCARD_TOO_MANY_EXPANSIONS",
        "FIELD_UNKNOWN",
        "FIELD_UNKNOWN_VALUE",
        "FIELD_RANGE_INVERTED",
        "PARSE_UNBALANCED_PAREN",
        "PARSE_EMPTY_GROUP",
        "PARSE_ALL_NEGATIVE",
        "PARSE_UNTERMINATED_PHRASE",
        "PARSE_BAD_NEAR",
        "PARSE_WILDCARD_NOT_SUFFIX",
        "PARSE_EXPECTED_TERM",
        "PARSE_EMPTY_TERM",
        "PARSE_NESTED_FIELD",
        "PARSE_TOO_DEEP",
        "FIELD_FILTER_SYNTAX",
        "PARSE_WILDCARD_DETACHED",
        "PARSE_AMBIGUOUS_MINUS",
        "PARSE_STRAY_COLON",
        "PARSE_AMBIGUOUS_QUOTE",
        "PARSE_PAREN_TOUCHES_WORD",
        "PARSE_TOO_LONG",
        "FIELD_COMPAT_ONLY",
        "WARN_FILTER_SCOPE",
        "WARN_LOOKALIKE_OPERATOR",
        "WARN_SYMBOLS_DROPPED",
        "WARN_SOURCE_PARTIAL",
        "COMPAT_POP_PHRASE",
        "COMPAT_NO_STEMMING",
        "WARN_CJK_RUN",
        "WARN_SPELLED_GREEK",
        *SPEC_04,
    ):
        assert DiagnosticCode(name)


def test_diagnostic_is_frozen_and_strict() -> None:
    d = Diagnostic(
        code=DiagnosticCode.PARSE_EMPTY_GROUP, message="Empty group `()` — remove it.", span=(3, 5)
    )
    with pytest.raises(ValidationError):
        Diagnostic(code="NOT_A_CODE", message="x", span=None)
    with pytest.raises(ValidationError):
        Diagnostic(code=DiagnosticCode.PARSE_EMPTY_GROUP, message="x", span=None, extra_field=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        d.message = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("span", [(5, 3), (-1, 2)])
def test_span_is_a_half_open_non_negative_range(span: tuple[int, int]) -> None:
    with pytest.raises(ValidationError):
        Diagnostic(code=DiagnosticCode.PARSE_EMPTY_GROUP, message="x", span=span)


def test_zero_width_span_allowed_for_expected_here() -> None:
    assert Diagnostic(
        code=DiagnosticCode.PARSE_UNBALANCED_PAREN, message="Add `)` here.", span=(7, 7)
    ).span == (7, 7)


def test_message_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        Diagnostic(code=DiagnosticCode.PARSE_EMPTY_GROUP, message="  ", span=None)


def test_reading_is_set_exactly_on_warn_mixed_and_or() -> None:
    """TASK-099: a client can rely on `reading` being there on WARN_MIXED_AND_OR and nowhere else."""
    mixed = DiagnosticCode.WARN_MIXED_AND_OR
    assert Diagnostic(code=mixed, message="m", span=(0, 8), reading="(a b) OR c").reading == "(a b) OR c"
    assert Diagnostic(code=DiagnosticCode.WARN_CJK_RUN, message="m").reading is None
    with pytest.raises(ValidationError, match="needs `reading`"):
        Diagnostic(code=mixed, message="m", span=(0, 8))
    with pytest.raises(ValidationError, match="takes no `reading`"):
        Diagnostic(code=DiagnosticCode.WARN_CJK_RUN, message="m", reading="x")
    with pytest.raises(ValidationError, match="blank"):
        Diagnostic(code=mixed, message="m", span=(0, 8), reading="  ")


def test_typed_error_carries_a_code() -> None:
    err = OpenProceedingsError(DiagnosticCode.API_INDEX_NOT_LOADED, "No index is loaded yet.")
    assert err.code is DiagnosticCode.API_INDEX_NOT_LOADED
    assert "No index is loaded yet." in str(err)


def test_typed_error_survives_pickling() -> None:
    import pickle

    err = OpenProceedingsError(DiagnosticCode.API_INTERNAL, "worker failed")
    back = pickle.loads(pickle.dumps(err))
    assert back.code is DiagnosticCode.API_INTERNAL and back.message == "worker failed"


@pytest.mark.parametrize("span", [["1", 2], (True, 2), (1.0, 2)])
def test_span_is_strict_about_types(span: object) -> None:
    with pytest.raises(ValidationError):
        Diagnostic(code=DiagnosticCode.PARSE_EMPTY_GROUP, message="x", span=span)


def test_every_code_a_parse_can_return_as_an_error_is_a_422() -> None:
    from openproceedings.diagnostics import http_status

    for code in DiagnosticCode:
        if code.startswith(("PARSE_", "FIELD_", "WILDCARD_")):
            assert http_status(code) == 422, code
        if code.startswith(("WARN_", "COMPAT_")):
            assert http_status(code) is None, code  # warnings and notices never fail a request
