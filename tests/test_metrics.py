"""Every metric against toy cases small enough to check by hand."""

import math

import pytest

from controlfinder.eval.metrics import (
    dedup_parents,
    ndcg,
    normalized_recall,
    precision,
    query_metrics,
    recall,
    recall_ceiling,
    reciprocal_rank,
)

GOLD = {"ac-2", "ia-2", "ac-3"}


def test_dedup_keeps_each_parents_first_rank():
    # C chunks AC-2(1), AC-2, AC-6, AC-2(3), IA-2, already mapped to their parents.
    assert dedup_parents(["ac-2", "ac-2", "ac-6", "ac-2", "ia-2"]) == ["ac-2", "ac-6", "ia-2"]


def test_repeats_eat_slots_unless_you_retrieve_deeper():
    deep = dedup_parents(["ac-2", "ac-2", "ac-6", "ac-2", "ia-2"])
    shallow = dedup_parents(["ac-2", "ac-2", "ac-6"])
    assert recall(deep, GOLD, 3) == pytest.approx(2 / 3)
    assert recall(shallow, GOLD, 3) == pytest.approx(1 / 3)


def test_recall_counts_gold_controls_found_not_results_that_look_right():
    assert recall(["ac-6", "si-4", "au-6"], GOLD, 3) == 0
    assert recall(["ac-3", "ia-2", "ac-2"], GOLD, 3) == 1


def test_ceiling_and_normalized_recall_with_more_gold_than_k():
    gold = {f"pm-{n}" for n in range(1, 41)}
    ranked = [f"pm-{n}" for n in range(1, 11)]
    assert recall(ranked, gold, 10) == pytest.approx(0.25)
    assert recall_ceiling(gold, 10) == pytest.approx(0.25)
    assert normalized_recall(ranked, gold, 10) == 1
    assert recall_ceiling(GOLD, 5) == 1


def test_precision_divides_by_k_even_when_fewer_came_back():
    assert precision(["ac-2", "ac-6"], GOLD, 5) == pytest.approx(1 / 5)


def test_reciprocal_rank():
    assert reciprocal_rank(["ac-6", "si-4", "ia-2", "ac-2"], GOLD) == pytest.approx(1 / 3)
    assert reciprocal_rank(["ac-6"], GOLD) == 0
    assert reciprocal_rank([f"pm-{n}" for n in range(1, 21)] + ["ac-2"], GOLD) == 0  # rank 21 is past the cutoff


def test_ndcg_by_hand():
    # Hits at ranks 2 and 4 out of 3 gold controls:
    # DCG = 1/log2(3) + 1/log2(5) = 0.6309 + 0.4307 = 1.0616
    # ideal = 1/log2(2) + 1/log2(3) + 1/log2(4) = 1 + 0.6309 + 0.5 = 2.1309
    assert ndcg(["ac-6", "ac-2", "si-4", "ia-2"], GOLD) == pytest.approx(0.4982, abs=1e-4)
    assert ndcg(["ac-6", "ac-2", "si-4", "ia-2"], GOLD) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3) + 1 / math.log2(4)))
    assert ndcg(["ia-2", "ac-3", "ac-2"], GOLD) == pytest.approx(1)


def test_query_metrics_refuses_unrolled_chunks():
    with pytest.raises(ValueError):
        query_metrics(["ac-2", "ac-2", "ia-2"], GOLD)


def test_query_metrics_on_one_query():
    m = query_metrics(["ac-2", "ac-6", "ia-2"], GOLD)
    assert m["recall@5"] == pytest.approx(2 / 3)
    assert m["norm_recall@5"] == pytest.approx(2 / 3)
    assert m["precision@5"] == pytest.approx(2 / 5)
    assert m["mrr"] == 1
