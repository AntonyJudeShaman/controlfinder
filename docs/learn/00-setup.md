# Phase 0: Setup

## What we built

A local Postgres 16 database with the pgvector 0.8.7 extension, a schema that every later phase writes into, and the tooling to bring it up, check it, and keep docs honest.

| File | What it is |
|---|---|
| `docker-compose.yml` | Postgres + pgvector, image pinned by tag and digest, named volume `pgdata`, TCP health check, host port 5433 |
| `src/controlfinder/index/schema.sql` | Tables `controls`, `chunks`, `query_log`; a GIN index for full-text search; one HNSW index per chunking strategy |
| `src/controlfinder/index/db.py` | `connect()` (reads `DATABASE_URL` from `.env`) and `apply_schema()` |
| `src/controlfinder/index/ann_filter_demo.py` | Reproduces the filtered-HNSW pitfall on synthetic vectors and writes `results/ann_filter_demo.json` |
| `src/controlfinder/docgen.py` | Renders doc tables from `results/*.json` (`make docs`) |
| `tests/test_db_smoke.py` | DB reachable, iterative scans supported, tables exist, `tsv` is generated, one HNSW index per strategy |
| `tests/test_docs_generated.py` | Fails if a generated table in the docs disagrees with `results/` |
| `Makefile` | `up`, `down`, `reset-db`, `schema`, `psql`, `test`, `ann-demo`, `docs` |
| `pyproject.toml`, `uv.lock` | Exact pins plus an `exclude-newer` cutoff date |
| `AGENTS.md`, `DECISIONS.md` | The project prompt with agreed amendments; the decision log |

## How it works

### `make up`, step by step

1. If `.env` is missing, copy `.env.example` to it. That gives `DATABASE_URL=postgresql://controlfinder:controlfinder@localhost:5433/controlfinder`.
2. `docker compose up -d --wait` starts the container and blocks until the health check (`pg_isready -h 127.0.0.1`) passes.
3. `make schema` runs `python -m controlfinder.index.db`, which executes `schema.sql`. Every statement is `IF NOT EXISTS`, so running it twice is harmless. We checked that.

### The schema

The part that matters most is the `chunks` table and its indexes:

```sql
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id           text PRIMARY KEY,
    strategy           text NOT NULL
                       CHECK (strategy IN ('A_control_only', 'B_control_plus_enh', 'C_separate')),
    control_id         text NOT NULL REFERENCES controls (id),
    parent_control_id  text NOT NULL REFERENCES controls (id),  -- = control_id for base controls
    text               text NOT NULL,
    -- Postgres computes this on every write; it can never drift from `text`.
    tsv                tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    embedding          vector(384)                              -- NULL until `make embed`
);

CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);              -- keyword search

-- One HNSW graph per strategy (a "partial index": it only contains rows matching WHERE).
CREATE INDEX chunks_embedding_hnsw_c ON chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE strategy = 'C_separate';
-- ... the same for 'A_control_only' and 'B_control_plus_enh'
```

`controls` holds one row per active control or enhancement. A CHECK constraint enforces `is_enhancement ⇔ parent_id IS NOT NULL`, so an enhancement can't exist without its parent. `query_log` has one row per request, with `jsonb` columns for what was retrieved, the scores, per-stage latency and the agent's trace.

### What a dense query must look like to use the index

```sql
SET hnsw.ef_search = 100;             -- must be >= LIMIT, or you get at most ef_search rows
SELECT chunk_id, embedding <=> %(q)s AS distance
FROM chunks
WHERE strategy = 'C_separate'         -- a literal, so the planner can match the partial index
ORDER BY embedding <=> %(q)s          -- <=> is cosine distance, the operator vector_cosine_ops indexes
LIMIT 50;
```

pgvector only uses the index when all of these hold:

- The ORDER BY uses the operator that matches the index's operator class. `vector_cosine_ops` goes with `<=>`. Ordering by `<->` (L2 distance) instead silently does an exact scan.
- The query's WHERE clause provably implies the index's WHERE clause, which requires a literal.
- The query has an ORDER BY distance with a LIMIT.
- The planner thinks the index is cheaper than scanning the table. At our size, it doesn't (see below).

