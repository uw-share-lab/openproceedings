"""Properties of the tokenizer beyond the golden table: offsets, idempotence, and agreement with the simple
whole-string definition of the token contract (spec 02 §Token semantics)."""

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.query.mathsyms import GREEK, LETTER_LOOKALIKES, OPERATOR_COMMANDS, OPERATORS
from openproceedings.query.normalize import TOKENIZER_VERSION, Token, normalize, tokenize

# Text without LaTeX syntax: the whole-string reference below doesn't model LaTeX.
PLAIN = st.text(alphabet=st.characters(blacklist_characters="\\$", blacklist_categories=("Cs",)), max_size=60)


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
        t = time.perf_counter()
        normalize(text)
        return time.perf_counter() - t

    secs(1000)  # warm up
    small, large = min(secs(5_000) for _ in range(3)), min(secs(20_000) for _ in range(3))
    assert large < small * 8  # 4× the input: linear is ~4×, quadratic ~16×


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
    ],
)
def test_leading_accent_markup_is_in_the_word_span(text: str, spans: list[tuple[int, int]]) -> None:
    assert [(t.start, t.end) for t in tokenize(text)] == spans
