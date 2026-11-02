"""The CI regression gate: hybrid retrieval on 30 dev queries, without downloading a model.

CI can't afford the embedding model, so `make ci-fixture` saves, from a fully embedded local
database, the vector of every strategy C chunk (with a hash of its text) and of 30 dev queries
drawn with the project seed. In CI, `load` writes those vectors into a freshly ingested
database and refuses if a chunk's text changed, because its vector would then be stale.
`gate` runs hybrid search (BM25 + dense, RRF, no reranker, as amended on 2026-11-01) for the 30
queries and fails if recall@10 is more than 3 points below results/ci_baseline.json, which
`baseline` writes with the same code. Usage: python -m controlfinder.eval.ci fixture|load|baseline|gate
"""

import gzip
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

from controlfinder.eval.baselines import rounded
from controlfinder.eval.bootstrap import SEED
from controlfinder.eval.goldset import load_queries
from controlfinder.eval.metrics import DEPTH, query_metrics
from controlfinder.index.db import connect
from controlfinder.ingest.sources import EMBED_MODEL, EMBED_REVISION
from controlfinder.retrieval import dense
from controlfinder.retrieval.pipeline import Retriever

FIXTURE = Path("data/ci/fixture.json.gz")
BASELINE = Path("results/ci_baseline.json")
STRATEGY = "C_separate"
RETRIEVAL = "hybrid"
QUERIES = 30
METRIC = "recall@10"
TOLERANCE = 0.03


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_fixture() -> dict:
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def fixture() -> None:
    queries = sorted(random.Random(SEED).sample(load_queries("dev"), QUERIES), key=lambda q: q.id)
    with connect() as conn:
        chunks = conn.execute("SELECT chunk_id, text, embedding::text FROM chunks WHERE strategy = %s ORDER BY chunk_id",
                              (STRATEGY,)).fetchall()
    if any(vector is None for _, _, vector in chunks):
        raise SystemExit("some strategy C chunks have no embedding: run `make embed`")
    vectors = dense.embed_queries(dense.load_model(), [q.text for q in queries])
    data = {"strategy": STRATEGY, "model": EMBED_MODEL, "revision": EMBED_REVISION,
            "chunks": [{"chunk_id": c, "text_sha256": sha256(text), "embedding": v} for c, text, v in chunks],
            "queries": [{"id": q.id, "text": q.text, "embedding": v} for q, v in zip(queries, vectors, strict=True)]}
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    print(f"wrote {FIXTURE}: {len(chunks)} chunks, {len(queries)} queries")


def load() -> None:
    saved = {c["chunk_id"]: c for c in read_fixture()["chunks"]}
    with connect() as conn:
        texts = dict(conn.execute("SELECT chunk_id, text FROM chunks WHERE strategy = %s", (STRATEGY,)).fetchall())
        stale = sorted(c for c in texts.keys() | saved.keys()
                       if c not in texts or c not in saved or sha256(texts[c]) != saved[c]["text_sha256"])
        if stale:
            raise SystemExit(f"{len(stale)} strategy C chunks don't match the fixture, such as {stale[:3]}:"
                             " rebuild it with `make ci-fixture`, then `make ci-baseline`")
        with conn.cursor() as cur:
            cur.executemany("UPDATE chunks SET embedding = %s::vector WHERE chunk_id = %s",
                            [(c["embedding"], c["chunk_id"]) for c in saved.values()])
        conn.execute("ANALYZE chunks")
    print(f"loaded {len(saved)} chunk vectors")


def recall() -> dict[str, float]:
    """Each fixture query's recall@10 from hybrid search, using its saved vector."""
    dev = {q.id: q for q in load_queries("dev")}
    per_query = {}
    with connect(autocommit=True) as conn:
        retriever = Retriever(conn, STRATEGY)
        for saved in read_fixture()["queries"]:
            q = dev[saved["id"]]
            if q.text != saved["text"]:
                raise SystemExit(f"query {q.id} changed since the fixture was built: rebuild it with `make ci-fixture`")
            parents = [h.parent_control_id for h in retriever.search(RETRIEVAL, q.text, saved["embedding"])]
            per_query[q.id] = query_metrics(parents[:DEPTH], set(q.gold))[METRIC]
    return per_query


def baseline() -> None:
    per_query = recall()
    BASELINE.write_text(json.dumps(rounded({
        "what": "The CI gate's baseline: hybrid retrieval (BM25 + dense, RRF, no reranker) on the fixture's dev queries",
        "strategy": STRATEGY, "retrieval": RETRIEVAL, "queries": len(per_query), "tolerance": TOLERANCE,
        METRIC: statistics.fmean(per_query.values()), "per_query": per_query}), indent=2) + "\n")
    print(f"wrote {BASELINE}: {METRIC} {statistics.fmean(per_query.values()):.4f}")


def gate() -> None:
    saved = json.loads(BASELINE.read_text())
    per_query = recall()
    now, floor = rounded(statistics.fmean(per_query.values())), rounded(saved[METRIC] - TOLERANCE)
    for qid, value in per_query.items():
        if rounded(value) != saved["per_query"][qid]:
            print(f"  {qid}: {METRIC} {saved['per_query'][qid]} -> {rounded(value)}")
    print(f"{METRIC} {now} on {len(per_query)} queries; baseline {saved[METRIC]}, floor {floor}")
    if now < floor:
        sys.exit(f"FAIL: {METRIC} dropped more than {TOLERANCE * 100:.0f} points below the baseline")
    print("PASS")


if __name__ == "__main__":
    {"fixture": fixture, "load": load, "baseline": baseline, "gate": gate}[sys.argv[1]]()
