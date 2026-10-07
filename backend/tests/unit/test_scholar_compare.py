"""The RIS-set comparison core (TASK-056, spec 07 §B, scholar-comparison-protocol skill): reading a RIS set,
matching it to the index by the merge rules, scoping, and classifying every disagreement, each class on a
hand-built corpus with a known answer. The engine here is the oracle itself: no index is built."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.eval.scholar_compare import (
    COMPAT_READING,
    COVERAGE_GAP,
    FILTERED,
    FULL_TEXT,
    OUR_BUG,
    QUERY_LIMIT,
    SCHOLAR_CAP,
    SCHOLAR_MISSED,
    STEMMING,
    UNSETTLED,
    MatchIndex,
    QueryComparison,
    QueryRefused,
    RisRecord,
    Scope,
    TooManyForms,
    abstract_source,
    compare_query,
    doi_key,
    forms_of,
    inflection_stem,
    load_ris,
    openreview_id,
    proceedings_key,
    read_ris,
    scholar_reading,
    scope_and_match,
    with_prefixes,
    with_variants,
)
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.ast import Node, _Node
from openproceedings.query.canonical import render
from openproceedings.query.defaults import apply_defaults
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode, parse

from tests.unit.ingest.test_dedup import H, paper

NAME = "set.ris"


def entry(
    title: str,
    *,
    venue: str | None = "NeurIPS",
    year: int | None = 2024,
    url: str | None = None,
    search: str | None = None,
    doi: str | None = None,
) -> str:
    lines = ["TY  - JOUR", f"TI  - {title}"]
    lines += [f"JF  - {venue}"] if venue else []
    lines += [f"UR  - {url}"] if url else []
    lines += [f"DO  - {doi}"] if doi else []
    lines += [f"PY  - {year}///"] if year else []
    lines += [f"M1  - Query date: {search}"] if search else []
    return "\n".join([*lines, "ER  - ", "", ""])


def forum(native: str) -> str:
    return f"https://openreview.net/pdf?id={native}"


def listing(n: int, year: int = 2024) -> str:
    return f"https://proceedings.neurips.cc/paper_files/paper/{year}/hash/{H[n]}-Abstract-Conference.html"


class Lying:
    """A served engine that disagrees with the oracle on chosen ids."""

    index_version = "lying"
    tokenizer_version = TOKENIZER_VERSION

    def __init__(
        self,
        corpus: Sequence[PaperRecord],
        drop: frozenset[str] = frozenset(),
        add: frozenset[str] = frozenset(),
    ) -> None:
        self.oracle, self.drop, self.add = ReferenceEngine(corpus), drop, add

    def match_ids(self, ast: Node) -> frozenset[str]:
        return (self.oracle.match_ids(ast) - self.drop) | self.add


def compare(
    q: str,
    ris: str,
    corpus: Sequence[PaperRecord],
    *,
    scope: Scope | None = None,
    engine: Lying | None = None,
    cap: int = 1000,
    mode: Mode = "scholar",
) -> QueryComparison:
    scope = scope or Scope()
    index = MatchIndex.build(corpus)
    side = scope_and_match(read_ris(ris, NAME), index, scope, cap)
    by_id = {r.id: r for r in corpus}
    return compare_query(
        "q",
        q,
        side=side,
        index=index,
        engine=engine or ReferenceEngine(corpus),
        fetch=lambda ids: {i: by_id[i] for i in ids},
        scope=scope,
        mode=mode,
    )


def classes(c: QueryComparison) -> dict[str, str]:
    return {r.op_id or r.scholar_key: r.auto_class for r in c.disagreements}


def nid(native: str, year: int = 2024, venue: str = "neurips") -> str:
    return f"op:{venue}:{year}:{native}"


# --- reading the RIS set -----------------------------------------------------------------------------------


def test_read_ris_reads_title_venue_year_ids_and_search() -> None:
    text = (
        entry("Trust in LLMs", venue="Advances in Neural Information Processing Systems", url=forum("abcd1234"),
              search="2026-09-19 10:03:05")
        + entry("Cut venue", venue="Advances in neural information processing …", url=listing(1))
        + entry("No year", venue="ICLR", year=None)
    )  # fmt: skip
    a, b, c = read_ris(text, NAME)
    assert (a.key, a.title, a.venue, a.year) == ("set.ris#1", "Trust in LLMs", "NeurIPS", 2024)
    assert a.forum_ids == ("abcd1234",) and a.proceedings_ids == () and a.search == "2026-09-19 10:03:05"
    # a venue string Scholar cut is not a venue (never a substring match); the URL still names the paper
    assert (b.venue, b.venue_raw) == (None, "Advances in neural information processing …")
    assert b.proceedings_ids == (("NeurIPS", 2024, f"nips-{H[1]}"),)
    assert (c.key, c.venue, c.year, c.search) == ("set.ris#3", "ICLR", None, None)


def test_a_text_with_content_but_no_record_is_refused() -> None:
    with pytest.raises(ValueError, match="no 'TY  - ' line"):
        read_ris("not a RIS file\n", NAME)
    assert read_ris("", NAME) == []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://openreview.net/pdf?id=QHROe7Mfcb", "QHROe7Mfcb"),
        ("https://openreview.net/forum?id=QHROe7Mfcb", "QHROe7Mfcb"),
        ("https://OpenReview.net/forum?id=QHROe7Mfcb", "QHROe7Mfcb"),
        ("https://openreview.net/pdf?id=a&id=b", None),  # two ids name no paper
        ("https://openreview.net/attachment?id=QHROe7Mfcb", None),
        ("https://example.org/forum?id=QHROe7Mfcb", None),
        ("ftp://openreview.net/forum?id=QHROe7Mfcb", None),
        ("https://openreview.net/pdf/0123456789abcdef.pdf", None),  # a file hash, not a forum id
    ],
)
def test_openreview_id(url: str, expected: str | None) -> None:
    assert openreview_id(url) == expected


def test_proceedings_key_carries_the_urls_own_venue_and_year() -> None:
    assert proceedings_key(listing(2, 2023)) == ("NeurIPS", 2023, f"nips-{H[2]}")
    assert proceedings_key("https://proceedings.mlr.press/v235/smith24a.html") == (
        "ICML",
        2024,
        "pmlr-v235-smith24a",
    )
    assert proceedings_key("https://proceedings.mlr.press/v238/smith24a.html") is None  # AISTATS: not ICML
    assert proceedings_key("https://arxiv.org/abs/2401.00001") is None
    # a dblp ICML record page names a dblp-<key> native but no year: no key, never a crash (decision-047)
    assert proceedings_key("https://dblp.org/rec/conf/icml/SzitaL09") is None


# --- matching ----------------------------------------------------------------------------------------------


def records() -> list[PaperRecord]:
    return [
        paper("frm00001", "Matched by forum id"),
        # one NeurIPS hash names a paper per year: the same hash, two years, two papers
        paper(f"nips-{H[1]}", "Listed in 2023", source="neurips_proceedings", year=2023),
        paper(f"nips-{H[1]}", "Listed in 2024", source="neurips_proceedings", year=2024),
        paper("ttl00001", "Matched by its title"),
        paper("twin0001", "Two notes one title"),
        paper("twin0002", "Two notes one title"),
        paper("yr250001", "Held in another year", year=2025),
    ]


def match_of(text: str) -> tuple[str | None, str, str]:
    index = MatchIndex.build(records())
    [r] = read_ris(text, NAME)
    m = index.match(r)
    return m.op_id, m.rule, m.problem


def test_match_order_is_forum_id_then_proceedings_id_then_title_venue_year() -> None:
    assert match_of(entry("Scholar's own title", url=forum("frm00001"))) == (nid("frm00001"), "forum_id", "")
    # the id decides even when the record names no venue or year
    assert match_of(entry("x", venue=None, year=None, url=forum("frm00001")))[1] == "forum_id"
    assert match_of(entry("x", url=listing(1, 2023))) == (nid(f"nips-{H[1]}", 2023), "proceedings_id", "")
    assert match_of(entry("x", url=listing(1, 2024))) == (nid(f"nips-{H[1]}", 2024), "proceedings_id", "")
    assert match_of(entry("MATCHED by its Title!")) == (nid("ttl00001"), "title_venue_year", "")


def test_a_title_alone_never_matches() -> None:
    index = MatchIndex.build(records())
    for text, problem in [
        (entry("Held in another year"), "not_found"),  # 2024 in the set, 2025 in the index
        (entry("Held in another year", venue="ICLR", year=2025), "not_found"),  # another venue
        (entry("Held in another year", year=None), "no_year"),
        (entry("Held in another year", venue="Some Other Conference", year=2025), "no_venue"),
    ]:
        [r] = read_ris(text, NAME)
        m = index.match(r)
        assert (m.op_id, m.problem) == (None, problem)
        assert m.near == (nid("yr250001", 2025),)  # named for a person, never matched


def test_two_candidates_are_ambiguous_and_a_cut_title_says_so() -> None:
    index = MatchIndex.build(records())
    [r] = read_ris(entry("Two notes one title"), NAME)
    m = index.match(r)
    assert (m.op_id, m.problem, m.candidates) == (None, "ambiguous", (nid("twin0001"), nid("twin0002")))
    assert match_of(entry("Matched by its …")) == (None, "", "truncated_title")
    assert match_of(entry("Nobody indexed this")) == (None, "", "not_found")


# --- scope and counting ------------------------------------------------------------------------------------


def test_scope_drops_before_comparing_and_counts_a_paper_once() -> None:
    corpus = [*records(), paper("old00001", "An old paper", year=2019)]
    text = (
        entry("Matched by forum id", url=forum("frm00001"), search="s1")
        + entry("Matched by forum id", search="s2")  # the same paper again, by title
        + entry("x", url=forum("old00001"))  # outside the years, by the index's own year
        + entry("Not indexed, too old", year=2019)
        + entry("Elsewhere", venue="AISTATS")
        + entry("Held in another year", venue="… Information Processing …", year=2025)
        + entry("Unindexed and undated", year=None)  # can't be scoped: kept for a person
        + entry("Says 2026, held in 2025", year=2026, url=forum("yr250001"))  # scoped by the index's year
    )
    side = scope_and_match(read_ris(text, NAME), MatchIndex.build(corpus), Scope(years=(2020, 2025)))
    assert (side.read, len(side.entries), side.duplicates) == (8, 4, 1)
    assert [(e.record.key, e.match.op_id, e.year, e.copies) for e in side.entries] == [
        ("set.ris#1", nid("frm00001"), 2024, 2),
        ("set.ris#6", None, 2025, 1),  # no venue, but an in-scope record has its title: kept for a person
        ("set.ris#7", None, None, 1),
        ("set.ris#8", nid("yr250001", 2025), 2025, 1),
    ]
    assert [(d.record.key, d.reason, d.near) for d in side.out_of_scope] == [
        ("set.ris#3", "year", ()),
        ("set.ris#4", "year", ()),
        ("set.ris#5", "venue_unrecognised", ()),
    ]
    assert side.searches == {"s1": 1, "s2": 1} and side.capped == frozenset()


def test_scope_limits_venues() -> None:
    scope = Scope(venues=frozenset({"ICLR"}))
    assert scope.holds("ICLR", 1999) and not scope.holds("NeurIPS", 2024) and not scope.holds(None, 2024)
    assert not Scope(years=(2020, 2026)).holds("ICLR", None)
    assert Scope(years=(2020, 2026)).describe() == "ICLR, ICML, NeurIPS; 2020–2026"


# --- the classes -------------------------------------------------------------------------------------------

QUERY = '(LLM OR "foundation model") AND "trust" AND benchmark'


def corpus() -> list[PaperRecord]:
    return [
        paper("both0001", "LLM trust benchmark", abstract="An abstract."),
        paper("work0001", "A workshop LLM trust benchmark", track="workshop", abstract="An abstract."),
        paper("rjct0001", "A rejected LLM trust benchmark", status="rejected", abstract="An abstract."),
        paper("stem0001", "Trusted LLMs", abstract="We are benchmarking them."),
        paper("stwk0001", "Trusting foundation models benchmarks", track="workshop", abstract="An abstract."),
        paper("full0001", "Graph networks", abstract="We study graphs with an LLM."),
        paper("noab0001", "Graph kernels"),
        paper("miss0001", "A benchmark of trust", abstract="For every LLM."),
        paper("othr0001", "Unrelated and absent from the set", abstract="Nothing."),
    ]


SET = (
    entry("Scholar cut this title…", url=forum("both0001"))
    + entry("A workshop LLM trust benchmark")
    + entry("A rejected LLM trust benchmark")
    + entry("Trusted LLMs")
    + entry("Trusting foundation models benchmarks")
    + entry("Graph networks")
    + entry("Graph kernels")
    + entry("A paper nobody indexed")
)


def test_every_disagreement_gets_its_class_in_protocol_order() -> None:
    c = compare(QUERY, SET, corpus())
    assert [r.op_id for r in c.kept] == [nid("both0001")]
    assert classes(c) == {
        nid("work0001"): FILTERED,
        nid("rjct0001"): FILTERED,
        nid("stem0001"): STEMMING,
        nid("stwk0001"): FILTERED,  # the filters are judged first; the inflected forms are in its evidence
        nid("full0001"): FULL_TEXT,
        nid("noab0001"): UNSETTLED,
        "set.ris#8": COVERAGE_GAP,
        nid("miss0001"): SCHOLAR_MISSED,
    }
    assert c.our_bug == 0
    evidence = {r.op_id or r.scholar_key: r.auto_evidence for r in c.disagreements}
    assert evidence[nid("work0001")] == "track=workshop"
    assert evidence[nid("rjct0001")] == "status=rejected"
    assert evidence[nid("stem0001")] == "matches with benchmarking, llms, trusted"
    assert evidence[nid("stwk0001")] == (
        "track=workshop; also stemming (matches with benchmarks, models, trusting)"
    )
    assert evidence[nid("full0001")] == "no title or abstract match for group 2, 3, inflected forms included"
    assert evidence[nid("miss0001")] == (
        "exact match on group 1: llm (abstract); group 2: trust (title); group 3: benchmark (title)"
    )
    # what a person must decide: the record with no abstract, and every scholar_missed row
    assert (
        evidence["set.ris#8"] == "no forum id, proceedings id, DOI or title+venue+year match in the snapshot"
    )
    assert {r.op_id or r.scholar_key for r in c.disagreements if not r.settled} == {
        nid("noab0001"),
        nid("miss0001"),
        "set.ris#8",  # a gap, or Scholar's venue is wrong: a person checks which
    }


def test_sizes_add_up_and_the_result_is_exactly_the_engines() -> None:
    records, engine = corpus(), ReferenceEngine(corpus())
    c = compare(QUERY, SET, records)
    parsed = parse(QUERY, "scholar")
    assert parsed.effective_ast is not None
    served = engine.match_ids(parsed.effective_ast)
    assert {r.op_id for r in c.kept} | {r.op_id for r in c.added} == served  # guarantee 5: nothing re-matched
    assert (c.total, c.in_scope, c.scholar_in_scope, c.matched) == (2, 2, 8, 7)
    assert len(c.kept) + len(c.dropped) + len(c.not_in_index) == c.scholar_in_scope
    assert [r.side for r in c.added] == ["openproceedings"] and c.added[0].scholar_key == ""
    assert c.counts("scholar") == {FILTERED: 3, STEMMING: 1, FULL_TEXT: 1, UNSETTLED: 1, COVERAGE_GAP: 1}
    assert c.counts("openproceedings") == {SCHOLAR_MISSED: 1}


def test_concept_groups_count_the_matched_scholar_papers() -> None:
    c = compare(QUERY, SET, corpus())
    assert [(g.text, g.exact, g.with_forms) for g in c.groups] == [
        ('(llm OR "foundation model")', 4, 6),  # + LLMs, foundation models
        ("trust", 3, 5),  # + trusted, trusting
        ("benchmark", 3, 5),  # + benchmarking, benchmarks
    ]
    assert c.variants == {
        "benchmark": ("benchmarking", "benchmarks"),
        "llm": ("llms",),
        "model": ("models",),
        "trust": ("trusted", "trusting"),
    }


def test_the_scope_limits_the_result_too() -> None:
    records = [
        *corpus(),
        paper("y1900001", "LLM trust benchmark of 2019", year=2019, abstract="An abstract."),
    ]
    c = compare(QUERY, SET, records, scope=Scope(years=(2020, 2026)))
    assert (c.total, c.in_scope) == (3, 2)
    assert nid("y1900001", 2019) not in classes(c)


def test_a_coverage_gap_with_the_title_elsewhere_goes_to_a_person() -> None:
    records = [*corpus(), paper("yr250001", "A paper nobody indexed", year=2025, abstract="An abstract.")]
    [gap] = compare(QUERY, SET, records).not_in_index
    assert (gap.auto_class, gap.settled) == (COVERAGE_GAP, False)
    assert gap.auto_evidence == (
        "no id or title match in NeurIPS 2024; same title elsewhere: op:neurips:2025:yr250001 (NeurIPS 2025)"
    )
    [linked] = compare(
        QUERY, entry("Filed under NeurIPS", url="https://Link.Springer.com/chapter/1"), corpus()
    ).not_in_index
    assert linked.auto_evidence.endswith("in the snapshot; its links are on link.springer.com")


def test_what_matching_cannot_settle_is_unsettled() -> None:
    records = [paper("twin0001", "Two notes one title"), paper("twin0002", "Two notes one title")]
    text = entry("Two notes one title") + entry("Undated", year=None) + entry("Cut by Scholar …")
    c = compare(QUERY, text, records)
    assert [(r.auto_class, r.settled) for r in c.not_in_index] == [(UNSETTLED, False)] * 3
    assert c.not_in_index[0].auto_evidence == (
        "its id or title names 2 records: op:neurips:2024:twin0001, op:neurips:2024:twin0002"
    )
    assert c.not_in_index[1].auto_evidence == "no year and no id: matched by id only"
    assert c.not_in_index[2].auto_evidence == "the title is cut (…), so its key can't match"


# --- our_bug -----------------------------------------------------------------------------------------------


def test_our_bug_when_the_oracle_matches_and_the_served_engine_does_not() -> None:
    records = corpus()
    c = compare(
        QUERY, SET, records, engine=Lying(records, drop=frozenset({nid("both0001"), nid("miss0001")}))
    )
    assert classes(c)[nid("both0001")] == OUR_BUG  # in the set: only in Scholar, and it is our bug
    assert nid("miss0001") not in classes(c)  # neither side holds it now: outside the compared records
    assert c.our_bug == 1


def test_our_bug_when_the_served_engine_matches_and_the_oracle_does_not() -> None:
    records = corpus()
    c = compare(QUERY, SET, records, engine=Lying(records, add=frozenset({nid("othr0001"), nid("full0001")})))
    assert classes(c)[nid("othr0001")] == OUR_BUG  # only in openproceedings
    # in both sets, so not a disagreement between the sides: still a bug, never hidden as kept
    assert classes(c)[nid("full0001")] == OUR_BUG
    assert c.our_bug == 2 and not any(r.settled for r in c.disagreements if r.auto_class == OUR_BUG)


# --- compat_reading and scholar_cap --------------------------------------------------------------------------

POP = "(foundation model | LLM) trust"


def test_decision_002_differences_are_compat_reading_on_both_sides() -> None:
    records = [
        paper("both0001", "Foundation model trust", abstract="An abstract."),
        # Scholar read `foundation AND (model OR LLM) AND trust`: no phrase needed
        paper("schl0001", "A model of a foundation for trust", abstract="An abstract."),
        # the phrase reading matches on LLM alone; Scholar's needs `foundation`
        paper("ours0001", "LLM trust", abstract="An abstract."),
    ]
    text = entry("Foundation model trust") + entry("A model of a foundation for trust")
    c = compare(POP, text, records)
    assert c.notices[DiagnosticCode.COMPAT_POP_PHRASE] == 1
    assert c.scholar_reading == (
        "(foundation AND (model OR llm) AND trust AND track:(datasets_benchmarks OR main OR position) AND "
        "status:accepted)"
    )
    assert classes(c) == {nid("schl0001"): COMPAT_READING, nid("ours0001"): COMPAT_READING}
    assert all(r.settled and r.auto_evidence.startswith("decision-002") for r in c.disagreements)


def test_a_dollar_match_is_compat_reading_and_says_so() -> None:
    records = [paper("plur0001", "LLMs trust", abstract="An abstract."), paper("sing0001", "LLM trust")]
    c = compare("LLM$ trust", entry("LLM trust"), records)
    [row] = c.added
    assert (row.op_id, row.auto_class) == (nid("plur0001"), COMPAT_READING)
    assert row.auto_evidence == "`$`: a zero-or-one wildcard here, no wildcard in Scholar"
    assert c.scholar_reading is not None and "llm$" not in c.scholar_reading


def test_a_string_scholar_reads_as_run_has_no_scholar_reading() -> None:
    assert compare(QUERY, SET, corpus()).scholar_reading is None


def test_scholar_cap_when_a_search_covering_the_cell_returned_the_cap() -> None:
    records = corpus()
    text = entry("LLM trust benchmark", search="s1") + entry("Graph networks", search="s1")
    assert classes(compare(QUERY, text, records, cap=2))[nid("miss0001")] == SCHOLAR_CAP
    assert classes(compare(QUERY, text, records, cap=3))[nid("miss0001")] == SCHOLAR_MISSED
    # a capped search in another venue-year says nothing about this record
    other = [*records, paper("iclr0001", "Graph networks", venue="ICLR", abstract="An abstract.")]
    elsewhere = entry("Graph networks", venue="ICLR", search="s1") * 2 + entry(
        "LLM trust benchmark", search="s2"
    )
    assert classes(compare(QUERY, elsewhere, other, cap=2))[nid("miss0001")] == SCHOLAR_MISSED


# --- the readings ----------------------------------------------------------------------------------------------


def reading(q: str, **only: bool) -> str:
    parsed = parse(q, "scholar")
    assert parsed.ast is not None
    pop = {d.span for d in parsed.translations if d.code == DiagnosticCode.COMPAT_POP_PHRASE and d.span}
    tree = apply_defaults(scholar_reading(parsed.ast, pop, **only), len(q)).identification
    assert tree is not None
    return render(tree)


def test_scholar_reading_ors_neighbouring_words_and_drops_the_dollar() -> None:
    q = "(large language model$ | LLM | foundation model$) (trust | trustworthy AI$)"
    assert reading(q) == (
        "(large AND language AND (model OR llm OR foundation) AND model AND (trust OR trustworthy) AND ai)"
    )
    assert reading(q, dollars=False) == (
        "(large AND language AND (model$ OR llm OR foundation) AND model$ AND (trust OR trustworthy) AND ai$)"
    )
    assert reading(q, phrases=False) == (
        '(("large language model" OR llm OR "foundation model") AND (trust OR "trustworthy ai"))'
    )


def test_scholar_reading_leaves_quoted_phrases_and_star_wildcards() -> None:
    assert reading('"foundation model$" OR bench* OR -LLM$ trust') == reading(
        '"foundation model" OR bench* OR -LLM trust'
    )
    assert "bench*" in reading('"foundation model$" OR bench* OR -LLM$ trust')


@pytest.mark.parametrize(
    ("token", "stem"),
    [
        ("benchmark", "benchmark"), ("benchmarks", "benchmark"), ("benchmarking", "benchmark"),
        ("benchmarked", "benchmark"), ("llms", "llm"), ("studies", "study"), ("study", "study"),
        ("evaluate", "evaluat"), ("evaluates", "evaluat"), ("evaluated", "evaluat"), ("evaluating", "evaluat"),
        ("running", "run"), ("modelling", "modell"),  # l, s and z stay doubled
        ("trustworthy", "trustworthy"), ("trustworthiness", "trustworthiness"),  # no derivation
        ("bias", "bias"), ("analysis", "analysis"), ("class", "class"), ("corpus", "corpus"),
        ("thing", "thing"), ("string", "string"), ("need", "need"),  # too short, or no vowel left
        ("vlms", "vlm"), ("gnns", "gnn"),  # a plural acronym needs no vowel
        ("ai", "ai"), ("gpt4s", "gpt4s"), ("naïves", "naïves"),  # not ASCII letters: its own stem
    ],
)  # fmt: skip
def test_inflection_stem(token: str, stem: str) -> None:
    assert inflection_stem(token) == stem


def test_with_variants_adds_forms_to_words_phrases_and_wildcards() -> None:
    forms = forms_of(["model", "models", "foundation", "foundations", "llm", "llms", "trust"])
    parsed = parse('"foundation model" OR LLM$ OR (model -trust)', "scholar")
    assert parsed.ast is not None
    tree = apply_defaults(with_variants(parsed.ast, forms), 0).identification
    assert tree is not None
    assert render(tree) == (
        '("foundation model" OR "foundation models" OR "foundations model" OR "foundations models" OR llm$ OR '
        "llms OR ((model OR models) AND NOT trust))"
    )


def test_a_phrase_with_too_many_spellings_is_refused_not_cut() -> None:
    forms = {inflection_stem("word"): tuple(f"word{i}" for i in range(30))}
    parsed = parse('"word word"', "native")
    assert parsed.ast is not None
    with pytest.raises(ValueError, match="961 inflected spellings"):
        with_variants(parsed.ast, forms)


def test_a_query_that_does_not_parse_is_refused_by_code() -> None:
    with pytest.raises(QueryRefused) as e:
        compare("(LLM AND", SET, corpus())
    assert e.value.codes and "LLM" not in str(e.value)  # the codes, never the query's text


# --- review round 2: provenance, id conflicts, the filter-first order, caps and bounds ----------------------


def test_an_id_matches_a_record_with_no_year_or_venue_and_scopes_it_by_the_index() -> None:
    side = scope_and_match(
        read_ris(entry("Scholar's title", venue=None, year=None, url=forum("frm00001")), NAME),
        MatchIndex.build(records()),
        Scope(years=(2024, 2024)),
    )
    [e] = side.entries
    assert (e.match.op_id, e.match.rule, e.venue, e.year) == (nid("frm00001"), "forum_id", "NeurIPS", 2024)


def test_a_forum_id_two_records_carry_is_ambiguous() -> None:
    linked = paper(
        "pmlr-v235-smith24a", "A listing", source="pmlr", venue="ICML", urls_forum="https://openreview.net/forum?id=frm00001"
    )  # fmt: skip
    index = MatchIndex.build([*records(), linked])
    [r] = read_ris(entry("x", url=forum("frm00001")), NAME)
    m = index.match(r)
    assert (m.op_id, m.problem) == (None, "ambiguous")
    assert m.candidates == (nid("pmlr-v235-smith24a", venue="icml"), nid("frm00001"))


def test_a_forum_id_and_a_proceedings_id_naming_different_records_are_ambiguous() -> None:
    index = MatchIndex.build(records())
    text = "\n".join(
        ["TY  - JOUR", "TI  - x", f"UR  - {forum('frm00001')}", f"UR  - {listing(1, 2024)}", "ER  - ", ""]
    )
    [r] = read_ris(text, NAME)
    m = index.match(r)
    assert (m.op_id, m.problem) == (None, "ambiguous")
    assert set(m.candidates) == {nid("frm00001"), nid(f"nips-{H[1]}", 2024)}


def test_a_record_with_a_cut_or_empty_venue_and_a_same_year_title_goes_to_a_person() -> None:
    records = corpus()
    text = (
        entry("Graph networks", venue="… Information Processing …")
        + entry("Graph kernels", venue=None)  # no venue string at all, same year: kept
        + entry("Graph networks", venue="… Information Processing …", year=2023)  # another year: out
        + entry("Graph networks", venue="International Conference on Artificial Intelligence and Statistics")
        + entry("Elsewhere", venue="AISTATS")
    )
    c = compare(QUERY, text, records)
    assert c.scholar_in_scope == 2  # the denominator: a record that names another venue in full stays out
    assert [r.scholar_key for r in c.not_in_index] == ["set.ris#1", "set.ris#2"]
    row = c.not_in_index[0]
    assert (row.scholar_key, row.auto_class, row.settled, row.venue) == (
        "set.ris#1", UNSETTLED, False, "… Information Processing …",
    )  # fmt: skip
    assert row.auto_evidence == (
        "its venue string is no venue, so no title match is made; same title: "
        "op:neurips:2024:full0001 (NeurIPS 2024)"
    )
    assert row.near == (
        nid("full0001"),
    )  # the record the evidence names: what an `in_both` call pairs it with


def test_full_text_says_when_the_record_also_fails_the_filters() -> None:
    records = [*corpus(), paper("fwrk0001", "Graph theory", track="workshop", abstract="No query word.")]
    c = compare(QUERY, SET + entry("Graph theory"), records)
    row = next(r for r in c.dropped if r.op_id == nid("fwrk0001"))
    assert (row.auto_class, row.fails_filters, row.settled) == (FULL_TEXT, True, True)
    assert row.auto_evidence == (
        "no title or abstract match for group 1, 2, 3, inflected forms included; also fails the filters "
        "(track=workshop)"
    )
    plain = next(r for r in c.dropped if r.op_id == nid("full0001"))
    assert (plain.auto_class, plain.fails_filters) == (FULL_TEXT, False)
    assert {r.op_id for r in c.dropped if r.fails_filters} == {
        nid("work0001"), nid("rjct0001"), nid("stwk0001"), nid("fwrk0001"),
    }  # fmt: skip


def test_a_record_the_querys_own_year_or_venue_limit_excludes_is_query_limit_not_full_text() -> None:
    """TASK-185: the query's own `year:` or `venue:` clause leaving a record out is no text miss."""
    records = [
        *corpus(),
        paper("old00001", "An LLM trust benchmark of 2019", year=2019, abstract="An abstract."),
        paper("old00002", "Graph theory of 2019", year=2019, abstract="No query word."),
        paper("iclr0001", "An LLM trust benchmark at ICLR", venue="ICLR", abstract="An abstract."),
        paper("oldw0001", "A workshop LLM trust benchmark of 2019", year=2019, track="workshop",
              abstract="An abstract."),
    ]  # fmt: skip
    text = (
        entry("An LLM trust benchmark of 2019", year=2019)
        + entry("Graph theory of 2019", year=2019)
        + entry("An LLM trust benchmark at ICLR", venue="ICLR")
        + entry("A workshop LLM trust benchmark of 2019", year=2019)
        + entry("Graph networks")
        + entry("A gap of 2018", year=2018)
        + entry("A gap of 2024")
    )
    c = compare(f"{QUERY} AND year:2020..2026 AND NOT source:ICLR", text, records)
    rows = {r.op_id or r.scholar_key: r for r in c.only_scholar}
    assert {k: (r.auto_class, r.settled) for k, r in rows.items()} == {
        nid("old00001", 2019): (QUERY_LIMIT, True),
        nid("old00002", 2019): (QUERY_LIMIT, True),  # outside the limit whatever its text
        nid("iclr0001", venue="iclr"): (QUERY_LIMIT, True),
        nid("oldw0001", 2019): (QUERY_LIMIT, True),  # the query's own limit before the default filters
        nid("full0001"): (FULL_TEXT, True),  # inside the limits: the text decides, as before
        "set.ris#6": (QUERY_LIMIT, False),  # no index record: judged on the file's year, for a person
        "set.ris#7": (COVERAGE_GAP, False),
    }
    assert rows[nid("old00001", 2019)].auto_evidence == (
        "outside the query's own limit: `year:2020..2026` (year 2019); the rest of the query matches it (as run)"
    )
    assert rows[nid("old00002", 2019)].auto_evidence == (
        "outside the query's own limit: `year:2020..2026` (year 2019); the rest of the query doesn't match it "
        "either (as run)"
    )
    assert rows[nid("iclr0001", venue="iclr")].auto_evidence.startswith(
        "outside the query's own limit: `NOT venue:ICLR` (venue ICLR);"
    )
    assert rows[nid("oldw0001", 2019)].auto_evidence.endswith("; also fails the filters (track=workshop)")
    assert rows["set.ris#6"].auto_evidence == (
        "outside the query's own limit, by the file's venue and year: `year:2020..2026` (year 2018); not in the "
        "snapshot"
    )
    assert c.counts("scholar")[QUERY_LIMIT] == 5


