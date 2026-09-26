"""The token contract (spec 02 §Token semantics, token-contract skill): the ONLY implementation.

The query side and the index side both call this, so a query term and an indexed word can never disagree
about what a "word" is. In this order, and nothing else:

1. Unicode NFKC (`ﬁ` → `fi`, full-width → ASCII, `²` → `2`).
2. Case-fold (`str.casefold()`: `ß` → `ss`).
3. Diacritic fold: NFD, drop combining marks whose base letter is Latin, Greek, Cyrillic, Hebrew or
   Arabic (accents and optional vowel points: `naïve` → `naive`, `שָׁלוֹם` → `שלום`), recompose with NFC.
   Marks that spell a different word are KEPT: Thai tones (`ป่า` ≠ `ปา`), kana voicing (`が` ≠ `か`),
   Indic viramas and vowel signs. A stray mark with no base letter is dropped.
4. LaTeX: `\\cmd{X}` → `X`; a bare `\\cmd` outside math is dropped. Math regions are `$…$` (Pandoc's
   tex_math_dollars rule: the opener is followed by a non-space, the closer is preceded by a non-space and
   not followed by a digit, so `$5` and `US$ 5` are currency), `$$…$$`, `\\(…\\)` and `\\[…\\]`; inside
   them a command name is a word (`$\\mathcal$` → `mathcal`), except that math spelled in LaTeX gives the
   token its Unicode spelling gives (decision-006, `mathsyms.py`): a Greek command is its letter
   (`$\\epsilon$` → `ε`, like `ε`), an operator command is its operator's name (`$\\le$` → `leq`, like `≤`),
   and `^`/`_` before one letter or digit, or a braced run of them, join it (`$n^2$` → `n2`, like `n²`).
   `\\%`, `\\&`, `\\$`, `\\\\` are separators and `\\$` never opens math. Accent macros (`G\\"odel`,
   `Erd\\H{o}s`, `na\\"{\\i}ve`) and `\\-` join the word.
5. Split on every character that is not a letter, digit or (non-combining) mark. A Unicode operator or
   relation in `mathsyms.OPERATORS` is a token of its own, its LaTeX name (`5×3` → `5`, `times`, `3`). Invisible characters join
   (format characters such as the soft hyphen and zero-width joiner, variation selectors, enclosing marks,
   the combining grapheme joiner), so `bench\\u00admark` stays one word; the invisible math operators
   U+2061–2064 separate.

Never: stemming, lemmatization, stopword removal, synonyms, spelling correction, n-grams, number
normalization. Changing what ANY input tokenizes to requires bumping TOKENIZER_VERSION.

`tokenize` works character by character so every token carries the half-open code-point span of the RAW
text it came from (spec 04 §Conventions); highlights use those spans. A single raw character can produce
more than one token (`½` → `1`, `2`), in which case they share its span.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from openproceedings.query.mathsyms import GREEK, LETTER_LOOKALIKES, NEGATED, OPERATOR_COMMANDS, OPERATORS

TOKENIZER_VERSION = "2"  # 2: math spelled in LaTeX or Unicode gives one token (decision-006)
# Base letters whose combining marks fold (accents, optional vowel points): matched on the Unicode name.
FOLDING_SCRIPTS = ("LATIN", "GREEK", "CYRILLIC", "HEBREW", "ARABIC", "EXTENDED ARABIC", "DIGIT")
# Marks that spell a distinct letter even in those scripts, so they are kept: Cyrillic breve (й ≠ и) and
# Arabic hamza above/below (أ, ؤ, ئ are letters, not vowel points).
KEPT_MARKS = {
    "\u0306": ("CYRILLIC",),
    "\u0654": ("ARABIC", "EXTENDED ARABIC"),
    "\u0655": ("ARABIC", "EXTENDED ARABIC"),
}
# Invisible math operators (function application, times, separator, plus) separate words.
INVISIBLE_SEPARATORS = frozenset("\u2061\u2062\u2063\u2064")

# LaTeX mask values: a normal char, a separator, markup that joins its neighbours, and a math command that
# stands for a Unicode spelling (its replacement is in the `subs` map, keyed by the backslash's index)
KEEP, SEP, JOIN, SUB = 0, 1, 2, 3
ACCENT_SYMBOLS = frozenset("'`^\"~=.")  # \'e \`e \^e \"o \~n \=a \.z
ACCENT_LETTERS = frozenset("uvHcdbrk")  # \u{a} \v{c} \H{o} \c{c} \d{a} \b{a} \r{a} \k{a}


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int  # raw code-point offset, inclusive
    end: int  # raw code-point offset, exclusive


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _folds_marks(base: str | None, mark: str) -> bool:
    """Does `mark` on `base` fold away? Yes for decorative accents and optional vowel points."""
    if base is None:
        return True
    name = unicodedata.name(base, "")
    if mark in KEPT_MARKS and name.startswith(KEPT_MARKS[mark]):
        return False
    return name.startswith(FOLDING_SCRIPTS)


def _invisible(ch: str) -> bool:
    """Characters that join rather than split: format chars, enclosing marks, variation selectors, CGJ."""
    cp = ord(ch)
    return (
        unicodedata.category(ch) in ("Cf", "Me")
        or 0xFE00 <= cp <= 0xFE0F
        or 0xE0100 <= cp <= 0xE01EF
        or 0x180B <= cp <= 0x180F
        or cp == 0x034F
    )


@dataclass(frozen=True, slots=True)
class _Op:
    """An operator found in a character's NFKC form: a token of its own, its LaTeX name."""

    name: str


