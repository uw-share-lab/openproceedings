"""A query's concept groups (spec 04 §SearchResponse, `groups`; TASK-176).

A reviewer's string is an AND of concept groups (AI-system terms × trust terms × benchmark terms), and when it
returns few papers the question is which group is cutting. "Top-level" is judged as `defaults.py` and the
facets judge it: on the canonical tree's top-level AND conjuncts (parenthesised AND groups flattened). Of
those conjuncts:
- a **group** is one that searches text and is not negated: a term, wildcard, phrase or NEAR, or an OR
  holding one (`(llm OR venue:ICLR)` too: it is not a filter clause);
- everything else is **kept** for every group: the filter clauses (`venue:x`, `NOT track:y`, an OR of
  filters; the default track and status filters included, since the effective tree spells them out) and the
  negated text conjuncts (`NOT survey`, the builder's leave-out terms).

A group **alone** is the query with every other group removed: that group AND everything kept. The query
**without** a group is every other group AND everything kept (leave-one-out): what the group, given the
others, removes is that count less `total`. Both trees match a superset of the query's matches, so neither
count is below `total`, and the counts of two groups are comparable: all are under the same filters. Only
the AST is read here; an engine counts the trees.
"""

from __future__ import annotations

from dataclasses import dataclass

from openproceedings.query.ast import And, Filter, Node, Not, Or


@dataclass(frozen=True, slots=True)
class Groups:
    groups: tuple[Node, ...]  # in query order, each with its span in `q`
    kept: tuple[Node, ...]  # every other top-level conjunct, applied to each group alone

    def alone(self, group: Node) -> Node:
        """The query with every other group removed: `group` AND everything kept."""
        return _and((group, *self.kept))

    def without(self, group: Node) -> Node:
        """The query with `group` removed: every other group AND everything kept (the leave-one-out tree).
        Only asked of a query with two or more groups, so another group is always left."""
        return _and((*(g for g in self.groups if g is not group), *self.kept))


def _and(nodes: tuple[Node, ...]) -> Node:
    return nodes[0] if len(nodes) == 1 else And(span=(0, 0), children=nodes)


def _conjuncts(n: Node) -> list[Node]:
    """Top-level AND conjuncts, nested ANDs flattened."""
    return [x for c in n.children for x in _conjuncts(c)] if isinstance(n, And) else [n]


def _searches_text(n: Node) -> bool:
    """Whether a text leaf (term, wildcard, phrase, NEAR) occurs anywhere under `n`."""
    if isinstance(n, Filter):
        return False
    if isinstance(n, Not):
        return _searches_text(n.child)
    if isinstance(n, And | Or):
        return any(_searches_text(c) for c in n.children)
    return True


def split(ast: Node) -> Groups:
    """`ast`'s groups and what is kept for each (the module docstring). `ast` is canonical (an effective
    tree): a conjunct is negated exactly when it is a `Not`."""
    groups: list[Node] = []
    kept: list[Node] = []
    for c in _conjuncts(ast):
        (groups if not isinstance(c, Not) and _searches_text(c) else kept).append(c)
    return Groups(tuple(groups), tuple(kept))
