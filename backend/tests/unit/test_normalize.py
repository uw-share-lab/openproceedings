"""Properties of the tokenizer beyond the golden table: offsets, idempotence, and agreement with the simple
whole-string definition of the token contract (spec 02 §Token semantics)."""

import unicodedata
from itertools import pairwise

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from openproceedings.query.mathsyms import GREEK, LETTER_LOOKALIKES, OPERATOR_COMMANDS, OPERATORS
from openproceedings.query.normalize import (
    TOKENIZER_VERSION,
    Tail,
    Token,
    _tokenize_each_char,
    normalize,
    tokenize,
    tokenize_with_tail,
)

# Text without LaTeX syntax: the whole-string reference below doesn't model LaTeX. Tokenizer 3 reads the NFKC
# form, so the characters whose NFKC form is `\` or `$` (full-width, small) are LaTeX syntax too.
LATEX_SYNTAX = "\\$\uff3c\uff04\ufe68\ufe69"
PLAIN = st.text(
    alphabet=st.characters(blacklist_characters=LATEX_SYNTAX, blacklist_categories=("Cs",)), max_size=60
)


# The per-script mark rule, computed a different way from the implementation: the implementation checks a
# base letter's Unicode name at runtime; the reference precomputes the full set of folding bases once, by
# scanning the whole Unicode database. (Spec 02: a mark folds when its base's name begins with LATIN, GREEK,
# CYRILLIC, HEBREW, ARABIC or EXTENDED ARABIC, or the base is an ASCII digit named DIGIT …)
def _names_starting(*prefixes: str) -> frozenset[str]:
    out = set()
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        if unicodedata.name(chr(cp), "").startswith(prefixes):
            out.add(chr(cp))
    return frozenset(out)


FOLDING_BASES = _names_starting("LATIN", "GREEK", "CYRILLIC", "HEBREW", "ARABIC", "EXTENDED ARABIC", "DIGIT")
CYRILLIC_BASES = _names_starting("CYRILLIC")
ARABIC_BASES = _names_starting("ARABIC", "EXTENDED ARABIC")
KEPT_ON = {"\u0306": CYRILLIC_BASES, "\u0654": ARABIC_BASES, "\u0655": ARABIC_BASES}
INVISIBLE_SEPARATORS = {"\u2061", "\u2062", "\u2063", "\u2064"}


def _block_folds(base: str | None, mark: str) -> bool:
    if base is None:
        return True
    if mark in KEPT_ON and base in KEPT_ON[mark]:
        return False
    return base in FOLDING_BASES


def _invisible(c: str) -> bool:
    cp = ord(c)
    return (
        unicodedata.category(c) in ("Cf", "Me")
        or 0xFE00 <= cp <= 0xFE0F
        or 0xE0100 <= cp <= 0xE01EF
        or 0x180B <= cp <= 0x180F
        or cp == 0x034F
    )


def reference(text: str) -> list[str]:
    """The token contract stated as simply as possible, over the whole string (no LaTeX)."""
    # NFKC first (it composes `∈` + U+0338 into `∉`); then an operator is its own word, and a look-alike
    # letter (`∆`) is the letter
    text = unicodedata.normalize("NFKC", text)
    text = "".join(f" {OPERATORS[c]} " if c in OPERATORS else LETTER_LOOKALIKES.get(c, c) for c in text)
    s = unicodedata.normalize("NFD", text.casefold())
    kept, base = [], None
    for c in s:
        if c in INVISIBLE_SEPARATORS:
            kept.append(" ")
            base = None
            continue
        if _invisible(c):
            continue  # format chars, variation selectors, enclosing marks, CGJ: join
        if unicodedata.combining(c):
            if not _block_folds(base, c):
                kept.append(c)
            continue
        kept.append(c)
        base = c if (c.isalnum() or unicodedata.category(c).startswith("M")) else None
    s = unicodedata.normalize("NFC", "".join(kept))  # recompose (Hangul, kept marks)
    words, cur = [], []
    for c in s:
        if c.isalnum() or unicodedata.category(c).startswith("M"):
            cur.append(c)
        elif cur:
            words.append("".join(cur))
            cur = []
    if cur:
        words.append("".join(cur))
    return [w for w in words if not all(unicodedata.category(ch).startswith("M") for ch in w)]


@given(PLAIN)
def test_char_by_char_tokenizer_equals_the_whole_string_definition(text: str) -> None:
    assert normalize(text) == reference(text)


