"""The served tokenizer versions (`SERVED_TOKENIZERS`, index-versioning skill): version 2 stays byte-stable while an
index built with it may be pinned by a search record, and version 3 reads every Unicode form of a text alike.

- Version 2 equals a frozen copy of itself (`tests/unit/tokenizer_v2/`, `normalize.py` and `mathsyms.py` as they
  stood when version 3 replaced them): tokens with their spans and `op`, the `Tail`, the math regions.
- Version 3 is version 2 run on the NFKC form of the whole text (step 1 before step 4): the same tokens, and the
  same spans on a text already in NFKC; its NFC, NFD, NFKC and NFKD forms give the same token texts (TASK-168's
  finding: `Caf\\é` split in NFD, `caf` only).
"""

import unicodedata
from itertools import pairwise

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from openproceedings.query.normalize import (
    SERVED_TOKENIZERS,
    TOKENIZER_VERSION,
    first_math_end,
    math_regions,
    normalize,
    tokenize,
    tokenize_with_tail,
)
from openproceedings.query.parser import parse

from tests.unit.test_normalize import full
from tests.unit.tokenizer_v2 import normalize as frozen_v2

FORMS = ("NFC", "NFD", "NFKC", "NFKD")
# LaTeX syntax, accented letters in several forms, compatibility characters (ligatures, full-width syntax,
# superscripts), marks that compose or reorder, and Hangul jamo that compose across characters
PIECES = [
    "\\", "$", "$$", "\\(", "\\)", "\\[", "\\]", "{", "}", "^", "_", " ", "a", "e", "O", "5", '\\"', "\\'", "\\H",
    "\\v", "\\c", "\\-", "\\i", "\\alpha", "\\leq", "\\not", "\\in", "=", "é", "é", "ő", "ő", "ö",
    "́", "̈", "̸", "ͅ", "̣", "̂", "ﬁ", "²", "½", "⑴", "＼", "＄", "﹩", "﹨", "（",
    "ｅ", "Å", "Å", "ᄀ", "ᅡ", "ᆨ", "가", "中", "​", "­", "-", "%", "&",
]  # fmt: skip
LATEXISH = st.lists(st.sampled_from(PIECES), max_size=14).map("".join)
ANY_TEXT = st.one_of(st.text(max_size=60), LATEXISH)


def test_the_served_versions_are_the_current_one_and_the_one_before() -> None:
    assert TOKENIZER_VERSION == "3" and list(SERVED_TOKENIZERS) == ["2", "3"]
    assert [form.nfkc_first for form in SERVED_TOKENIZERS.values()] == [False, True]


@pytest.mark.parametrize("version", ["1", "4", "", "3 "])
def test_a_version_this_code_does_not_serve_is_refused(version: str) -> None:
    for call in (tokenize, tokenize_with_tail, normalize):
        with pytest.raises(ValueError, match="not one this code serves"):
            call("plain text", version)


# --- version 2: byte-stable ----------------------------------------------------------------------------------
@given(
    ANY_TEXT.flatmap(lambda t: st.sampled_from([unicodedata.normalize(f, t) for f in (*FORMS, "NFC")] + [t]))
)
@example("Caf\\é")  # TASK-168: version 2's own answer, `caf`, stays its answer
@example("Erd\\H{ő}s")
@example("＄\\alpha＄")
def test_version_2_equals_its_frozen_copy(text: str) -> None:
    assert full(tokenize(text, "2")) == full(frozen_v2.tokenize(text))
    tokens, tail = tokenize_with_tail(text, "2")
    frozen_tokens, frozen_tail = frozen_v2.tokenize_with_tail(text)
    assert (full(tokens), tail.start, tail.pieces) == (
        full(frozen_tokens),
        frozen_tail.start,
        frozen_tail.pieces,
    )
    assert math_regions(text, "2") == frozen_v2.math_regions(text)
    assert first_math_end(text, "2") == frozen_v2.first_math_end(text)


# --- version 3: every Unicode form alike ---------------------------------------------------------------------
@given(ANY_TEXT)
@example("Caf\\é")
@example("Erd\\H{ő}s")
@example("x \\ﬁne $x^²$ ＼emph{y}")
@example("\\가")  # jamo that compose into one syllable after a backslash
def test_every_unicode_form_of_a_text_tokenizes_alike(text: str) -> None:
    tokens = normalize(text)
    for form in FORMS:
        assert normalize(unicodedata.normalize(form, text)) == tokens, (form, text)