def _fold(c: str, base: str | None) -> tuple[list[str | _Op], str | None]:
    """Steps 1–3 for one raw character, given the base letter the previous characters left open.

    Returns the folded pieces (characters, and an `_Op` for each operator NFKC yields: `∬` → two `int`,
    `𝛁` → `nabla`, `ŀ` → `l` then `cdot`) and the base letter to carry forward, so a combining mark in the
    NEXT raw character knows which script it decorates.
    """
    out: list[str | _Op] = []
    for piece in unicodedata.normalize("NFKC", c):
        if piece in OPERATORS:
            out.append(_Op(OPERATORS[piece]))
            base = None
            continue
        for ch in unicodedata.normalize("NFD", LETTER_LOOKALIKES.get(piece, piece).casefold()):
            if ch in INVISIBLE_SEPARATORS:
                out.append(" ")
                base = None
                continue
            if _invisible(ch):
                continue  # joins its neighbours
            if unicodedata.combining(ch):
                if not _folds_marks(base, ch):
                    out.append(ch)  # a mark that spells the word stays
                continue
            out.append(ch)
            base = ch if _is_word_char(ch) else None
    return out, base


def _find_closing_dollar(text: str, i: int) -> int:
    """Index of the `$` that closes single-dollar math opened at `i`, or -1 (Pandoc tex_math_dollars):
    the opener must be followed by a non-space; a closer is an unescaped single `$` preceded by a non-space
    and not followed by a digit."""
    n = len(text)
    if i + 1 >= n or text[i + 1].isspace():
        return -1
    j = i + 1
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "$":
            if j + 1 < n and text[j + 1] == "$":
                return -1  # `$$` inside inline math: not a valid closer; treat the opener as literal
            if not text[j - 1].isspace() and not (j + 1 < n and text[j + 1].isdigit()):
                return j
        j += 1
    return -1


def _find(text: str, start: int, closer: str) -> int:
    """Index of the next unescaped `closer` at or after `start`, or -1. Any other backslash escapes the
    character after it, so `\\\\)` (an escaped backslash, then `)`) never closes `\\(`."""
    j = start
    while j < len(text):
        if text.startswith(closer, j):
            return j
        j += 2 if text[j] == "\\" else 1
    return -1


def _script_join(text: str, i: int) -> int:
    """Inside math, `^`/`_` at `i` joins what it raises or lowers when that is one ASCII letter or digit,
    or a braced run of them (`n^2`, `x_{ij}`), as NFKC joins `n²` and `xᵢⱼ`. (Not `x^\\alpha`: NFKC reads
    `ᵅ` as the Latin `ɑ`, so no Unicode spelling agrees with it.) Returns
    the index of the closing `}` to join too, `i` when there is none, or -1 when it doesn't join."""
    if i + 1 >= len(text):
        return -1
    nxt = text[i + 1]
    if nxt.isascii() and nxt.isalnum():
        return i
    if nxt == "{":
        k = i + 2  # scan the run itself (linear), never ahead to some later `}`
        while k < len(text) and text[k].isascii() and text[k].isalnum():
            k += 1
        return k if k > i + 2 and k < len(text) and text[k] == "}" else -1
    return -1