@given(st.text(max_size=80))
def test_reindexing_normalised_text_is_idempotent(text: str) -> None:
    # The index is fed " ".join(tokens); re-tokenising that must give the same tokens (tokenizer parity).
    tokens = normalize(text)
    assert normalize(" ".join(tokens)) == tokens


@given(st.text(max_size=80))
def test_every_token_maps_back_to_a_raw_span_that_produces_it(text: str) -> None:
    toks = tokenize(text)
    assert [t.text for t in toks] == normalize(text)
    last_start = 0
    for t in toks:
        assert 0 <= t.start < t.end <= len(text)
        # Starts never go backwards. Spans may coincide: one raw char can yield two tokens ("½" → "1", "2").
        assert t.start >= last_start
        last_start = t.start
        assert t.text  # never an empty token


@given(st.text(max_size=80))
def test_tokens_have_no_separator_characters(text: str) -> None:
    for tok in normalize(text):
        assert " " not in tok and tok == tok.casefold()


def test_spans_point_at_the_raw_text() -> None:
    text = "The ﬁne-tuned GPT-4o's naïve \\textit{TrustLLM}"
    got = [(t.text, text[t.start : t.end]) for t in tokenize(text)]
    assert got == [
        ("the", "The"),
        ("fine", "ﬁne"),
        ("tuned", "tuned"),
        ("gpt", "GPT"),
        ("4o", "4o"),
        ("s", "s"),
        ("naive", "naïve"),
        ("trustllm", "TrustLLM"),
    ]


def test_decomposed_input_span_covers_the_combining_mark() -> None:
    text = "café au lait"
    first = tokenize(text)[0]
    assert (first.text, text[first.start : first.end]) == ("cafe", "café")


def test_accent_macro_markup_is_inside_the_span() -> None:
    text = "r\\'esum\\'e"
    assert [(t.text, text[t.start : t.end]) for t in tokenize(text)] == [("resume", text)]


def test_token_is_frozen() -> None:
    t = Token("trust", 0, 5)
    try:
        t.text = "x"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Token must be immutable")


def test_tokenizer_version_is_a_nonempty_string() -> None:
    assert isinstance(TOKENIZER_VERSION, str) and TOKENIZER_VERSION


# Adversarial alphabet: combining marks after ligatures and compatibility forms, loose Hangul jamo that only
# compose with their neighbours, case-folding specials, format characters and dash variants.
TRICKY_ALPHABET = [
    *"aeiouAEIOU0129 -_.'",
    # combining marks and Indic signs
    "\u0301",
    "\u0308",
    "\u030a",
    "\u0327",
    "\u0307",
    "\u094d",
    "\u093e",
    # compatibility forms and case-folding specials
    "\ufb01",
    "\ufb00",
    "\u00bd",
    "\u00b2",
    "\u2460",
    "\uff2c",
    "\u00df",
    "\u0130",
    "\u01c5",
    "\u03a3",
    "\u03c2",
    "\u00c5",
    "\u212b",
    "\u2122",
    "\u2026",
    # Hangul: leading, vowel and trailing jamo, a syllable, a compatibility jamo
    "\u1100",
    "\u1161",
    "\u11a8",
    "\uc2e0",
    "\u3131",
    # format characters and dash/space variants
    "\u00ad",
    "\u200b",
    "\u200d",
    "\u2010",
    "\u2013",
    "\u2212",
    "\u00a0",
    # Devanagari and Arabic letters and marks
    "\u0915",
    "\u093f",
    "\u0652",
    "\u062b",
    "\u0642",
]
TRICKY = st.text(alphabet=st.sampled_from(TRICKY_ALPHABET), max_size=40)


@given(TRICKY)
def test_adversarial_char_by_char_equals_whole_string_definition(text: str) -> None:
    assert normalize(text) == reference(text)


@given(TRICKY)
def test_adversarial_reindexing_is_idempotent(text: str) -> None:
    tokens = normalize(text)
    assert normalize(" ".join(tokens)) == tokens


# --- decision-006: every table entry, both spellings, one token -----------------------------------------------


@pytest.mark.parametrize("name", sorted(GREEK))
def test_every_greek_command_is_its_letter(name: str) -> None:
    assert normalize(f"${chr(92)}{name}$") == normalize(GREEK[name])


@pytest.mark.parametrize("command", sorted(OPERATOR_COMMANDS))
def test_every_operator_command_is_its_operators_token(command: str) -> None:
    name = OPERATOR_COMMANDS[command]
    assert normalize(f"$a {chr(92)}{command} b$") == ["a", name, "b"]
    symbols = [c for c, n in OPERATORS.items() if n == name]
    assert all(normalize(f"a {c} b") == ["a", name, "b"] for c in symbols)