def test_a_track_or_status_clause_the_user_writes_is_a_limit_too() -> None:
    """A `track:` or `status:` clause other than the default is the query's own limit (TASK-185 gate round 1)."""
    records = [
        paper("posn0001", "Trust in position papers", track="position", abstract="An abstract."),
        paper("posn0002", "Graph theory", track="position", abstract="No query word."),
        paper("main0001", "Trust in main papers", abstract="An abstract."),
    ]
    text = entry("Trust in position papers") + entry("Graph theory") + entry("Trust in main papers")
    c = compare("trust track:main", text, records, mode="native")
    rows = {r.op_id: r for r in c.dropped}
    assert [r.op_id for r in c.kept] == [nid("main0001")]
    assert {i: r.auto_class for i, r in rows.items()} == {
        nid("posn0001"): QUERY_LIMIT,
        nid("posn0002"): QUERY_LIMIT,
    }
    assert rows[nid("posn0001")].auto_evidence == (
        "outside the query's own limit: `track:main` (track position); the rest of the query matches it (as run)"
    )
    assert rows[nid("posn0002")].auto_evidence == (
        "outside the query's own limit: `track:main` (track position); the rest of the query doesn't match it "
        "either (as run)"
    )
    # `NOT status:accepted` replaces the status default, so it is the query's own limit
    records = [
        paper("acpt0001", "Trust accepted", abstract="An abstract."),
        paper("rjct0001", "Trust rejected", status="rejected", abstract="An abstract."),
    ]
    c = compare(
        "trust NOT status:accepted", entry("Trust accepted") + entry("Trust rejected"), records, mode="native"
    )
    [row] = c.dropped
    assert (row.op_id, row.auto_class) == (nid("acpt0001"), QUERY_LIMIT)
    assert row.auto_evidence.startswith(
        "outside the query's own limit: `NOT status:accepted` (status accepted);"
    )
    assert [r.op_id for r in c.kept] == [nid("rjct0001")]


