"""Retrieval metrics for one query, computed on parent controls.

`ranked` is what a system retrieved, rolled up to base controls with `dedup_parents`, best
first. `gold` is the answer key's set of base controls. Each function is checked against
hand-computed toy cases in tests/test_metrics.py.

- recall@k: the share of gold controls found in the top k. "Did the right controls show up?"
- recall ceiling@k: the best recall@k any system could reach, min(k, |gold|) / |gold|.
- normalized recall@k: hits@k / min(k, |gold|), so 1.0 means "as good as possible".
- precision@k: hits@k / k. It divides by k even when fewer than k came back.
- MRR: 1 / the rank of the first gold control in the top 20, or 0. "How high is the first hit?"
- nDCG@10: each hit is worth 1 / log2(rank + 1), and the sum is divided by the best possible
  sum for this gold set, so a hit at rank 1 counts more than one at rank 9.
"""

import math
from collections.abc import Iterable

KS = (5, 10, 20)
DEPTH = max(KS)  # parent controls scored per query


def dedup_parents(parent_ids: Iterable[str]) -> list[str]:
    """['ac-2', 'ac-2', 'ac-6'] -> ['ac-2', 'ac-6']: each parent keeps the rank of its first chunk."""
    return list(dict.fromkeys(parent_ids))


def hits(ranked: list[str], gold: set[str], k: int) -> int:
    return len(set(ranked[:k]) & gold)


def recall(ranked: list[str], gold: set[str], k: int) -> float:
    return hits(ranked, gold, k) / len(gold)


def recall_ceiling(gold: set[str], k: int) -> float:
    return min(k, len(gold)) / len(gold)


def normalized_recall(ranked: list[str], gold: set[str], k: int) -> float:
    return hits(ranked, gold, k) / min(k, len(gold))


def precision(ranked: list[str], gold: set[str], k: int) -> float:
    return hits(ranked, gold, k) / k


def reciprocal_rank(ranked: list[str], gold: set[str], k: int = DEPTH) -> float:
    return next((1 / rank for rank, control in enumerate(ranked[:k], 1) if control in gold), 0.0)


def ndcg(ranked: list[str], gold: set[str], k: int = 10) -> float:
    dcg = sum(1 / math.log2(rank + 1) for rank, control in enumerate(ranked[:k], 1) if control in gold)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(gold)) + 1))
    return dcg / ideal


def query_metrics(ranked: list[str], gold: set[str]) -> dict[str, float]:
    """Every reported metric for one query."""
    if len(set(ranked)) != len(ranked):
        raise ValueError("ranked has repeats: roll chunks up with dedup_parents first")
    return {
        **{f"recall@{k}": recall(ranked, gold, k) for k in KS},
        **{f"norm_recall@{k}": normalized_recall(ranked, gold, k) for k in KS},
        "precision@5": precision(ranked, gold, 5),
        "precision@10": precision(ranked, gold, 10),
        "mrr": reciprocal_rank(ranked, gold),
        "ndcg@10": ndcg(ranked, gold, 10),
    }
