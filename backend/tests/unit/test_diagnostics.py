"""The one Diagnostic shape and the code registry (error-diagnostics skill, spec 04 §Error handling)."""

import pytest
from openproceedings.diagnostics import Diagnostic, DiagnosticCode, OpenProceedingsError, http_status
from pydantic import ValidationError

# Spec 04 §Error handling — the only table of HTTP statuses and API codes.
SPEC_04 = {
    "API_BAD_PARAM": 422,
    "API_PAPER_NOT_FOUND": 404,
    "API_RECORD_NOT_FOUND": 404,
    "API_INDEX_VERSION_UNAVAILABLE": 409,
    "API_RECORD_MISMATCH": 409,
    "API_RATE_LIMITED": 429,
    "API_INDEX_NOT_LOADED": 503,
    "API_INTERNAL": 500,
}


@pytest.mark.parametrize(("code", "status"), sorted(SPEC_04.items()))
def test_api_codes_map_to_spec_04_statuses(code: str, status: int) -> None:
    assert http_status(DiagnosticCode(code)) == status


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
