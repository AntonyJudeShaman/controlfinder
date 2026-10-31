"""RRF and the parent roll-up, on hand-computed toy rankings."""

import pytest

from controlfinder.retrieval import Hit
from controlfinder.retrieval.fusion import rrf
from controlfinder.retrieval.pipeline import top_parents


def ranking(*parents: str, tag: str = "") -> list[Hit]:
    return [Hit(parent + tag, parent, 0.0) for parent in parents]


def test_rrf_sums_one_over_k_plus_rank():
    fused = rrf([ranking("a", "b", "c"), ranking("b", "c", "d")])
    assert [h.parent_control_id for h in fused] == ["b", "c", "a", "d"]
    assert [h.score for h in fused] == pytest.approx([1 / 62 + 1 / 61, 1 / 63 + 1 / 62, 1 / 61, 1 / 63])


def test_rrf_reads_ranks_not_scores():
    bm25 = [Hit("x:1", "x", 250.0), Hit("y:1", "y", 3.0)]
    dense = [Hit("y:2", "y", 0.9), Hit("x:2", "x", 0.1)]
    assert rrf([bm25, dense]) == [Hit("x:1", "x", 1 / 61 + 1 / 62), Hit("y:2", "y", 1 / 62 + 1 / 61)]


def test_score_ties_go_to_the_better_single_rank_then_the_parent_id():
    fused = rrf([ranking("z", "a"), ranking("b", "a")], k=0)
    assert [(h.parent_control_id, h.score) for h in fused] == [("b", 1.0), ("z", 1.0), ("a", 1.0)]


def test_a_parent_ranked_equally_keeps_the_first_rankings_chunk():
    assert rrf([ranking("a", tag=":bm25"), ranking("a", tag=":dense")])[0].chunk_id == "a:bm25"


def test_rrf_rejects_a_ranking_with_repeated_parents():
    with pytest.raises(ValueError):
        rrf([[Hit("ac-2", "ac-2", 0.0), Hit("ac-2.1", "ac-2", 0.0)]])


def test_top_parents_keeps_each_parents_first_chunk():
    hits = [Hit("ac-2.1", "ac-2", 0.9), Hit("ac-3", "ac-3", 0.8), Hit("ac-2", "ac-2", 0.7), Hit("ac-6", "ac-6", 0.6)]
    assert top_parents(hits, 2) == [hits[0], hits[1]]
    assert top_parents(hits, 5) == [hits[0], hits[1], hits[3]]