def test_a_default_or_nested_filter_is_no_limit_of_the_query() -> None:
    # the default filters are `filtered`'s; a clause under an OR is part of the search, not a limit
    records = [*corpus(), paper("old00001", "Graph theory of 2019", year=2019, abstract="No query word.")]
    c = compare(
        f"{QUERY} AND track:(main OR datasets_benchmarks OR position) AND (year:2020..2026 OR graph)",
        SET + entry("Graph theory of 2019", year=2019),
        records,
        mode="native",
    )
    assert QUERY_LIMIT not in c.counts("scholar")
    assert classes(c)[nid("work0001")] == FILTERED


def test_a_filtered_record_scholar_reads_differently_is_filtered_and_says_so() -> None:
    records = [
        paper("schw0001", "A model of a foundation for trust", track="workshop", abstract="An abstract.")
    ]
    [row] = compare(POP, entry("A model of a foundation for trust"), records).dropped
    assert row.auto_class == FILTERED
    assert row.auto_evidence.startswith("track=workshop; also compat_reading (decision-002")


def test_the_cap_is_reached_at_exactly_a_thousand_records() -> None:
    index = MatchIndex.build(records())

    def capped(n: int) -> frozenset[tuple[str, int]]:
        text = "".join(entry(f"Unindexed paper {i}", search="s1") for i in range(n))
        return scope_and_match(read_ris(text, NAME), index, Scope()).capped

    assert capped(999) == frozenset()
    assert capped(1000) == frozenset({("NeurIPS", 2024)})


