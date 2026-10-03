"""/api/v1 is released: a change to the contract is additive only (api-contract skill §Versioning rules; spec
04 §Conventions). `breaking_changes(old, new)` compares two OpenAPI documents by those rules, and the test
runs it from the last released contract, the snapshot on `origin/dev` (or `$OPENAPI_BASELINE_REF`), to the
committed one (skipped only where that ref isn't fetched; CI checks out with full history).

Breaking: a path, operation, parameter, response status, component schema or property removed; a
parameter or a request-body field made required (or a new required one); a type, format, pattern or bound
changed; a response field made optional or nullable; a value removed from an enum, or added to a closed one
(decision-009). Allowed: new paths, operations, optional parameters, response fields and schemas, and new
values in an open enum. `ALLOWED` lists each exception with the decision that allows it.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from openproceedings.api.openapi import OPEN_NOTE, REF, request_schemas

SNAPSHOT = Path(__file__).with_name("openapi.json")
REPO = Path(__file__).resolve().parents[3]
TEXT = frozenset({"description", "title", "examples", "readOnly"})  # documentation, not contract
# (schema.property, what): exceptions, each with its decision record
ALLOWED = {
    # decision-014: null only in answer to the new opt-in `replay=false` (TASK-091); never null otherwise
    ("RecordResponse.replay", "nullable"),
}


def _bare(schema: Any) -> Any:
    """`schema` without its documentation keys, recursively."""
    if isinstance(schema, dict):
        return {k: _bare(v) for k, v in schema.items() if k not in TEXT}
    if isinstance(schema, list):
        return [_bare(v) for v in schema]
    return schema


def _nullable_of(new: dict[str, Any], old: dict[str, Any]) -> bool:
    """Whether `new` is `old` or null (`anyOf: [old, {type: null}]`)."""
    options = new.get("anyOf")
    return (
        isinstance(options, list)
        and len(options) == 2
        and {"type": "null"} in [_bare(o) for o in options]
        and _bare(old) in [_bare(o) for o in options]
    )


def _compare(old: Any, new: Any, where: str, request: bool, out: list[tuple[str, str]]) -> None:
    if not isinstance(old, dict) or not isinstance(new, dict):
        if old != new:
            out.append((where, "changed"))
        return
    if "enum" in old:
        before, after = set(old["enum"]), set(new.get("enum", []))
        if not before <= after:
            out.append((where, "enum value removed"))
        elif after - before and OPEN_NOTE not in old.get("description", ""):
            out.append((where, "value added to a closed enum"))
        rest_old = {k: v for k, v in _bare(old).items() if k != "enum"}
        rest_new = {k: v for k, v in _bare(new).items() if k != "enum"}
        if rest_old != rest_new:
            out.append((where, "changed"))
        return
    if "properties" in old:
        props_old, props_new = old["properties"], new.get("properties", {})
        for name, schema in props_old.items():
            if name not in props_new:
                out.append((f"{where}.{name}", "removed"))
            else:
                _compare(schema, props_new[name], f"{where}.{name}", request, out)
        req_old, req_new = set(old.get("required", [])), set(new.get("required", []))
        if request:
            out += [(f"{where}.{n}", "made required") for n in sorted(req_new - req_old)]
        else:
            out += [(f"{where}.{n}", "made optional") for n in sorted(req_old - req_new)]
        rest = TEXT | {"properties", "required"}
        if {k: v for k, v in old.items() if k not in rest} != {k: v for k, v in new.items() if k not in rest}:
            out.append((where, "changed"))
        return
    if _bare(old) != _bare(new):
        out.append((where, "nullable" if not request and _nullable_of(new, old) else "changed"))


def breaking_changes(old: dict[str, Any], new: dict[str, Any]) -> list[tuple[str, str]]:
    """Every change from `old` to `new` that breaks a /api/v1 client, as (where, what), less `ALLOWED`."""
    out: list[tuple[str, str]] = []
    for path, ops in old["paths"].items():
        for method, op in ops.items():
            new_op = new["paths"].get(path, {}).get(method)
            where = f"{method.upper()} {path}"
            if new_op is None:
                out.append((where, "removed"))
                continue
            params_new = {(p["in"], p["name"]): p for p in new_op.get("parameters", [])}
            for p in op.get("parameters", []):
                q = params_new.get((p["in"], p["name"]))
                if q is None:
                    out.append((f"{where} {p['name']}", "removed"))
                    continue
                if q.get("required", False) and not p.get("required", False):
                    out.append((f"{where} {p['name']}", "made required"))
                _compare(p.get("schema", {}), q.get("schema", {}), f"{where} {p['name']}", True, out)
            for key, q in params_new.items():
                if q.get("required", False) and key not in {
                    (p["in"], p["name"]) for p in op.get("parameters", [])
                }:
                    out.append((f"{where} {key[1]}", "new required parameter"))
            for status in op.get("responses", {}):
                if status not in new_op.get("responses", {}):
                    out.append((f"{where} {status}", "response removed"))
    requests = request_schemas(old) | request_schemas(new)
    schemas_old, schemas_new = old["components"]["schemas"], new["components"]["schemas"]
    for name, schema in schemas_old.items():
        if name not in schemas_new:
            out.append((name, "removed"))
        else:
            _compare(schema, schemas_new[name], name, name in requests, out)
    return [c for c in out if c not in ALLOWED]


def _baseline() -> dict[str, Any]:
    ref = os.environ.get("OPENAPI_BASELINE_REF", "origin/dev")
    required = os.environ.get("OPENAPI_BASELINE_REQUIRED") == "1"  # CI (test.yml): a skip would hide a break
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=REPO, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as e:
        if required:
            detail = e.stderr.decode().strip() if isinstance(e, subprocess.CalledProcessError) else str(e)
            pytest.fail(
                f"{ref} isn't available, so the contract can't be checked against the released one: {detail}"
            )
        pytest.skip(f"{ref} isn't available here, so there is no released contract to compare against")
    try:
        text = subprocess.run(
            ["git", "show", f"{ref}:backend/tests/contract/openapi.json"],
            cwd=REPO,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        # main held only the specs before its first promotion: no backend, so no released contract. A base that
        # has a backend but no snapshot at this path (a moved snapshot) must not skip a required check
        predates = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}:backend/pyproject.toml"], cwd=REPO, check=False
        )
        if required and predates.returncode == 0:
            pytest.fail(f"{ref} has a backend but no snapshot at backend/tests/contract/openapi.json")
        pytest.skip(f"{ref} has no OpenAPI snapshot yet, so there is no released contract to compare against")
    return json.loads(text)  # type: ignore[no-any-return]


def test_the_committed_contract_is_additive_over_the_released_one() -> None:
    assert breaking_changes(_baseline(), json.loads(SNAPSHOT.read_text(encoding="utf-8"))) == []


# --- the checker itself --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _changed(doc: dict[str, Any], edit: Any) -> list[tuple[str, str]]:
    new = copy.deepcopy(doc)
    edit(new)
    return breaking_changes(doc, new)


def test_an_identical_document_has_no_breaking_change(doc: dict[str, Any]) -> None:
    assert breaking_changes(doc, doc) == []


def _schemas(d: dict[str, Any]) -> dict[str, Any]:
    return d["components"]["schemas"]  # type: ignore[no-any-return]


def _record_get(d: dict[str, Any]) -> dict[str, Any]:
    return d["paths"]["/api/v1/records/{id}"]["get"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (
            lambda d: _schemas(d)["SearchResponse"]["properties"].pop("total"),
            ("SearchResponse.total", "removed"),
        ),
        (
            lambda d: _schemas(d)["SearchResponse"]["properties"]["total"].update(type="number"),
            ("SearchResponse.total", "changed"),
        ),
        (
            lambda d: _schemas(d)["SearchResponse"]["required"].remove("total"),
            ("SearchResponse.total", "made optional"),
        ),
        (
            lambda d: _schemas(d)["SearchResponse"]["properties"].update(
                total={"anyOf": [{"type": "integer"}, {"type": "null"}]}
            ),
            ("SearchResponse.total", "nullable"),
        ),
        (
            lambda d: _schemas(d)["ReplayInfo"]["properties"]["status"]["enum"].append("withheld"),
            ("ReplayInfo.status", "value added to a closed enum"),
        ),
        (
            lambda d: _schemas(d)["Hit"]["properties"]["track"]["enum"].remove("other"),
            ("Hit.track", "enum value removed"),
        ),
        (
            lambda d: _schemas(d)["RecordRequest"]["required"].append("index_version"),
            ("RecordRequest.index_version", "made required"),
        ),
        (lambda d: d["paths"].pop("/api/v1/coverage"), ("GET /api/v1/coverage", "removed")),
        (
            lambda d: _record_get(d)["parameters"].append(
                {"in": "query", "name": "must", "required": True, "schema": {"type": "string"}}
            ),
            ("GET /api/v1/records/{id} must", "new required parameter"),
        ),
    ],
)
def test_each_breaking_change_is_found(doc: dict[str, Any], edit: Any, expected: tuple[str, str]) -> None:
    assert expected in _changed(doc, edit)


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: _schemas(d)["SearchResponse"]["properties"].update(new_total={"type": "integer"}),
        lambda d: _schemas(d)["Hit"]["properties"]["track"]["enum"].append("oral_only"),  # open
        lambda d: _record_get(d)["parameters"].append(
            {
                "in": "query",
                "name": "maybe",
                "required": False,
                "schema": {"type": "boolean", "default": True},
            }
        ),
        lambda d: _schemas(d)["SearchResponse"]["properties"]["total"].update(description="reworded"),
        lambda d: _schemas(d).update(NewThing={"type": "object", "properties": {}}),
    ],
    ids=["new response field", "open enum value", "optional parameter", "reworded", "new schema"],
)
def test_additive_changes_pass(doc: dict[str, Any], edit: Any) -> None:
    assert _changed(doc, edit) == []


def test_the_one_allowed_widening_is_only_the_record_replay(doc: dict[str, Any]) -> None:
    """decision-014 allows `RecordResponse.replay` to be nullable; the same widening anywhere else is breaking."""
    old = copy.deepcopy(doc)
    replay = _schemas(old)["RecordResponse"]["properties"]["replay"]
    replay.pop("anyOf", None)
    replay["$ref"] = REF + "ReplayInfo"
    assert breaking_changes(old, doc) == []
    new = copy.deepcopy(doc)
    diff = _schemas(new)["RecordDiff"]["properties"]
    diff["record_id"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert ("RecordDiff.record_id", "nullable") in breaking_changes(doc, new)
