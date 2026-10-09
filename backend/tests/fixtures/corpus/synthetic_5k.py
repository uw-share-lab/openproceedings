"""The synthetic ~5,000-record differential corpus (decision-004; spec 07 §A; task-028).

Generated deterministically in memory (nothing to commit or keep in sync): `records()` always returns the
same records, and `test_differential.py` pins their hash, so a change is deliberate. Words follow a Zipfian
ranking: the query language's awkward cases first (the shared strategy vocabulary: stopwords, operator
words, filter values as text, CJK, Thai; then LaTeX, NFKC forms, marks, astral characters, invisible
separators), then ~8,000 pseudo-words built on shared roots, so there are rare terms and hapaxes, prefixes
shared by many words, and a few roots whose short stems expand past the 200-term cap. Every venue × year ×
track × status combination occurs, and some records have no abstract.

`vocab()` is the corpus's own term dictionary as a strategy vocabulary (`tests.strategies.Vocab`): rare terms
(df 1-3), a few absent terms, and stems past the 200-term cap are weighted in. `cap_records()` and `cap_vocab()`
add stems at the cap's edge (200, 201 and 199 terms) for the differential suite.
"""

from __future__ import annotations

import dataclasses
import itertools
import random
from collections import Counter
from functools import cache

from openproceedings.query.normalize import normalize
from openproceedings.vocab import STATUSES
from tests.corpus import Rec
from tests.strategies import NGRAMS, VOCABULARY, Vocab

SIZE = 5_000
VENUES = ("NeurIPS", "ICLR", "ICML")
# pinned to the vocabulary before decision-049 added tracks: `product(VENUES, YEARS, TRACKS, STATUSES)` assigns
# every record, so reading vocab.TRACKS would reshuffle the whole corpus and every fixture and bench built on it
TRACKS = ("main", "datasets_benchmarks", "position", "workshop", "competition", "tiny_papers", "blogpost",
          "other", "unknown")  # fmt: skip
YEARS = tuple(range(2019, 2027))
ODDITIES = (
    "vision-language", "GPT-4o", "state-of-the-art", "LLMs'", "trust/reliance", "e.g.", "U.S.",
    "naïve", "Naïve", "résumé", 'G\\"odel', "Erd\\H{o}s", 'na\\"{\\i}ve', "bench\\-mark",
    "$\\alpha$-divergence", "$x^2$", "$n_{ij}$", "$a \\le b$", "$\\not\\in$", "$\\hat\\theta$", "\\textbf{trust}",
    "ﬁne-tuning", "ＡＩ", "Ｔrust", "²", "信頼性", "が", "ป่า", "trust\u200bworthy", "𝐓rust", "😀", "𝔸I",
    "2024", "2021", "4o", "AND", "or", "NOT", "near",
)  # fmt: skip
ROOTS = ("re", "tr", "ca", "mo", "de", "co", "pa", "st", "ex", "in", "pro", "con", "sub", "ver", "lan", "gra")
HEAVY = ("re", "tr", "co")  # roots with ~900 words each, so their 2-letter stems are refused
SYLLABLES = ("la", "ne", "ti", "so", "ru", "ka", "mi", "do", "ve", "pu", "ze", "go", "fa", "li", "no", "ta")
SUFFIXES = ("", "", "s", "ing", "ed", "er", "ness", "ation", "ity", "ive")


def _pseudo_words(rng: random.Random) -> list[str]:
    words: set[str] = set()
    for root in ROOTS:
        mine: set[str] = set()
        while len(mine) < (900 if root in HEAVY else 300):
            body = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(1, 3)))
            mine.add(root + body + rng.choice(SUFFIXES))
        words |= mine
    ordered = sorted(words)
    rng.shuffle(ordered)  # the Zipf rank is random, not alphabetical
    return ordered


