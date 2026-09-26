"""decision-006's operator table is generated from `mathsyms`; the committed copy must match the code."""

from pathlib import Path

from openproceedings.query.mathsyms import ALSO_WORDS, OPERATOR_COMMANDS, OPERATORS, operator_table

DECISION = next((Path(__file__).parents[3] / "backlog" / "decisions").glob("decision-006 *"))


def test_the_decision_shows_the_real_table() -> None:
    assert operator_table() in DECISION.read_text(encoding="utf-8")


def test_every_word_flag_names_an_operator() -> None:
    assert set(ALSO_WORDS) <= set(OPERATORS.values())
    assert set(OPERATOR_COMMANDS.values()) <= set(OPERATORS.values()) | {"notin"}
