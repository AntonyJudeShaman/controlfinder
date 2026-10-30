"""Dense retrieval: bge-small-en-v1.5 embeddings, ranked by pgvector cosine distance.

Queries get BGE's instruction prefix and passages don't. BGE was trained on pairs of
(instruction + short question, plain passage), so the prefix tells it "this is a question
looking for a passage", which pulls the query's vector toward passages that answer it rather
than toward other text that merely sounds like it. The model card recommends it for short
queries searching long passages.

Each search applies its settings with SET LOCAL, so they last for that one query. `EXACT`
turns index scans off, so Postgres measures the distance to every chunk: the true top-k that
HNSW is measured against. HNSW settings force the strategy's partial index instead. The
strategy is always a SQL literal, because the planner can only use a partial index whose
predicate it can match at plan time.
"""

from psycopg import Connection, sql
from sentence_transformers import SentenceTransformer

from controlfinder.ingest.chunks import STRATEGIES
from controlfinder.ingest.sources import EMBED_MODEL, EMBED_REVISION
from controlfinder.retrieval import Hit

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EXACT = {"enable_indexscan": "off"}


def load_model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL, revision=EMBED_REVISION, device="cpu")


def to_pgvector(vector) -> str:
    """pgvector's text form. Each float32, widened to a Python float, round-trips exactly."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def embed_queries(model: SentenceTransformer, texts: list[str]) -> list[str]:
    vectors = model.encode([QUERY_PREFIX + text for text in texts], batch_size=32, normalize_embeddings=True)
    return [to_pgvector(v) for v in vectors]


def _statement(strategy: str, depth: int, explain: bool = False) -> sql.Composed:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    return sql.SQL(
        "{explain}SELECT chunk_id, parent_control_id, embedding <=> %(q)s::vector AS distance"
        " FROM chunks WHERE strategy = {strategy} ORDER BY embedding <=> %(q)s::vector LIMIT {depth}"
    ).format(explain=sql.SQL("EXPLAIN (FORMAT JSON) " if explain else ""),
             strategy=sql.Literal(strategy), depth=sql.Literal(depth))


def _apply(conn: Connection, settings: dict[str, str]) -> None:
    if not conn.autocommit:
        raise ValueError("needs an autocommit connection, so that SET LOCAL ends with each query")
    for name, value in settings.items():
        conn.execute(sql.SQL("SET LOCAL {} = {}").format(sql.Identifier(*name.split(".")), sql.Literal(value)))


def search(conn: Connection, query_vector: str, strategy: str, depth: int, settings: dict[str, str]) -> list[Hit]:
    """Nearest chunks first, scored by cosine similarity (1 - cosine distance)."""
    with conn.transaction():
        _apply(conn, settings)
        # Never prepared: after 5 runs psycopg would prepare the statement, and Postgres may then
        # reuse a cached plan made under earlier settings (an exact scan for an HNSW request).
        rows = conn.execute(_statement(strategy, depth), {"q": query_vector}, prepare=False).fetchall()
    return [Hit(chunk_id, parent, 1 - distance) for chunk_id, parent, distance in rows]


def plan(conn: Connection, query_vector: str, strategy: str, depth: int, settings: dict[str, str]) -> str:
    """The plan Postgres picks under `settings`, e.g. 'Limit > Index Scan (chunks_embedding_hnsw_c)'."""
    with conn.transaction():
        _apply(conn, settings)
        ((explained,),) = conn.execute(_statement(strategy, depth, explain=True), {"q": query_vector},
                                       prepare=False).fetchall()
    node, shape = explained[0]["Plan"], []
    while node:
        shape.append(node["Node Type"] + (f" ({node['Index Name']})" if "Index Name" in node else ""))
        node = node.get("Plans", [None])[0]
    return " > ".join(shape)
