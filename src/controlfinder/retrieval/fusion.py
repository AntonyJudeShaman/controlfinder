"""Reciprocal rank fusion (RRF): merge several rankings of parent controls into one.

A parent's fused score is the sum, over the rankings it appears in, of 1 / (k + its rank),
with ranks starting at 1. RRF reads only ranks, never the retrievers' own scores: a BM25 score
is an unbounded sum that depends on the query's length, while a cosine similarity sits between
-1 and 1, so adding raw scores would let whichever scale runs larger decide. k = 60 flattens
the top: rank 1 is worth 1/61 and rank 10 still 1/70, so a parent that both retrievers rank
fairly high beats one that a single retriever ranks first.
"""

from collections import defaultdict

from controlfinder.retrieval import Hit

K = 60


def rrf(rankings: list[list[Hit]], k: int = K) -> list[Hit]:
    """One parent-level ranking, best first, scored by RRF.

    Each parent keeps the chunk from the ranking where it placed best (the earlier ranking on
    a tie). Equal fused scores go to the parent with the better single rank, then by parent ID.
    """
    scores, best = defaultdict(float), {}
    for ranking in rankings:
        if len({h.parent_control_id for h in ranking}) != len(ranking):
            raise ValueError("a ranking repeats a parent: roll chunks up to parents first")
        for rank, hit in enumerate(ranking, 1):
            parent = hit.parent_control_id
            scores[parent] += 1 / (k + rank)
            if parent not in best or rank < best[parent][0]:
                best[parent] = (rank, hit.chunk_id)
    order = sorted(scores, key=lambda p: (-scores[p], best[p][0], p))
    return [Hit(best[p][1], p, scores[p]) for p in order]
