"""Queries are validated on the selected index's tokenizer, including export pins and CLI saves."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.query.parser import parse

from tests.contract.conftest import build, make_app, point_current
from tests.corpus import Rec


@pytest.fixture
def versions(tmp_path: Path) -> tuple[Path, str, str]:
    data = tmp_path / "data"
    corpus = [Rec("fx:9001", "alpha trust", "trust", year=2020)]
    old = build(corpus, data / "snapshots", "snap", data / "indexes", tokenizer_version="2")
    new = build(corpus, data / "snapshots", "snap", data / "indexes", tokenizer_version="3")
    point_current(data, new)
    return data, old, new


def test_pinned_export_validates_with_the_target_tokenizer(versions: tuple[Path, str, str]) -> None:
    data, old, new = versions
    with TestClient(make_app(data)) as client:
        accepted = client.get(
            "/api/v1/export", params={"q": "＼alpha", "format": "jsonl", "index_version": old}
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.headers["x-tokenizer-version"] == "2"
        assert [json.loads(line)["id"] for line in accepted.text.splitlines()] == ["op:iclr:2020:Fx9001"]
        refused = client.get(
            "/api/v1/export", params={"q": "＼alpha", "format": "jsonl", "index_version": new}
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "PARSE_EMPTY_TERM"


@pytest.mark.parametrize("command", ["search", "export", "record"])
def test_cli_validates_with_the_target_tokenizer(
    versions: tuple[Path, str, str], command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    data, old, new = versions
    for version, expected in ((old, 0), (new, 1)):
        args = {
            "search": ["search", "＼alpha", "--ids"],
            "export": ["export", "＼alpha", "--format", "jsonl"],
            "record": ["record", "save", "＼alpha", "--json"],
        }[command]
        assert cli.main(["--data-dir", str(data), *args, "--index", version]) == expected
        out, err = capsys.readouterr()
        if expected:
            assert "PARSE_EMPTY_TERM" in err and not out
        else:
            assert "PARSE_EMPTY_TERM" not in err
            if command == "search":
                assert out.strip() == "op:iclr:2020:Fx9001"
            elif command == "export":
                assert json.loads(out)["id"] == "op:iclr:2020:Fx9001"
            else:
                body = json.loads(out)
                assert body["total"] == 1 and body["tokenizer_version"] == "2"


@pytest.mark.parametrize(
    ("version", "value", "canonical"),
    [
        ("2", "＼ICLR", "venue:ICLR"),
        ("2", "＼textbf{ICLR}", None),
        ("3", "＼ICLR", None),
        ("3", "＼textbf{ICLR}", "venue:ICLR"),
    ],
)
def test_source_aliases_follow_the_query_tokenizer(version: str, value: str, canonical: str | None) -> None:
    result = parse(f"source:{value}", "scholar", version)
    assert result.canonical == (
        f"({canonical} AND track:(datasets_benchmarks OR main OR position) AND status:accepted)"
        if canonical
        else None
    )
    if canonical is None:
        assert [e.code for e in result.errors] == ["FIELD_UNKNOWN_VALUE"]


def test_parse_filter_edits_follow_the_served_tokenizer(versions: tuple[Path, str, str]) -> None:
    data, old, _ = versions
    point_current(data, old)
    with TestClient(make_app(data)) as client:
        response = client.post("/api/v1/parse", json={"q": "＼alpha year:2020", "mode": "native"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert not body["errors"]
        assert all(clause["toggleable"] and clause["reason"] is None for clause in body["filters"].values())


def test_pinned_export_charges_target_verification_once(versions: tuple[Path, str, str]) -> None:
    data, old, _ = versions
    app = make_app(
        data,
        max_verified_clauses=1,
        rate_limit=RateLimit(
            capacity=3,
            refill_per_second=0.000001,
            export_weight=1,
            verified_weight=2,
            verify_token_ms=1_000_000,
        ),
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/export",
            params={
                "q": '＼alpha AND "trust trust*"',
                "format": "jsonl",
                "index_version": old,
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["x-total"] == "0"
        # The verified admission cost is two total tokens (including the base); one search token remains.
        assert [client.get("/api/v1/search", params={"q": "trust"}).status_code for _ in range(2)] == [
            200,
            429,
        ]


def test_export_length_precedes_pin_and_pin_precedes_semantics(versions: tuple[Path, str, str]) -> None:
    data, _, _ = versions
    with TestClient(make_app(data)) as client:
        for q, code, status in [
            ("a" * 2001, "PARSE_TOO_LONG", 422),
            ("＼alpha", "API_INDEX_VERSION_UNAVAILABLE", 409),
        ]:
            response = client.get(
                "/api/v1/export", params={"q": q, "format": "jsonl", "index_version": "0" * 12}
            )
            assert response.status_code == status
            assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("args", [["search"], ["export", "--format", "jsonl"], ["record", "save"]])
def test_cli_length_precedes_missing_index(
    args: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command = [*args[:2], "a" * 2001, *args[2:]] if args[0] == "record" else [args[0], "a" * 2001, *args[1:]]
    assert cli.main(["--data-dir", str(tmp_path / "absent"), *command]) == 1
    out, err = capsys.readouterr()
    assert not out and "PARSE_TOO_LONG" in err


@pytest.mark.parametrize(
    ("version", "value", "warns"),
    [
        ("2", "＼ICLR", True),
        ("2", "＼textbf{ICLR}", False),
        ("3", "＼ICLR", False),
        ("3", "＼textbf{ICLR}", True),
    ],
)
def test_source_scope_warning_uses_the_query_tokenizer(version: str, value: str, warns: bool) -> None:
    result = parse(f"source:ICML OR {value}", "scholar", version)
    assert ("WARN_FILTER_SCOPE" in [w.code for w in result.warnings]) is warns