### The filtered-ANN demo

`make ann-demo` builds a throwaway 1,600-row table shaped like `chunks`, with 300 rows of strategy A, 300 of B and 1,000 of C, all random unit vectors. It asks 20 queries for the 50 nearest strategy-A rows under each setup, then rolls everything back. The vectors are random, so this measures how many rows come back, not retrieval quality.

<!-- BEGIN generated: ann_filter_demo -->
| Setup (top-50 for A_control_only) | Rows returned: median (min–max) | p50 latency (ms) | Plan |
|---|---|---|---|
| exact: sequential scan, no index | 50 (50–50) | 0.61 | Limit > Sort > Seq Scan |
| global index, ef_search=40 (default) | 7 (2–11) | 0.67 | Limit > Index Scan (ann_demo_idx) |
| global index, ef_search=100 | 19 (12–25) | 0.71 | Limit > Index Scan (ann_demo_idx) |
| global index, ef_search=40, iterative_scan=relaxed_order | 50 (50–50) | 0.93 | Limit > Index Scan (ann_demo_idx) |
| partial index, ef_search=40 (default) | 40 (40–40) | 0.53 | Limit > Index Scan (ann_demo_idx) |
| partial index, ef_search=100 | 50 (50–50) | 0.6 | Limit > Index Scan (ann_demo_idx) |
<!-- END generated: ann_filter_demo -->

How to read the table:

- **Global index, default `ef_search`.** HNSW collected its 40 best candidates from the whole table. Only the strategy-A rows among them survived the WHERE filter, a median of 7 of the 50 we asked for. Nothing errors and nothing warns. Raising `ef_search` to 100 only gets you to about 19.
- **Iterative scan** (pgvector 0.8+). The index scan keeps going until the LIMIT is filled, so it returns all 50 even with a global index.
- **Partial index, default `ef_search`.** Exactly 40 rows. There's no filter loss, because the graph only contains A rows, but `ef_search` caps the result count.
- **Partial index, `ef_search = 100`.** All 50. This is what our schema and queries do.
- **Default plan.** Without forcing, the planner chose `Limit > Sort > Seq Scan`, an exact search, even with the partial index available. At 1,600 rows, reading everything is cheaper than walking a graph.

## Concepts

### Why pgvector instead of a dedicated vector database

**At our scale.** The corpus is about a thousand controls (Phase 1 saves the exact count), so all three strategies together come to a few thousand chunks. In the demo, an exact sequential scan over 1,600 vectors answered in about a millisecond, round trip included. A dedicated vector database can't beat "exact and about a millisecond". What Postgres gives us is one system. Controls, chunks, the full-text index, the vectors and the query log live together. Hybrid search is one SQL round trip with joins to metadata and real transactions, and there's one thing to back up and operate.

**In general.** Purpose-built engines such as Qdrant, Milvus or Pinecone earn their keep when:

- you have hundreds of millions of vectors and need sharding and replication built in;
- you need very high query rates;
- you need filtered search integrated into the graph traversal;
- you need quantization and tiered storage to fit indexes in memory.

pgvector's limits are real:

- An HNSW index performs well only when it fits in memory.
- Builds need `maintenance_work_mem`.
- Writes scale on a single primary.
- Dead tuples and filters can shrink result sets.
- Indexed `vector` columns top out at 2,000 dimensions (`halfvec` goes to 4,000).

For an app that already runs Postgres with up to a few million vectors, pgvector is usually the right first choice.

### HNSW vs IVFFlat

**IVFFlat (inverted file):**

- **Build.** Run k-means on the existing rows to find `lists` centroids, then assign each row to its nearest centroid's list.
- **Query.** Find the `probes` nearest centroids, and scan only those lists, exactly.
- **Knobs.** `lists` is fixed at build time. `probes` is per query; more probes means higher recall and slower queries, and `probes = lists` is an exact search.
- **Tradeoffs.** It builds fast and stays small. It needs data before you build it, since centroids are learned from the rows. Its recall drifts as new data stops matching the old centroids, until you rebuild. pgvector's rule of thumb is `lists = rows / 1000` up to a million rows.

