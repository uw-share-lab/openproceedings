#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit) reminder, non-blocking: the token contract (spec 02 §Token semantics)
# is shared by the query side and the index side. Touching it without bumping TOKENIZER_VERSION makes
# old search records claim a reproducibility they no longer have. Feeds a reminder back to the agent.
python3 -c '
import json, re, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
ti = payload.get("tool_input") or {}
path = (ti.get("file_path") or "").replace("\\", "/")
contract = re.compile(r"(^|/)backend/src/openproceedings/(query/normalize\.py|engine/(tokenizer|tantivy_engine|reference)\.py)$")
if not contract.search(path):
    raise SystemExit(0)
msg = (
    f"Token-contract file changed ({path}). Before this is reviewable: "
    "(1) if tokens can differ for ANY input, bump TOKENIZER_VERSION; "
    "(2) run the golden-token suite and the tokenizer-parity test; "
    "(3) run the differential suite (TantivyEngine == ReferenceEngine); "
    "(4) /review-gate will route this diff to exactness-guardian. Skill: token-contract."
)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
'
exit 0
