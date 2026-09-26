"""The token contract (spec 02 §Token semantics, token-contract skill): the ONLY implementation.

The query side and the index side both call this, so a query term and an indexed word can never disagree
about what a "word" is. In this order, and nothing else:

1. Unicode NFKC (`ﬁ` → `fi`, full-width → ASCII, `²` → `2`).
2. Case-fold (`str.casefold()`: `ß` → `ss`).
3. Diacritic fold: NFD, drop combining marks (`naïve` → `naive`), recompose with NFC.
4. LaTeX: `\\cmd{X}` → `X`; inside `$…$` a command name is a word (`$\\epsilon$` → `epsilon`); a bare
   `\\cmd` outside math is dropped; `\\%`, `\\&`, `\\$`, `\\\\` are separators (and `\\$` never opens math).
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


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int  # raw code-point offset, inclusive
    end: int  # raw code-point offset, exclusive


def _fold(c: str) -> str:
    """Steps 1–3 for one raw character; may return "" (a combining mark or format char) or several chars."""
    s = unicodedata.normalize("NFKC", c).casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf")


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


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
            in_math = not in_math
        i += 1
    return sep


def tokenize(text: str) -> list[Token]:
    """Tokens of `text` with their raw code-point spans."""
    latex = _latex_mask(text)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0

    def close() -> None:
        nonlocal buf
        if buf:
            out.append(Token(unicodedata.normalize("NFC", "".join(buf)), start, end))
            buf = []

    for i, c in enumerate(text):
        if latex[i]:
            close()
            continue
        folded = _fold(c)
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
