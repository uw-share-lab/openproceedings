"""The synthetic ~5,000-record differential corpus (decision-004; spec 07 §A; task-028).

Generated deterministically in memory (nothing to commit or keep in sync): `records()` always returns the
same records. The text is drawn from the vocabulary and n-grams the shared AST strategies draw from
(`tests/strategies.py`), so random queries hit documents, mixed with what the tokenizer treats specially:
hyphens, LaTeX (math, accent macros, `\\-`), NFKC forms, marks, CJK, astral characters and digits. Every
venue × year × track × status combination occurs, and some records have no abstract.
"""

from __future__ import annotations

import itertools
import random
from functools import cache

from openproceedings.vocab import STATUSES, TRACKS
from tests.corpus import Rec
from tests.strategies import NGRAMS, VOCABULARY

SIZE = 5_000
VENUES = ("NeurIPS", "ICLR", "ICML")
YEARS = tuple(range(2019, 2027))
ODDITIES = (
    "vision-language", "GPT-4o", "state-of-the-art", "LLMs'", "trust/reliance", "e.g.", "U.S.",
    "naïve", "Naïve", "résumé", 'G\\"odel', "Erd\\H{o}s", 'na\\"{\\i}ve', "bench\\-mark",
    "$\\alpha$-divergence", "$x^2$", "$n_{ij}$", "$a \\le b$", "$\\not\\in$", "$\\hat\\theta$", "\\textbf{trust}",
    "ﬁne-tuning", "ＡＩ", "Ｔrust", "²", "信頼性", "が", "ป่า", "trust\u200bworthy", "𝐓rust", "😀", "𝔸I",
    "2024", "2021", "4o", "AND", "or", "NOT", "near",
)  # fmt: skip


@cache
def records() -> tuple[Rec, ...]:
    rng = random.Random(20260926)
    combos = list(itertools.product(VENUES, YEARS, TRACKS, STATUSES))  # each at least once
    words = [*VOCABULARY, *VOCABULARY, *ODDITIES]
    out = []
    for i in range(SIZE):
        venue, year, track, status = combos[i] if i < len(combos) else rng.choice(combos)
        out.append(
            Rec(
                id=f"fx:{i:04d}",
                title=_text(rng, words, 2, 9),
                abstract=None if i % 17 == 0 else _text(rng, words, 8, 60),
                venue=venue,
                year=year,
                track=track,
                status=status,
            )
        )
    return tuple(out)


def _text(rng: random.Random, words: list[str], lo: int, hi: int) -> str:
    parts: list[str] = []
    while len(parts) < rng.randint(lo, hi):
        if rng.random() < 0.15:
            parts.extend(rng.choice(NGRAMS))  # a phrase that really occurs, so phrases and NEAR match
        else:
            parts.append(rng.choice(words))
    return " ".join(parts)
