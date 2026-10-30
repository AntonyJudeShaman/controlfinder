# Phase 2: Eval set, metrics and baselines

## What we built

An answer key from NIST, 469 questions split into a dev set and a sealed test set, the metrics with confidence intervals, and the first four retrievers measured on dev. Every number below comes from `results/goldset_stats.json`, `results/embed_stats.json` or `results/baselines_dev.json`, and `make docs` regenerates the tables.

| File | What it is |
|---|---|
| `data/raw/csf2.xlsx` | NIST's CSF 2.0 "Informative References in the Core" spreadsheet, committed because its download URL isn't versioned. `ingest/sources.py` pins its sha256 |
| `src/controlfinder/eval/goldset.py` | `make goldset`: reads the spreadsheet, builds the answer key and the queries, splits them, and writes `data/eval/queries.jsonl` and `results/goldset_stats.json`. `load_queries()` refuses the test split |
| `data/eval/queries.jsonl` | The frozen answer key: one line per query, with its split and its gold controls |
| `src/controlfinder/eval/metrics.py` | recall@k and its ceiling, normalized recall, precision@k, MRR, nDCG@10, all on parent controls |
| `src/controlfinder/eval/bootstrap.py` | The cluster bootstrap (resample subcategories) and its paired version for comparing two systems |
| `src/controlfinder/index/embed.py` | `make embed`: one bge-small vector per chunk, written into `chunks.embedding` |
| `src/controlfinder/retrieval/fts.py` | Postgres full-text search, AND and OR, ranked by `ts_rank_cd` |
| `src/controlfinder/retrieval/bm25.py` | BM25 (`rank_bm25`) over the same lexemes Postgres makes |
| `src/controlfinder/retrieval/dense.py` | Query embedding with the BGE prefix, and cosine search, exact or through HNSW |
| `src/controlfinder/retrieval/__init__.py` | `Hit`, and `fetch_depth()`: how many chunks to fetch so that 20 distinct parents always fit |
| `src/controlfinder/eval/baselines.py` | `make baselines`: runs everything on dev and writes `results/baselines_dev.json` |
| `tests/test_goldset.py`, `test_metrics.py`, `test_bootstrap.py`, `test_retrieval.py` | The answer-key rules, hand-computed metric cases, bootstrap behavior, and the retrievers on hand-made chunks |

## How it works

### `make goldset`, step by step

1. **Read the spreadsheet.** Sheet `CSF 2.0`, header on row 2. Column C holds the subcategory (`GV.OC-01: The organizational mission is understood…`), column D its implementation examples (`Ex1: … Ex2: …`), column E its references, one per line. If the header changes, the run stops.
2. **Keep the right rows.** Rows without a subcategory are function or category headings; their references are ignored and counted. Rows marked `[Withdrawn: …]` are CSF 1.1 leftovers and are skipped.
3. **Keep the right references.** Only lines starting `SP 800-53 Rev 5.2.0:`, which matches our catalog. The file also carries Rev 5.1.1 references for the same rows; taking both would double-count.
4. **Resolve each reference to base controls.** A family code (`CP`) is dropped. A withdrawn control is remapped to where its content went (`RA-04` → `ra-3`). An enhancement counts as its parent (`AC-02(01)` → `ac-2`). Anything that isn't an active control raises.
5. **Build queries.** Each subcategory gives one `subcat` query (its own text) and one `example` query per implementation example. Every query of a subcategory has the same gold set.
6. **Split by subcategory.** Within each CSF function, subcategories are ordered by a sha256 of `20261023:<id>`, and the first 70% go to dev. All of a subcategory's queries land on the same side.

<!-- BEGIN generated: goldset_counts -->
| CSF 2.0 → SP 800-53 Rev 5.2.0 answer key | Count |
|---|---|
| Active subcategories | 106 |
| Withdrawn subcategory rows (skipped) | 79 |
| Subcategories with at least one 800-53 base control | 106 |
| Rev 5.2.0 references to a base control | 718 |
| Rev 5.2.0 references to an enhancement (counted as its base control) | 18 |
| Rev 5.2.0 references to a withdrawn control (remapped) | 1 |
| Rev 5.2.0 family-level references (dropped) | 3 |
| References that repeated a control already in the gold set | 4 |
| Rev 5.1.1 references (ignored) | 734 |
| Rev 5.2.0 references on function or category rows (ignored) | 6 |
| Gold controls per subcategory: min / median / max | 1 / 5 / 40 |
| Implementation examples per subcategory: min / median / max | 1 / 3 / 10 |
| Subcategories with more than 5 gold controls | 38 |
| Subcategories with more than 10 gold controls | 18 |
| Subcategories with more than 20 gold controls | 7 |
<!-- END generated: goldset_counts -->

<!-- BEGIN generated: split_counts -->
| Split | Subcategories | `subcat` queries | `example` queries | All queries | Subcategories per CSF function |
|---|---|---|---|---|---|
| dev | 75 | 75 | 263 | 338 | DE 8, GV 22, ID 15, PR 15, RC 6, RS 9 |
| test | 31 | 31 | 100 | 131 | DE 3, GV 9, ID 6, PR 7, RC 2, RS 4 |
<!-- END generated: split_counts -->

