"""The retrieval pipeline: BM25 and dense search, fused with RRF, then reranked.

Every stage passes on parent controls, not chunks. Each retriever's chunks are rolled up to
their parents first (a parent keeps its best-ranked chunk), so a list of 50 always means 50
distinct controls, for every chunking strategy. The reranker then reads, for each control, the
one chunk that list kept.
"""

from psycopg import Connection

from controlfinder.retrieval import Hit, dense, fetch_depth
from controlfinder.retrieval.bm25 import BM25Index
from controlfinder.retrieval.fusion import rrf
from controlfinder.retrieval.rerank import Reranker, Scored

CANDIDATES = 50  # parents taken from each retriever, kept after fusion, and reranked
RETRIEVALS = ("bm25", "dense", "hybrid")


def top_parents(hits: list[Hit], n: int) -> list[Hit]:
    """The first `n` distinct parents, best first, each with its first (best-ranked) chunk."""
    first = {}
    for hit in hits:
        first.setdefault(hit.parent_control_id, hit)
    return list(first.values())[:n]


class Retriever:
    """BM25, dense and hybrid search over one strategy, each returning CANDIDATES parents."""

    def __init__(self, conn: Connection, strategy: str):
        self.conn, self.strategy = conn, strategy
        self.bm25 = BM25Index(conn, strategy)
        self.depth = fetch_depth(conn, strategy, CANDIDATES)
        self.texts = dict(conn.execute("SELECT chunk_id, text FROM chunks WHERE strategy = %s", (strategy,)).fetchall())

    def search(self, retrieval: str, query: str, query_vector: str) -> list[Hit]:
        """Parents best first; dense search is exact, and `query_vector` comes from `dense.embed_queries`."""
        lists = []
        if retrieval in ("bm25", "hybrid"):
            lists.append(top_parents(self.bm25.search(self.conn, query, self.depth), CANDIDATES))
        if retrieval in ("dense", "hybrid"):
            lists.append(top_parents(dense.search(self.conn, query_vector, self.strategy, self.depth, dense.EXACT),
                                     CANDIDATES))
        if not lists:
            raise ValueError(f"unknown retrieval {retrieval!r}")
        return rrf(lists)[:CANDIDATES] if retrieval == "hybrid" else lists[0]


def rerank(reranker: Reranker, query: str, hits: list[Hit], texts: dict[str, str]) -> tuple[list[Hit], Scored]:
    """`hits` reordered by the cross-encoder's score for (query, each hit's chunk); ties keep their order."""
    scored = reranker.score(query, [texts[h.chunk_id] for h in hits])
    order = sorted(range(len(hits)), key=lambda i: -scored.scores[i])
    return [hits[i]._replace(score=scored.scores[i]) for i in order], scored