def test_command_tokens_span_the_command_name() -> None:
    assert tokenize("$\\le$") == [Token("leq", 2, 4, op=True)]
    assert tokenize("$x\\alpha$") == [Token("xα", 1, 8)]
    assert tokenize("$\\alpha$") == [Token("α", 2, 7)]
    assert tokenize("$\\not\\in$") == [Token("notin", 2, 8, op=True)]
    assert tokenize("a ∈\u0338 b") == [Token("a", 0, 1), Token("notin", 2, 4, op=True), Token("b", 5, 6)]
    assert tokenize("5×3") == [Token("5", 0, 1), Token("times", 1, 2, op=True), Token("3", 2, 3)]


def test_script_join_is_linear() -> None:
    import time

    def secs(n: int) -> float:
        text = "$" + "^{a" * n + "x$"
        t = time.thread_time()  # CPU time: being preempted on a busy machine doesn't count
        normalize(text)
        return time.thread_time() - t

    secs(1000)  # warm up
    # best of 9: one busy moment on a shared machine can't push the ratio over (task-070's lesson)
    small, large = min(secs(5_000) for _ in range(9)), min(secs(20_000) for _ in range(9))
    assert large < small * 8  # 4× the input: linear is ~4×, quadratic ~16×


@pytest.mark.parametrize("text", ["\u0301", "a\u0301"])
def test_a_run_of_marks_is_linear(text: str) -> None:
    # TASK-067: each mark rescanned the rest of its run, so a query or abstract of a few thousand marks cost
    # seconds; a mark-heavy `q` is anyone's to send
    import time

    def secs(n: int) -> float:
        body = text + "\u0301" * n
        t = time.thread_time()
        tokenize(body)
        return time.thread_time() - t

    secs(1000)
    small, large = min(secs(5_000) for _ in range(9)), min(secs(20_000) for _ in range(9))
    assert large < small * 8


@pytest.mark.parametrize(
    ("text", "spans"),
    [
        ('\\"{O}del', [(0, 8)]),  # a word that begins with an accent macro starts at its backslash (task-074)
        ("\\v{S}ekar", [(0, 9)]),
        ('x \\"{O}del', [(0, 1), (2, 10)]),
        ("\\'{E}cole and \\H{O}", [(0, 9), (10, 13), (14, 19)]),
        ('a \\"{\\i}ve', [(0, 1), (2, 10)]),
        ('G\\"odel', [(0, 7)]),  # inside a word: unchanged
        ("\\-mark", [(0, 6)]),
        ("$n\\leq5$", [(1, 2), (3, 6), (6, 7)]),  # after an operator command, a word starts after its name
        ("$^2x$", [(1, 4)]),  # a script that opens a word is markup too: `^2x` lights the caret
        ("CT$^2$S", [(0, 2), (3, 5), (6, 7)]),
        ("$_{ij}$", [(1, 6)]),
        ("$\\neq1$", [(2, 5), (5, 6)]),
        ("$\\not=x$", [(2, 6), (6, 7)]),
        ("$3\\times10^5$", [(1, 2), (3, 8), (8, 12)]),
    ],
)
def test_leading_accent_markup_is_in_the_word_span(text: str, spans: list[tuple[int, int]]) -> None:
    assert [(t.start, t.end) for t in tokenize(text)] == spans


