"""Query logging: every API search and answer becomes one query_log row, which `make report` reads.

A row keeps the query, the pipeline that served it, the controls retrieved, their scores, each
stage's latency in milliseconds, the decision (answers only) and the agent's or pipeline's trace.
"""

from psycopg import Connection
from psycopg.types.json import Jsonb


def log_request(conn: Connection, query: str, pipeline: str, latency_ms: dict[str, float], retrieved: list[str],
                scores: object = None, decision: str | None = None, trace: list[dict] | None = None) -> int:
    """Writes one row and returns its id."""
    (log_id,) = conn.execute(
        "INSERT INTO query_log (query, pipeline, retrieved, scores, latency_ms, decision, trace)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (query, pipeline, Jsonb(retrieved), None if scores is None else Jsonb(scores), Jsonb(latency_ms), decision,
         None if trace is None else Jsonb(trace))).fetchone()
    return log_id
