"""Postgres full-text search over the generated `tsv` column, ranked by ts_rank_cd.

`and` is plainto_tsquery: a chunk must contain every lexeme of the query. `or` uses the same
lexemes joined by | instead of &, so a chunk needs only one of them. ts_rank_cd rewards chunks
where query lexemes occur often and close together. It uses no corpus statistics, so a word
that appears in every chunk counts as much as a rare one (no IDF), and with normalization 0,
the default, it doesn't adjust for chunk length.
"""

from psycopg import Connection, sql

from controlfinder.ingest.chunks import STRATEGIES
from controlfinder.retrieval import Hit

TSQUERY = {
    "and": "plainto_tsquery('english', %(q)s)",
    # plainto_tsquery only ever joins lexemes with &, so swapping the operator keeps the lexemes.
    "or": "replace(plainto_tsquery('english', %(q)s)::text, ' & ', ' | ')::tsquery",
}


def search(conn: Connection, query: str, strategy: str, mode: str, depth: int) -> list[Hit]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    statement = sql.SQL(
        "SELECT chunk_id, parent_control_id, ts_rank_cd(tsv, tsq) AS score"
        " FROM chunks, (SELECT {tsquery} AS tsq) AS q"
        " WHERE strategy = {strategy} AND tsv @@ tsq"
        " ORDER BY score DESC, chunk_id LIMIT {depth}"
    ).format(tsquery=sql.SQL(TSQUERY[mode]), strategy=sql.Literal(strategy), depth=sql.Literal(depth))
    return [Hit(*row) for row in conn.execute(statement, {"q": query})]
