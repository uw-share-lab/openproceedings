"""The RIS-set comparison core (TASK-056, spec 07 §B, scholar-comparison-protocol skill): reading a RIS set,
matching it to the index by the merge rules, scoping, and classifying every disagreement, each class on a
hand-built corpus with a known answer. The engine here is the oracle itself: no index is built."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.eval.scholar_compare import (
    COMPAT_READING,
    COVERAGE_GAP,
    FILTERED,
    FULL_TEXT,
    OUR_BUG,
    SCHOLAR_CAP,
    SCHOLAR_MISSED,
    STEMMING,
    UNSETTLED,
    MatchIndex,
    QueryComparison,
    QueryRefused,
    Scope,
    compare_query,
    forms_of,
    inflection_stem,
    openreview_id,
    proceedings_key,
    read_ris,
    scholar_reading,
    scope_and_match,
    with_variants,
)
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.ast import Node
from openproceedings.query.canonical import render
from openproceedings.query.defaults import apply_defaults
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse

from tests.unit.ingest.test_dedup import H, paper

NAME = "set.ris"


def entry(
    title: str,
    *,
    venue: str | None = "NeurIPS",
    year: int | None = 2024,
    url: str | None = None,
    search: str | None = None,
) -> str:
    lines = ["TY  - JOUR", f"TI  - {title}"]
    lines += [f"JF  - {venue}"] if venue else []
    lines += [f"UR  - {url}"] if url else []
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
    assert (side.read, len(side.entries), side.duplicates) == (8, 3, 1)
    assert [(e.record.key, e.match.op_id, e.year, e.copies) for e in side.entries] == [
        ("set.ris#1", nid("frm00001"), 2024, 2),
        ("set.ris#7", None, None, 1),
        ("set.ris#8", nid("yr250001", 2025), 2025, 1),
    ]
    assert [(d.record.key, d.reason, d.near) for d in side.out_of_scope] == [
        ("set.ris#3", "year", ()),
        ("set.ris#4", "year", ()),
        ("set.ris#5", "venue_unrecognised", ()),
        ("set.ris#6", "venue_unrecognised", (nid("yr250001", 2025),)),
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
        nid("stwk0001"): STEMMING,  # the first class in order; the filter is in its evidence
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
        "matches with benchmarks, models, trusting; also filtered (track=workshop)"
    )
    assert evidence[nid("full0001")] == "no title or abstract match for group 2, 3, inflected forms included"
    assert evidence[nid("miss0001")] == (
        "exact match on group 1: llm (abstract); group 2: trust (title); group 3: benchmark (title)"
    )
    # what a person must decide: the record with no abstract, and every scholar_missed row
    assert evidence["set.ris#8"] == "no forum id, proceedings id or title+venue+year match in the snapshot"
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
    assert c.counts("scholar") == {FILTERED: 2, STEMMING: 2, FULL_TEXT: 1, UNSETTLED: 1, COVERAGE_GAP: 1}
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
