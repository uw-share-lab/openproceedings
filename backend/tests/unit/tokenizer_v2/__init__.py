"""Tokenizer 2 as it stood when tokenizer 3 replaced it: `query/normalize.py` and `query/mathsyms.py` at 433399a9,
copied whole (only `normalize.py`'s import of `mathsyms` changed, to this copy). The oracle that keeps
`tokenize(text, "2")` byte-stable while this code still serves indexes built with it (`SERVED_TOKENIZERS`):
`tests/unit/test_tokenizer_versions.py` holds the served version 2 equal to it. Never edit it to follow the
tokenizer; delete it when "2" is retired.
"""
