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
more than one token (`½` → `1`, `2`), in which case they share its span; two spans overlap only on exactly
one such code point (a combining-slash cluster gives each piece the raw characters it came from:
`_cluster_spans`). What a query parses to never depends on those spans: the lexer's detached-wildcard test
reads the folded pieces after the last word (`tokenize_with_tail`), never a span.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from openproceedings.query.mathsyms import (
    GREEK,
    LETTER_LOOKALIKES,
    NEGATED,
    NEGATION,
    OPERATOR_COMMANDS,
    OPERATORS,
)

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
    op: bool = False  # an operator's name (`×` → `times`), not a word of the text: never a wildcard stem


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


def _cluster_spans(
    text: str, i: int, j: int, folded: list[str | _Op], base: str | None
) -> list[tuple[int, int]]:
    """The raw span of each piece of `folded`, the `_fold` of the slash cluster `text[i:j]` (a character, then
    combining marks, one of them U+0338), so pieces that land in different tokens don't claim the same marks
    (task-075). Offsets only: the pieces are always the whole cluster's `_fold`, so tokens can't change.

    NFKC attaches the marks to the last starter of the character's own NFKC form, so two kinds of piece can
    end one token and start another inside a cluster, and each gets the raw characters it came from:
    - pieces before that starter come from the character alone (`½` + slash is `1⁄2` + slash): `1` spans
      `½`, not the slash, so `x½` + slash + `y` gives `x1` and `2y`, which share `½` and nothing else;
    - U+0345 (ypogegrammeni) is the only mark that folds to a letter, `ι`, and its combining class (240, the
      highest, and its alone) sorts it after every other mark, so its `ι`s are the fold's last pieces. After
      a piece that isn't a letter (`⩶` + slash + U+0345 → `==`, `neq`, `ι`) they start a word of their own, which starts at
      the first raw U+0345, and the pieces before it end there. The one exception to "each piece spans what
      it came from": the pieces before the first raw U+0345 end at it, even if a later mark belongs to them
      (`=` + U+0345 + slash: `neq` spans only `=`, and the slash is in the `ι` word's span). Contiguous spans
      can't split interleaved marks, and this keeps them from overlapping.
    Every other piece spans the whole cluster, as a combining mark extends the word it follows."""
    spans = [(i, j)] * len(folded)
    nfkc = unicodedata.normalize("NFKC", text[i])
    last = max((k for k, ch in enumerate(nfkc) if not unicodedata.combining(ch)), default=0)
    if last:
        head, _ = _fold(nfkc[:last], base)
        if folded[: len(head)] == head:
            spans[: len(head)] = [(i, i + 1)] * len(head)
    iotas = [m for m in range(i + 1, j) if text[m] == "\u0345"]
    q = len(iotas)
    if q and len(folded) > q and all(p == "\u03b9" for p in folded[-q:]):
        before = folded[-q - 1]
        if isinstance(before, _Op) or not _is_word_char(before):
            m1 = iotas[0]
            spans[:-q] = [(a, min(b, m1)) for a, b in spans[:-q]]
            spans[-q:] = [(m1, j)] * q
    return spans


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