def test_many_searches_cost_no_more_than_one() -> None:
    """One search per record must not make the count quadratic (20,000 records once took 10.9 s)."""
    import time

    index = MatchIndex.build(records())
    same = read_ris("".join(entry(f"Paper {i}", search="s") for i in range(20_000)), NAME)
    each = read_ris("".join(entry(f"Paper {i}", search=f"s{i}") for i in range(20_000)), NAME)

    def cost(rs: list[RisRecord]) -> float:
        started = time.thread_time()
        side = scope_and_match(rs, index, Scope())
        assert sum(side.searches.values()) == 20_000
        return time.thread_time() - started

    pairs = [(cost(same), cost(each)) for _ in range(3)]
    assert min(b for _, b in pairs) < 3 * min(a for a, _ in pairs) + 0.5


def test_not_and_near_take_inflected_forms_inside_a_comparison() -> None:
    records = [
        paper("near0001", "LLMs for benchmarks", abstract="An abstract."),  # NEAR holds only with both forms
        paper("nots0001", "Trusted benchmarks", abstract="An abstract."),  # `trusted`, but NOT benchmark(s)
    ]
    near = compare("LLM NEAR/2 benchmark", entry("LLMs for benchmarks"), records, mode="native")
    assert [(r.auto_class, r.auto_evidence) for r in near.dropped] == [
        (STEMMING, "matches with benchmarks, llms")
    ]
    negated = compare("trust -benchmark", entry("Trusted benchmarks"), records)
    [row] = negated.dropped
    assert row.auto_class == FULL_TEXT  # a form of the negated word excludes it, as the word itself would


