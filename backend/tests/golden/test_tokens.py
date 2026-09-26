"""Golden token table: the token contract (spec 02 §Token semantics, token-contract skill), pinned case by case.

Add a row for every bug ever found; never delete one. A change that alters any row is a TOKENIZER_VERSION bump.
"""

import pytest
from openproceedings.query.normalize import normalize

GOLDEN: list[tuple[str, list[str]]] = [
    # --- the token-contract skill's own table --------------------------------------------------------
    ("Benchmarking LLMs", ["benchmarking", "llms"]),
    ("Trust-aware", ["trust", "aware"]),
    ("Vision–Language", ["vision", "language"]),  # en dash
    ("naïve Bayes", ["naive", "bayes"]),
    ("GPT-4o", ["gpt", "4o"]),
    ("model's", ["model", "s"]),
    ("$\\epsilon$-DP", ["epsilon", "dp"]),
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
    ("$\\alpha$-divergence", ["alpha", "divergence"]),
    ("$x_i$", ["x", "i"]),
    ("$O(n^2)$", ["o", "n", "2"]),
    ("$\\mathcal{L}_{\\text{KL}}$", ["mathcal", "l", "text", "kl"]),  # inside math, command names are words
    ("error of 5\\%", ["error", "of", "5"]),
    ("R\\&D", ["r", "d"]),
    ("\\cite{smith2020} shows", ["smith2020", "shows"]),
    ("trust\\\\benchmark", ["trust", "benchmark"]),  # \\ line break
    ("a \\newline b", ["a", "b"]),  # bare command outside math is dropped
    ("$\\epsilon$", ["epsilon"]),
    ("$\\epsilon$-differentially private", ["epsilon", "differentially", "private"]),
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
    # --- CJK: no word segmentation, so a run is one token (spec 02 §Known limits)
    ("信頼性", ["信頼性"]),  # does NOT contain the token 信頼
    # --- currency dollar is not math (spec 02 §Token semantics step 3)
    ("costs $5 and \\textbf{x}", ["costs", "5", "and", "x"]),
    ("from $10 to $20", ["from", "10", "to", "20"]),
    ("$x$ costs $5", ["x", "costs", "5"]),
    # --- emoji and symbols are separators ---------------------------------------------------------------
    ("trust 🤖 benchmark", ["trust", "benchmark"]),
    ("trust→benchmark", ["trust", "benchmark"]),
    ("trust•benchmark", ["trust", "benchmark"]),
    ("α-β", ["α", "β"]),
    ("\u00b5-law", ["\u03bc", "law"]),  # micro sign → NFKC → Greek small mu
]


def test_table_has_at_least_100_cases() -> None:
    assert len(GOLDEN) >= 100
    assert len({text for text, _ in GOLDEN}) == len(GOLDEN), "duplicate inputs in the golden table"


@pytest.mark.parametrize(("text", "tokens"), GOLDEN, ids=[repr(t)[:40] for t, _ in GOLDEN])
def test_golden(text: str, tokens: list[str]) -> None:
    assert normalize(text) == tokens
