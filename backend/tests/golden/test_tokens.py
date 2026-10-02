"""Golden token table: the token contract (spec 02 §Token semantics, token-contract skill), pinned case by case.

Add a row for every bug ever found; never delete one. A change that alters any row is a TOKENIZER_VERSION bump.
Every row runs under every served tokenizer version (`SERVED_TOKENIZERS`): a row whose tokens changed in a later
version keeps its old tokens here and names its new ones in that version's table (`CHANGED_IN_3`).
"""

import unicodedata

import pytest
from openproceedings.query.normalize import SERVED_TOKENIZERS, TOKENIZER_VERSION, normalize

GOLDEN: list[tuple[str, list[str]]] = [
    # --- the token-contract skill's own table --------------------------------------------------------
    ("Benchmarking LLMs", ["benchmarking", "llms"]),
    ("Trust-aware", ["trust", "aware"]),
    ("Vision–Language", ["vision", "language"]),  # en dash
    ("naïve Bayes", ["naive", "bayes"]),
    ("GPT-4o", ["gpt", "4o"]),
    ("model's", ["model", "s"]),
    ("$\\epsilon$-DP", ["ε", "dp"]),
    ("\\textit{TrustLLM}", ["trustllm"]),
    ("ﬁne-tuning", ["fine", "tuning"]),  # ligature
    ("STRASSE", ["strasse"]),
    ("Straße", ["strasse"]),
    # --- no stemming, no stopwords, no synonyms (guarantee 1) ----------------------------------------
    ("benchmark", ["benchmark"]),
    ("benchmarks", ["benchmarks"]),
    ("benchmarking", ["benchmarking"]),
    ("trust", ["trust"]),
    ("trustworthy", ["trustworthy"]),
    ("trustworthiness", ["trustworthiness"]),
    ("distrust", ["distrust"]),
    ("trust in AI", ["trust", "in", "ai"]),
    ("the a an of to and or not", ["the", "a", "an", "of", "to", "and", "or", "not"]),
    ("running ran runs", ["running", "ran", "runs"]),
    ("LLM LLMs", ["llm", "llms"]),
    ("evaluation evaluate evaluating", ["evaluation", "evaluate", "evaluating"]),
    ("models model's modelling", ["models", "model", "s", "modelling"]),
    ("colour color", ["colour", "color"]),
    # --- case folding ---------------------------------------------------------------------------------
    ("LLM", ["llm"]),
    ("llm", ["llm"]),
    ("LlM", ["llm"]),
    ("TrustLLM", ["trustllm"]),
    ("ΣΙΣΥΦΟΣ", ["σισυφοσ"]),  # casefold maps final sigma to σ too
    ("İstanbul", ["istanbul"]),  # dotted capital I: casefold + mark drop
    ("ǅemal", ["dzemal"]),  # titlecase digraph → NFKC → dz
    # --- hyphens, dashes, slashes, punctuation ------------------------------------------------------
    ("vision-language", ["vision", "language"]),
    ("vision language", ["vision", "language"]),
    ("vision—language", ["vision", "language"]),  # em dash
    ("vision‐language", ["vision", "language"]),  # U+2010 hyphen
    ("vision‑language", ["vision", "language"]),  # U+2011 non-breaking hyphen
    ("vision−language", ["vision", "language"]),  # U+2212 minus
    ("LLM-as-a-judge", ["llm", "as", "a", "judge"]),
    ("state-of-the-art", ["state", "of", "the", "art"]),
    ("input/output", ["input", "output"]),
    ("e.g. i.e.", ["e", "g", "i", "e"]),
    ("U.S.A.", ["u", "s", "a"]),
    ("trust,safety;fairness", ["trust", "safety", "fairness"]),
    ("(trust)", ["trust"]),
    ("[trust]", ["trust"]),
    ('"trust"', ["trust"]),
    ("“trust”", ["trust"]),  # curly quotes
    ("‘trust’", ["trust"]),
    ("trust!", ["trust"]),
    ("trust?", ["trust"]),
    ("trust...", ["trust"]),
    ("trust…", ["trust"]),  # ellipsis character: NFKC → "..."
    ("trust_score", ["trust", "score"]),
    ("trust@scale", ["trust", "scale"]),
    ("trust#1", ["trust", "1"]),
    ("a+b=c", ["a", "b", "c"]),
    ("50%", ["50"]),
    ("~trust~", ["trust"]),
    ("don't", ["don", "t"]),
    ("don’t", ["don", "t"]),  # right single quotation mark
    # --- digits and versions: never normalised as numbers -------------------------------------------
    ("GPT-4", ["gpt", "4"]),
    ("GPT4", ["gpt4"]),
    ("Llama 3.1 70B", ["llama", "3", "1", "70b"]),
    ("2024", ["2024"]),
    ("1,000", ["1", "000"]),
    ("3.14", ["3", "14"]),
    ("v1.2.3", ["v1", "2", "3"]),
    ("x²", ["x2"]),  # superscript two → NFKC → 2
    ("½", ["1", "2"]),  # vulgar fraction → 1⁄2 → fraction slash splits
    ("①", ["1"]),  # circled one → NFKC → 1
    ("٣", ["٣"]),  # Arabic-Indic digit three stays a digit (no number normalisation)
    ("0.5x", ["0", "5x"]),
    # --- full-width and compatibility forms (NFKC) -----------------------------------------------------
    ("ＬＬＭ", ["llm"]),  # full-width Latin
    ("ｔｒｕｓｔ", ["trust"]),
    ("１２３", ["123"]),  # full-width digits
    ("ﬀ ﬂ ﬃ", ["ff", "fl", "ffi"]),
    ("Ⅳ", ["iv"]),  # Roman numeral four
    ("™", ["tm"]),
    ("㎏", ["kg"]),
    # --- diacritics folded ------------------------------------------------------------------------------
    ("café", ["cafe"]),
    ("café", ["cafe"]),  # e + combining acute (decomposed input)
    ("Gödel", ["godel"]),
    ("Erdős", ["erdos"]),
    ("Zürich", ["zurich"]),
    ("façade", ["facade"]),
    ("résumé", ["resume"]),
    ("Ångström", ["angstrom"]),
    ("Øresund", ["øresund"]),  # ø has no decomposition: it is a letter, not o + mark
    ("Łódź", ["łodz"]),  # ł has no decomposition either
    # --- invisible and format characters ---------------------------------------------------------------
    ("bench­mark", ["benchmark"]),  # soft hyphen is invisible: the word stays whole
    ("bench​mark", ["benchmark"]),  # zero-width space is a format char, dropped
    ("bench‍mark", ["benchmark"]),  # zero-width joiner
    ("trust benchmark", ["trust", "benchmark"]),  # no-break space separates
    ("trust\tbenchmark\nsuite", ["trust", "benchmark", "suite"]),
    ("  trust   ", ["trust"]),
    ("", []),
    ("   ", []),
    ("---", []),
    ("$$", []),
    # --- LaTeX -------------------------------------------------------------------------------------------
    ("\\emph{trustworthy} models", ["trustworthy", "models"]),
    ("\\textbf{LLM}-as-a-judge", ["llm", "as", "a", "judge"]),
    ("$\\alpha$-divergence", ["α", "divergence"]),
    ("$x_i$", ["xi"]),  # a subscript joins, as NFKC joins xᵢ
    ("$O(n^2)$", ["o", "n2"]),
    ("$\\mathcal{L}_{\\text{KL}}$", ["mathcal", "l", "text", "kl"]),  # inside math, command names are words
    ("error of 5\\%", ["error", "of", "5"]),
    ("R\\&D", ["r", "d"]),
    ("\\cite{smith2020} shows", ["smith2020", "shows"]),
    ("trust\\\\benchmark", ["trust", "benchmark"]),  # \\ line break
    ("a \\newline b", ["a", "b"]),  # bare command outside math is dropped
    ("$\\epsilon$", ["ε"]),
    ("$\\epsilon$-differentially private", ["ε", "differentially", "private"]),
    ("cost \\$5", ["cost", "5"]),  # escaped dollar is not a math delimiter
    # --- non-Latin scripts are words, split only on non-letters -------------------------------------------
    ("可信的人工智能", ["可信的人工智能"]),  # CJK: no word segmentation, one run
    ("信頼 評価", ["信頼", "評価"]),
    ("доверие к ИИ", ["доверие", "к", "ии"]),
    ("ثقة", ["ثقة"]),
    ("विश्वास", ["विश्वास"]),  # Devanagari: virama and vowel signs are spelling, never folded
    ("신뢰", ["신뢰"]),
    # --- marks: folded only where they decorate (Latin, Greek, Cyrillic accents; Hebrew/Arabic vowel points),
    #     kept where they spell a different word (Thai tones, kana voicing, Indic signs)
    ("ά", ["α"]),  # Greek tonos folds
    ("ёж", ["еж"]),  # Cyrillic diaeresis folds
    ("שָׁלוֹם", ["שלום"]),  # Hebrew niqqud (optional vowel points) folds
    ("كَتَبَ", ["كتب"]),  # Arabic harakat (optional vowel points) fold
    ("ป่า ปา", ["ป่า", "ปา"]),  # Thai tone mark kept: "forest" and "throw" stay distinct
    ("が か", ["が", "か"]),  # kana voicing kept
    ("パ ハ", ["パ", "ハ"]),  # half-voiced kana kept
    ("नमस्ते", ["नमस्ते"]),  # Devanagari signs kept
    ("\u0301abc", ["abc"]),  # a stray mark with no base letter is dropped
    # a vowel sign of combining class 0 (U+0CE2) is a non-combining mark, so a word character even with no
    # base: alone it is a marks-only run and makes no token, but a letter after it joins it (nightly property)
    ("\u0ce2", []),
    ("\u0ce2x", ["\u0ce2x"]),
    ("abcd-\u0ce2x", ["abcd", "\u0ce2x"]),
    ("-\ufe0fx", ["x"]),  # but a variation selector is invisible (step 5), not a word character
    ("-\u0f73x", ["x"]),  # and NFKC decomposes U+0F73 into combining marks: stray, dropped
    # --- CJK: no word segmentation, so a run is one token (spec 02 §Known limits)
    ("信頼性", ["信頼性"]),  # does NOT contain the token 信頼
    # --- currency dollar is not math (spec 02 §Token semantics step 3)
    ("costs $5 and \\textbf{x}", ["costs", "5", "and", "x"]),
    ("from $10 to $20", ["from", "10", "to", "20"]),
    ("$x$ costs $5", ["x", "costs", "5"]),
    # --- inline math per Pandoc's tex_math_dollars rule (task-010 review round 2)
    ("a $2$-approximation with $\\epsilon$-DP", ["a", "2", "approximation", "with", "ε", "dp"]),
    ("$1$ and $\\alpha$", ["1", "and", "α"]),
    ("$10^{-3}$ lr and \\textsc{Adam}", ["10", "3", "lr", "and", "adam"]),
    ("US$ 5 and \\emph{x}", ["us", "5", "and", "x"]),
    ("cost \\$5 via \\textbf{x}", ["cost", "5", "via", "x"]),
    ("$a\\$b$", ["a", "b"]),
    ("$$\\alpha$$", ["α"]),
    ("\\(\\epsilon\\)-DP", ["ε", "dp"]),
    ("\\[\\alpha\\]", ["α"]),
    (
        "＄\\alpha＄",
        [],
    ),  # tokenizer 2: full-width dollar is not a math delimiter (3: it is `$`, CHANGED_IN_3)
    ("$x$\\emph{w}$ end", ["x", "w", "end"]),  # a closing $ must never re-open math
    ("$$x$$\\emph{w}$$", ["x", "w"]),  # nor a closing $$
    # --- each Pandoc delimiter condition, pinned by a row that changes if it is dropped
    ("$5 via \\textbf{y}-$10", ["5", "via", "y", "10"]),  # a `$` followed by a digit never closes
    ("$5 via \\textbf{y} $x", ["5", "via", "y", "x"]),  # a closer cannot follow a space
    ("costs 5 $ \\textbf{b}$", ["costs", "5", "b"]),  # an opener cannot be followed by a space
    ("$a\\$ \\textbf{b}$", ["a", "textbf", "b"]),  # an escaped `\$` never closes
    ("\\(x\\\\)\\alpha y\\)", ["x", "α", "y"]),  # an escaped backslash never closes `\(`
    # --- LaTeX accent macros and the discretionary hyphen join the word
    ('na\\"{\\i}ve', ["naive"]),  # BibTeX dotless i
    ("\\v{\\j}", ["j"]),
    ('G\\"odel', ["godel"]),
    ('G\\"{o}del', ["godel"]),
    ("Erd\\H{o}s", ["erdos"]),
    ("Poincar\\'e", ["poincare"]),
    ("\\c{c}a", ["ca"]),
    ("bench\\-mark", ["benchmark"]),
    ("\\é x", ["e", "x"]),
    ("\\Huge text", ["text"]),  # a multi-letter command is not an accent macro
    # --- invisible characters never become or split tokens
    ("I ❤️ AI", ["i", "ai"]),
    ("trust️", ["trust"]),
    ("葛\U000e0100", ["葛"]),
    ("1️⃣", ["1"]),
    ("a͏b", ["ab"]),  # combining grapheme joiner
    ("a⁣b", ["a", "b"]),  # invisible separator separates
    ("x⁢y", ["x", "y"]),  # invisible times separates
    # --- marks that spell a different letter are kept even in folding scripts
    ("мой мои", ["мой", "мои"]),  # Cyrillic short i (breve) is its own letter
    ("سؤال", ["سؤال"]),  # Arabic hamza on a seat is spelling, not a vowel point
    ("أسئلة", ["أسئلة"]),
    ("ป\\%́x", ["ป", "x"]),  # a LaTeX separator resets the base: the mark is stray, dropped
    # --- OpenReview abstracts carry LaTeX/Markdown markup that PMLR pages don't; both must give the same
    #     tokens, so OpenReview-first precedence (decision-005) never changes what matches
    ("reaches \\textbf{63.7\\%} accuracy", ["reaches", "63", "7", "accuracy"]),
    ("reaches 63.7% accuracy", ["reaches", "63", "7", "accuracy"]),
    ("*Can LLMs judge?*", ["can", "llms", "judge"]),
    ("**bold** claim", ["bold", "claim"]),
    # --- emoji and symbols are separators ---------------------------------------------------------------
    ("trust 🤖 benchmark", ["trust", "benchmark"]),
    ("trust→benchmark", ["trust", "rightarrow", "benchmark"]),  # an operator is its LaTeX name
    ("trust•benchmark", ["trust", "benchmark"]),
    ("α-β", ["α", "β"]),
    ("\u00b5-law", ["\u03bc", "law"]),  # micro sign → NFKC → Greek small mu
    # --- math spelled in LaTeX or Unicode gives one token (decision-006): Greek letters are the letter,
    #     operators their LaTeX name, super/subscripts join; each pair pinned both ways
    ("5.7$\\times$", ["5", "7", "times"]),
    ("5.7×", ["5", "7", "times"]),
    ("$\\leq$ 3", ["leq", "3"]),
    ("$\\le$ 3", ["leq", "3"]),  # an alias gives its operator's one name
    ("≤ 3", ["leq", "3"]),
    ("$\\alpha$-DP", ["α", "dp"]),
    ("α-DP", ["α", "dp"]),
    ("alpha-DP", ["alpha", "dp"]),  # the spelled word stays its own token
    ("$O(n^2)$ time", ["o", "n2", "time"]),
    ("O(n²) time", ["o", "n2", "time"]),
    ("$x_{ij}$", ["xij"]),
    ("xᵢⱼ", ["xij"]),
    ("$\\Delta$", ["δ"]),  # case folds
    ("$\\varepsilon$ and $\\epsilon$", ["ε", "and", "ε"]),
    ("ϵ and ε", ["ε", "and", "ε"]),  # NFKC folds the lunate form
    ("$\\alpha\\beta$", ["αβ"]),
    ("αβ", ["αβ"]),
    ("$\\alpha_1$", ["α1"]),
    ("$a \\to b$", ["a", "rightarrow", "b"]),
    ("$a \\rightarrow b$", ["a", "rightarrow", "b"]),
    ("a → b", ["a", "rightarrow", "b"]),
    ("5×3", ["5", "times", "3"]),  # an operator splits the word it sits in
    ("x ∈ S", ["x", "in", "s"]),  # collides with the word `in` (decision-006)
    ("$10^{-3}$", ["10", "3"]),  # a braced run that isn't letters or digits doesn't join
    ("10⁻³", ["10", "3"]),
    ("$x^\\alpha$", ["x", "α"]),  # no join: NFKC reads ᵅ as the Latin ɑ, so nothing could agree
    ("\\alpha outside math", ["outside", "math"]),  # a command outside math is still markup
    ("snake_case and a^b", ["snake", "case", "and", "a", "b"]),  # ^ and _ join only inside math
    ("$\\mathcal{L}$", ["mathcal", "l"]),  # a command with no Unicode spelling is still its name
    # --- decision-006 review rows
    ("$\\hat\\theta$", ["hat", "θ"]),  # a Greek letter after another command's name starts a word
    ("$\\sin\\alpha$", ["sin", "α"]),
    ("$\\mathbf\\Sigma$", ["mathbf", "σ"]),
    ("$x\\alpha$", ["xα"]),  # but after a letter it joins, as `xα` does
    ("$x\\times y$", ["x", "times", "y"]),
    ("$x^α$", ["x", "α"]),  # only ASCII after ^/_ joins
    ("$x^{αβ}$", ["x", "αβ"]),
    ("$x^{}y$", ["x", "y"]),  # empty braces raise nothing, so nothing joins
    ("＝\u0338", ["neq"]),  # the slash composes with the character's NFKC form
    ("=\u0301\u0338", ["neq"]),  # whatever the marks' order
    ("∈\u0301\u0338", ["notin"]),
    (
        "≰ ≱ ⊄ ⊈ ∌ ∄ ∤ ∦ ≢ ≁ ≉",
        [
            "nleq",
            "ngeq",
            "nsubset",
            "nsubseteq",
            "notni",
            "nexists",
            "nmid",
            "nparallel",
            "nequiv",
            "nsim",
            "napprox",
        ],
    ),
    (
        "$\\not\\subset$ $\\nsubset$ $\\not\\leq$ $\\nleq$ $\\nexists$",
        ["nsubset", "nsubset", "nleq", "nleq", "nexists"],
    ),
    ("$\\not =$", ["neq"]),  # TeX allows a space after \not
    ("$\\in\u0338$", ["notin"]),  # a slash after an operator command negates it
    ("ก×\u0e48ข", ["ก", "times", "ข"]),  # an operator ends the word: the tone mark after it is stray
    ("a\ufe68b", ["a", "b"]),  # tokenizer 2: small reverse solidus is text, not LaTeX (3: it is `\`)
    ("∈\u0338", ["notin"]),  # a decomposed ∉ is ∉, never `in`
    ("=\u0338", ["neq"]),
    ("∉ and ≠", ["notin", "and", "neq"]),
    ("$\\not\\in$ and $\\not=$", ["notin", "and", "neq"]),
    ("$\\notin$", ["notin"]),
    ("∬", ["int", "int"]),  # NFKC first, then operators
    ("\U0001d6c1", ["nabla"]),  # mathematical bold nabla
    (
        "col\u0387lecci\u00f3 and co\u0140lecci\u00f3 and col·lecció",
        ["col", "cdot", "leccio", "and", "col", "cdot", "leccio", "and", "col", "cdot", "leccio"],
    ),
    ("∆ and $\\Delta$", ["δ", "and", "δ"]),  # the increment sign is written for Δ
    ("$\\ell_2$ and ℓ₂", ["l2", "and", "l2"]),
    (
        "a ⟹ b and $a \\implies b$ and $a \\Longrightarrow b$",
        ["a", "rightarrow", "b", "and", "a", "rightarrow", "b", "and", "a", "rightarrow", "b"],
    ),
    ("a ⟺ b and $a \\iff b$", ["a", "leftrightarrow", "b", "and", "a", "leftrightarrow", "b"]),
    ("a ∣ b ∗ c ⋆ d ⋯", ["a", "mid", "b", "ast", "c", "star", "d", "cdots"]),
    ("$a \\mid b \\ast c \\star d \\cdots$", ["a", "mid", "b", "ast", "c", "star", "d", "cdots"]),
]


