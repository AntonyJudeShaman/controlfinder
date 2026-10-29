-- ControlFinder schema. Idempotent, so `make schema` is safe to re-run.
-- IF NOT EXISTS never alters an existing table: after changing a column, run `make reset-db`.

CREATE EXTENSION IF NOT EXISTS vector;

-- Active SP 800-53 controls and enhancements, keyed by normalized OSCAL id ('ac-2', 'ac-2.1').
CREATE TABLE IF NOT EXISTS controls (
    id              text PRIMARY KEY,
    family          text NOT NULL,
    title           text NOT NULL,
    statement       text NOT NULL,
    guidance        text,
    parent_id       text REFERENCES controls (id),
    is_enhancement  boolean NOT NULL,
    CHECK (is_enhancement = (parent_id IS NOT NULL))
);

-- All three chunking strategies share one table; `strategy` selects the experiment.
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id           text PRIMARY KEY,
    strategy           text NOT NULL
                       CHECK (strategy IN ('A_control_only', 'B_control_plus_enh', 'C_separate')),
    control_id         text NOT NULL REFERENCES controls (id),
    -- Base control this chunk rolls up to (equals control_id for base controls).
    -- Metrics are computed at this level.
    parent_control_id  text NOT NULL REFERENCES controls (id),
    text               text NOT NULL,
    -- The config must be explicit: generated columns need an immutable expression, and
    -- one-argument to_tsvector(text) depends on the default_text_search_config setting.
    tsv                tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    -- bge-small-en-v1.5, L2-normalized. NULL until `make embed` runs.
    embedding          vector(384)
);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);

-- One partial HNSW index per strategy instead of one global index: an HNSW scan returns at
-- most hnsw.ef_search candidates and applies WHERE afterwards, so a global index plus
-- "WHERE strategy = ..." silently returns fewer rows than LIMIT (see results/ann_filter_demo.json).
-- To use one of these, a query must contain the same predicate with the strategy as a literal
-- and ORDER BY embedding <=> query (<=> is cosine distance, matching vector_cosine_ops).
-- m and ef_construction are pgvector's defaults, spelled out so they are visible.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_a ON chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE strategy = 'A_control_only';
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_b ON chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE strategy = 'B_control_plus_enh';
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_c ON chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE strategy = 'C_separate';

-- One row per /search, /ask or eval request. `trace` holds the agent's node transitions.
CREATE TABLE IF NOT EXISTS query_log (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    query       text NOT NULL,
    pipeline    text NOT NULL,
    retrieved   jsonb,
    scores      jsonb,
    latency_ms  jsonb,
    decision    text,
    trace       jsonb
);