# A slash cluster (task-075): a character, then combining marks including U+0338 (SL below), folded whole.
# Each piece spans the raw characters it came from, so two tokens share at most one multi-piece code point.
@pytest.mark.parametrize(
    ("text", "spans"),
    [
        ("x\u00bd\u0338y", [(0, 2), (1, 4)]),  # x 1/2 SL y -> x1, 2y: they share the 1/2 and only it
        ("x\u00bdy", [(0, 2), (1, 3)]),  # no slash: unchanged
        ("x\u00bd\u0338", [(0, 2), (1, 3)]),  # the last piece's token covers the slash
        ("x\u2474\u0338y", [(0, 1), (1, 2), (3, 4)]),  # parenthesized 1 is `(1)`; SL is on `)`, not on 1
        ("x\u222c\u0338y", [(0, 1), (1, 2), (1, 3), (3, 4)]),  # double integral SL -> int, int
        ("\u01c6\u0338", [(0, 2)]),  # dz digraph SL -> dz: one word, the whole cluster
        ("a \u2208\u0338 b", [(0, 1), (2, 4), (5, 6)]),  # element-of SL composes to notin: the whole cluster
        # U+0345 (ypogegrammeni) folds to the letter iota: after a piece that isn't a letter it starts a word
        # at its own mark, and the pieces before it end there
        ("=\u0338\u0345x", [(0, 2), (2, 4)]),  # neq, iota x
        ("\u2a76\u0338\u0345x", [(0, 2), (2, 4)]),  # `===` SL -> `==` neq iota: found by a 300k differential
        # Trade-off: marks in the other order. The slash belongs to neq, but neq ends at the first U+0345
        # and the slash falls in iota's span: contiguous spans can't split interleaved marks, so the one
        # exception is "pieces before the first U+0345 end at it" (spec 02), and nothing overlaps
        ("=\u0345\u0338", [(0, 1), (1, 3)]),
        ("\u2208\u0338\u0345", [(0, 2), (2, 3)]),  # notin, iota
        (
            "\u03b1\u0338\u0345",
            [(0, 3)],
        ),  # after a letter, iota joins its word (alpha iota): the whole cluster
        # accent markup before a character belongs to its first piece: a word after an operator or separator
        # piece starts at its own piece, never back at the markup (starts would go backwards)
        ('\\"\u222d\u0338\u0345', [(2, 3), (2, 3), (2, 4), (4, 5)]),  # triple integral SL iota: int x3, iota
        ('\\"\u2474', [(2, 3)]),  # parenthesized 1: `(` is a separator piece, so 1 doesn't take the markup
        ('\\"\u00bd', [(0, 3), (2, 3)]),  # 1/2: 1 is the first piece and takes it; 2 shares the 1/2
    ],
)
def test_slash_cluster_pieces_span_what_they_came_from(text: str, spans: list[tuple[int, int]]) -> None:
    assert [(t.start, t.end) for t in tokenize(text)] == spans


LATEX_PIECES = ["$", "\\(", "\\)", " ", "a", "O", "5", "{", "}", "^", "_", '\\"', "\\'", "\\v", "\\H", "\\-",
                "\\leq", "\\times", "\\alpha", "\\not", "=", "\\in", "\u0301", "\u200b", "中", "é", "-",
                "\u00bd", "\u2474", "\u0338", "\u0345"]  # fmt: skip


@given(
    st.lists(st.sampled_from(LATEX_PIECES), max_size=12)
    .map("".join)
    .flatmap(lambda t: st.sampled_from([t, f"${t}$"]))
)
@example("a\u00bd\u0338a")  # task-075: `a1` and `2a` overlapped on the 1/2 and the slash
@example("=\u0338\u0345")  # task-075: neq and the iota word both spanned the whole cluster
@example('\\"\u222d\u0338\u0345')  # task-075: the iota word took the markup's start, before the ints'
def test_token_spans_are_valid_and_never_overlap(text: str) -> None:
    tokens = tokenize(text)
    for t in tokens:
        assert 0 <= t.start < t.end <= len(text), (text, t)
    for a, b in pairwise(tokens):
        assert a.start <= b.start, (text, a, b)
        # Two spans overlap only on one code point that NFKC folds to several pieces (`½` → 1, 2), each piece's
        # token covering it; the marks of a slash cluster belong to the pieces they fold into (task-075)
        if b.start < a.end:
            shared = text[b.start : a.end]
            assert len(shared) == 1 and len(unicodedata.normalize("NFKC", shared)) > 1, (text, a, b)


def full(tokens: list[Token]) -> list[tuple[str, int, int, bool]]:
    """Everything a token carries."""
    return [(t.text, t.start, t.end, t.op) for t in tokens]


# --- the Tail: what a text ends with after its last word or operator piece (the lexer's detached-wildcard
# test, spec 02 "directly after a letter or digit", judged on the folded pieces; decision-008) ---------------
@pytest.mark.parametrize(
    ("text", "start", "pieces"),
    [
        ("abcd⒈", 4, "."),  # `1.`: the `1` joins the word, the `.` is the tail
        ("abcd⒈̸", 4, "."),  # the slash on the `.` folds away
        ("abcd⑴", 4, ")"),  # `(1)`
        ("abcd½", 5, ""),  # `1⁄2`: ends on `2`
        ("abcd≠ͅ", 6, ""),  # neq, then iota: a letter
        ("abc×", 4, ""),  # ends on an operator piece (the lexer's own message covers it)
        ("vision-", 6, "-"),
        ("abc．", 3, "."),  # full-width full stop
        ("abc\\%", 3, "\\%"),  # LaTeX separators are pieces
        ("bench\\-", 7, ""),  # markup that joins the word is not
        ("abcé", 5, ""),  # nor is a mark that folds away
        ("abc⁡", 3, " "),  # an invisible math operator separates
        ("\u0ce2", 1, ""),  # a lone vowel sign: no token and no piece
        ("abcd-\u0ce2", 4, "-"),  # the vowel sign after `-` is not a piece: the tail is still `-`
        ("", 0, ""),
        ("...", 0, "..."),
    ],
    ids=ascii,
)
def test_tail_is_the_folded_pieces_after_the_last_word(text: str, start: int, pieces: str) -> None:
    tokens, tail = tokenize_with_tail(text)
    assert tail == Tail(start, pieces)
    assert full(tokens) == full(tokenize(text))