def test_a_near_with_too_many_spellings_is_refused_not_cut() -> None:
    forms = {inflection_stem("word"): tuple(f"word{i}" for i in range(30))}
    parsed = parse("word NEAR/2 word", "native")
    assert parsed.ast is not None
    with pytest.raises(TooManyForms, match="a NEAR has 961 inflected spellings") as e:
        with_variants(parsed.ast, forms)
    assert e.value.count == 961


def imported(native: str, title: str, **kw: object) -> PaperRecord:
    """A record only an imported RIS set holds."""
    return paper(native, title, source="ris", **kw)  # type: ignore[arg-type]


def test_rows_say_whether_their_record_is_crawled_or_only_the_imported_set() -> None:
    records = [
        paper("crwl0001", "LLM trust benchmark", abstract="An abstract."),
        imported("ris00001", "Graph networks", abstract="The import's own text."),
        imported("ris00002", "Another LLM trust benchmark", abstract="The import's own text.", year=2026),
        paper("miss0001", "A benchmark of trust", abstract="For every LLM."),
    ]
    index = MatchIndex.build(records)
    assert index.independent == {nid("crwl0001"), nid("miss0001")}
    assert index.crawled == {("NeurIPS", 2024): 2}  # none in 2026: nothing can be `added` there
    assert index.abstracts[nid("ris00001")] == "ris" and index.abstracts[nid("crwl0001")] == "openreview_v2"
    text = (
        entry("LLM trust benchmark")
        + entry("Graph networks")
        + entry("Another LLM trust benchmark", year=2026)
    )
    c = compare(QUERY, text, records)
    assert {r.op_id: r.independent for r in c.kept} == {nid("crwl0001"): True, nid("ris00002", 2026): False}
    [dropped] = c.dropped
    assert (dropped.auto_class, dropped.independent, dropped.abstract_source) == (FULL_TEXT, False, "ris")
    [added] = c.added
    assert (added.independent, added.abstract_source) == (True, "openreview_v2")
    assert all(r.independent is None and r.abstract_source == "" for r in c.not_in_index)