**HNSW (hierarchical navigable small world):**

- **Build.** Every inserted vector draws a random top layer. Upper layers are exponentially sparser, like an express lane. A node keeps up to `m` neighbors per layer (2·`m` on the bottom layer). `ef_construction` is the candidate-list size used when choosing those neighbors; a higher value gives a better graph and a slower build.
- **Query.** Start at the entry point on the top layer and greedily hop to closer neighbors, dropping a layer at a time. On the bottom layer, run a best-first search that keeps the best `ef_search` candidates, then return the top LIMIT of them. That's why a query can never return more than `ef_search` rows.
- **Tradeoffs.** HNSW has a better speed-recall curve than IVFFlat and no training step, so it can be built on an empty table and handles inserts. It costs a slower build and more memory.

| Knob | Index | When it applies | Effect of raising it |
|---|---|---|---|
| `m` | HNSW | build | More edges per node: better recall, bigger and slower index |
| `ef_construction` | HNSW | build | Better neighbor choices: better recall, slower build |
| `ef_search` | HNSW | query | More candidates: better recall, slower queries, and the cap on result count |
| `lists` | IVFFlat | build | Smaller lists: faster queries at fixed probes, lower recall |
| `probes` | IVFFlat | query | More lists scanned: better recall, slower queries |

We chose HNSW: no training step, a better recall-speed curve, and it's what production systems use. We always measure it against exact search, because at our size exact search is the real competitor.

### Cosine similarity and normalized embeddings

- Cosine similarity, `cos(a, b) = a·b / (‖a‖ ‖b‖)`, compares direction and ignores length. Embedding models encode meaning in direction.
- pgvector's `<=>` returns cosine **distance**, `1 − cos`: 0 means the same direction, 2 means opposite.
- A normalized embedding has length 1. For unit vectors, `cos(a, b) = a·b` and `‖a − b‖² = 2 − 2·a·b`. That means cosine, dot product and L2 distance all rank neighbors identically. BGE models are trained with cosine similarity, and we'll normalize at embed time in Phase 2.
- **Why still `vector_cosine_ops`?** With unit vectors, inner product (`<#>`, `vector_ip_ops`) gives the same ranking for slightly less arithmetic. Cosine stays correct even if an unnormalized vector slips in, and the operator class must match the operator in the ORDER BY, so we picked one and use it everywhere.
- Zero vectors aren't indexed for cosine (their direction is undefined), and neither are NULLs. Chunks therefore only enter the HNSW graph once `make embed` has filled `embedding`.

### Why a generated `tsvector` column

Postgres full-text search compares a `tsvector`, the document's normalized lexemes with positions, against a `tsquery`. You could produce the `tsvector` in four ways:

1. **Compute it in every query** (`to_tsvector('english', text) @@ q`). Postgres re-parses every row on every query.
2. **Expression index on that same expression.** Matching gets fast, but the query must repeat the exact expression to use the index, and ranking still recomputes the vector.
3. **A column maintained by a trigger.** This was the pre-Postgres-12 way. It's more code, and it can drift if the trigger is disabled or buggy.
4. **A generated STORED column** (our choice). Postgres computes it on every write, so it always matches `text`. GIN indexes it, and both matching and `ts_rank_cd` read it directly. The cost is some extra storage and work at write time, which is trivial for a few thousand rows.

The smoke test shows what "normalized lexemes" means. `'Managing accounts and accounting'` becomes `'account':2,4 'manag':1`. Stemming folds "accounts" and "accounting" into one lexeme. The stopword "and" disappears but keeps position 3, because `ts_rank_cd` cares about how close the matches are.

### Correction: Postgres FTS ranking is not BM25

The original prompt describes FTS as having "no IDF saturation". That mixes two different ideas. BM25 scores a document D for a query Q as follows:

```
score(D, Q) = Σ over query terms t of  IDF(t) · f(t,D)·(k1 + 1) / ( f(t,D) + k1·(1 − b + b·|D|/avgdl) )

IDF(t) = ln( 1 + (N − n_t + 0.5) / (n_t + 0.5) )      # N docs in the corpus, n_t of them contain t
```

- **IDF** is a rarity weight that needs corpus statistics. A match on "cryptographic" is worth more than a match on "information", which appears in almost every control.
- **Term-frequency saturation (`k1`, typically 1.2–2).** The tenth occurrence of a term adds much less than the first.
- **Length normalization (`b`, typically 0.75).** A match in a short chunk counts for more than the same match in a long one.

Postgres's `ts_rank` and `ts_rank_cd` look at one document at a time and use no corpus statistics, so they have no IDF at all. `ts_rank` weights by how often the terms occur. `ts_rank_cd` uses "cover density", which rewards matched terms that appear close together. Neither has BM25-style saturation, and length normalization is off by default; you opt in with a normalization flag (for example, `1` divides by 1 + log(length)). Phase 2 measures whether these differences matter on our data.

## Decisions

Each of these has a row in `DECISIONS.md`.

- **Image `pgvector/pgvector:0.8.7-pg16`, pinned by digest, instead of the floating `pg16` tag.** It's the newest pg16 tag at least two weeks old. The digest is a multi-arch index, so the same pin works on an arm64 Mac and amd64 CI.
- **Exact pins plus `exclude-newer = 2026-10-09`, instead of pinning direct dependencies only.** The cutoff applies the two-week rule to transitive dependencies too. `uv.lock` records what was resolved: 12 packages.
- **One partial HNSW index per strategy, instead of a global index, a global index with iterative scan, or a table per strategy.** The demo shows a global index returning a median of 7 of 50 rows, while the partial index returns all 50 at `ef_search = 100`. Iterative scan also fills the LIMIT. It's the general fix when filter values are many or dynamic, like per-tenant data, and we'll compare its recall on real embeddings in Phase 2.
- **Strategy as a SQL literal, not a bind parameter.** With `PREPARE`, a custom plan used `chunks_embedding_hnsw_a`, but a generic plan (`plan_cache_mode = force_generic_plan`) fell back to `Seq Scan` + `Sort`. psycopg prepares statements on the server after 5 executions, and Postgres may then switch to a generic plan, so a bind parameter could quietly turn "HNSW" into exact search halfway through an eval.
- **Always measure HNSW against exact search, and record the plan.** The planner picks exact search at our size (`default_plan_with_partial_index` in the demo). "HNSW recall" only means something if the index actually ran.
- **Schema applied from Python instead of `docker-entrypoint-initdb.d`.** Init scripts only run on an empty volume, and CI's service container can't mount them the same way. `make schema` works in both places and is idempotent.
- **TCP health check.** On first boot, the image runs a temporary server that listens only on the Unix socket while init scripts run. A socket check can report "ready" before the real server is up.
- **`parent_control_id` NOT NULL, equal to `control_id` for base controls.** Parent-level dedup becomes a single column.
- **CHECK on `strategy`.** A misspelled strategy would silently miss its partial index.
- **Host port 5433.** It avoids colliding with a locally installed Postgres.
- **Generated doc tables.** A test fails if a doc table disagrees with `results/`. That's how we keep the "never type a number" rule honest.

## Gotchas we hit