@given(
    st.one_of(
        PLAIN,
        st.lists(st.sampled_from([*LATEX_PIECES, "⒈", "⑴", "½", "×", "."]), max_size=12).map("".join),
    )
)
@example("abcd⒈̸")
@example("abcd⑴")
@example("\u0ce2")  # nightly: a lone vowel sign makes no token, but `x` after it joins it (U+0CE2 then `x`)
@example("abcd-\u0ce2")
@example("abc-\u0301")
def test_tail_says_whether_a_letter_after_the_text_joins_its_last_word(text: str) -> None:
    """Independent of how the tail is tracked: a letter written after a text with a tail is a word of its
    own; after a text that ends on a word piece it extends that word. A word of its own may start with the
    marks-only run the text ends with (a lone vowel sign, combining class 0): alone it made no token."""
    tokens, tail = tokenize_with_tail(text)
    assert full(tokens) == full(tokenize(text))
    assert 0 <= tail.start <= len(text) and (tail.pieces or tail.start == len(text))
    if "$" in text or "\\" in text:
        return  # an appended letter can change what LaTeX means (`\cmd` + x, a math closer before x)
    after = normalize(text + "x")
    if tail.pieces or not tokens or tokens[-1].op:
        assert after and after[:-1] == [t.text for t in tokens], (text, tail)
        head, last = after[-1][:-1], after[-1][-1]
        assert last == "x" and all(unicodedata.category(c).startswith("M") for c in head), (text, tail)
        # it starts on a mark of class 0: a stray combining mark (`abc-` + U+0301) is dropped, never kept
        assert not head or (
            unicodedata.category(head[0]) in ("Mn", "Mc") and not unicodedata.combining(head[0])
        ), (text, tail)
    else:
        assert after == [t.text for t in tokens[:-1]] + [tokens[-1].text + "x"], (text, tail)


_MARKS_AND_FORMATS = [
    chr(c)
    for c in range(0x80, 0x30000)
    if unicodedata.category(chr(c)) in ("Mn", "Mc", "Me", "Cf", "Lm", "Sk")
]


@pytest.mark.parametrize("sep", ["-", ".", "/"])
def test_a_mark_that_makes_no_word_keeps_the_separator_in_the_tail(sep: str) -> None:
    """M3a gate round 2 (exactness-guardian): a vowel sign after a separator folds to a word piece, but a
    marks-only word is dropped, so the separator is still what the text ends with. Every mark, format
    character, modifier letter and modifier symbol after each separator: when no token starts after the
    separator, the tail keeps it."""
    wrong = []
    for c in _MARKS_AND_FORMATS:
        text = f"abcd{sep}{c}"
        tokens, tail = tokenize_with_tail(text)
        if all(t.start < 5 for t in tokens) and not tail.pieces.startswith(sep):
            wrong.append((c, tail))
    assert wrong == []


# --- task-073's fast paths (the whole-text ASCII path in `tokenize`, the ASCII branch of the loop) rely on
# no ASCII character folding to an operator or a letter look-alike (exactness-guardian, M3a gate) -------------
def test_no_operator_or_letter_lookalike_is_ascii() -> None:
    assert [c for c in OPERATORS if any(ch.isascii() for ch in c)] == []
    assert [c for c in LETTER_LOOKALIKES if any(ch.isascii() for ch in c)] == []


@pytest.mark.parametrize(
    "text", [chr(c) for c in range(128)] + [f"a{chr(c)}b" for c in range(128)], ids=ascii
)
def test_every_ascii_character_tokenizes_the_same_on_the_fast_paths(text: str) -> None:
    assert full(tokenize(text)) == full(_tokenize_each_char(text))
    slow: list[Tail] = []
    _tokenize_each_char(text, slow)
    assert [tokenize_with_tail(text)[1]] == slow