The test split is sealed in code: `load_queries("test")` raises `PermissionError` unless `CONTROLFINDER_UNSEAL_TEST=1` is set, and only the final Phase 6 run sets it. Nothing in this phase has seen a test score.

### `make embed`

Every chunk of every strategy goes through bge-small-en-v1.5 at the same pinned revision Phase 1 counted tokens with. The result is a 384-number vector per chunk, scaled to length 1 ("normalized"). All 1,614 chunks get one, and the script checks every length is 1 to within 0.00001. It ends with `VACUUM ANALYZE`, so the planner has fresh statistics after every row was rewritten. It also measures one thing Phase 1 could only guess: of the 165 base controls with enhancements, 16 have a B vector identical to their A vector, because B's 512-token window fills up before the first enhancement starts.

### `make baselines`, step by step

1. **Load the 338 dev queries.** The test split stays sealed.
2. **Embed the queries**, with the BGE instruction prefix (explained below).
3. **Pick the fetch depth.** In strategy C, several chunks share a parent, so fetching 20 chunks can give fewer than 20 controls. `fetch_depth()` asks Postgres for the 19 parents with the most chunks and adds their counts, plus one: 293. Even if the first 292 results all came from those 19 parents, result 293 has to be a 20th.
4. **Run four systems**, each fetching 293 chunks of strategy C:
   - `fts_and`: `plainto_tsquery`, so a chunk must contain every query lexeme.
   - `fts_or`: the same lexemes joined with OR. Both are ranked by `ts_rank_cd`.
   - `bm25`: `rank_bm25` over the same lexemes.
   - `dense`: exact cosine search, every chunk compared.
5. **Score.** Roll the chunks up to parent controls (each parent keeps the rank of its first chunk), keep the top 20, and compute every metric for every query.
6. **Add uncertainty.** Average per query type (`subcat`, `example`) and over all queries, each with a 95% confidence interval from the cluster bootstrap. Compare pairs of systems with the paired version.
7. **Check HNSW.** The dense queries run again through the HNSW index under six settings and are compared with exact search.
8. **Save evidence for the lessons below:** the queries where dense and BM25 disagree completely, and the words `rank_bm25` overweights.

## Results on dev

recall@10, the primary metric: of each query's gold controls, the share found in the top 10.

<!-- BEGIN generated: baseline_recall -->
| recall@10: mean [95% CI] | `subcat` (75 queries) | `example` (263 queries) | `all` (338 queries) |
|---|---|---|---|
| `fts_and` | 0.031 [0.000, 0.071] | 0.002 [0.000, 0.005] | 0.008 [0.001, 0.018] |
| `fts_or` | 0.419 [0.340, 0.495] | 0.277 [0.233, 0.325] | 0.309 [0.261, 0.360] |
| `bm25` | 0.461 [0.391, 0.538] | 0.346 [0.290, 0.408] | 0.372 [0.317, 0.433] |
| `dense` | 0.501 [0.423, 0.577] | 0.397 [0.342, 0.459] | 0.420 [0.363, 0.479] |
| ceiling (best possible) | 0.911 | 0.902 | 0.904 |
<!-- END generated: baseline_recall -->

How to read it:

- **The order is the same for every query type:** dense, then BM25, then FTS-OR, with FTS-AND near zero.
- **"Ceiling" is the best any system could score.** Some subcategories have more than 10 gold controls, and a top 10 can't hold them all. Dense, the best system, reaches 0.420 of a possible 0.904 over all queries, so there is a lot of room for Phases 3 to 5.
- **`subcat` queries score higher than `example` queries for every system.** A likely reason: the subcategory text is NIST's own wording, and NIST wrote the controls too, while the examples read more like a practitioner talking.

All metrics, per query type, with the recall ceilings:

<!-- BEGIN generated: baseline_metrics -->
| System | Queries | recall@5 | recall@10 | recall@20 | norm_recall@10 | precision@5 | precision@10 | mrr | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|
| `fts_and` | `subcat` | 0.031 | 0.031 | 0.031 | 0.032 | 0.013 | 0.007 | 0.047 | 0.035 |
| `fts_or` | `subcat` | 0.343 | 0.419 | 0.526 | 0.453 | 0.272 | 0.188 | 0.544 | 0.398 |
| `bm25` | `subcat` | 0.340 | 0.461 | 0.564 | 0.491 | 0.269 | 0.203 | 0.533 | 0.408 |
| `dense` | `subcat` | 0.387 | 0.501 | 0.635 | 0.535 | 0.301 | 0.221 | 0.660 | 0.480 |
| ceiling | `subcat` | 0.806 | 0.911 | 0.972 | – | – | – | – | – |
| `fts_and` | `example` | 0.002 | 0.002 | 0.002 | 0.002 | 0.002 | 0.001 | 0.008 | 0.003 |
| `fts_or` | `example` | 0.203 | 0.277 | 0.397 | 0.315 | 0.221 | 0.165 | 0.433 | 0.284 |
| `bm25` | `example` | 0.249 | 0.346 | 0.467 | 0.374 | 0.206 | 0.164 | 0.459 | 0.316 |
| `dense` | `example` | 0.279 | 0.397 | 0.509 | 0.429 | 0.256 | 0.197 | 0.524 | 0.373 |
| ceiling | `example` | 0.782 | 0.902 | 0.971 | – | – | – | – | – |
| `fts_and` | `all` | 0.008 | 0.008 | 0.008 | 0.009 | 0.005 | 0.002 | 0.016 | 0.010 |
| `fts_or` | `all` | 0.234 | 0.309 | 0.426 | 0.346 | 0.233 | 0.170 | 0.458 | 0.309 |
| `bm25` | `all` | 0.269 | 0.372 | 0.488 | 0.400 | 0.220 | 0.172 | 0.475 | 0.336 |
| `dense` | `all` | 0.303 | 0.420 | 0.537 | 0.453 | 0.266 | 0.203 | 0.554 | 0.397 |
| ceiling | `all` | 0.788 | 0.904 | 0.971 | – | – | – | – | – |
<!-- END generated: baseline_metrics -->

