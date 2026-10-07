#!/usr/bin/env python3
"""Fake `curl`, `npm` and `gh` for the /dependabot-review case table (dependabot_cases.py; TASK-211).

    python3 dependabot_fake.py <curl|npm|gh> <args...>

Answers from the JSON fixtures in $DEPBOT_FIX (`curl.json`, `npm.json`, `gh.json`) and appends each call to
`$DEPBOT_FIX/calls.log`, so no case reaches a live service. A request with no fixture fails the way the real
tool would (HTTP 404, `npm error 404`, a non-zero `gh`).
"""

from __future__ import annotations

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
        Path(opts["-D"]).write_text("\r\n".join(lines) + "\r\n\r\n")
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


def gh(args: list[str]) -> int:
    fx = fixtures("gh.json")
    if args[:2] == ["api", "graphql"]:
        seq = fx.get("graphql", [])
        counter = FIX / "graphql.count"
        n = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n + 1))
        if not seq:
            return 1
        print(json.dumps(seq[min(n, len(seq) - 1)]))
        return 0
    if args[:1] == ["api"]:
        key = f"api {args[1]}"
    elif args[:2] == ["attestation", "verify"]:
        key = f"attestation {args[2]} {args[args.index('--owner') + 1]}"
        code = fx.get(key)
        if code is None or code:
            print("fake gh: attestation verification failed", file=sys.stderr)
            return 1
        return 0
    elif args[:2] == ["pr", "list"]:
        joined = " ".join(args)
        if (
            "--author app/dependabot" not in joined
            or "--base dev" not in joined
            or "--state open" not in joined
        ):
            print("fake gh: pr list without the Dependabot/dev/open filter", file=sys.stderr)
            return 2
        key = "pr list"
    else:
        print(f"fake gh: unexpected call {args}", file=sys.stderr)
        return 2
    if key not in fx:
        print(f"fake gh: HTTP 404 ({key})", file=sys.stderr)
        return 1
    print(json.dumps(fx[key]))
    return 0


def main() -> int:
    tool, args = sys.argv[1], sys.argv[2:]
    log(tool, args)
    return {"curl": curl, "npm": npm, "gh": gh}[tool](args)


if __name__ == "__main__":
    sys.exit(main())