@given(ANY_TEXT)
def test_version_3_is_version_2_on_the_nfkc_form(text: str) -> None:
    nfkc = unicodedata.normalize("NFKC", text)
    assert normalize(text) == normalize(nfkc, "2")
    # a text already in NFKC is read as it stands: spans, `op` and the tail too
    assert full(tokenize(nfkc)) == full(tokenize(nfkc, "2"))
    assert tokenize_with_tail(nfkc)[1] == tokenize_with_tail(nfkc, "2")[1]
    assert math_regions(nfkc) == math_regions(nfkc, "2")


@given(ANY_TEXT)
@example("$\\alpha$\u0301 \uff04x\uff04")
@example("\\(\\)")
def test_version_3_math_regions_are_the_nfkc_forms_in_raw_offsets(text: str) -> None:
    """Each region is one of the NFKC form's, in raw offsets: in order, disjoint, and its raw text's NFKC form
    opens and closes math (`$`, `$$`, `\\(`, `\\[` … their closers)."""
    nfkc = unicodedata.normalize("NFKC", text)
    regions = math_regions(text)
    assert len(regions) == len(math_regions(nfkc))
    for (_, end), (start, _) in pairwise(regions):
        assert end <= start
    for start, end in regions:
        assert 0 <= start < end <= len(text)
        inner = unicodedata.normalize("NFKC", text[start:end])
        assert inner.startswith(("$", "\\(", "\\[")) and inner.endswith(("$", "\\)", "\\]")), (text, inner)
    # `first_math_end` is the decision at position 0 for `$…$` and `$$…$$`
    at_zero = next((e for s, e in regions if s == 0), -1)
    assert first_math_end(text) == (at_zero if nfkc.startswith("$") else -1)


@given(ANY_TEXT)
def test_version_3_tails_read_the_nfkc_form(text: str) -> None:
    tokens, tail = tokenize_with_tail(text)
    assert full(tokens) == full(tokenize(text))
    assert tail.pieces == tokenize_with_tail(unicodedata.normalize("NFKC", text))[1].pieces
    assert 0 <= tail.start <= len(text) and (tail.pieces or tail.start == len(text))


@pytest.mark.parametrize(
    ("text", "spans"),
    [
        ("Caf\\é", [(0, 3), (4, 6)]),  # NFD: `e` spans the letter and its accent
        ("Caf\\é", [(0, 3), (4, 5)]),
        ("Erd\\H{ő}s", [(0, 10)]),
        ("x \\ﬁne y", [(0, 1), (7, 8)]),  # `\fine` is dropped markup
        ("$x^²$", [(1, 4)]),  # `x2`: the script joins, as `$x^2$`
        ("＼emph{x}", [(6, 7)]),
        ("가 b", [(0, 2), (3, 4)]),  # jamo compose into one syllable: one word over both
        ("≠ͅ", [(0, 1), (1, 3)]),  # interleaved marks: as version 2 (task-075)
    ],
    ids=ascii,
)
def test_version_3_spans_are_raw(text: str, spans: list[tuple[int, int]]) -> None:
    assert [(t.start, t.end) for t in tokenize(text)] == spans


# --- the query side: a query typed in NFC or NFD means the same --------------------------------------------
QUERY_PIECES = [*PIECES, '"', "(", ")", "|", "*", "OR", "AND", "-", "title:", "NEAR/2", "trust", "model"]


@given(st.lists(st.sampled_from(QUERY_PIECES), max_size=14).map(" ".join))
@example("Caf\\é OR Erd\\H{ő}s")
@example('"na\\"{ï}ve model$"')
def test_a_query_parses_alike_in_nfc_and_nfd(q: str) -> None:
    """Canonical equivalence changes no syntax character the lexer reads (quotes, parentheses, `|`, `:`, `-`,
    `*`, `$`, `\\`, spaces, digits), so a query and its NFC and NFD forms lex to the same words; tokenizer 3 then
    reads each word alike, so they parse to the same canonical string (or fail with the same errors)."""
    nfc, nfd = (parse(unicodedata.normalize(f, q)) for f in ("NFC", "NFD"))
    assert nfc.canonical == nfd.canonical
    assert [e.code for e in nfc.errors] == [e.code for e in nfd.errors]
