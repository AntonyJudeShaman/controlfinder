"""`make embed`: fill chunks.embedding with bge-small-en-v1.5 vectors, for every strategy.

Passages are embedded as they are; only queries get BGE's instruction prefix (see
retrieval/dense.py). The model's own pipeline cuts each chunk at 512 tokens, takes the [CLS]
token's vector and scales it to length 1, so cosine distance is 1 minus the dot product.
VACUUM ANALYZE afterwards clears the row versions the UPDATE replaced and refreshes the
planner's statistics. Writes results/embed_stats.json.
"""

import json
from pathlib import Path

from controlfinder.index.db import connect
from controlfinder.ingest.sources import EMBED_MODEL, EMBED_REVISION
from controlfinder.ingest.stats import MAX_TOKENS
from controlfinder.retrieval.dense import load_model, to_pgvector

OUT = Path("results/embed_stats.json")
UNIT_LENGTH_TOLERANCE = 1e-5


def main() -> None:
    model = load_model()
    if model.max_seq_length != MAX_TOKENS:
        raise RuntimeError(f"the model reads {model.max_seq_length} tokens, but corpus stats assume {MAX_TOKENS}")
    with connect() as conn:
        rows = conn.execute("SELECT chunk_id, text FROM chunks ORDER BY chunk_id").fetchall()
        vectors = model.encode([text for _, text in rows], batch_size=32, normalize_embeddings=True,
                               show_progress_bar=True)
        if (worst := max(abs(float(v @ v) ** 0.5 - 1) for v in vectors)) > UNIT_LENGTH_TOLERANCE:
            raise RuntimeError(f"a vector's length is off by {worst}")
        with conn.cursor() as cur:
            cur.executemany("UPDATE chunks SET embedding = %s::vector WHERE chunk_id = %s",
                            [(to_pgvector(v), chunk_id) for (chunk_id, _), v in zip(rows, vectors, strict=True)])
    with connect(autocommit=True) as conn:
        conn.execute("VACUUM ANALYZE chunks")
        per_strategy = dict(conn.execute(
            "SELECT strategy, count(*) FROM chunks WHERE embedding IS NOT NULL GROUP BY 1 ORDER BY 1").fetchall())
        # Truncation made visible: a B vector equal to its A vector carries none of B's enhancements.
        without, cut_off, with_enhancements = conn.execute(
            "SELECT count(*) FILTER (WHERE b.text = a.text),"
            " count(*) FILTER (WHERE b.text <> a.text AND (a.embedding <=> b.embedding) < 1e-6),"
            " count(*) FILTER (WHERE b.text <> a.text)"
            " FROM chunks a JOIN chunks b ON b.control_id = a.control_id AND b.strategy = 'B_control_plus_enh'"
            " WHERE a.strategy = 'A_control_only'").fetchone()

    OUT.write_text(json.dumps({
        "model": EMBED_MODEL,
        "revision": EMBED_REVISION,
        "dimensions": model.get_embedding_dimension(),
        "max_seq_length": model.max_seq_length,
        "chunks_embedded": per_strategy,
        "unit_length_tolerance": UNIT_LENGTH_TOLERANCE,
        "b_vector_equals_a": {
            "base_controls_without_enhancements": without,
            "base_controls_with_enhancements": with_enhancements,
            "of_which_every_enhancement_was_cut_off": cut_off,
        },
    }, indent=2) + "\n")
    print(f"embedded {sum(per_strategy.values())} chunks {per_strategy}; wrote {OUT}")


if __name__ == "__main__":
    main()