def test_an_imported_abstract_names_what_scholarmend_read_it_from() -> None:
    from openproceedings.ingest.dedup import resolve
    from openproceedings.ingest.record import Claim

    from tests.unit.ingest.test_dedup import T0

    def claim(field: str, value: object, evidence: str | None = None) -> Claim:
        return Claim(field=field, value=value, source="ris", fetched_at=T0, evidence=evidence)  # type: ignore[arg-type]

    record, _ = resolve(
        "op:iclr:2026:ris00009",
        [
            claim("title", "An imported paper"), claim("venue", "ICLR"), claim("year", 2026),
            claim("track", "main"), claim("status", "accepted"),
            claim("abstract", "Text.", "scholarmend:proceedings_page https://proceedings.iclr.cc/x"),
        ],
    )  # fmt: skip
    assert abstract_source(record) == "ris:proceedings_page"
    assert abstract_source(paper("noab0002", "No abstract")) == "none"


def test_two_set_records_hitting_one_paper_under_two_ids_are_flagged_not_merged() -> None:
    records = [
        paper("dupe0001", "One paper twice", abstract="No query word."),
        imported("dupe0002", "One paper twice", abstract="No query word."),  # the import's copy, never merged
        imported("solo0001", "Only the import has this", abstract="No query word."),
    ]
    text = (
        entry("One paper twice", url=forum("dupe0001"))
        + entry("One paper twice", url=forum("dupe0002"))
        + entry("Only the import has this", url=forum("solo0001"))
    )
    index = MatchIndex.build(records)
    side = scope_and_match(read_ris(text, NAME), index, Scope())
    assert [(e.match.op_id, e.match.shared) for e in side.entries] == [
        (nid("dupe0001"), ()),  # a crawled record: its title elsewhere is ordinary (a workshop copy, a twin)
        (nid("dupe0002"), (nid("dupe0001"),)),
        (nid("solo0001"), ()),
    ]
    assert side.duplicates == 0  # two ids, so the set counts the paper twice: said, not hidden
    c = compare(QUERY, text, records)
    assert [(r.op_id, r.auto_class, r.settled) for r in c.dropped] == [
        (nid("dupe0001"), FULL_TEXT, True),
        (nid("dupe0002"), UNSETTLED, False),
        (nid("solo0001"), FULL_TEXT, True),
    ]
    assert c.dropped[1].auto_evidence == (
        "matched by forum id to a record only the imported set holds, whose title is also on "
        "op:neurips:2024:dupe0001 (NeurIPS 2024): possibly one paper under two ids; otherwise `full_text` "
        "(no title or abstract match for group 1, 2, 3, inflected forms included)"
    )


def test_the_prefix_reading_bounds_how_far_a_wider_stemmer_could_move_full_text() -> None:
    records = [
        paper(
            "pref0001", "LLM trustworthiness benchmark", abstract="An abstract."
        ),  # `trust*`, not a form of trust
        paper("none0001", "Graph networks", abstract="No query word."),
    ]
    c = compare(QUERY, entry("LLM trustworthiness benchmark") + entry("Graph networks"), records)
    assert [r.auto_class for r in c.dropped] == [FULL_TEXT, FULL_TEXT]
    assert c.full_text_by_prefix == 1
    parsed = parse('"AI agent$" OR LLM', "scholar")
    assert parsed.ast is not None
    tree = apply_defaults(with_prefixes(parsed.ast, TOKENIZER_VERSION), 0).identification
    assert tree is not None and render(tree) == '("ai agent*" OR llm*)'  # a two-letter word stays a word