def _negation(text: str, j: int) -> tuple[str, int] | None:
    """After `\\not` ending at `j`: the negated operator's name and where it ends, or None."""
    if j < len(text) and text[j] in NEGATED:
        return NEGATED[text[j]], j + 1
    if text.startswith("\\", j):
        k = j + 1
        while k < len(text) and text[k].isascii() and text[k].isalpha():
            k += 1
        if text[j + 1 : k] in NEGATED:
            return NEGATED[text[j + 1 : k]], k
    return None


def _latex_mask(
    text: str,
    regions: list[tuple[int, int]] | None = None,
    subs: dict[int, tuple[str, bool, int, bool]] | None = None,
) -> list[int]:
    """Classify every raw character for step 4: KEEP, SEP (LaTeX syntax that separates) or JOIN (markup
    inside a word, such as an accent macro or `\\-`). Math regions: `$…$` (Pandoc rule), `$$…$$`, `\\(…\\)`,
    `\\[…\\]`; inside them a command name is a word, outside it is dropped. Each math region found is
    appended to `regions` as a half-open span from its opening delimiter to the end of its closing one. A
    math command with a Unicode spelling is SUB at its backslash and JOIN over its name; `subs` maps the
    backslash's index to (the spelling, whether it is an operator token, the command's end, whether it
    starts a new word because another command's name ends right before it: `\\hat\\theta` → `hat θ`)."""
    name_end = -1  # where the last kept command name (a word inside math) ended
    n = len(text)
    opened = -1  # where the current math region's opening delimiter starts
    mask = [KEEP] * n
    math_until = -1  # index where the current math region's closing delimiter starts, or -1
    close_len = 0  # length of that delimiter: 1 for `$`, 2 for `$$`, `\\)`, `\\]`
    i = 0
    while i < n:
        c = text[i]
        if i == math_until:  # the closing delimiter: a separator that ends math and never re-opens it
            for k in range(i, i + close_len):
                mask[k] = SEP
            i += close_len
            if regions is not None:
                regions.append((opened, i))
            math_until, close_len = -1, 0
            continue
        in_math = i < math_until
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if not in_math and nxt in "([":
                close = _find(text, i + 2, "\\)" if nxt == "(" else "\\]")
                if close >= 0:
                    mask[i] = mask[i + 1] = SEP
                    math_until, close_len, opened = close, 2, i
                    i += 2
                    continue
            if nxt == "-":
                mask[i] = mask[i + 1] = JOIN  # discretionary hyphen: `bench\\-mark` is one word
                i += 2
                continue
            if nxt in ACCENT_SYMBOLS or (nxt in ACCENT_LETTERS and i + 2 < n and text[i + 2] == "{"):
                mask[i] = mask[i + 1] = JOIN  # accent macro: `G\\"odel`, `Erd\\H{o}s` stay one word
                k = i + 2
                if (
                    k + 3 < n
                    and text[k] == "{"
                    and text[k + 1 : k + 3] in ("\\i", "\\j")
                    and text[k + 3] == "}"
                ):
                    mask[k] = mask[k + 1] = mask[k + 3] = JOIN  # BibTeX dotless i/j: `na\\"{\\i}ve`
                    i = k + 4
                    continue
                if k + 2 < n and text[k] == "{" and text[k + 2] == "}":
                    mask[k] = mask[k + 2] = JOIN
                    i = k + 3
                    mask[k + 1] = KEEP
                    continue
                i = k
                continue
            if nxt.isascii() and nxt.isalpha():
                j = i + 1
                while j < n and text[j].isascii() and text[j].isalpha():
                    j += 1
                name = text[i + 1 : j]
                negated = _negation(text, j) if in_math and name == "not" else None
                if negated is not None:  # `\\not\\in`, `\\not=`: one operator, like `∉`, `≠`
                    spelling, j = negated
                    mask[i] = SUB
                    for k in range(i + 1, j):
                        mask[k] = JOIN
                    if subs is not None:
                        subs[i] = (spelling, True, j, False)
                    i = j
                    continue
                if in_math and (name in GREEK or name in OPERATOR_COMMANDS):
                    mask[i] = SUB
                    for k in range(i + 1, j):
                        mask[k] = JOIN
                    if subs is not None:
                        op = name not in GREEK
                        subs[i] = (OPERATOR_COMMANDS[name] if op else GREEK[name], op, j, i == name_end)
                    i = j
                    continue
                if in_math:
                    name_end = j
                mask[i] = SEP
                if not in_math:  # a command name outside math is markup, not content
                    for k in range(i + 1, j):
                        mask[k] = SEP
                i = j
                continue
            if nxt.isascii():
                mask[i] = mask[i + 1] = (
                    SEP  # \\% \\& \\$ \\\\ \\{ … — escaped punctuation; \\$ never opens math
                )
                i += 2
                continue
            mask[i] = SEP  # backslash before a non-ASCII char: drop the backslash, keep the char
            i += 1
            continue
        if c == "\\":
            mask[i] = SEP
        elif in_math and c in "^_" and (close := _script_join(text, i)) >= 0:
            mask[i] = JOIN
            if close > i:  # a braced run: the braces join too
                mask[i + 1] = mask[close] = JOIN
                i += 2
                continue
        elif c == "$":
            mask[i] = SEP
            if not in_math and i + 1 < n and text[i + 1] == "$":
                close = _find(text, i + 2, "$$")
                mask[i + 1] = SEP
                if close >= 0:
                    math_until, close_len, opened = close, 2, i
                i += 2
                continue
            if not in_math:
                close = _find_closing_dollar(text, i)
                if close >= 0:
                    math_until, close_len, opened = close, 1, i
        i += 1
    return mask


