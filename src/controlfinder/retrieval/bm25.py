"""BM25 (rank_bm25's BM25Okapi, k1=1.5, b=0.75) over the lexemes Postgres FTS sees.

Chunks and queries are tokenized by Postgres itself, with ts_debug and the 'english' config:
the same parser, stemmer and stopword list as the `tsv` column, so BM25 and FTS differ only in
how they score. Unlike ts_rank_cd, BM25 weighs each term by IDF (rare terms count more),
saturates term frequency (the tenth "account" adds less than the second) and normalizes for
chunk length. It doesn't read the `tsv` column, because a tsvector keeps at most 255 positions
per lexeme and long B chunks hit that cap, which would cap their term frequencies.
"""

from collections import defaultdict

from psycopg import Connection, sql
from rank_bm25 import BM25Okapi

from controlfinder.ingest.chunks import STRATEGIES
from controlfinder.retrieval import Hit


def lexemes(conn: Connection, text: str) -> list[str]:
    """The lexemes FTS makes of `text`, repeats included."""
    (found,) = conn.execute(
        "SELECT coalesce(array_agg(lexeme), '{}') FROM ts_debug('english', %s) AS token, unnest(token.lexemes) AS lexeme",
        (text,),
    ).fetchone()
    return found


class BM25Index:
    """BM25 over one strategy's chunks, built once and reused for every query."""

    def __init__(self, conn: Connection, strategy: str):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        rows = conn.execute(sql.SQL(
            "SELECT c.chunk_id, c.parent_control_id, lexeme FROM chunks c,"
            " ts_debug('english', c.text) AS token, unnest(token.lexemes) AS lexeme WHERE c.strategy = {}"
        ).format(sql.Literal(strategy)))
        tokens, self.parents = defaultdict(list), {}
        for chunk_id, parent, lexeme in rows:
            tokens[chunk_id].append(lexeme)
            self.parents[chunk_id] = parent
        self.chunk_ids = sorted(tokens)
        self.bm25 = BM25Okapi([tokens[chunk_id] for chunk_id in self.chunk_ids])

    def search(self, conn: Connection, query: str, depth: int) -> list[Hit]:
        """Chunks sharing at least one lexeme with the query, best first."""
        scores = self.bm25.get_scores(lexemes(conn, query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], self.chunk_ids[i]))
        return [Hit(self.chunk_ids[i], self.parents[self.chunk_ids[i]], float(scores[i]))
                for i in order[:depth] if scores[i] > 0]
