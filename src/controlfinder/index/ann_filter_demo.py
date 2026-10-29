"""Reproduce the filtered-HNSW pitfall so the schema's index design rests on a measurement.

Builds a throwaway table shaped like `chunks` (three strategies of different sizes, random
unit vectors), asks for the 50 nearest strategy-A rows under several index setups, and
records how many rows come back and how long each query takes. The vectors are random,
so this says nothing about retrieval quality; HNSW-vs-exact recall on real embeddings is
measured in Phase 2. Everything runs in one transaction that is rolled back.

Writes results/ann_filter_demo.json.
"""

import json
import random
import statistics
import time
from pathlib import Path

from psycopg import sql

from controlfinder.index.db import connect

SEED = 42
DIM = 384
ROWS_PER_STRATEGY = {"A_control_only": 300, "B_control_plus_enh": 300, "C_separate": 1000}
TARGET = "A_control_only"
LIMIT = 50
N_QUERIES = 20
OUT = Path("results/ann_filter_demo.json")

# The strategy must be a literal, not a bind parameter: the planner can only use a partial
# index when it can prove the query's WHERE implies the index predicate at plan time.
QUERY = sql.SQL(
    "SELECT id FROM ann_demo WHERE strategy = {} ORDER BY embedding <=> %s::vector LIMIT {}"
).format(sql.Literal(TARGET), sql.Literal(LIMIT))

# (label, index to have in place, session settings). enable_seqscan=off forces the index:
# at ~1.6k rows the planner would otherwise pick an exact sequential scan by itself.
SETUPS = [
    ("exact: sequential scan, no index", None, {}),
    ("global index, ef_search=40 (default)", "global", {"enable_seqscan": "off", "hnsw.ef_search": "40"}),
    ("global index, ef_search=100", "global", {"enable_seqscan": "off", "hnsw.ef_search": "100"}),
    ("global index, ef_search=40, iterative_scan=relaxed_order", "global",
     {"enable_seqscan": "off", "hnsw.ef_search": "40", "hnsw.iterative_scan": "relaxed_order"}),
    ("partial index, ef_search=40 (default)", "partial", {"enable_seqscan": "off", "hnsw.ef_search": "40"}),
    ("partial index, ef_search=100", "partial", {"enable_seqscan": "off", "hnsw.ef_search": "100"}),
]

INDEX_DDL = {
    "global": "CREATE INDEX ann_demo_idx ON ann_demo USING hnsw (embedding vector_cosine_ops)",
    "partial": "CREATE INDEX ann_demo_idx ON ann_demo USING hnsw (embedding vector_cosine_ops) "
               f"WHERE strategy = '{TARGET}'",
}


def random_unit_vector(rng: random.Random) -> str:
    v = [rng.gauss(0, 1) for _ in range(DIM)]
    norm = sum(x * x for x in v) ** 0.5
    return "[" + ",".join(f"{x / norm:.6f}" for x in v) + "]"


def plan_shape(conn, query_vector: str) -> str:
    (plan,) = conn.execute(sql.SQL("EXPLAIN (FORMAT JSON) ") + QUERY, (query_vector,)).fetchone()
    node, shape = plan[0]["Plan"], []
    while node:
        shape.append(node["Node Type"] + (f" ({node['Index Name']})" if "Index Name" in node else ""))
        node = node.get("Plans", [None])[0]
    return " > ".join(shape)


def measure(conn, queries: list[str]) -> dict:
    counts, latencies = [], []
    for q in queries:
        start = time.perf_counter()
        counts.append(len(conn.execute(QUERY, (q,)).fetchall()))
        latencies.append((time.perf_counter() - start) * 1000)
    return {
        "rows_returned": {"min": min(counts), "median": statistics.median(counts), "max": max(counts)},
        "latency_ms_p50": round(statistics.median(latencies), 2),
    }


def main() -> None:
    rng = random.Random(SEED)
    rows = [(s, random_unit_vector(rng)) for s, n in ROWS_PER_STRATEGY.items() for _ in range(n)]
    queries = [random_unit_vector(rng) for _ in range(N_QUERIES)]

    with connect() as conn:
        (pgvector_version,) = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        (postgres_version,) = conn.execute("SHOW server_version").fetchone()
        conn.execute("CREATE TABLE ann_demo (id serial PRIMARY KEY, strategy text NOT NULL, embedding vector(384) NOT NULL)")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO ann_demo (strategy, embedding) VALUES (%s, %s::vector)", rows)
        conn.execute("ANALYZE ann_demo")

        conn.execute(INDEX_DDL["partial"])
        default_plan = plan_shape(conn, queries[0])
        conn.execute("DROP INDEX ann_demo_idx")

        results, current_index = [], None
        for label, index, settings in SETUPS:
            if index != current_index:
                if current_index:
                    conn.execute("DROP INDEX ann_demo_idx")
                if index:
                    conn.execute(INDEX_DDL[index])
                current_index = index
            conn.execute("RESET ALL")
            for name, value in settings.items():
                conn.execute(sql.SQL("SET {} = {}").format(sql.Identifier(*name.split(".")), sql.Literal(value)))
            results.append({"setup": label, "plan": plan_shape(conn, queries[0]), **measure(conn, queries)})
        conn.rollback()

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "what": "Rows returned for a strategy-filtered top-50 ANN query under different index setups",
        "caveat": "Synthetic random unit vectors: measures result counts and latency, not retrieval quality",
        "pgvector_version": pgvector_version,
        "postgres_version": postgres_version,
        "seed": SEED,
        "rows_per_strategy": ROWS_PER_STRATEGY,
        "target_strategy": TARGET,
        "limit": LIMIT,
        "n_queries": N_QUERIES,
        "default_plan_with_partial_index": default_plan,
        "setups": results,
    }, indent=2) + "\n")
    for r in results:
        print(f"{r['setup']:<58} rows={r['rows_returned']}  p50={r['latency_ms_p50']}ms  plan={r['plan']}")
    print(f"default plan (no forcing, partial index present): {default_plan}")


if __name__ == "__main__":
    main()