1. **Docker wasn't running.** The Docker CLI talks to Colima's VM, which was stopped. Fix: `colima start`.
2. **Filtered HNSW silently drops rows.** See the demo: a median of 7 of 50 with a global index at the default `ef_search`.
3. **`ef_search` caps results even with no filter loss.** The partial index at the default returned exactly 40.
4. **The planner ignores HNSW at our size.** The default plan is an exact sequential scan. To measure HNSW, we have to force it (`SET enable_seqscan = off`) and say so.
5. **Generic plans can't use partial indexes.** We verified this with `PREPARE`. Fix: interpolate the strategy as a literal with `psycopg.sql.Literal`.
6. **`hnsw.*` settings are fake until the extension library loads.** In a fresh session, `SET hnsw.made_up_setting = 'x'` succeeded, while `SHOW hnsw.iterative_scan` failed with "unrecognized configuration parameter". After any vector operation loads the library, pgvector reserves the `hnsw.` prefix and the same typo errors. So a typo like `hnsw.ef_serach` at the start of a session would be silently ignored. The smoke test loads the library before checking the setting.
7. **Seeds don't make HNSW builds reproducible.** Across three runs of the demo, the global-index counts moved by a row or two, while every count fixed by structure (50, 40, 50) stayed put. pgvector draws each node's layer at random, and our Python seed doesn't reach that. Reproducibility here means "same data, same settings, measured recall", not bit-identical graphs.

## Interview questions

**1. Why Postgres and pgvector instead of a dedicated vector database?**
Our corpus is about a thousand controls, so a few thousand chunks across three chunking strategies. In our demo, an exact sequential scan over 1,600 vectors answered in about a millisecond including the round trip, so a dedicated engine buys no speed. Postgres keeps controls, chunks, the full-text index, vectors and logs in one place, which makes hybrid search a single SQL query with joins and transactions, and leaves one system to operate. I'd revisit at hundreds of millions of vectors, very high query rates, or heavy filtered search, where sharding, quantization and filter-aware indexes matter.

**2. Explain HNSW vs IVFFlat, and what `ef_search`, `lists` and `probes` do.**
IVFFlat clusters the vectors into `lists` with k-means at build time, then each query scans only the `probes` nearest clusters exactly. It builds fast but needs data first and drifts as data changes. HNSW builds a layered proximity graph, with `m` edges per node and `ef_construction` controlling build quality. A query walks down the layers and keeps the best `ef_search` candidates on the bottom one. Raising `ef_search` or `probes` trades latency for recall, and with HNSW `ef_search` also caps how many rows can come back: our partial index returned exactly 40 rows for a LIMIT of 50 at the default of 40.

**3. You put `WHERE strategy = 'A'` on an HNSW query. What happens?**
pgvector applies the filter after the index search, so you only get the matching rows among the `ef_search` candidates. In our demo, a global index at the default setting returned a median of 7 of the 50 rows we asked for, with no error or warning, and raising `ef_search` to 100 only reached about 19. The fixes are a partial index per filter value, which returned all 50 at `ef_search = 100`, or pgvector 0.8's iterative scan, which also returned 50. We chose partial indexes because we have exactly three fixed strategies, and we'll compare iterative scan on real embeddings in Phase 2.

**4. Your planner picked a sequential scan. Is the HNSW index useless?**
At our size, the planner is right: reading 1,600 rows is cheaper than walking a graph, and it's exact. The index is there because it's the production design and becomes the default path at around 100 times our size. It also lets us measure what ANN costs in recall against exact search, which we do in Phase 2 by forcing it with `enable_seqscan = off`. The trap is reporting "HNSW numbers" that were actually exact search, so every dense result records which plan ran.

**5. Why cosine, and what does normalizing embeddings buy you?**
Embedding models put meaning in a vector's direction, and cosine compares direction while ignoring length. Once vectors have length 1, cosine, dot product and L2 distance rank neighbors identically, because ‖a − b‖² = 2 − 2·a·b. We use pgvector's `<=>` with `vector_cosine_ops`. The operator has to match the operator class, or Postgres silently skips the index. Inner product would be a hair faster on unit vectors, but cosine stays correct if an unnormalized vector ever slips in.

**6. Why a generated `tsvector` column?**
It's computed once per write instead of on every query, and Postgres maintains it, so it can never drift from the text the way a buggy trigger can. GIN indexes it, and both matching and `ts_rank_cd` read it directly. It needs an explicit text-search config, `to_tsvector('english', text)`, because generated columns must be immutable and the one-argument form depends on a session setting. Our smoke test pins the behavior: "Managing accounts and accounting" becomes `'account':2,4 'manag':1`.

