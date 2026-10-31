"""Hand-written retrieval over the chunks table: Postgres FTS, BM25 and pgvector dense search,
then RRF fusion and cross-encoder reranking, which `pipeline` puts together.

Each step returns `Hit`s, best first. There are no retrieval frameworks: FTS and vector search
are raw SQL, BM25 is rank_bm25 over lexemes from Postgres's own text parser, and fusion and
reranking are plain Python.
"""

from typing import NamedTuple

from psycopg import Connection, sql


class Hit(NamedTuple):
    chunk_id: str
    parent_control_id: str
    score: float  # higher is better; only comparable within one retriever


def fetch_depth(conn: Connection, strategy: str, parents: int) -> int:
    """How many chunks to fetch so that any ranking holds at least `parents` distinct parents.

    The worst case is a ranking that starts with every chunk of the `parents - 1` largest
    parents, so one chunk more than all of those must belong to a new parent. For strategies
    A and B, with one chunk per parent, this is just `parents`.
    """
    (depth,) = conn.execute(sql.SQL(
        "SELECT (1 + coalesce(sum(n), 0))::int FROM (SELECT count(*) AS n FROM chunks WHERE strategy = {}"
        " GROUP BY parent_control_id ORDER BY n DESC LIMIT {}) AS largest"
    ).format(sql.Literal(strategy), sql.Literal(parents - 1))).fetchone()
    return depth