def test_the_prefix_is_built_on_the_inflection_stem_not_the_word_as_typed() -> None:
    parsed = parse("benchmarks OR evaluating OR evaluation", "native")
    assert parsed.ast is not None
    tree = apply_defaults(with_prefixes(parsed.ast, TOKENIZER_VERSION), 0).identification
    assert tree is not None and render(tree) == "(benchmark* OR evaluat* OR evaluation*)"
    # typed in the plural, the paper has another ending: `benchmarks*` would miss it, and so do the inflected forms
    records = [paper("stem0002", "A benchmarkable design", abstract="An abstract.")]
    c = compare("benchmarks", entry("A benchmarkable design"), records, mode="native")
    assert [r.auto_class for r in c.dropped] == [FULL_TEXT] and c.full_text_by_prefix == 1


# --- matching by DOI (TASK-186): Scopus and Web of Science exports ----------------------------------------------

EXPORTS = (
    Path(__file__).resolve().parents[1] / "fixtures" / "ris" / "exports"
)  # synthetic, in each vendor's layout


def doi_corpus() -> list[PaperRecord]:
    return [
        # the DOI decides: the index's title is not the export's
        paper("doi00001", "Trust calibration benchmark for LLM agents", year=2022, urls_doi="10.52202/068431-0101"),
        # held in 2022; the Scopus record says 2023
        paper("doi00002", "Reliance on explanations under distribution shift", year=2022,
              urls_doi="10.52202/068431-0202"),
        paper("doi00003", "Counterfactual advice and overreliance", urls_doi="10.52202/079017-0303-AB"),
        paper("pmlr0001", "Auditing human-AI teams", venue="ICML"),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("10.52202/068431-0101", "10.52202/068431-0101"),
        (" 10.52202/079017-0303-AB ", "10.52202/079017-0303-ab"),  # case-blind
        ("https://doi.org/10.52202/079017-0303-AB", "10.52202/079017-0303-ab"),
        ("http://dx.doi.org/10.1000/a%2Fb", "10.1000/a/b"),
        ("doi:10.1000/xyz", "10.1000/xyz"),
        ("10.1000", None),
        ("11.1000/xyz", None),
        ("10.1000/two words", None),
        ("https://example.org/10.1000/xyz", None),
        # the forms exports and people write (TASK-186 gate round 1)
        ("doi: 10.1000/xyz", "10.1000/xyz"),
        ("DOI 10.1000/xyz", "10.1000/xyz"),
        ("DOI:10.1000/XYZ", "10.1000/xyz"),
        ("https://www.doi.org/10.1000/xyz", "10.1000/xyz"),
        ("doi.org/10.1000/xyz", "10.1000/xyz"),
        ("www.doi.org/10.1000/xyz", "10.1000/xyz"),
        ("dx.doi.org/10.1000/xyz", "10.1000/xyz"),
        ("https://doi.org/10.1000/xyz?utm_source=x", "10.1000/xyz"),
        ("https://doi.org/10.1000/xyz#section-2", "10.1000/xyz"),
        ("10.1000/xyz.", "10.1000/xyz"),
        ("10.1000/xyz,", "10.1000/xyz"),
        ("10.1000/xyz;", "10.1000/xyz"),
        ("(doi:10.1000/xyz)", None),  # a leading parenthesis is no form of a DOI
        ("10.1000/xyz)", "10.1000/xyz"),
        (
            "10.1002/(SICI)1097-0258(19980815)",
            "10.1002/(sici)1097-0258(19980815)",
        ),  # its own parentheses kept
        ("10.1000/xyz).", "10.1000/xyz"),
        ("doi", None),
        ("doi:", None),
        ("doinot10.1000/xyz", None),
        # no control character survives into a key (a key is quoted in a row's evidence)
        ("10.1000/a\x00b", None),
        ("https://doi.org/10.1000/a%00b", None),
        ("10.1000/a\x7fb", None),
        ("10.1000/a\x85b", None),
        # nor a bidi format character, which could make a quoted key read as another
        *(
            (f"10.1000/a{c}b", None)
            for c in "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        ),
        ("https://doi.org/10.1000/a%E2%80%AEb", None),
        # a label in front of a link
        ("DOI https://doi.org/10.1000/xyz", "10.1000/xyz"),
        ("doi: doi.org/10.1000/XYZ?x=1", "10.1000/xyz"),
    ],
)
def test_doi_key(text: str, key: str | None) -> None:
    assert doi_key(text) == key


@pytest.mark.parametrize(
    "hostile",
    [
        "10.1/x" + ")" * 1_000_000,
        "10.1/x" + "." * 1_000_000,
        "10.1/x" + ".,;)" * 250_000,
        "10.1/x(" + ")" * 1_000_000,
        "doi:" + " " * 1_000_000 + "10.1/x",
        "10.1/x" + " " * 1_000_000 + ".",
        "https://doi.org/10.1/x" + "?" * 1_000_000,
        "10." + "1." * 500_000 + "/x!",
        "doi:" + " " * 1_000_000 + "https://doi.org/10.1/x",
    ],
    ids=[
        "parens",
        "dots",
        "mixed",
        "one-open",
        "label-spaces",
        "inner-spaces",
        "queries",
        "registrant",
        "label-link",
    ],
)
def test_doi_key_is_linear_on_a_hostile_value(hostile: str) -> None:
    """The trim is one pass, not a character at a time (a hostile file must not defeat /compare's time cap)."""
    started = time.perf_counter()
    doi_key(hostile)
    assert time.perf_counter() - started < 0.5


def test_a_di_tag_is_not_read() -> None:
    # `DI` is Web of Science's plain-text tag, not RIS (WoS RIS writes `DO`); a RIS reader never meets it
    [r] = read_ris(entry("x").replace("ER  - ", "DI  - 10.52202/068431-0101\nER  - "), NAME)
    assert r.dois == ()


def test_a_doi_only_a_claim_carries_matches() -> None:
    """A merged record keeps every `urls.doi` claim, the resolved one in `urls.doi` and any other in its
    provenance: a DOI in either names it."""
    record = paper("doi00001", "Trust", year=2022, urls_doi="10.52202/068431-0101")
    claim_only = record.model_copy(update={"urls": record.urls.model_copy(update={"doi": None})})
    index = MatchIndex.build([claim_only])
    [r] = read_ris(entry("x", year=2022, doi="10.52202/068431-0101"), NAME)
    assert (index.match(r).op_id, index.match(r).rule) == (nid("doi00001", 2022), "doi")


