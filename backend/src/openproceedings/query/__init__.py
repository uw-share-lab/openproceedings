"""The query language (spec 02): token contract, lexer, parser, canonical form."""

# Versions the query semantics that live outside the index: parser, compiler (NEAR/slop, wildcard rules),
# default filters and the `source:` alias table. Bump it whenever some query could mean something
# different (spec 04 §Conventions, index-versioning skill). TOKENIZER_VERSION (normalize.py) covers the
# token contract.
QUERY_VERSION = "1"
