"""Properties of the tokenizer beyond the golden table: offsets, idempotence, and agreement with the simple
whole-string definition of the token contract (spec 02 §Token semantics)."""

import unicodedata

from hypothesis import given
from hypothesis import strategies as st
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
    s = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text).casefold())
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