def test_a_scopus_export_is_matched_by_doi_never_across_year() -> None:
    index = MatchIndex.build(doi_corpus())
    one, other_year, no_doi = load_ris(EXPORTS / "scopus.ris")
    assert (one.venue, one.year, one.dois) == ("NeurIPS", 2022, ("10.52202/068431-0101",))
    assert (one.forum_ids, one.proceedings_ids) == ((), ())  # a Scopus link names no paper
    m = index.match(one)
    assert (m.op_id, m.rule) == (nid("doi00001", 2022), "doi")
    # the DOI names a 2022 paper and the file says 2023: never a match, and the row says why
    m = index.match(other_year)
    assert (m.op_id, m.problem, m.doi_elsewhere) == (None, "not_found", (nid("doi00002", 2022),))
    assert (index.match(no_doi).op_id, index.match(no_doi).rule) == (
        nid("pmlr0001", venue="icml"),
        "title_venue_year",
    )


def test_a_web_of_science_export_is_matched_by_doi_and_scoped_by_the_index() -> None:
    index = MatchIndex.build(doi_corpus())
    records = load_ris(EXPORTS / "wos.ris")
    same, upper, unknown = records
    # WoS writes the venue with its volume and edition: no venue, so only an id can match it
    assert (same.venue, same.venue_raw) == (
        None,
        "ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS 35 (NEURIPS 2022)",
    )
    assert (index.match(same).op_id, index.match(same).rule) == (nid("doi00001", 2022), "doi")
    assert (index.match(upper).op_id, index.match(upper).rule) == (nid("doi00003"), "doi")  # case-blind
    assert (index.match(unknown).op_id, index.match(unknown).problem) == (None, "no_venue")
    side = scope_and_match(records, index, Scope(years=(2020, 2026)))
    assert [(e.record.key, e.match.op_id, e.venue, e.year) for e in side.entries] == [
        ("wos.ris#1", nid("doi00001", 2022), "NeurIPS", 2022),
        ("wos.ris#2", nid("doi00003"), "NeurIPS", 2024),
    ]
    assert [(d.record.key, d.reason) for d in side.out_of_scope] == [("wos.ris#3", "venue_unrecognised")]
    # the same paper exported by both vendors is one paper
    both = scope_and_match([*load_ris(EXPORTS / "scopus.ris"), *records], index, Scope())
    assert both.duplicates == 1


def test_a_doi_is_checked_against_the_files_venue_too_and_its_ids() -> None:
    corpus = [*doi_corpus(), paper("frm00001", "Another paper"), paper("twin0001", "x", urls_doi="10.1000/twin"),
              paper("twin0002", "y", urls_doi="10.1000/TWIN")]  # fmt: skip
    index = MatchIndex.build(corpus)

    def match(text: str) -> tuple[str | None, str, str, tuple[str, ...]]:
        [r] = read_ris(text, NAME)
        m = index.match(r)
        return m.op_id, m.rule, m.problem, m.candidates or m.doi_elsewhere

    # a venue the file names that is not the record's: never a match
    assert match(entry("x", venue="ICLR", year=2022, doi="10.52202/068431-0101")) == (
        None, "", "not_found", (nid("doi00001", 2022),),
    )  # fmt: skip
    # no year in the file: the DOI alone decides, as an id does
    assert match(entry("x", year=None, doi="10.52202/068431-0101"))[:2] == (nid("doi00001", 2022), "doi")
    # a doi.org link is a DOI too
    assert match(entry("x", year=2022, url="https://doi.org/10.52202/068431-0101"))[:2] == (
        nid("doi00001", 2022), "doi",
    )  # fmt: skip
    # a DOI two records carry is ambiguous, and so is a DOI naming another record than the forum id
    assert match(entry("x", doi="10.1000/twin"))[2:] == ("ambiguous", (nid("twin0001"), nid("twin0002")))
    assert match(entry("x", year=2022, url=forum("frm00001"), doi="10.52202/068431-0101"))[2:] == (
        "ambiguous", (nid("doi00001", 2022), nid("frm00001")),
    )  # fmt: skip
    # the same record by both: the forum id's rule, first in the order
    assert match(entry("x", year=2022, url=forum("doi00001"), doi="10.52202/068431-0101"))[:2] == (
        nid("doi00001", 2022), "forum_id",
    )  # fmt: skip


def test_a_doi_in_another_year_is_named_in_the_gap_row() -> None:
    corpus = [*doi_corpus(), paper("both0001", "LLM trust benchmark", abstract="An abstract.")]
    c = compare(QUERY, (EXPORTS / "scopus.ris").read_text(encoding="utf-8"), corpus)
    [gap] = c.not_in_index
    assert (gap.scholar_key, gap.auto_class, gap.settled) == ("set.ris#2", COVERAGE_GAP, False)
    assert gap.auto_evidence.endswith(
        "; its DOI names op:neurips:2022:doi00002 (NeurIPS 2022), another venue or year: never a match"
    )
    assert [(r.op_id, r.auto_evidence) for r in c.kept] == [
        (nid("doi00001", 2022), "doi")
    ]  # matched by its DOI
    assert [r.op_id for r in c.dropped] == [nid("pmlr0001", venue="icml")]


# --- cost: the tree is serialised once per comparison, not once per row (TASK-200) --------------------------------


def _serialisations(
    monkeypatch: pytest.MonkeyPatch, q: str, make: Callable[[int], PaperRecord], n: int, cls: str
) -> int:
    """How many times a comparison of `n` such records serialises a query tree (the memo's key)."""
    records = [make(k) for k in range(n)]
    text = "".join(entry(r.title, year=r.year) for r in records if "extra" not in r.title) or entry(
        "Unrelated"
    )
    calls = 0
    real = _Node.model_dump_json

    def counted(self: _Node, *args: Any, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        return real(self, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(_Node, "model_dump_json", counted)
        c = compare(q, text, records)
    rows = [r for r in c.disagreements if r.op_id]
    assert len(rows) == n and all(r.auto_class == cls for r in rows)  # every record is a row of the path
    return calls


@pytest.mark.parametrize(
    ("q", "make", "cls"),
    [
        (  # `query_limit`: whether the rest of the query matches (`ids(unlimited)`)
            f"{QUERY} AND year:2025..2026",
            lambda k: paper(f"lim{k:05d}", f"LLM trust benchmark {k}", abstract="An abstract."),
            QUERY_LIMIT,
        ),
        (  # `stemming`: which inflected forms decide it
            QUERY,
            lambda k: paper(f"stm{k:05d}", f"Trusted LLMs {k}", abstract="We are benchmarking them."),
            STEMMING,
        ),
        (  # `filtered`, also `compat_reading`: which rewrite decides it
            POP,
            lambda k: paper(
                f"pop{k:05d}",
                f"A model of a foundation for trust {k}",
                track="workshop",
                abstract="An abstract.",
            ),
            FILTERED,
        ),
        (  # `scholar_missed`: where each leaf matches
            QUERY,
            lambda k: paper(f"add{k:05d}", f"LLM trust benchmark extra {k}", abstract="An abstract."),
            SCHOLAR_MISSED,
        ),
    ],
    ids=["query_limit", "stemming", "compat_reading", "scholar_missed"],
)
def test_a_rows_evidence_serialises_no_tree_per_row(
    monkeypatch: pytest.MonkeyPatch, q: str, make: Callable[[int], PaperRecord], cls: str
) -> None:
    few, many = _serialisations(monkeypatch, q, make, 2, cls), _serialisations(monkeypatch, q, make, 12, cls)
    assert few == many, f"{cls}: {few} serialisations for 2 rows, {many} for 12"
