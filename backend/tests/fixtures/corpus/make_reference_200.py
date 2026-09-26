"""Generate the 200-record golden fixture for ReferenceEngine (task-016 AC2). Run from the repo root:

    uv run python backend/tests/fixtures/corpus/make_reference_200.py

Expected id sets are computed here by a deliberately separate evaluator: a regex tokenizer (NFKD, strip
marks, casefold, split on non-alphanumerics; exact for this ASCII/Latin corpus) and a tiny tuple
language, never openproceedings' lexer, parser or normalize(). Review the output diff before committing.
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent
WORDS = [
    "trust",
    "trustworthy",
    "trustworthiness",
    "trusted",
    "calibration",
    "calibrated",
    "benchmark",
    "benchmarks",
    "benchmarking",
    "model",
    "models",
    "modeling",
    "language",
    "vision-language",
    "large",
    "human",
    "humans",
    "reliance",
    "reliable",
    "evaluation",
    "evaluations",
    "dataset",
    "datasets",
    "agent",
    "agents",
    "naïve",
    "résumé",
    "safety",
    "fairness",
    "bias",
    "llm",
    "llms",
    "gpt-4o",
    "in",
    "of",
    "the",
    "and",
    "a",
    "for",
    "with",
    "ai",
]


def tokens(text: str) -> list[str]:
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return [t for t in re.split(r"[^0-9a-z]+", text.casefold()) if t]


def fields(rec: dict[str, object], field: str | None) -> list[list[str]]:
    names = [field] if field else ["title", "abstract"]
    return [tokens(str(rec[f] or "")) for f in names]


def item_ok(tok: str, item: str) -> bool:
    if item.endswith("*"):
        return tok.startswith(item[:-1])
    if item.endswith("$"):
        stem = item[:-1]
        return tok == stem or (len(tok) == len(stem) + 1 and tok.startswith(stem))
    return tok == item


def spans(toks: list[str], items: list[str]) -> list[tuple[int, int]]:
    k = len(items)
    return [
        (i, i + k) for i in range(len(toks) - k + 1) if all(item_ok(toks[i + j], items[j]) for j in range(k))
    ]


def ev(rec: dict[str, object], t: list) -> bool:  # type: ignore[type-arg]
    op = t[0]
    if op == "and":
        return all(ev(rec, x) for x in t[1:])
    if op == "or":
        return any(ev(rec, x) for x in t[1:])
    if op == "not":
        return not ev(rec, t[1])
    if op == "seq":  # ["seq", field, [items]]
        return any(spans(f, t[2]) for f in fields(rec, t[1]))
    if op == "near":  # ["near", field, [a items], [b items], n]
        for f in fields(rec, t[1]):
            for a in spans(f, t[2]):
                for b in spans(f, t[3]):
                    first, second = sorted([a, b])
                    if first[1] <= second[0] and second[0] - first[1] <= t[4]:
                        return True
        return False
    if op == "eq":
        return str(rec[t[1]]).casefold() == str(t[2]).casefold()
    if op == "years":
        return t[1] <= int(rec["year"]) <= t[2]  # type: ignore[call-overload]
    raise ValueError(op)


QUERIES: list[tuple[str, list]] = [  # type: ignore[type-arg]
    ("trust", ["seq", None, ["trust"]]),
    ("trusted", ["seq", None, ["trusted"]]),
    ("benchmark", ["seq", None, ["benchmark"]]),
    ("benchmark*", ["seq", None, ["benchmark*"]]),
    ("model$", ["seq", None, ["model$"]]),
    ("llm", ["seq", None, ["llm"]]),
    ("llm$", ["seq", None, ["llm$"]]),
    ("trustworth*", ["seq", None, ["trustworth*"]]),
    ("naive", ["seq", None, ["naive"]]),
    ("Résumé", ["seq", None, ["resume"]]),
    ("title:calibration", ["seq", "title", ["calibration"]]),
    ("abstract:agent$", ["seq", "abstract", ["agent$"]]),
    ('"trust calibration"', ["seq", None, ["trust", "calibration"]]),
    ('"large language model$"', ["seq", None, ["large", "language", "model$"]]),
    ("vision-language", ["seq", None, ["vision", "language"]]),
    ("gpt-4o", ["seq", None, ["gpt", "4o"]]),
    ('title:"human reliance"', ["seq", "title", ["human", "reliance"]]),
    ('"the model*"', ["seq", None, ["the", "model*"]]),
    ("trust NEAR/0 calibration", ["near", None, ["trust"], ["calibration"], 0]),
    ("trust NEAR/2 evaluation", ["near", None, ["trust"], ["evaluation"], 2]),
    ("abstract:(agent$ NEAR/3 safety)", ["near", "abstract", ["agent$"], ["safety"], 3]),
    ('"vision language" NEAR/1 benchmark*', ["near", None, ["vision", "language"], ["benchmark*"], 1]),
    ("trust calibration", ["and", ["seq", None, ["trust"]], ["seq", None, ["calibration"]]]),
    ("trust OR reliance", ["or", ["seq", None, ["trust"]], ["seq", None, ["reliance"]]]),
    ("trust NOT bias", ["and", ["seq", None, ["trust"]], ["not", ["seq", None, ["bias"]]]]),
    (
        "(trust OR reliance) (benchmark* OR dataset$)",
        [
            "and",
            ["or", ["seq", None, ["trust"]], ["seq", None, ["reliance"]]],
            ["or", ["seq", None, ["benchmark*"]], ["seq", None, ["dataset$"]]],
        ],
    ),
    ("trust venue:ICLR", ["and", ["seq", None, ["trust"]], ["eq", "venue", "ICLR"]]),
    (
        "trust venue:(ICML OR NeurIPS)",
        ["and", ["seq", None, ["trust"]], ["or", ["eq", "venue", "ICML"], ["eq", "venue", "NeurIPS"]]],
    ),
    ("model$ year:2021..2023", ["and", ["seq", None, ["model$"]], ["years", 2021, 2023]]),
    ("model$ track:workshop", ["and", ["seq", None, ["model$"]], ["eq", "track", "workshop"]]),
    ("model$ status:rejected", ["and", ["seq", None, ["model$"]], ["eq", "status", "rejected"]]),
    (
        "trust NOT track:workshop NOT status:rejected",
        [
            "and",
            ["seq", None, ["trust"]],
            ["not", ["eq", "track", "workshop"]],
            ["not", ["eq", "status", "rejected"]],
        ],
    ),
    (
        "title:trust* NOT abstract:trust*",
        ["and", ["seq", "title", ["trust*"]], ["not", ["seq", "abstract", ["trust*"]]]],
    ),
    (
        "(human* NEAR/1 relian*) OR fairness",
        ["or", ["near", None, ["human*"], ["relian*"], 1], ["seq", None, ["fairness"]]],
    ),
    ("ai agent$", ["and", ["seq", None, ["ai"]], ["seq", None, ["agent$"]]]),
    ('"ai agent$"', ["seq", None, ["ai", "agent$"]]),
    ("of", ["seq", None, ["of"]]),
    ('"of the"', ["seq", None, ["of", "the"]]),
    ("safety year:2020", ["and", ["seq", None, ["safety"]], ["years", 2020, 2020]]),
    (
        "evaluation* venue:NeurIPS year:2024 track:datasets_benchmarks",
        [
            "and",
            ["seq", None, ["evaluation*"]],
            ["eq", "venue", "NeurIPS"],
            ["years", 2024, 2024],
            ["eq", "track", "datasets_benchmarks"],
        ],
    ),
]


def main() -> None:
    rng = random.Random(20260925)
    records = []
    for i in range(200):
        title = " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 7))).capitalize()
        abstract = (
            None if i % 23 == 0 else " ".join(rng.choice(WORDS) for _ in range(rng.randint(8, 30))) + "."
        )
        if abstract and i % 7 == 0:  # seed multi-word phrases, which random word order almost never makes
            abstract += " We study large language models and a large language model."
        if i % 11 == 0:
            title += " for human reliance"
        records.append(
            {
                "id": f"op:fx:{i:03d}",
                "title": title,
                "abstract": abstract,
                "venue": rng.choice(["NeurIPS", "ICLR", "ICML"]),
                "year": rng.randint(2020, 2025),
                "track": rng.choice(
                    ["main", "main", "main", "datasets_benchmarks", "workshop", "position", "unknown"]
                ),
                "status": rng.choice(
                    ["accepted", "accepted", "accepted", "rejected", "withdrawn", "unknown"]
                ),
            }
        )
    (HERE / "reference-200.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    )
    golden = [{"q": q, "expected": sorted(r["id"] for r in records if ev(r, tree))} for q, tree in QUERIES]
    (HERE / "reference-200-queries.json").write_text(json.dumps(golden, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(records)} records, {len(golden)} queries; sizes:", [len(g["expected"]) for g in golden])


if __name__ == "__main__":
    main()