<!-- BEGIN generated: baseline_costs -->
| System | p50 latency (ms) | Queries (of 338) with fewer than 20 parents |
|---|---|---|
| `fts_and` | 0.5 | 337 |
| `fts_or` | 8.7 | 0 |
| `bm25` | 1.7 | 0 |
| `dense` | 2.5 | 0 |
<!-- END generated: baseline_costs -->

Latency here is one retrieval call on a laptop, with the query vector and the BM25 index built beforehand, so it changes a little on every run. At about a thousand chunks every system answers in milliseconds, so speed doesn't separate them yet. The "fewer than 20 parents" column is the fetch depth doing its job. FTS-AND falls short almost every time, because so few chunks contain every word of a sentence.

Is one system really better than another, or did it get lucky with these questions? The paired cluster bootstrap on recall@10:

<!-- BEGIN generated: baseline_comparisons -->
| recall@10 difference | Queries | Mean [95% CI] | CI excludes 0 |
|---|---|---|---|
| `fts_or` − `fts_and` | `subcat` | +0.389 [+0.309, +0.465] | yes |
| `fts_or` − `fts_and` | `example` | +0.275 [+0.231, +0.323] | yes |
| `fts_or` − `fts_and` | `all` | +0.300 [+0.255, +0.353] | yes |
| `bm25` − `fts_or` | `subcat` | +0.042 [-0.018, +0.108] | no |
| `bm25` − `fts_or` | `example` | +0.069 [+0.013, +0.126] | yes |
| `bm25` − `fts_or` | `all` | +0.063 [+0.013, +0.116] | yes |
| `dense` − `bm25` | `subcat` | +0.040 [-0.015, +0.096] | no |
| `dense` − `bm25` | `example` | +0.051 [+0.014, +0.087] | yes |
| `dense` − `bm25` | `all` | +0.049 [+0.017, +0.081] | yes |
<!-- END generated: baseline_comparisons -->

Over all queries, each step up the ladder is distinguishable from noise: OR beats AND, BM25 beats FTS-OR, dense beats BM25. On the 75 `subcat` queries alone, BM25 vs FTS-OR and dense vs BM25 are not. Their intervals include 0, so with this few questions we can't tell those apart.

Dense search through the HNSW index, against exact search:

<!-- BEGIN generated: hnsw_vs_exact -->
| Dense search, LIMIT 293 | Plan | Rows returned: median (min–max) | Queries with fewer than 20 parents | Share of exact top-10 chunks found | recall@10 minus exact [95% CI] | recall@20 minus exact [95% CI] | p50 latency (ms) |
|---|---|---|---|---|---|---|---|
| no settings (the planner's own choice) | Limit > Sort > Seq Scan | – | – | – | – | – | – |
| exact (index scans off) | Limit > Sort > Seq Scan | 293 (293–293) | 0 | 1.000 | +0.0000 [+0.0000, +0.0000] | +0.0000 [+0.0000, +0.0000] | 2.5 |
| hnsw, ef_search=40 (default) | Limit > Index Scan (chunks_embedding_hnsw_c) | 40 (40–40) | 34 | 0.995 | +0.0007 [-0.0007, +0.0027] | +0.0023 [-0.0005, +0.0057] | 1.4 |
| hnsw, ef_search=293 | Limit > Index Scan (chunks_embedding_hnsw_c) | 293 (293–293) | 0 | 1.000 | +0.0000 [+0.0000, +0.0000] | +0.0000 [+0.0000, +0.0000] | 2.5 |
| hnsw, ef_search=1000 | Limit > Index Scan (chunks_embedding_hnsw_c) | 293 (293–293) | 0 | 1.000 | +0.0000 [+0.0000, +0.0000] | +0.0000 [+0.0000, +0.0000] | 2.8 |
| hnsw, ef_search=40, iterative_scan=strict_order | Limit > Index Scan (chunks_embedding_hnsw_c) | 293 (293–293) | 0 | 0.995 | +0.0007 [-0.0007, +0.0027] | +0.0028 [+0.0002, +0.0062] | 2.5 |
| hnsw, ef_search=40, iterative_scan=relaxed_order | Limit > Index Scan (chunks_embedding_hnsw_c) | 293 (293–293) | 0 | 1.000 | +0.0000 [+0.0000, +0.0000] | +0.0000 [+0.0000, +0.0000] | 2.4 |
<!-- END generated: hnsw_vs_exact -->

- **The default `ef_search` of 40 returns exactly 40 rows for a LIMIT of 293.** That leaves 34 of the 338 queries with fewer than 20 controls. With `ef_search` at 293 or more, or with an iterative scan, every query gets all 293 rows.
- **HNSW at `ef_search` ≥ LIMIT matched exact search.** On this small table, the approximate index loses nothing measurable.
- **Without any settings, Postgres skips the index entirely** and does an exact sequential scan. That's why the dense baseline above is exact search, and why we force each path and record the plan.
- **A few differences come out slightly positive.** HNSW "beating" exact sounds impossible, but exact search gives the true nearest neighbors, not the most relevant controls. When the approximate search skips a close chunk from a wrong control, a gold control further down can slide into the top 20. One of the ten HNSW intervals in the last two columns excludes 0, by 0.0002. With ten intervals at 95% each, one edge case like that isn't surprising, and +0.0028 changes nothing in practice.

Where dense and BM25 disagree completely: one found every gold control in its top 10, the other found none.

<!-- BEGIN generated: dense_vs_bm25_examples -->
| Query | Text | Gold | Found all of it (the other found none) | Gold chunk BM25 scored highest | Query lexemes in that chunk |
|---|---|---|---|---|---|
| GV.RR-03 | Adequate resources are allocated commensurate with the cybersecurity risk strategy, roles, responsibilities, and policies | pm-3 | `dense` | `C:pm-3` | `resourc` ×5, `polici` ×1 |
| GV.RR-03/ex2 | Identify resource allocation and investment in line with risk tolerance and response | pm-3 | `bm25` | `C:pm-3` | `resourc` ×5, `invest` ×4 |
| GV.RR-03/ex3 | Provide adequate and sufficient people, process, and technical resources to support the cybersecurity strategy | pm-3 | `dense` | `C:pm-3` | `provid` ×1, `process` ×1, `resourc` ×5 |
| ID.RA-08/ex2 | Assign responsibilities and verify the execution of procedures for processing, analyzing the impact of, and responding to cybersecurity threat, vulnerability, or incident disclosures by suppliers, customers, partners, and government cybersecurity organizations | ra-5 | `bm25` | `C:ra-5` | `assign` ×3, `respons` ×1, `procedur` ×1, `process` ×5, `analyz` ×3, `impact` ×2, `vulner` ×44, `disclosur` ×3, `custom` ×1, `organ` ×14 |
| PR.AA-02/ex2 | Issue a different credential for each person (i.e., no credential sharing) | ia-12 | `bm25` | `C:ia-12.4` | `issu` ×1, `credenti` ×1, `person` ×3 |
| PR.AT-02/ex3 | Periodically assess or test users on their understanding of cybersecurity practices for their specialized roles | at-3 | `bm25` | `C:at-3.3` | `assess` ×1, `practic` ×4, `role` ×1 |
| PR.AT-02/ex4 | Require annual refreshers to reinforce existing practices and introduce new practices | at-3 | `bm25` | `C:at-3.3` | `reinforc` ×1, `practic` ×4 |
| RC.CO-03/ex4 | Coordinate crisis communication between the organization and its critical suppliers | ir-4, ir-6, sr-8 | `dense` | `C:ir-4.8` | `coordin` ×3, `organ` ×8 |
<!-- END generated: dense_vs_bm25_examples -->

BM25 wins 5 of these and dense wins 3, so each has questions only it can answer. That's the case for hybrid search in Phase 3.

The words `rank_bm25` gives more weight than it should:

<!-- BEGIN generated: bm25_idf_floor -->
| Lexeme (strategy C, 1,014 chunks) | Chunks containing it | IDF in `rank_bm25` |
|---|---|---|
| `organ` | 840 | 1.327 (floored) |
| `system` | 758 | 1.327 (floored) |
| `defin` | 693 | 1.327 (floored) |
| `assign` | 669 | 1.327 (floored) |
| `organization-defin` | 657 | 1.327 (floored) |
| `includ` | 573 | 1.327 (floored) |
| `inform` | 536 | 1.327 (floored) |
| `use` | 468 | 0.154 |
| `secur` | 417 | 0.358 |
| `provid` | 382 | 0.503 |
| `organiz` | 381 | 0.507 |
| `may` | 377 | 0.524 |
| `requir` | 362 | 0.588 |
| `control` | 337 | 0.697 |
| `implement` | 332 | 0.719 |
| `process` | 324 | 0.755 |
| `compon` | 309 | 0.824 |
| `b` | 289 | 0.919 |
| `access` | 285 | 0.938 |
| `individu` | 284 | 0.943 |
| `privaci` | 266 | 1.033 |
| `oper` | 250 | 1.116 |
| `protect` | 245 | 1.142 |
| `identifi` | 244 | 1.148 |
| `manag` | 244 | 1.148 |
| `polici` | 218 | 1.293 |
| `function` | 217 | 1.299 |
| `risk` | 214 | 1.317 |
| `1` | 213 | 1.323 |
| `employ` | 213 | 1.323 |
<!-- END generated: bm25_idf_floor -->

The "floored" lexemes are in more than half the chunks, where BM25's IDF formula goes negative. `rank_bm25` replaces a negative IDF with 0.25 × the average IDF (5.307), which is 1.327. That is more than 23 rarer lexemes get, so in a query, "organization" counts for more than "security" or "control". The baseline keeps the library's default; whether to change it is a Phase 3 question, decided on dev.

## Concepts

### The answer key, and why we can measure at all

Most RAG demos are judged by reading a few answers and nodding. We can do better because NIST publishes a mapping: for each CSF 2.0 subcategory, the SP 800-53 controls that implement it. Turn each subcategory into a question, and the mapped controls are the answer key. A retriever is good if it finds them.

Think of a school quiz with an answer sheet written by the teacher. The `subcat` queries are the teacher's own questions. The `example` queries are the same questions asked by students in their own words ("Provide adequate and sufficient people, process, and technical resources…"), and they share the same answer sheet. They give us 338 dev questions instead of 75, but they aren't 338 independent questions, which matters for the confidence intervals.

### The metrics, ELI10

A made-up example: the answer key is {AC-2, IA-2, AC-3}, and after rolling chunks up to parents, a system returns AC-6, AC-2, SI-4, IA-2, …

- **recall@k: "Did the right answers show up at all?"** Of the gold controls, the share in the top k. Top 3: only AC-2, so 1/3. Top 4: AC-2 and IA-2, so 2/3. This is what matters most when the results feed an LLM: a control that isn't retrieved can't be cited.
- **Ceiling: "What's the best score possible?"** A subcategory with 40 gold controls (our largest) can have at most 10 of them in a top 10, so its best recall@10 is 10/40 = 0.25. The ceiling is min(k, |gold|) / |gold|, averaged over queries. Reporting recall without it would make a perfect system look mediocre.
- **Normalized recall@k:** hits / min(k, |gold|), so 1.0 means "as good as possible for this k".
- **precision@k: "How much of the list is right?"** Hits / k. In the example, precision@4 is 2/4. It divides by k even when fewer than k results came back, so returning almost nothing can't look precise. For an LLM, low precision means context full of noise.
- **MRR, mean reciprocal rank: "How far down is the first right answer?"** 1 / its rank, here 1/2, or 0 if none is in the top 20. It suits a search box, where the user clicks the first good result. It's an average of 1/rank, which hides a lot: one query with a hit at rank 1 (1.0) and one with no hit (0) also average 0.5.
- **nDCG@10: "Are the right answers near the top?"** Each hit is worth 1 / log2(rank + 1): rank 1 is worth 1, rank 2 is worth 0.63, rank 4 is worth 0.43. Divide the sum by the best possible sum, all hits at the top. In the example: (0.631 + 0.431) / (1 + 0.631 + 0.5) = 0.498. Our relevance is binary (gold or not); with graded labels (perfect, partial, wrong), nDCG is the metric that can use them.

All of them are computed per query and then averaged over queries.

### Why Postgres FTS is not BM25

Both start from the same words. We even made them use identical lexemes: BM25 reads Postgres's own output through `ts_debug`, so the only difference is the scoring. BM25 scores a chunk d for a query q as

\[ \text{BM25}(q, d) = \sum_{t \in q} \text{IDF}(t) \cdot \frac{tf_{t,d}\,(k_1 + 1)}{tf_{t,d} + k_1 \left(1 - b + b \frac{|d|}{\text{avgdl}}\right)} \]

with three ideas built in:

1. **IDF: rare words count more.** \( \text{IDF}(t) = \ln \frac{N - df_t + 0.5}{df_t + 0.5} \), where \( df_t \) is how many of the N chunks contain t. "vulnerability" says a lot about a chunk; "organization" says almost nothing, because it's everywhere.
2. **Saturation: the tenth repeat adds less than the second.** k1 = 1.5 sets how fast the term-frequency part flattens out.
3. **Length normalization: a match in a long chunk counts less.** b = 0.75 sets how much.

Postgres's `ts_rank_cd` rewards chunks where query words appear often and close together ("cover density"). It uses no statistics about the rest of the corpus, so there's no IDF: every matched word counts the same. It has no BM25-style saturation curve. And it normalizes for length only when you pass a normalization flag; we use the default, 0, which doesn't.

Measured: BM25 beats FTS-OR by 0.063 recall@10 over all dev queries, with a paired CI of [+0.013, +0.116].

One catch: `rank_bm25`'s IDF floor. Seven lexemes are in more than half the chunks, where the formula goes negative, and the library replaces them with 1.327, more than 23 rarer lexemes get. The textbook formula isn't what every library computes, so read the code of the one you use.

### AND, OR, plainto and websearch

`plainto_tsquery('english', 'Policies, processes, and procedures for authorizing personnel')` gives `'polici' & 'process' & 'procedur' & 'author' & 'personnel'`. That's an AND: a chunk must contain all five. CSF sentences are long, and almost no chunk contains every word, so `fts_and` scores 0.008 recall@10 and returns fewer than 20 controls for 337 of 338 queries.

`websearch_to_tsquery` is also AND for plain words. On top of that, it reads `or`, `-` and quotes as search operators, which is right for a search box and wrong for prose, where "or" is just an English word. So we kept `plainto_tsquery` and built OR ourselves from its lexemes: `fts_or` matches any of them and lets the ranking sort it out. That alone lifts recall@10 from 0.008 to 0.309.

The general lesson: AND suits short keyword queries that people type. For sentence-length queries, you want OR plus a good ranking function, and BM25 is a better ranking function than `ts_rank_cd`.

### Why dense wins on paraphrase and loses on exact words

An embedding is a list of 384 numbers that describes what a text is about. Texts about similar things get similar lists even when they share no words. Cosine similarity measures how closely two lists point the same way; ours are normalized, so it's just a dot product.

The disagreement table shows both sides:

- **Dense wins on paraphrase.** "Coordinate crisis communication between the organization and its critical suppliers" has to reach IR-4 (Incident Handling), IR-6 (Incident Reporting) and SR-8 (Notification Agreements). The controls say "incident", not "crisis", and Postgres stems "supplier" and "supply" differently. In the gold chunk it scored highest, BM25 matched only `coordin` and `organ`. Dense got all three in its top 10, because "crisis" and "incident", and "suppliers" and "supply chain", mean nearly the same thing.
- **BM25 wins on exact, rare words.** "…responding to cybersecurity threat, vulnerability, or incident disclosures…" → RA-5 (Vulnerability Monitoring and Scanning), whose chunk contains `vulner` 44 times. "Issue a different credential for each person" → IA-12, whose enhancement IA-12(4) contains "credential", "issued" and "in-person".
- **Some keyword wins are luck.** "Require annual refreshers to reinforce existing practices…" → AT-3 (Role-Based Training). AT-3 never says "annual" or "refresher". BM25 found it because AT-3(3) is "Practical Exercises" (and "practical" and "practices" share the stem `practic`), plus the rare word "reinforce".

In general, dense search also struggles with acronyms and identifiers ("FIPS 140-3", "PIV") that it rarely saw in training and that its tokenizer chops into pieces, while keyword search matches them exactly. CSF sentences have few of those, so this set doesn't measure it.

Measured: dense beats BM25 by 0.049 recall@10 over all dev queries, CI [+0.017, +0.081]. On the 75 `subcat` queries alone the CI is [−0.015, +0.096], so there we can't tell them apart.

### The gold-set limitation: precision is a lower bound

NIST's mapping lists controls that implement a subcategory. It doesn't promise to list every relevant one. Look at GV.RR-03, "Adequate resources are allocated commensurate with the cybersecurity risk strategy…". Its only gold control is PM-3 (Information Security and Privacy Resources). For GV.RR-03 and GV.RR-03/ex2 in the disagreement table, both systems rank SA-2 first or second (`dense_top5` and `bm25_top5` in `results/baselines_dev.json`), and SA-2 is titled "Allocation of Resources". The metric calls that a mistake.

So every "false positive" might be a real answer NIST didn't list, and measured precision is a lower bound on true precision. Recall is measured against NIST's list too: it means "how much of NIST's mapping did we find", not "how much of everything relevant". The comparisons stay fair, because every system faces the same key. But a system that finds relevant controls NIST didn't map gets no credit for them.

### Confidence intervals with 75 subcategories

A score from 75 subcategories is partly luck: with a different 75, it would come out a bit different. A 95% confidence interval says how big that wobble is.

The bootstrap measures it without any formulas. Picture 75 bags, one per dev subcategory, each holding that subcategory's questions: the `subcat` query plus 1 to 10 examples. Draw 75 bags at random, with replacement, so some bags come up twice and some not at all. Average all the questions in them, and repeat 1,000 times. The middle 95% of those 1,000 averages is the interval.

We draw bags, not single questions, because questions in the same bag share one answer key, so they succeed or fail together. Drawing single questions would pretend we have 338 independent data points, and the interval would come out too narrow. A test checks this: with correlated questions, the cluster interval is more than twice as wide.

**Paired** means comparing two systems question by question. A hard question is hard for both systems, and taking the difference cancels that out. This matters more than it sounds. Dense's interval, [0.363, 0.479], overlaps BM25's, [0.317, 0.433], yet the paired difference, [+0.017, +0.081], excludes 0. Overlapping intervals don't mean "no difference"; the paired test is the one to read.

With roughly a hundred subcategories, the intervals are wide: about ±0.06 on recall@10 over all dev queries, and wider on the 75 `subcat` queries alone. Differences of a point or two between systems can't be told apart from noise. That's why every comparison in this project gets a CI, and why "it went up by 0.01" is never a result on its own.

### Leakage, and why we split by subcategory

Imagine a practice test with "What's 7×8?" and a final exam with "What's 8×7?". A student who memorized the practice answers aces the final without learning multiplication.

Our example queries are like that. GV.RR-03/ex2 and GV.RR-03/ex3 share the same answer key and similar words. If we split by query, one could land in dev and the other in test. Every time we tuned something on dev in later phases, we'd be tuning on the test's answers, and the final test score would be inflated. Splitting by subcategory keeps every answer key entirely on one side. Stratifying by CSF function keeps every function in both splits, so test isn't, say, missing all the Recover questions.

### Why queries get a prefix and chunks don't

Search is lopsided: queries are short questions, and chunks are long statements. bge-small was trained for that: a query starts with "Represent this sentence for searching relevant passages: ", and a passage is embedded as it is. Roughly, the prefix tells the model "this is a question looking for its answer", which moves the query's vector toward the passages that answer it, rather than toward passages that merely sound like it. Prefixing the chunks too would make them look like questions. The model card recommends the prefix for short queries that retrieve longer passages, and says v1.5 also works without it. We haven't measured the difference on our data.

### Exact search vs HNSW

Exact search compares the query with all 1,014 C vectors and sorts them. That's always right, but it costs one comparison per chunk.

HNSW is a map of friends-of-friends. Start from an entry point, keep hopping to whichever neighbor is closest to the query, and stop when no neighbor is closer. `ef_search` is how many candidates you keep in your notebook while hopping. Without an iterative scan, that's also the most rows the index can return, which is why the default of 40 returned 40 rows for a LIMIT of 293. pgvector 0.8's iterative scan keeps hopping until the LIMIT is filled. `strict_order` returns rows in exact distance order; `relaxed_order` may return them slightly out of order, so we re-sort.

At a thousand vectors, HNSW buys nothing: exact search takes milliseconds, and Postgres picks it on its own. HNSW pays off at hundreds of thousands of vectors and up, and that's when its settings need tuning against exact search, the way we did here.

## Decisions

Each of these has a row in `DECISIONS.md`.

- **The spreadsheet is pinned by sha256 and committed.** Its URL isn't versioned, so a changed download fails loudly instead of quietly changing the answer key.
- **Enhancement references count as their base control,** because metrics work on parent controls.
- **References on function and category rows are ignored and logged.** Copying them to every subcategory below would invent mappings NIST never made.
- **The split is by subcategory, stratified by CSF function and ordered by a hash.** No leakage, every function in both splits, and the order doesn't depend on Python's random module.
- **`queries.jsonl` is committed, and the test split is sealed in code.**
- **The metric definitions were fixed in code and tests before the first baseline run,** with recall@10 as the primary metric.
- **The fetch depth guarantees 20 distinct parents:** 293 chunks for strategy C.
- **BM25 uses Postgres's lexemes through `ts_debug`, and `rank_bm25`'s defaults.** FTS and BM25 then differ only in scoring. The IDF floor is reported, not fixed yet.
- **FTS-OR reuses `plainto_tsquery`'s lexemes, and both FTS queries rank with `ts_rank_cd` at normalization 0.**
- **The dense baseline is exact search, and HNSW is measured against it.**
- **Dense queries are never prepared** (next section).
- **Queries get the BGE prefix and chunks don't.**

## Gotchas we hit

1. **HNSW silently ran as exact search.** The first baseline run reported 293 rows for HNSW at the default `ef_search` of 40, which can only return 40. After 5 runs of the same SQL, psycopg prepares the statement on the server, and Postgres can then reuse one cached plan. The exact-search runs came first, so their plan (sequential scan) got cached. Every later "HNSW" run reused it, because changing a planner setting with `SET LOCAL` doesn't replan a cached statement. It's like a waiter who learns your usual order after five visits and stops listening when you order something else. The plan we recorded with `EXPLAIN` looked right, because `EXPLAIN` plans its query fresh every time it runs. Fix: dense queries run with `prepare=False`, so each one is planned under its own settings. `tests/test_retrieval.py` repeats the exact sequence, 12 exact runs and then HNSW, and fails without the fix.
2. **The fetch depth came back as a `Decimal`.** Postgres's `sum()` of counts is `numeric`, and Python can't slice a list with it. Fixed with a cast to `int` in SQL.
3. **`tsvector` caps positions.** It keeps at most 255 positions per lexeme (300 repeats of "account" kept 255), and long B chunks hit that, so BM25 can't take its counts from the `tsv` column. It re-tokenizes with `ts_debug`.
4. **Stems collide and split.** "practices" and "practical" both become `practic`. "organization" becomes `organ` but "organizational" becomes `organiz`, and "supplier" and "supply" stem differently. "organization-defined" becomes three lexemes: the whole word plus both halves. Keyword search inherits every one of these quirks.
5. **`rank_bm25`'s IDF floor** gives the seven most common lexemes more weight than 23 rarer ones.
6. **A Phase 1 claim was wrong.** The Phase 1 learn doc said every over-limit base control loses all of its enhancements in B. Measuring the vectors showed it's 16 of 165, and the doc is corrected.

## Interview questions

**1. How did you build your evaluation set?**
NIST maps each CSF 2.0 subcategory to the SP 800-53 controls that implement it, so every subcategory is a question with an official answer key. I took the Rev 5.2.0 references to match my catalog, counted enhancements as their base control, dropped 3 family-level references, and remapped 1 reference to a withdrawn control. All 106 active subcategories have at least one control: the median is 5, the largest has 40. 106 questions is small, so I added NIST's implementation examples as extra queries with the same answer key, for 469 queries in total. Dev has 75 subcategories and 338 queries; test has 31 and 131, and it's sealed in code until the final run.

**2. What's your primary metric, and what does your best score mean?**
recall@10 on parent controls: of a query's gold controls, the share in the top 10. That's what matters when the results feed an LLM, because a control that isn't retrieved can't be cited. Exact dense search scores 0.420 over all dev queries. Some subcategories have more than 10 gold controls, so the best possible is 0.904, not 1. I report that ceiling next to every recall, plus normalized recall, which divides hits by min(k, |gold|).

**3. Postgres FTS and BM25 see the same words. Why do they score differently?**
I made the tokens identical on purpose: BM25 uses Postgres's own lexemes, so only the scoring differs. BM25 weighs rare words higher (IDF), stops rewarding repeats after a few (k1) and discounts long chunks (b). `ts_rank_cd` uses no corpus statistics, has no saturation, and at the default normalization ignores length. BM25 beat FTS-OR by 0.063 recall@10, CI [+0.013, +0.116]. Plain FTS with AND is nearly useless for sentence queries: 0.008, because no chunk contains every word.

**4. Dense beat BM25 by 0.049. How do you know that's real?**
A paired cluster bootstrap. Both systems answer the same queries, so I take per-query differences, then resample subcategories rather than queries, because examples share their subcategory's answer key and aren't independent. 1,000 resamples give a 95% CI of [+0.017, +0.081], which excludes zero. The two systems' own intervals overlap, which is exactly why you test the paired difference. On the 75 subcategory-text queries alone, the CI includes zero, so I don't claim a win there.

**5. Why split by subcategory and not by query?**
Leakage. A subcategory's examples share its answer key and much of its wording. Split by query, and tuning on dev would partly tune on test's answers, inflating the test score. I split by subcategory, stratified by CSF function, using a seeded hash order, and the test split raises an error if anything but the final run loads it.

**6. How did you check your vector index?**
Against exact search, with the plan recorded for every setting. At the default `ef_search` of 40, HNSW returned only 40 rows for a LIMIT of 293, leaving 34 of 338 queries with fewer than 20 controls. With `ef_search` at the LIMIT or higher, it matched exact search. The interesting part is a bug I caught: the first run showed every HNSW setup returning 293 rows, which is impossible at `ef_search` 40. psycopg prepares a statement after 5 runs, and Postgres reused the cached exact-search plan, ignoring the new settings, while `EXPLAIN` still showed the index. I fixed it by not preparing dense queries, and added a test that reproduces it.

**7. What are the limits of your answer key?**
NIST's mappings aren't exhaustive. For GV.RR-03, about allocating adequate resources, both systems rank SA-2, "Allocation of Resources", first or second on two of its queries, but the only gold control is PM-3, so SA-2 counts as a miss. Measured precision is a lower bound on true precision. Recall means "how much of NIST's mapping we found". Comparisons stay fair, because every system faces the same key, but a system that finds unmapped relevant controls gets no credit.

**8. When does keyword search beat embeddings?**
On exact, rare terms. "Vulnerability disclosures" goes straight to RA-5, whose chunk mentions vulnerabilities 44 times, and "credential for each person" finds IA-12(4) on "credential", "issued" and "in-person". Dense wins on paraphrase: "crisis communication with critical suppliers" reaches the incident-handling and incident-reporting controls without sharing those words. Among dev queries where one system found every gold control in its top 10 and the other found none, BM25 won 5 and dense won 3. Each has questions only it answers, which is the argument for hybrid search.

## Follow-ups from the quiz

**Why not shuffle all 469 queries and split them at random?**
Because the queries of one subcategory are near-copies. GV.RR-03 gives four: its own text and three implementation examples, all about resources and all with the same gold control, PM-3. A random split would put some of them in dev and some in test. Anything tuned on dev would then have practiced the test's questions in other words, like a practice test with "7×8" and an exam with "8×7", so the test score would come out too high. Splitting by subcategory keeps all four on one side; here they're all in dev.

**Dense beat BM25 by 0.049. How do we know it isn't luck?**
75 dev subcategories is a small sample, so we measure how much the score wobbles. The bootstrap redraws 75 subcategories at random from our 75, some twice and some not at all, recomputes the score, and repeats that 1,000 times. Two details keep it honest. It's paired: both systems answer the same queries, so we resample per-query differences, and a question that's hard for both cancels out. And it draws whole subcategories, because GV.RR-03's four queries share one answer key and succeed or fail together; counting them as four independent data points would make the interval too narrow. In 95% of the redraws, dense minus BM25 fell between +0.017 and +0.081, so zero is outside the interval. On the 75 `subcat` queries alone it ran from −0.015 to +0.096, so there we can't call a winner.

**Dense won overall. Why not drop keyword search?**
Because each finds controls the other misses. Dense matches meaning: "Coordinate crisis communication between the organization and its critical suppliers" reaches IR-4, IR-6 and SR-8, though those controls say "incident", not "crisis". BM25 matches rare exact words: "…vulnerability, or incident disclosures…" goes straight to RA-5, and dense misses it. Of the dev queries where one system found every gold control in its top 10 and the other found none, BM25 won 5 and dense won 3. So Phase 3 combines them: run both and merge the rankings.