# Tokenizer 3 reads the NFKC form of the whole text before LaTeX (decision-030), so a character whose NFKC form
# is LaTeX syntax is that syntax: full-width `＄` and `＼` and small `﹩` and `﹨` are `$` and `\`.
CHANGED_IN_3: dict[str, list[str]] = {
    "＄\\alpha＄": ["α"],
    "a\ufe68b": ["a"],  # `\b`: a command outside math, dropped
}

# Backslash + accent in every Unicode form (TASK-168's finding): tokenizer 2 read the raw form, so NFD `Caf\e`
# + U+0301 was the command `\e` and NFC `Caf\é` a backslash before a letter. Tokenizer 3 gives each row's
# tokens for its NFC, NFD, NFKC and NFKD forms alike.
FORMS: list[tuple[str, list[str]]] = [
    ("Caf\\é", ["caf", "e"]),  # 2 in NFD: `caf`
    ("Erd\\H{ő}s", ["erdos"]),  # 2 in NFD: `erd`, `o`, `s`
    ('G\\"{ö}del', ["godel"]),
    ('na\\"{ï}ve', ["naive"]),
    ("\\'école", ["ecole"]),
    ("Pr\\'{é}cis \\v{š}", ["precis", "s"]),
    ("\\c{ç}a", ["ca"]),
    ("\\ö and \\ő", ["o", "and", "o"]),  # 2 in NFD: `and`
    ("$\\é$ y", ["e", "y"]),
    ("x \\ﬁne y", ["x", "y"]),  # NFKC `\fine`: a command outside math (2 in NFC: `fine`)
    ("$x^²$", ["x2"]),  # NFKC `$x^2$` (2 in NFC: `x`, `2`)
    ("＼emph{x} and ＄\\alpha＄", ["x", "and", "α"]),  # NFKC `\emph{x} and $\alpha$`
]


def test_table_has_at_least_100_cases() -> None:
    assert len(GOLDEN) >= 100
    assert len({text for text, _ in GOLDEN}) == len(GOLDEN), "duplicate inputs in the golden table"
    assert set(CHANGED_IN_3) <= {text for text, _ in GOLDEN}


@pytest.mark.parametrize("version", SERVED_TOKENIZERS)
@pytest.mark.parametrize(("text", "tokens"), GOLDEN, ids=[repr(t)[:40] for t, _ in GOLDEN])
def test_golden(text: str, tokens: list[str], version: str) -> None:
    expected = CHANGED_IN_3.get(text, tokens) if version == "3" else tokens
    assert normalize(text, version) == expected


@pytest.mark.parametrize("form", ["NFC", "NFD", "NFKC", "NFKD"])
@pytest.mark.parametrize(("text", "tokens"), FORMS, ids=[repr(t)[:40] for t, _ in FORMS])
def test_every_unicode_form_tokenizes_alike(text: str, tokens: list[str], form: str) -> None:
    assert TOKENIZER_VERSION == "3"  # these rows are tokenizer 3's; a later version adds its own
    assert normalize(unicodedata.normalize(form, text)) == tokens