**7. Is Postgres's `ts_rank_cd` BM25? If not, what's different?**
No. BM25 multiplies each matching term's IDF, a corpus-wide rarity weight, by a term-frequency curve that saturates through k1, and normalizes for document length through b. `ts_rank_cd` looks at one document at a time, so it has no IDF: a match on "information" counts like a match on "cryptographic". It scores how densely the matched terms cluster, and length normalization is off unless you pass a flag. That's why we run real BM25 with `rank_bm25` next to Postgres FTS in Phase 2, and let the numbers decide.

**8. How did you make the setup reproducible, and what still isn't?**
The Postgres image is pinned by digest, direct dependencies are pinned exactly, and `exclude-newer` makes uv ignore anything published after 2026-10-09, so the lockfile can't pick up a fresh transitive release. The schema is idempotent, and every step is one `make` command. What isn't bit-reproducible is the HNSW graph: across three demo runs, the global-index row counts moved by a row or two because pgvector picks node layers at random. LLM outputs won't be reproducible either, which is why every LLM response is cached on disk from Phase 4.

## Follow-ups from the quiz

**Every strategy-A row is in the global index. Why doesn't the search find 50 of them?**
The HNSW index stores vectors, neighbor links and row pointers, not `strategy`, so it can't apply the filter while it searches. Without iterative scan, it returns one batch of `ef_search` candidates and stops; Postgres filters that batch afterwards and has no way to ask for a second one. Expect about `ef_search` × the filter's share of rows to survive: 40 × 300/1,600 ≈ 7.5 (we measured a median of 7), and 100 × 300/1,600 ≈ 19 (we measured 19). A B-tree doesn't have this problem, because its scan just keeps reading the next entry until enough rows pass the filter.

**Why set `ef_search` above the LIMIT instead of equal to it?**
First, `ef_search` is a hard ceiling on the rows returned: the partial index at 40 returned exactly 40 for a LIMIT of 50. Above that minimum, a bigger candidate list also improves accuracy. The search stops only when the nearest unexplored node is farther away than the worst candidate in its list, so a longer list keeps it exploring longer, and the best 50 of 100 candidates are more likely to be the true 50 nearest. 100 is a starting value, not a measured one; Phase 2 measures recall against exact search at several values.

**Why can't Postgres use our cosine index for `ORDER BY embedding <-> q`?**
An index can serve ORDER BY only with an operator in its operator class, and `vector_cosine_ops` contains only `<=>`. The graph's links were chosen by cosine distance, and Postgres can't assume every vector is normalized (for unnormalized vectors, cosine and L2 distance rank differently), so it plans an exact scan instead. With our normalized vectors the results would be identical, but the scan is slower at scale, and any "HNSW" number would silently be an exact-search number.

**Is "exact search" the same as exact keyword matching?**
No. There are two separate choices: what "close" means (meaning, through embeddings, or shared words, through BM25 or FTS) and how carefully you look (exact means checking everything; approximate means a shortcut like HNSW). Exact vector search returns the true nearest chunks by meaning, but it still doesn't match keywords. That's why it can miss a literal control ID or acronym, and why Phase 3 combines it with keyword search.

**Would you copy the partial-index design for 500 tenants filtered by `tenant_id`?**
No. Three fixed strategies justify three partial indexes, but 500 tenants that come and go would mean DDL on every signup, 500 graphs to maintain, and a slower planner. One global index fails the other way: with equal-sized tenants, each owns 0.2% of the rows, so the default `ef_search` of 40 expects 0.08 matching candidates, and iterative scan would need to visit about 25,000 rows to fill a LIMIT of 50, past pgvector's default `hnsw.max_scan_tuples` of 20,000. Instead, use a B-tree on `tenant_id` with exact search for small tenants and partitions with their own HNSW index for the few large ones. To prove completeness, assert that each query returns min(LIMIT, tenant size) rows and measure recall against exact search, deliberately including the smallest tenants.