@cache
def records(size: int = SIZE, abstract_words: tuple[int, int] = (8, 60)) -> tuple[Rec, ...]:
    """The corpus; the defaults are the pinned 5k differential corpus. The benchmark report scales it up
    (80k, abstracts of realistic length) with the same generator."""
    rng = random.Random(20260926)
    ranked = [*VOCABULARY, *ODDITIES, *_pseudo_words(rng)]
    cumulative = list(itertools.accumulate(1 / (rank + 1) ** 1.05 for rank in range(len(ranked))))
    combos = list(itertools.product(VENUES, YEARS, TRACKS, STATUSES))  # each at least once
    out = []
    for i in range(size):
        venue, year, track, status = combos[i] if i < len(combos) else rng.choice(combos)
        out.append(
            Rec(
                id=f"fx:{i:04d}",
                title=_text(rng, ranked, cumulative, 2, 9),
                abstract=None if i % 17 == 0 else _text(rng, ranked, cumulative, *abstract_words),
                venue=venue,
                year=year,
                track=track,
                status=status,
            )
        )
    return tuple(out)


def _text(rng: random.Random, words: list[str], cumulative: list[float], lo: int, hi: int) -> str:
    target = rng.randint(lo, hi)
    parts: list[str] = []
    while len(parts) < target:
        if rng.random() < 0.1:
            parts.extend(rng.choice(NGRAMS))  # a phrase from the golden fixture, so shared phrases occur
        else:
            parts.extend(rng.choices(words, cum_weights=cumulative, k=1))
    return " ".join(parts)


# Stems at the 200-expansion cap (TASK-057): the corpus's own stems jump from 117 terms to 278, so none sits near
# it, and regenerating the corpus would move every fixture built from it. `cap_records()` adds 20 records whose
# words give each stem exactly its count; `qc*` itself expands to 600 and is refused. The exact cap first:
# `sampled_from` favours the first entries.
CAP_STEMS = {"qcb": 200, "qcc": 201, "qca": 199}


@cache
def cap_records() -> tuple[Rec, ...]:
    """The cap stems' words, 30 to a record (5 in the title), across venues, years, tracks and statuses. Each
    stem's first 26 words are one letter longer than it (so `qcb$` expands to 26 terms; the stem itself
    is not a word), the rest two letters."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    words = [
        stem + (letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26])
        for stem, n in CAP_STEMS.items()
        for i in range(n)
    ]
    combos = list(itertools.product(VENUES, YEARS, TRACKS, STATUSES))
    out = []
    for k in range(20):
        venue, year, track, status = combos[k * 37 % len(combos)]
        mine = words[k * 30 : (k + 1) * 30]
        out.append(Rec(f"fx:{9000 + k}", " ".join(mine[:5]), " ".join(mine[5:]), venue, year, track, status))
    return tuple(out)


@cache
def cap_vocab() -> Vocab:
    """`vocab()` with the cap stems drawn about one stem in ten (`*` or `$`), for engines over `records()` +
    `cap_records()`."""
    return dataclasses.replace(vocab(), cap=tuple(CAP_STEMS))


@cache
def vocab() -> Vocab:
    """The corpus's term dictionary as a strategy vocabulary: the 600 most frequent terms and the rare ones (df 1-3)
    weighted in,
    stems from 2 characters up (those past the 200-term cap listed apart), and n-grams that really occur."""
    df: Counter[str] = Counter()
    ngrams: set[tuple[str, ...]] = set()
    for r in records():
        for text in (r.title, r.abstract or ""):
            tokens = normalize(text)
            df.update(set(tokens))
            ngrams.update(tuple(tokens[i : i + k]) for k in (2, 3) for i in range(len(tokens) - k + 1))
    terms = sorted(df)
    stems = sorted({t[:k] for t in terms for k in range(2, len(t))} | set(ROOTS))
    wide = tuple(s for s in stems if sum(t.startswith(s) for t in terms) > 200)  # `*` over them is refused
    sample = random.Random(1).sample(sorted(ngrams), 5_000)
    common = sorted(sorted(terms, key=lambda t: (-df[t], t))[:600])  # so most trees match something
    absent = ("zzqabsent", "notacorpusword", "trustq")  # terms no record holds: empty matches from a leaf
    rare = tuple(t for t in terms if df[t] <= 3) + absent
    return Vocab(tuple(common), tuple(stems), tuple(sample), rare, wide)