def first_math_end(text: str) -> int:
    """If LaTeX math opens at the start of `text` (`$…$` by the Pandoc rule, or `$$…$$`), the index just after
    its closing delimiter; else -1. Exactly the decision step 4 makes at position 0 (so it agrees with
    `math_regions`), in one scan to the closer instead of a pass over the whole text."""
    if not text.startswith("$"):
        return -1
    if text.startswith("$$"):
        close = _find(text, 2, "$$")
        return close + 2 if close >= 0 else -1
    close = _find_closing_dollar(text, 0)
    return close + 1 if close >= 0 else -1


def math_regions(text: str) -> list[tuple[int, int]]:
    """The LaTeX math regions of `text` exactly as step 4 finds them (half-open, delimiters included).
    The query lexer uses this so that it and the tokenizer never disagree about what `$…$` is."""
    regions: list[tuple[int, int]] = []
    _latex_mask(text, regions)
    return regions


def tokenize(text: str) -> list[Token]:
    """Tokens of `text` with their raw code-point spans."""
    subs: dict[int, tuple[str, bool, int, bool]] = {}
    latex = _latex_mask(text, subs=subs)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0
    base: str | None = None

    def close() -> None:
        nonlocal buf
        if buf:
            word = unicodedata.normalize("NFC", "".join(buf))
            # A run of marks with no letter (a lone vowel sign) is not a word.
            if not all(unicodedata.category(ch).startswith("M") for ch in word):
                out.append(Token(word, start, end))
            buf = []

    n = len(text)
    i = 0
    while i < n:
        c, stop = text[i], i + 1
        if latex[i] == SUB:  # a math command with a Unicode spelling; its span starts at its name
            spelling, operator, cmd_end, split = subs[i]
            if operator or split:
                close()
            if operator:  # a token of its own
                out.append(Token(spelling, i + 1, cmd_end))
                base = None
            else:  # a Greek letter: part of the word, like the letter itself
                folded, base = _fold(spelling, base)
                if not buf:
                    start = i + 1
                buf.extend(p for p in folded if isinstance(p, str))
                end = cmd_end
            i += 1
            continue
        if latex[i] == SEP:
            close()
            base = None
            i += 1
            continue
        if latex[i] == JOIN:  # markup inside a word: keep the word open and cover the markup in its span
            if buf:
                end = i + 1
            i += 1
            continue
        if i + 1 < n and text[i + 1] == "\u0338" and latex[i + 1] == KEEP:
            composed = unicodedata.normalize("NFC", c + "\u0338")  # `∈` + slash is `∉`, `=` + slash is `≠`
            if len(composed) == 1:
                c, stop = composed, i + 2
        folded, base = _fold(c, base)
        if not folded:  # combining mark or invisible format char: extends an open word, never starts one
            if buf:
                end = stop
            i = stop
            continue
        for piece in folded:
            if isinstance(piece, _Op):
                close()
                out.append(Token(piece.name, i, stop))
            elif _is_word_char(piece):
                if not buf:
                    start = i
                buf.append(piece)
                end = stop
            else:
                close()
        i = stop
    close()
    return out


def normalize(text: str) -> list[str]:
    """The tokens of `text` (spec 02 §Token semantics). The index is fed `" ".join(normalize(field))`."""
    return [t.text for t in tokenize(text)]
