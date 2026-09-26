"""The token contract (spec 02 §Token semantics, token-contract skill): the ONLY implementation.

The query side and the index side both call this, so a query term and an indexed word can never disagree
about what a "word" is. In this order, and nothing else:

1. Unicode NFKC (`ﬁ` → `fi`, full-width → ASCII, `²` → `2`).
2. Case-fold (`str.casefold()`: `ß` → `ss`).
3. Diacritic fold: NFD, drop combining marks whose base letter is Latin, Greek, Cyrillic, Hebrew or
   Arabic (accents and optional vowel points: `naïve` → `naive`, `שָׁלוֹם` → `שלום`), recompose with NFC.
   Marks that spell a different word are KEPT: Thai tones (`ป่า` ≠ `ปา`), kana voicing (`が` ≠ `か`),
   Indic viramas and vowel signs. A stray mark with no base letter is dropped.
4. LaTeX: `\\cmd{X}` → `X`; inside `$…$` a command name is a word (`$\\epsilon$` → `epsilon`); a bare
   `\\cmd` outside math is dropped; `\\%`, `\\&`, `\\$`, `\\\\` are separators. `\\$` never opens math, and
   neither does a `$` followed by a digit (currency: `$5`).
5. Split on every character that is not a letter, digit or (non-combining) mark. Invisible format
   characters (soft hyphen, zero-width joiner/space) join, so `bench\\u00admark` stays one word.

Never: stemming, lemmatization, stopword removal, synonyms, spelling correction, n-grams, number
normalization. Changing what ANY input tokenizes to requires bumping TOKENIZER_VERSION.

`tokenize` works character by character so every token carries the half-open code-point span of the RAW
text it came from (spec 04 §Conventions); highlights use those spans. A single raw character can produce
more than one token (`½` → `1`, `2`), in which case they share its span.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

TOKENIZER_VERSION = "1"
FOLDING_SCRIPTS = ("LATIN", "GREEK", "CYRILLIC", "HEBREW", "ARABIC")


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int  # raw code-point offset, inclusive
    end: int  # raw code-point offset, exclusive


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _folds_marks(base: str | None) -> bool:
    """Does a combining mark on `base` fold away? Yes for decorative accents and optional vowel points."""
    return base is None or unicodedata.name(base, "").startswith(FOLDING_SCRIPTS)


def _fold(c: str, base: str | None) -> tuple[str, str | None]:
    """Steps 1–3 for one raw character, given the base letter the previous characters left open.

    Returns the folded characters (possibly "" or several) and the base letter to carry forward, so a
    combining mark in the NEXT raw character knows which script it decorates.
    """
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", unicodedata.normalize("NFKC", c).casefold()):
        if unicodedata.category(ch) == "Cf":
            continue  # invisible format characters join
        if unicodedata.combining(ch):
            if not _folds_marks(base):
                out.append(ch)  # a mark that spells the word stays
            continue
        out.append(ch)
        base = ch if _is_word_char(ch) else None
    return "".join(out), base


def _latex_mask(text: str) -> list[bool]:
    """True where a raw character is LaTeX syntax to treat as a separator (step 4)."""
    sep = [False] * len(text)
    in_math = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            j = i + 1
            if text[j].isascii() and text[j].isalpha():
                while j < n and text[j].isascii() and text[j].isalpha():
                    j += 1
                sep[i] = True
                if not in_math:  # a command name outside math is markup, not content
                    for k in range(i + 1, j):
                        sep[k] = True
                i = j
                continue
            sep[i] = sep[j] = True  # \% \& \$ \\ \{ … — escaped punctuation; \$ never toggles math
            i = j + 1
            continue
        if c == "\\":
            sep[i] = True
        elif c == "$":
            sep[i] = True
            if in_math or not (i + 1 < n and text[i + 1].isdigit()):  # `$5` is currency, not math
                in_math = not in_math
        i += 1
    return sep


def tokenize(text: str) -> list[Token]:
    """Tokens of `text` with their raw code-point spans."""
    latex = _latex_mask(text)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0
    base: str | None = None

    def close() -> None:
        nonlocal buf
        if buf:
            out.append(Token(unicodedata.normalize("NFC", "".join(buf)), start, end))
            buf = []

    for i, c in enumerate(text):
        if latex[i]:
            close()
            base = None
            continue
        folded, base = _fold(c, base)
        if not folded:  # combining mark or invisible format char: extends an open word, never starts one
            if buf:
                end = i + 1
            continue
        for ch in folded:
            if _is_word_char(ch):
                if not buf:
                    start = i
                buf.append(ch)
                end = i + 1
            else:
                close()
    close()
    return out


def normalize(text: str) -> list[str]:
    """The tokens of `text` (spec 02 §Token semantics). The index is fed `" ".join(normalize(field))`."""
    return [t.text for t in tokenize(text)]
