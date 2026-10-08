#!/usr/bin/env python3
"""Fake `curl`, `npm` and `gh` for the /dependabot-review case table (dependabot_cases.py; TASK-211).

    python3 dependabot_fake.py <curl|npm|gh> <args...>

Answers from the JSON fixtures in $DEPBOT_FIX (`curl.json`, `npm.json`, `gh.json`) and appends each call to
`$DEPBOT_FIX/calls.log`, so no case reaches a live service. A request with no fixture fails the way the real
tool would (HTTP 404, `npm error 404`, a non-zero `gh`). With `"cloud": true` in `gh.json` the fake `gh` is a
Claude Code cloud session (TASK-213): every GraphQL call, so every `gh pr` command, fails with the session's
HTTP 403 body, and the `/ccr/` routes answer (outside a session they are a 404, as on api.github.com).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

FIX = Path(os.environ["DEPBOT_FIX"])


def fixtures(name: str) -> dict[str, Any]:
    p = FIX / name
    return json.loads(p.read_text()) if p.exists() else {}


def log(tool: str, args: list[str]) -> None:
    with (FIX / "calls.log").open("a") as f:
        f.write(json.dumps([tool, *args]) + "\n")


def curl(args: list[str]) -> int:
    opts: dict[str, str] = {}
    headers: dict[str, str] = {}
    head = False
    i = 0
    while i < len(args) - 1:
        a = args[i]
        if a in ("-D", "-o", "-w", "--proto", "--max-time"):
            opts[a] = args[i + 1]
            i += 2
            continue
        if a == "-H":
            value = args[i + 1]
            lines = Path(value[1:]).read_text().splitlines() if value.startswith("@") else [value]
            if not value.startswith("@") and value.lower().startswith("authorization"):
                print("fake curl: a credential on the command line", file=sys.stderr)
                return 2
            for line in lines:
                k, _, v = line.partition(":")
                headers[k.strip()] = v.strip()
            i += 2
            continue
        head = head or a == "-I"
        i += 1
    url = args[-1]
    if opts.get("--proto") != "=https":
        print("fake curl: called without --proto =https", file=sys.stderr)
        return 2
    if not url.startswith("https://"):  # what curl --proto =https does
        print("curl: (1) Protocol not supported or disabled", file=sys.stderr)
        return 1
    cands = fixtures("curl.json").get(url, [])
    for c in cands if isinstance(cands, list) else [cands]:
        want = c.get("if", {})
        if all(v in headers.get(k, "") for k, v in want.items()):
            answer = c
            break
    else:
        answer = {"status": 404, "headers": {}, "body": ""}
    if "-D" in opts:
        lines = [f"HTTP/1.1 {answer['status']} X"] + [
            f"{k}: {v}" for k, v in answer.get("headers", {}).items()
        ]
        # behind an HTTPS proxy curl's -D starts with the CONNECT answer; the real response is the last block
        proxy = "HTTP/1.1 200 Connection established\r\n\r\n" if answer.get("proxy") else ""
        Path(opts["-D"]).write_text(proxy + "\r\n".join(lines) + "\r\n\r\n")
    if "-o" in opts and not head:
        body = answer.get("body", "")
        Path(opts["-o"]).write_text(body if isinstance(body, str) else json.dumps(body))
    print(answer["status"], end="")
    return 0


def npm(args: list[str]) -> int:
    if args[:1] != ["view"] or "--json" not in args:
        print(f"fake npm: unexpected call {args}", file=sys.stderr)
        return 2
    reg = args[args.index("--registry") + 1] if "--registry" in args else ""
    if reg != "https://registry.npmjs.org/":
        print("fake npm: not asked of registry.npmjs.org", file=sys.stderr)
        return 1
    data = fixtures("npm.json").get(args[1])
    if data is None:
        # as npm does with --json: the error object on stdout, a non-zero exit
        print(json.dumps({"error": {"code": "E404", "summary": f"{args[1]} is not in this registry."}}))
        print(f"npm error 404 {args[1]}", file=sys.stderr)
        return 1
    if Path(".npmrc").exists():  # as npm would: a project .npmrc in the working directory redirects the scope
        data = {**data, "dist": {**data.get("dist", {}), "integrity": "sha512-from-a-project-npmrc"}}
    print(json.dumps(data))
    return 0


# What a Claude Code cloud session answers for every GraphQL call (HTTP 403; the routine's live runs, 2026-10-08).
GRAPHQL_403 = (
    "GitHub GraphQL is not available from Claude Code sessions; use the REST API (gh api "
    "repos/{owner}/{repo}/...). For review threads, auto-merge, and draft/ready-for-review use the CCR routes on "
    "api.github.com: GET /repos/{owner}/{repo}/pulls/{n}/ccr/review_threads, POST "
    "/repos/{owner}/{repo}/pulls/{n}/ccr/comments/{comment_id}/resolve (or /unresolve), PUT or DELETE "
    "/repos/{owner}/{repo}/pulls/{n}/ccr/auto_merge, POST /repos/{owner}/{repo}/pulls/{n}/ccr/ready_for_review, "
    "POST /repos/{owner}/{repo}/pulls/{n}/ccr/convert_to_draft."
)


def not_found(what: str) -> int:
    """As gh does on an API error: the error body on stdout, a message on stderr, exit 1."""
    print(json.dumps({"message": "Not Found", "status": "404"}))
    print(f"gh: Not Found (HTTP 404) ({what})", file=sys.stderr)
    return 1


def graphql_blocked() -> int:
    print(json.dumps({"message": GRAPHQL_403}))
    print(f"gh: {GRAPHQL_403} (HTTP 403)", file=sys.stderr)
    return 1


def answer(fx: dict[str, Any], key: str) -> Any:
    """The fixture for `key`; a `{"__seq": [...]}` fixture answers its items in turn, then repeats the last."""
    ans = fx.get(key)
    if isinstance(ans, dict) and "__seq" in ans:
        counter = FIX / f"count-{hashlib.sha256(key.encode()).hexdigest()[:16]}"
        n = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n + 1))
        seq = ans["__seq"]
        return seq[min(n, len(seq) - 1)]
    return ans


def gh_api(fx: dict[str, Any], args: list[str]) -> int:
    method, path, jq = "GET", None, None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-X", "--method"):
            method = args[i + 1]
            i += 2
        elif a in ("-f", "-F", "--raw-field", "--field", "-H", "--header"):
            i += 2
        elif a in ("--jq", "-q"):
            jq = args[i + 1]
            i += 2
        elif a.startswith("-"):
            print(f"fake gh: unexpected flag {a}", file=sys.stderr)
            return 2
        elif path is None:
            path = a
            i += 1
        else:
            print(f"fake gh: a second path {a}", file=sys.stderr)
            return 2
    if path is None:
        print("fake gh: api without a path", file=sys.stderr)
        return 2
    if "{" in path:  # a `{owner}/{repo}` placeholder needs a github.com remote a cloud clone may not have
        print(f"fake gh: a placeholder in {path}", file=sys.stderr)
        return 2
    if path == "graphql":
        if fx.get("cloud"):
            return graphql_blocked()
        ans = fx.get("graphql")
        if ans is None:
            return not_found("graphql")
        print(json.dumps(ans))
        return 0
    # the CCR routes exist only behind a Claude Code session's proxy (api.github.com answers 404 for them)
    if "/ccr/" in path and not fx.get("cloud"):
        return not_found(path)
    key = f"api {path}" if method == "GET" else f"api {method} {path}"
    ans = answer(fx, key)
    if ans is None:
        return not_found(key)
    if (
        isinstance(ans, dict) and "__exit" in ans
    ):  # gh dying another way (a signal, a timeout): no answer at all
        print("fake gh: died", file=sys.stderr)
        return int(ans["__exit"])
    if isinstance(ans, dict) and "__status" in ans:
        if ans["__status"] >= 300:
            body = ans.get("body", {"message": "error"})
            print(json.dumps(body))
            print(f"gh: {body.get('message', 'error')} (HTTP {ans['__status']})", file=sys.stderr)
            return 1
        ans = ans.get("body", "")
    if jq is not None:
        if jq != ".login":
            print(f"fake gh: unsupported --jq {jq}", file=sys.stderr)
            return 2
        print(ans["login"])
        return 0
    print(json.dumps(ans) if ans != "" else "")
    return 0


def gh(args: list[str]) -> int:
    fx = fixtures("gh.json")
    if args[:2] == ["auth", "token"]:
        # as gh does: a token variable first, then the stored login
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or fx.get("stored login")
        if tok:
            print(tok)
            return 0
        print("no oauth token found for github.com", file=sys.stderr)
        return 1
    if args[:1] == ["api"]:
        return gh_api(fx, args[1:])
    if args[:2] == ["attestation", "verify"]:
        key = f"attestation {args[2]} {args[args.index('--owner') + 1]}"
        code = fx.get(key)
        if code is None or code:
            print("fake gh: attestation verification failed", file=sys.stderr)
            return 1
        return 0
    if args[:1] == ["pr"]:  # every `gh pr` command reads or writes through GraphQL
        if fx.get("cloud"):
            return graphql_blocked()
        if args[1:2] == ["merge"]:
            code = int(fx.get("pr merge", 1))
            if code:
                print("fake gh: merge refused", file=sys.stderr)
            return code
    print(f"fake gh: unexpected call {args}", file=sys.stderr)
    return 2


def main() -> int:
    tool, args = sys.argv[1], sys.argv[2:]
    log(tool, args)
    return {"curl": curl, "npm": npm, "gh": gh}[tool](args)


if __name__ == "__main__":
    sys.exit(main())