class _Closers:
    """`_find` and `_find_closing_dollar` for every start at once (task-070). Each scan's walk from a
    position is fixed (a backslash skips the character after it), so one right-to-left pass gives every
    position's answer: an unclosed opener costs a lookup instead of a scan to the end of the text. Built
    per closer, only when an opener needs it."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.tables: dict[str, list[int]] = {}  # `find`'s, per closer string
        self.dollars: list[int] | None = None  # `dollar`'s: the Pandoc rule, not a closer string

    def find(self, start: int, closer: str) -> int:
        """`_find(text, start, closer)`."""
        if closer not in self.tables:
            text, n = self.text, len(self.text)
            res = [-1] * (n + 2)
            for p in range(n - 1, -1, -1):
                res[p] = p if text.startswith(closer, p) else res[p + (2 if text[p] == "\\" else 1)]
            self.tables[closer] = res
        return self.tables[closer][start] if start < len(self.text) else -1

    def dollar(self, i: int) -> int:
        """`_find_closing_dollar(text, i)`."""
        text, n = self.text, len(self.text)
        if i + 1 >= n or text[i + 1].isspace():
            return -1
        if self.dollars is None:
            res = [-1] * (n + 2)
            for p in range(n - 1, 0, -1):  # a walk starts after an opener, so never at 0
                c = text[p]
                if c == "\\":
                    res[p] = res[p + 2]
                elif c == "$" and p + 1 < n and text[p + 1] == "$":
                    res[p] = -1
                elif c == "$" and not text[p - 1].isspace() and not (p + 1 < n and text[p + 1].isdigit()):
                    res[p] = p
                else:
                    res[p] = res[p + 1]
            self.dollars = res
        return self.dollars[i + 1]


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
    """After `\\not` ending at `j` (spaces may follow, as TeX allows): the negated operator's name and
    where it ends, or None."""
    while j < len(text) and text[j] == " ":
        j += 1
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
    closers = _Closers(text)
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
                close = closers.find(i + 2, "\\)" if nxt == "(" else "\\]")
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
                    op = name not in GREEK
                    spelling = OPERATOR_COMMANDS[name] if op else GREEK[name]
                    if op and j < n and text[j] == "\u0338" and spelling in NEGATION:
                        spelling, j = NEGATION[spelling], j + 1  # `\\in` + a slash is `∉`
                    mask[i] = SUB
                    for k in range(i + 1, j):
                        mask[k] = JOIN
                    if subs is not None:
                        subs[i] = (spelling, op, j, i == name_end)
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
                close = closers.find(i + 2, "$$")
                mask[i + 1] = SEP
                if close >= 0:
                    math_until, close_len, opened = close, 2, i
                i += 2
                continue
            if not in_math:
                close = closers.dollar(i)
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


# An ASCII text with no `\` and no `$` holds no LaTeX (every mask entry is KEEP: math and commands need one
# of the two) and no character that NFKC, case-folding, marks or the operator table change beyond ASCII
# lower-casing, so its tokens are exactly its runs of ASCII letters and digits, lower-cased, each spanning
# itself (task-073). Most abstracts are such texts; a property pins this path to the loop below.
_ASCII_WORD = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[Token]:
    """Tokens of `text` with their raw code-point spans."""
    if _plain_ascii(text):
        return [Token(m.group().lower(), m.start(), m.end()) for m in _ASCII_WORD.finditer(text)]
    return _tokenize_each_char(text)


@dataclass(frozen=True, slots=True)
class Tail:
    """What `text` ends with after its last word or operator piece (`tokenize_with_tail`): the folded
    pieces, in order (`abcd⒈` → `.`, `vision-` → `-`, `x⑴` → `)`), and the raw offset of the character the
    first of them came from. Empty `pieces` means `text` ends on a letter, digit or operator piece (or has
    no piece at all). Invisible characters, dropped marks and LaTeX markup that joins a word are not pieces,
    and a marks-only run that makes no token (`vision-` + a lone vowel sign) leaves the tail as it was (`-`)."""

    start: int
    pieces: str


def tokenize_with_tail(text: str) -> tuple[list[Token], Tail]:
    """`tokenize(text)` plus its `Tail`, from the same pass: the lexer's detached-wildcard test (spec 02:
    a wildcard goes directly after a letter or digit, judged on the folded pieces)."""
    if _plain_ascii(text):
        tokens = tokenize(text)
        end = tokens[-1].end if tokens else 0
        return tokens, Tail(end, text[end:])
    out: list[Tail] = []
    tokens = _tokenize_each_char(text, out)
    return tokens, out[0]


def _plain_ascii(text: str) -> bool:
    """ASCII with no LaTeX: every character is a word character or a separator, as it stands (task-073)."""
    return text.isascii() and "\\" not in text and "$" not in text


def _tokenize_each_char(text: str, tail: list[Tail] | None = None) -> list[Token]:
    """`tokenize`'s definition for any text, one raw character at a time (steps 1-5 above). Given a `tail`
    list, it appends the text's `Tail` to it."""
    subs: dict[int, tuple[str, bool, int, bool]] = {}
    latex = _latex_mask(text, subs=subs)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0
    base: str | None = None
    lead: int | None = None  # where markup before a word began (`\\"{O}del`): the word's span starts there
    # The separator pieces since the last word or operator TOKEN (the Tail). A word clears it only when it
    # is emitted: a marks-only word (`-` + a lone vowel sign) is dropped, so the `-` stays what the text ends
    # with (M3a gate round 2: clearing it on the mark let `vision-ަ*` pass as `vision*`).
    rest: list[str] = []
    rest_start = len(text)

    def close() -> None:
        nonlocal buf, rest
        if buf:
            word = unicodedata.normalize("NFC", "".join(buf))
            # A run of marks with no letter (a lone vowel sign) is not a word.
            if not all(unicodedata.category(ch).startswith("M") for ch in word):
                out.append(Token(word, start, end))
                rest = []
            buf = []

    n = len(text)
    # The run of combining marks last found (TASK-067): it ends at `run_end`, and `run_slash` is one past its
    # last slash (the run's start if it has none). A mark inside a run reuses them, so a run is scanned once,
    # not once per mark (quadratic: a `q` or an abstract of a few thousand marks cost seconds).
    run_end = run_slash = 0
    i = 0
    while i < n:
        c, stop = text[i], i + 1
        if latex[i] == SUB:  # a math command with a Unicode spelling; its span starts at its name
            spelling, operator, cmd_end, split = subs[i]
            if operator or split:
                close()
            if operator:  # a token of its own
                out.append(Token(spelling, i + 1, cmd_end, op=True))
                base = None
            else:  # a Greek letter: part of the word, like the letter itself
                folded, base = _fold(spelling, base)
                if not buf:
                    start = i + 1 if lead is None else lead
                buf.extend(p for p in folded if isinstance(p, str))
                end = cmd_end
            rest = []
            lead = None
            # an operator's name is its own token's: skip it, so no word after it starts inside it (`\\leq5`)
            i = cmd_end if operator else i + 1
            continue
        if latex[i] == SEP:
            close()
            base = lead = None
            if not rest:
                rest_start = i
            rest.append(c)
            i += 1
            continue
        if latex[i] == JOIN:  # markup inside a word: keep the word open and cover the markup in its span
            if buf:
                end = i + 1
            elif lead is None:  # markup before any letter: a word starting next starts here
                lead = i
            i += 1
            continue
        first, lead = lead, None
        if c < "\x80" and (stop == n or not unicodedata.combining(text[stop])):
            # an ASCII character with no mark after it (most characters of most texts; task-073): `_fold`
            # would give it back lower-cased, and it is a word character exactly when it is alphanumeric
            if c.isalnum():
                if not buf:
                    start = i if first is None else first
                base = c.lower()
                buf.append(base)
                end = stop
            else:
                close()
                base = None
                if not rest:
                    rest_start = i
                rest.append(c)
            i = stop
            continue
        if i + 1 > run_end:  # past the last run found: find where the marks after i end, and the last slash
            run_end = run_slash = i + 1
            while run_end < n and latex[run_end] == KEEP and unicodedata.combining(text[run_end]):
                if text[run_end] == "\u0338":
                    run_slash = run_end + 1
                run_end += 1
        j = run_end  # whether a position continues a run doesn't depend on where the run began
        cluster = run_slash > i + 1  # a slash among text[i + 1 : j]
        if cluster:
            # a slash among the marks after a character: NFKC the whole cluster, as the whole-string rule
            # would (`∈` + slash is `∉`, full-width `＝` + slash is `≠`, whatever the marks' order)
            c, stop = text[i:j], j
        folded, folded_base = _fold(c, base)
        spans = _cluster_spans(text, i, j, folded, base) if cluster else [(i, stop)] * len(folded)
        base = folded_base
        if not folded:  # combining mark or invisible format char: extends an open word, never starts one
            if buf:
                end = stop
            i = stop
            continue
        for piece, (piece_start, piece_end) in zip(folded, spans, strict=True):
            if isinstance(piece, _Op):
                close()
                out.append(Token(piece.name, piece_start, piece_end, op=True))
                rest = []
            elif _is_word_char(piece):
                if not buf:
                    start = piece_start if first is None else first
                buf.append(piece)
                end = piece_end
            else:
                close()
                if not rest:
                    rest_start = i
                rest.append(piece)
            # markup before this character belongs to its first piece only: a word that starts after an
            # operator or a separator piece (`\\"∭` + slash + U+0345 → int ×3, then ι) starts at its own piece (task-075)
            first = None
        i = stop
    close()
    if tail is not None:
        tail.append(Tail(rest_start, "".join(rest)) if rest else Tail(len(text), ""))
    return out


def normalize(text: str) -> list[str]:
    """The tokens of `text` (spec 02 §Token semantics). The index is fed `" ".join(normalize(field))`."""
    return [t.text for t in tokenize(text)]
