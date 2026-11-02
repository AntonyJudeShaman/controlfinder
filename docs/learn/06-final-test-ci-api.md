# Phase 6: The sealed test run, a CI gate, an API and an app

## The short version

- **The sealed test set agreed with dev on every decision.** Production retrieval (dense, row 2) scored recall@10 0.421 on the 131 test queries, against 0.420 on the 338 dev queries. The reranker hurt again, by −0.111 [−0.175, −0.055] recall@10 (dev: −0.091). Hybrid's edge over dense stayed inside the noise, at +0.015 [−0.021, +0.051].
- **Base text still ships, with a smaller lead.** On the 50 test questions, it turned 2 of the plain pipeline's wrong refusals into correct answers and changed nothing else. That's +0.043 [+0.000, +0.116] abstention F1, against +0.119 on dev. The pipeline had only 4 wrong refusals on test (8 on dev), so there was less to fix.
- **Neither system answered any of the 20 unanswerable test questions,** and every answer they gave was correct (answer accuracy 1.000 for both).
- **35 of 346 dev-versus-test checks crossed the line we fixed beforehand.** Some flags are expected by chance, and none reverses a decision. Each is explained below.
- **The run broke six times** on a provider network error and was resumed from the caches each time. No number was seen before it finished.
- **CI now guards retrieval quality.** A gate on 30 dev queries failed when [PR #1](https://github.com/AntonyJudeShaman/controlfinder/pull/1) broke hybrid search, while every unit test still passed.
- **An API and an app** serve the production system, log every request with per-stage timing, and show numbers only from `results/`.

Every number below comes from `results/final_test.json`, the dev results, `results/ci_baseline.json` or `results/query_log_report.json`, and `make docs` regenerates the tables.

## What we built

| File | What it is |
|---|---|
| `src/controlfinder/eval/final_test.py` | `make final-test`: the one run on the sealed test split. It refuses to start if `results/final_test.json` exists, and prints no metric until the end |
| `results/final_test.json` | Every test metric with its 95% interval, the comparisons, the costs, and each test question's row |
| `src/controlfinder/eval/ci.py`, `data/ci/fixture.json.gz`, `results/ci_baseline.json` | The CI regression gate: a fixture with precomputed embeddings, and the recall@10 that CI must not drop below |
| `.github/workflows/eval.yml` | CI: Postgres + pgvector, the real ingest, the unit tests, then the gate |
| `src/controlfinder/api/app.py`, `src/controlfinder/api/backend.py` | The FastAPI routes, and the code behind them: search, ask, the catalog, the configs, the results and the logs |
| `src/controlfinder/obs/__init__.py`, `src/controlfinder/obs/report.py` | One `query_log` row per request, and `make report` |
| `tests/test_api.py` | 16 tests that call every route with fake models, so they make no model call or download |
| `web/` | The Next.js app: controls, configs with live knobs, results, ask and trace |
| `README.md` | The project's front page, with its results tables generated from `results/` |
| `src/controlfinder/docgen.py` | Gains the test-run tables, the τ charts, the CI gate and the query-log report |

## How it works

### Opening the sealed test set exactly once

Think of the test split as the exam paper in a sealed envelope. We studied with practice papers (dev) for five phases, and every choice was made on dev. The envelope is opened once, at the end, to check that what we learned holds up on questions we never looked at.

Three things kept it sealed:

1. **The loaders refuse.** `load_queries("test")` and `load_questions("test")` raise `PermissionError` unless `CONTROLFINDER_UNSEAL_TEST=1` is set, and only `make final-test` sets it.
2. **The plan was committed first.** Commit `82d9f36` ("preregister the final test run") fixed which systems run, which metrics count, and what "differs noticeably" means, before the code that opens the envelope existed.
3. **It runs once.** `final_test.py` refuses to start if `results/final_test.json` exists. A second run would need a `DECISIONS.md` row and the old file moved away by hand.

What ran:

- **Retrieval:** Phase 2's four baselines and Phase 3's six rows, on the test half of the answer key, with the same metrics and the same bootstrap as dev (by subcategory, 1,000 resamples, seed 20261023). Rows 1 and 2 are the same setups as the BM25 and dense baselines, so the run checks that they give the same recall@10 and stops with an error if they don't. That catches a wiring bug before any number is trusted.
- **Answering:** the plain pipeline and the pipeline with base text, on the 50 test questions (30 answerable, 20 unanswerable), graded by code. The agent and the faithfulness judge stayed on dev, to save model calls. On dev, the agent gave the pipeline's answers word for word, and the judge gave every answer a 5.

### Six crashes, and why resuming is fair

The Cursor API failed six times mid-run with `InternalServerError: Network request failed`, during test questions 3, 14, 24, 28, 39 and 41. The seventh start finished.

The LLM cache is a notebook of finished calls: each prompt with its reply. A restart reads the notebook first, so every question that had finished replays its saved reply, and only the unfinished ones go to the model. Since a call is written down only once it succeeds, every call was made once, exactly as in an unbroken run. Retrieval has no randomness, so running it again on each start gave the same numbers. The progress lines (`question 28/50`) were the only output, so no test number was seen before the end. The caches grew by one entry per new call: 100 LLM entries (50 questions × 2 systems) and 393 reranker entries (131 queries × 3 reranked rows).

### What "differs noticeably" means

We fixed the rule before the run: a test result differs noticeably from dev when the dev number falls outside the test 95% interval. Fixing it first means the discussion can't pick which gaps count after seeing them.

The rule raises some false alarms. Suppose dev and test came from the same pool, so the true recall is identical. Dev's number still wobbles, and so does test's. The test interval only allows for test's wobble, so dev's number lands outside it more than 5% of the time. And with 346 checks, many of them measuring nearly the same thing (recall@5, normalized recall@5 and nDCG@10 move together), flags come in clusters. So a flag is a reason to look, not proof of a difference.

### The CI gate

Unit tests check that functions do what they say. They can't notice that search got worse: if a refactor quietly drops half of hybrid retrieval, every function still runs, and every test still passes. The gate measures quality on every push:

1. CI starts Postgres + pgvector and runs the real ingest of the pinned catalog.
2. It loads `data/ci/fixture.json.gz`, the embeddings of every C_separate chunk and of 30 dev queries, so CI never downloads a model. Each chunk's text hash is stored too, so the fixture refuses to load if chunking changed.
3. `make ci-gate` runs hybrid retrieval (BM25 + dense, fused with RRF, no reranker) on the 30 queries and fails if mean recall@10 is more than 0.03 below the baseline.

<!-- BEGIN generated: ci_gate -->
| CI gate | Value |
|---|---|
| what | The CI gate's baseline: hybrid retrieval (BM25 + dense, RRF, no reranker) on the fixture's dev queries |
| strategy | C_separate |
| retrieval | hybrid |
| queries | 30 |
| tolerance | 0.03 |
| recall@10 | 0.4953 |
<!-- END generated: ci_gate -->

To prove it works, [PR #1](https://github.com/AntonyJudeShaman/controlfinder/pull/1) dropped the dense half of hybrid search, a plausible refactor bug. Every unit test passed, and the gate failed: [run 41408595856](https://github.com/AntonyJudeShaman/controlfinder/actions/runs/41408595856). Main is green: [run 41408167015](https://github.com/AntonyJudeShaman/controlfinder/actions/runs/41408167015). Hybrid is gated, rather than production's dense search, because one number then covers both indexes and the fusion code. 0.03 is AGENTS.md's "3 points".

### The API

`make api` starts FastAPI on port 8000.

| Route | What it does |
|---|---|
| `GET /search?q=...` | Runs a Phase 3 setup (by default production: dense, C_separate, top 10, no reranker) and returns the controls, their scores and each stage's time |
| `POST /ask` | Answers with a system (by default the production pick, read from `results/agent_dev.json`) and returns the answer, its citations, each step and each stage's time |
| `GET /controls`, `/families`, `/controls/{id}` | The catalog, for the app's controls page |
| `GET /configs` | Every setup tested, the production setup, and the knob options for live search |
| `GET /results`, `/results/{name}` | The `results/*.json` files, for the app's results page |
| `GET /logs`, `/logs/{id}` | The query log, for the trace page |
| `GET /health` | Whether the API is up |

A concrete request: q001, "When an employee leaves the company, what should happen to their accounts and access?", with gold controls AC-2 and PS-4. `POST /ask` runs `retrieve`, `generate` and `verify_citations`, and answers citing PS-4, AC-2 and AC-2(3), all of them in the context. With `"system": "agent"`, it runs `scope_check`, `retrieve`, `grade_evidence`, `generate` and `verify_citations`, and cites PS-4, AC-2(3) and PS-6(3). Both are their dev answers in `results/agent_dev.json`, replayed from the cache.

The production system is read from `results/agent_dev.json` instead of being typed into the code, so the API can't drift from the evaluation. `tests/test_api.py` calls every route with fake models. A last check ran the real path end to end, through real retrieval and the real cache, with a model function that raises on any cache miss, so it couldn't make a call.

### The query log

Every request writes one `query_log` row: the time, the query, the pipeline, the retrieved controls, their scores, each stage's time, the decision and the trace. Stage times follow pre-registered definition 8, so a cached model call reports the time of its original call, and the API's numbers line up with the evaluation's. `wall` is the request's own time. `make report` turns the log into p50 and p95 per stage, plus the abstention rate:

<!-- BEGIN generated: query_log_report -->
| Pipeline | Requests | Abstention rate | Stage: p50 / p95 (ms) |
|---|---|---|---|
| `agent/eval-dev` | 50 | 0.560 (28 of 50) | total 16,747 / 21,423<br>generate 9,596 / 13,689<br>retrieve 11 / 12<br>scope_check 6,575 / 9,124<br>grade_evidence 478 / 536<br>verify_citations 0 / 0<br>abstain 0 / 0 |
| `ask/agent` | 1 | 0.000 (0 of 1) | wall 43 / 43<br>total 20,278 / 20,278<br>generate 13,191 / 13,191<br>retrieve 12 / 12<br>scope_check 6,774 / 6,774<br>grade_evidence 301 / 301<br>verify_citations 0 / 0 |
| `ask/pipeline_base_text` | 2 | 0.000 (0 of 2) | wall 24 / 25<br>total 13,175 / 14,583<br>generate 13,162 / 14,569<br>retrieve 14 / 14<br>verify_citations 0 / 0 |
| `search/dense/C_separate` | 3 | – | wall 16 / 44<br>embed 11 / 33<br>total 16 / 44<br>retrieve 6 / 11 |
<!-- END generated: query_log_report -->

Look at `ask/agent`: `total` is about 20 seconds, the original calls' time, but `wall` is a few dozen milliseconds, because every call came from the cache. Without `wall`, the log couldn't tell a replayed request from a live one.

### The app

`make web` builds and serves the Next.js app on port 3000. It has five pages:

- **Controls:** browse and search the catalog.
- **Configs:** every setup tested, plus live knobs (retriever, chunking, k, reranker) that run `/search`.
- **Results:** every metric with its interval, dev beside test, and the τ sweep.
- **Ask:** ask a question with either system and see the citations and the steps.
- **Trace:** any logged request, step by step.

The rule: the app has no typed numbers. Every number arrives from the API, which reads `results/` and the database, and is checked against a schema (zod) before it's shown. Before the test run, the results page's test columns said "sealed", because `/results/final_test` returned 404. Once the file existed, they filled in with no code change. Building the app made no model calls: search is local, and the ask page's sample questions are dev questions, which replay from the cache.

## Results on test

### Retrieval

<!-- BEGIN generated: final_retrieval -->
| Setup | Retrieval | Chunking | Rerank | recall@10 dev (338 queries) [95% CI] | recall@10 test (131 queries) [95% CI] | Production |
|---|---|---|---|---|---|---|
| Phase 2 `fts_and` | `fts_and` | C_separate | no | 0.008 [0.001, 0.018] | 0.002 [0.000, 0.005] |  |
| Phase 2 `fts_or` | `fts_or` | C_separate | no | 0.309 [0.261, 0.360] | 0.343 [0.251, 0.448] |  |
| Phase 2 `bm25` | `bm25` | C_separate | no | 0.372 [0.317, 0.433] | 0.361 [0.292, 0.447] |  |
| Phase 2 `dense` | `dense` | C_separate | no | 0.420 [0.363, 0.479] | 0.421 [0.340, 0.513] |  |
| Phase 3 row 1 | `bm25` | C_separate | no | 0.372 [0.317, 0.433] | 0.361 [0.292, 0.447] |  |
| Phase 3 row 2 | `dense` | C_separate | no | 0.420 [0.363, 0.479] | 0.421 [0.340, 0.513] | **yes** |
| Phase 3 row 3 | `hybrid` | C_separate | no | 0.436 [0.378, 0.497] | 0.436 [0.359, 0.525] |  |
| Phase 3 row 4 | `hybrid` | C_separate | yes | 0.345 [0.299, 0.398] | 0.325 [0.275, 0.387] |  |
| Phase 3 row 5 | `hybrid` | A_control_only | yes | 0.362 [0.311, 0.420] | 0.337 [0.286, 0.400] |  |
| Phase 3 row 6 | `hybrid` | B_control_plus_enh | yes | 0.378 [0.322, 0.437] | 0.343 [0.284, 0.416] |  |
<!-- END generated: final_retrieval -->

By query type, on test:

<!-- BEGIN generated: final_rows_by_type -->
| # | Retrieval | Chunking | Rerank | test recall@10, `subcat` (31 queries) | test recall@10, `example` (100 queries) | test recall@10, `all` (131 queries) |
|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 0.461 [0.360, 0.583] | 0.330 [0.262, 0.415] | 0.361 [0.292, 0.447] |
| 2 | `dense` | C_separate | no | 0.535 [0.412, 0.656] | 0.386 [0.306, 0.478] | 0.421 [0.340, 0.513] |
| 3 | `hybrid` | C_separate | no | 0.567 [0.456, 0.682] | 0.396 [0.319, 0.477] | 0.436 [0.359, 0.525] |
| 4 | `hybrid` | C_separate | yes | 0.332 [0.253, 0.429] | 0.323 [0.260, 0.389] | 0.325 [0.275, 0.387] |
| 5 | `hybrid` | A_control_only | yes | 0.372 [0.289, 0.474] | 0.325 [0.274, 0.385] | 0.337 [0.286, 0.400] |
| 6 | `hybrid` | B_control_plus_enh | yes | 0.381 [0.291, 0.482] | 0.331 [0.268, 0.402] | 0.343 [0.284, 0.416] |
<!-- END generated: final_rows_by_type -->

Every metric, on test:

<!-- BEGIN generated: final_rows_metrics -->
| # | Retrieval | Chunking | Rerank | test recall@5 | test recall@10 | test recall@20 | test norm_recall@10 | test precision@5 | test mrr | test ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 0.236 | 0.361 | 0.497 | 0.372 | 0.231 | 0.432 | 0.310 |
| 2 | `dense` | C_separate | no | 0.273 | 0.421 | 0.572 | 0.434 | 0.249 | 0.536 | 0.374 |
| 3 | `hybrid` | C_separate | no | 0.285 | 0.436 | 0.575 | 0.451 | 0.267 | 0.577 | 0.400 |
| 4 | `hybrid` | C_separate | yes | 0.202 | 0.325 | 0.522 | 0.343 | 0.215 | 0.424 | 0.287 |
| 5 | `hybrid` | A_control_only | yes | 0.217 | 0.337 | 0.531 | 0.355 | 0.226 | 0.465 | 0.305 |
| 6 | `hybrid` | B_control_plus_enh | yes | 0.194 | 0.343 | 0.533 | 0.360 | 0.208 | 0.440 | 0.294 |
<!-- END generated: final_rows_metrics -->

The comparisons behind each decision, test beside dev:

<!-- BEGIN generated: final_comparisons -->
| Difference, all queries | Metric | Dev [95% CI] | Test [95% CI] | Dev CI excludes 0 | Test CI excludes 0 |
|---|---|---|---|---|---|
| `fts_or` − `fts_and` | recall@10 | +0.300 [+0.255, +0.353] | +0.341 [+0.249, +0.446] | yes | yes |
| `bm25` − `fts_or` | recall@10 | +0.063 [+0.013, +0.116] | +0.018 [-0.064, +0.103] | yes | no |
| `dense` − `bm25` | recall@10 | +0.049 [+0.017, +0.081] | +0.060 [+0.006, +0.119] | yes | yes |
| hybrid vs best single retriever (row 3 − row 2) | recall@10 | +0.016 [-0.003, +0.036] | +0.015 [-0.021, +0.051] | no | no |
| reranker vs no reranker (row 4 − row 3) | recall@10 | -0.091 [-0.124, -0.061] | -0.111 [-0.175, -0.055] | yes | yes |
| reranker vs no reranker (row 4 − row 3) | ndcg@10 | -0.084 [-0.118, -0.057] | -0.113 [-0.166, -0.062] | yes | yes |
| reranker vs no reranker (row 4 − row 3) | mrr | -0.082 [-0.135, -0.038] | -0.153 [-0.234, -0.071] | yes | yes |
| reranker vs no reranker (row 4 − row 3) | precision@5 | -0.064 [-0.087, -0.043] | -0.052 [-0.084, -0.018] | yes | yes |
| best chunking vs runner-up (row 6 − row 5) | recall@10 | +0.015 [-0.004, +0.035] | +0.006 [-0.030, +0.046] | no | no |
| production (row 2) − row 1 | recall@10 | not computed on dev | +0.060 [+0.006, +0.119] | – | yes |
| production (row 2) − row 3 | recall@10 | -0.016 [-0.036, +0.003] | -0.015 [-0.051, +0.021] | no | no |
| production (row 2) − row 4 | recall@10 | not computed on dev | +0.096 [+0.035, +0.172] | – | yes |
| production (row 2) − row 5 | recall@10 | not computed on dev | +0.085 [+0.026, +0.148] | – | yes |
| production (row 2) − row 6 | recall@10 | not computed on dev | +0.078 [+0.029, +0.138] | – | yes |
<!-- END generated: final_comparisons -->

Every decision kept its direction. Dense beat BM25 on both splits. Hybrid minus dense includes zero on both, so dense stays. Every reranker comparison is below zero on both splits. The one weaker result: BM25 beat OR search on dev, +0.063 [+0.013, +0.116], but on test the interval includes zero, +0.018 [−0.064, +0.103]. So "BM25 beats OR search" rests on dev alone, because test's 31 subcategories are too few to confirm it.

### Answering

<!-- BEGIN generated: final_generation_metrics -->
| Metric [95% CI] | Pipeline, dev | Pipeline, test | Pipeline + base text, dev | Pipeline + base text, test |
|---|---|---|---|---|
| TP / FP / FN / TN | 20 / 8 / 0 / 22 | 20 / 4 / 0 / 26 | 20 / 2 / 0 / 28 | 20 / 2 / 0 / 28 |
| `abstention_precision` | 0.714 [0.542, 0.864] | 0.833 [0.667, 0.958] | 0.909 [0.762, 1.000] | 0.909 [0.762, 1.000] |
| `abstention_recall` | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| `abstention_f1` | 0.833 [0.703, 0.927] | 0.909 [0.800, 0.979] | 0.952 [0.865, 1.000] | 0.952 [0.865, 1.000] |
| `answer_rate` | 0.440 [0.300, 0.580] | 0.520 [0.380, 0.660] | 0.560 [0.420, 0.700] | 0.560 [0.420, 0.700] |
| `citation_precision` | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| `gold_citation_recall` | 0.864 [0.722, 0.974] | 0.962 [0.900, 1.000] | 0.893 [0.776, 0.982] | 0.946 [0.875, 1.000] |
| `answer_accuracy` | 0.909 [0.773, 1.000] | 1.000 [1.000, 1.000] | 0.929 [0.821, 1.000] | 1.000 [1.000, 1.000] |
| `gold_in_context` | 0.900 [0.788, 1.000] | 0.967 [0.893, 1.000] | 0.900 [0.788, 1.000] | 0.967 [0.893, 1.000] |
<!-- END generated: final_generation_metrics -->

<!-- BEGIN generated: final_versus -->
| Metric | Base text − pipeline, dev [95% CI] | Base text − pipeline, test [95% CI] | Agent − pipeline, dev [95% CI] | Agent − pipeline, test |
|---|---|---|---|---|
| `abstention_f1` | +0.119 [+0.040, +0.219] | +0.043 [+0.000, +0.116] | +0.000 [+0.000, +0.000] | not run |
| `answer_rate` | +0.120 [+0.040, +0.220] | +0.040 [+0.000, +0.100] | +0.000 [+0.000, +0.000] | not run |
| `answer_accuracy` | +0.019 [+0.000, +0.061] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | not run |
<!-- END generated: final_versus -->

<!-- BEGIN generated: final_decision_moves -->
| Test questions | Change from the pipeline | Pipeline + base text |
|---|---|---|
| answerable | refused → answered | 2 |
| answerable | answered → refused | 0 |
| unanswerable | refused → answered | 0 |
| unanswerable | answered → refused | 0 |
<!-- END generated: final_decision_moves -->

Base text was never worse on any test question. It answered 2 questions the pipeline refused, both correctly, and left every other decision alone. Abstention recall was 1.000 for both systems: no made-up answer to an unanswerable question on either split.

### Where test differs from dev

<!-- BEGIN generated: final_shifts -->
35 of 346 checks have the dev point estimate outside its test 95% interval:

| What | Metric | Queries | Dev | Test [95% CI] | Test is |
|---|---|---|---|---|---|
| `fts_and` | recall@5 | subcat | 0.031 | 0.003 [0.000, 0.009] | lower |
| `fts_and` | recall@10 | subcat | 0.031 | 0.003 [0.000, 0.009] | lower |
| `fts_and` | recall@20 | subcat | 0.031 | 0.003 [0.000, 0.009] | lower |
| `fts_and` | norm_recall@5 | subcat | 0.035 | 0.006 [0.000, 0.019] | lower |
| `fts_and` | norm_recall@10 | subcat | 0.032 | 0.003 [0.000, 0.010] | lower |
| `fts_and` | norm_recall@20 | subcat | 0.031 | 0.003 [0.000, 0.009] | lower |
| `fts_and` | ndcg@10 | subcat | 0.035 | 0.007 [0.000, 0.021] | lower |
| `fts_and` | recall@5 | all | 0.008 | 0.002 [0.000, 0.005] | lower |
| `fts_and` | recall@10 | all | 0.008 | 0.002 [0.000, 0.005] | lower |
| `fts_and` | recall@20 | all | 0.008 | 0.002 [0.000, 0.005] | lower |
| `fts_and` | norm_recall@10 | all | 0.009 | 0.002 [0.000, 0.006] | lower |
| `fts_and` | norm_recall@20 | all | 0.008 | 0.002 [0.000, 0.005] | lower |
| `fts_or` | recall@20 | subcat | 0.526 | 0.658 [0.556, 0.769] | higher |
| `fts_or` | norm_recall@20 | subcat | 0.538 | 0.658 [0.556, 0.769] | higher |
| `dense` | norm_recall@5 | example | 0.352 | 0.280 [0.221, 0.345] | lower |
| `dense` | norm_recall@5 | all | 0.377 | 0.318 [0.258, 0.377] | lower |
| row 2 | norm_recall@5 | example | 0.352 | 0.280 [0.221, 0.345] | lower |
| row 2 | norm_recall@5 | all | 0.377 | 0.318 [0.258, 0.377] | lower |
| row 4 | ndcg@10 | subcat | 0.377 | 0.288 [0.223, 0.363] | lower |
| row 5 | norm_recall@5 | subcat | 0.369 | 0.254 [0.177, 0.348] | lower |
| row 6 | recall@5 | subcat | 0.339 | 0.242 [0.170, 0.329] | lower |
| row 6 | norm_recall@5 | subcat | 0.408 | 0.285 [0.198, 0.379] | lower |
| row 6 | ndcg@10 | subcat | 0.392 | 0.309 [0.237, 0.390] | lower |
| row 6 | recall@5 | example | 0.248 | 0.179 [0.131, 0.230] | lower |
| row 6 | norm_recall@5 | example | 0.315 | 0.235 [0.173, 0.300] | lower |
| row 6 | recall@5 | all | 0.268 | 0.194 [0.153, 0.244] | lower |
| row 6 | norm_recall@5 | all | 0.336 | 0.247 [0.192, 0.304] | lower |
| row 4 − row 3 | recall@10 | subcat | -0.114 | -0.235 [-0.347, -0.129] | lower |
| row 4 − row 3 | ndcg@10 | subcat | -0.122 | -0.215 [-0.301, -0.131] | lower |
| Pipeline | gold_citation_recall | QA | 0.864 | 0.962 [0.900, 1.000] | higher |
| Pipeline | answer_accuracy | QA | 0.909 | 1.000 [1.000, 1.000] | higher |
| Pipeline + base text | answer_accuracy | QA | 0.929 | 1.000 [1.000, 1.000] | higher |
| Pipeline + base text − pipeline | abstention_f1 | QA | +0.119 | +0.043 [+0.000, +0.116] | lower |
| Pipeline + base text − pipeline | answer_rate | QA | +0.120 | +0.040 [+0.000, +0.100] | lower |
| Pipeline + base text − pipeline | answer_accuracy | QA | +0.019 | +0.000 [+0.000, +0.000] | lower |
<!-- END generated: final_shifts -->

They fall into five groups:

1. **AND search, at the floor.** AND search returns a chunk only if it contains every word of the query. CSF sentences are long, so it returns nothing for almost every query on both splits. A few lucky dev queries put dev's mean, 0.031 on subcategory queries, just above test's narrow interval, [0.000, 0.009]. It's a strawman baseline, and no decision rests on it.
2. **OR search at depth 20, on subcategory queries.** Test is higher, 0.658 against 0.526. Test has only 31 subcategory queries, so its interval is wide, and OR search's long result lists happened to reach more of test's gold by rank 20. No decision used recall@20.
3. **Dense search's top 5, normalized.** Normalized recall@5 for row 2 fell from 0.377 to 0.318 over all queries. Part of that is real: on example queries, plain recall@5 fell from 0.279 to 0.238. Part comes from the answer key. Normalized recall divides by min(5, gold controls) instead of by all the gold controls, so it only lifts queries with more than 5. Test's keys are smaller: its recall@5 ceiling is 0.843, against 0.788 on dev. So normalization lifts test's numbers less. Production sends the top 10 to the model, and recall@10 held at 0.421.
4. **The reranker hurt more on test.** The reranked rows (4, 5 and 6) were lower at the top 5 and on nDCG@10. On subcategory queries, reranking cost −0.235 [−0.347, −0.129] recall@10, against −0.114 on dev. That's the same direction, only bigger, so the case for leaving it off gets stronger.
5. **The answering numbers were better on test, and base text's lead shrank.**
   - Test was easier at the retrieval step. `gold_in_context` was 0.967 against 0.900, so a gold control reached the model for 29 of the 30 answerable test questions, against 27 of 30 on dev. That's why accuracy and gold citation recall rose.
   - Answer accuracy of 1.000 with the interval [1.000, 1.000] isn't certainty. When no answer is wrong, no resample can contain a wrong answer, so the bootstrap has nothing to vary.
   - Base text's lead fell from +0.119 to +0.043 because the pipeline made fewer mistakes for it to fix: 4 wrong refusals on test, against 8 on dev. Base text fixed 2 of the 4 on test and 6 of the 8 on dev. A lead that was chosen because it was the biggest on dev also tends to shrink on fresh data, which is called the winner's curse.

### What it costs

<!-- BEGIN generated: final_costs -->
| Latency (ms) | Dev | Test |
|---|---|---|
| Row 1 (bm25), p50 | 1.6 | 1.8 |
| Row 2 (dense), p50 | 2.6 | 2.9 |
| Row 3 (hybrid), p50 | 4.3 | 4.6 |
| Row 4 (hybrid, reranked), p50 | 4.4 + 1,661 rerank | 4.5 + 1,696 rerank |
| Row 5 (hybrid, reranked), p50 | 2.6 + 1,791 rerank | 2.8 + 1,832 rerank |
| Row 6 (hybrid, reranked), p50 | 2.5 + 2,127 rerank | 2.7 + 2,129 rerank |
| Pipeline: retrieval + generation, p50 / p95 | 9,559 / 13,675 | 11,101 / 100,506 |
| Pipeline + base text: retrieval + generation, p50 / p95 | 10,207 / 14,468 | 11,584 / 36,144 |
<!-- END generated: final_costs -->

First-stage retrieval takes a few milliseconds on either split. The reranker adds 1.7 to 2.1 seconds per query on this laptop's CPU, and it made results worse. Test generation's p95, 100,506 ms against 13,675 ms on dev, says more about the provider that day than about the system: it's the same trouble that crashed the run six times. The p50s, 11,101 ms against 9,559 ms, are closer.

## Concepts

### Why a test set is sealed and used once

A test score means "how well this system does on questions it has never seen". Every time you look at test results and then change something, a little of test leaks into the system. If you look ten times, picking the best each time, the final test number is partly a measure of how well you fitted the test set. That's called adaptive overfitting, or the garden of forking paths. So all choosing happens on dev, and test is looked at once, after every choice is final. Even the run's failure handling (resume from the caches, no output until the end) was designed so a crash couldn't become a second look.

### Pre-registration

Pre-registration means writing down what you'll measure and how you'll decide, before the data exists, in a place with a timestamp (here, a commit). It stops a natural bias: once you've seen the numbers, every choice of metric, threshold or comparison can lean toward the story you'd like. Our pre-registered rows fixed the systems, the metrics, the bootstrap, and what counts as a noticeable difference. The discussion above then had to cover all 35 flags, including the ones that make nothing look better.

### A regression gate isn't an evaluation

The evaluation answers "which setup is best, and by how much?", with intervals, on hundreds of queries. The gate answers "did this commit break retrieval?", fast, on every push. It uses a small fixed sample, 30 queries, and one number. Its tolerance has to sit above the run-to-run noise, so it doesn't fail on harmless changes, and below a real breakage, so it catches them. Because the fixture and the code are fixed, the gate's number only moves when the code or the data changes. That makes a small tolerance safe. The proof that it works is a deliberate break that it catches: PR #1.

### Why latency uses percentiles

A mean is pulled around by a few slow requests. The median (p50) is the typical request, and p95 is the slowest 1 in 20, which is roughly what an impatient user sees on a bad day. On test, the pipeline's p50 was 11,101 ms but its p95 was 100,506 ms, because a few calls hung on the provider. A mean would have blended the two into one number that describes neither.

### Zero errors doesn't mean perfect

With 0 mistakes in n tries, the bootstrap gives the interval [1.000, 1.000], because every resample also has 0 mistakes. That doesn't mean the true error rate is zero, only that it's small enough not to show up in n tries. A common rule of thumb, the rule of three, puts the 95% upper bound on the error rate at about 3/n. So a 1.000 on a few dozen answers should be read as "no errors seen", not "never wrong".

## What this means for Phase 7

- **The resume line comes from `results/final_test.json` only.** It should say that the reranker hurt, and it must not claim the agent helped.
- **The honest story:**
  - an evaluated retrieval layer whose test score matched dev;
  - a reranker and an agent, both measured and both rejected;
  - a small retrieval fix, base text, that held up on test with a smaller lead.
- **Phase 7** is a 45-minute mock interview on all of it.

## Decisions

Each of these has a row in `DECISIONS.md`. The first three were committed before the test split was opened.

- **What runs on test:** Phase 2's four baselines, Phase 3's six rows and their comparisons, plus production against every row; and the pipeline and base text on the 50 test questions, graded by code. The agent and the judge stay on dev.
- **The run happens once.** It refuses to start if the results exist, and prints no metric until the end.
- **"Differs noticeably"** means the dev point falls outside the test 95% interval, and every such result gets a reason here.
- **The CI gate:**
  - hybrid retrieval on 30 dev queries with precomputed embeddings;
  - it fails at more than 0.03 below the baseline;
  - actions are pinned by commit SHA, and `uv sync --locked` installs exactly the lockfile.
- **The API:**
  - it reads the production pick from `results/`;
  - stage times follow definition 8, plus `wall`;
  - `make report` gives p50 and p95 per stage.
- **The app:**
  - it reads every number from the API;
  - its dependencies are pinned exactly and are at least 14 days old;
  - building it made no model calls.
- **The test run's six restarts** each resumed from the caches, as written down beforehand, and the row records where each one stopped.

## Gotchas we hit

1. **The provider failed six times mid-run.** Every finished call was already in the cache, so each restart replayed them for free and carried on. Caching each call as it finishes, as in Phase 5, paid for itself again.
2. **A cached call still has a time.** Replaying the original call's time keeps the API's latencies comparable with the evaluation's. But it made a replayed request look 20 seconds long, so the log also records `wall`, the request's own time.
3. **A label can hide a cost.** The first version of the costs table showed reranked rows at a few milliseconds, because `retrieval_ms_p50` times first-stage retrieval only. The reranker is timed separately, and the table now shows both.
4. **Tests with fakes don't test the wiring.** The API tests use fake models, so production retrieval, the cache, the citation check and the log had never run together. One real request, with a model function that raises on any cache miss, checked all of it with no risk of a model call.
5. **CSS `uppercase` turned τ into Τ,** the capital Greek letter, which reads as "T". Labels with Greek letters can't be uppercased by CSS.
6. **TypeScript inferred `Loadable<unknown>`** from a generic helper used inside a ternary. Writing the type argument out (`loading<ControlDetail>()`) fixed it.
7. **`pnpm add` writes `^` ranges by default,** so a fresh resolve could pick a newer release than the one tested. Every dependency is now pinned to an exact version.

## Interview questions

**1. How did you make sure the test set never influenced a decision?**
The loaders for the test half raise an error unless one environment variable is set, and only the final-test command sets it. Before opening it, I committed what would run, which metrics count, and the rule for a noticeable difference. The script refuses to run if its results file exists, and it prints no metric until the end. Every choice, from chunking to τ to the production system, was made on dev. Test then ran once, and the production setup's recall@10 was 0.421 on test against 0.420 on dev.

**2. Your test run crashed six times. Isn't each restart another look at the test set?**
No. A look means seeing a number and being able to react to it, and the script printed only progress lines until the very end. Each restart resumed from the LLM cache, which stores a call only once it succeeds. So every model call was made exactly once, as in an unbroken run, and retrieval is deterministic. I wrote the restart policy down before the run, and a DECISIONS row records where each crash happened.

**3. Did the test set confirm your dev results?**
On every decision, yes. Dense beat BM25 on both splits (+0.060 [+0.006, +0.119] on test), hybrid's edge over dense stayed inside the noise (+0.015 [−0.021, +0.051]), and the reranker hurt on every metric (−0.111 [−0.175, −0.055] recall@10). Base text kept its lead over the plain pipeline, though smaller: +0.043 [+0.000, +0.116] abstention F1, against +0.119 on dev. 35 of 346 checks put the dev number outside the test interval. I explain each one, and none reverses a decision.

**4. Your reranker made things worse. On test too?**
Yes, and by more. Reranking the hybrid top 50 cost −0.111 recall@10 on test, against −0.091 on dev, and −0.235 on subcategory queries, against −0.114. It also cost about 1.7 seconds per query on a CPU, against a few milliseconds for retrieval. NIST's answer key is broad, mapping one CSF outcome to many controls, while a cross-encoder rewards the passage that most closely restates the query, often a narrow enhancement. So it's off in production, and I report it as a negative result.

**5. How does your CI catch a quality regression that unit tests miss?**
On every push, CI starts Postgres with pgvector, ingests the pinned catalog, and loads a fixture with precomputed embeddings for every chunk and for 30 dev queries, so no model is downloaded. It runs hybrid retrieval and fails if mean recall@10 is more than 0.03 below the saved baseline of 0.4953. To prove it, I opened a PR that drops the dense half of hybrid search. Every unit test passed, and the gate failed. The fixture also stores each chunk's text hash, so a chunking change can't be gated against stale vectors.

**6. What do you log per request, and why p95 rather than the mean?**
One row per request: the query, the pipeline, the retrieved controls and scores, each stage's time, the decision and the full trace. `make report` gives p50 and p95 per stage, because a mean mixes the typical request with the slow tail. On test, the pipeline's p50 was 11,101 ms but its p95 was 100,506 ms, because of provider trouble. I also log `wall` next to the stage times, because a cached call replays its original time, and `wall` shows what the request itself took.

**7. Both systems scored answer accuracy 1.000 [1.000, 1.000] on test. Are they perfect?**
No. With zero wrong answers, every bootstrap resample also has zero, so the interval collapses to a point. That shows the bootstrap's limit, not certainty. The rule of three says that with zero errors in n tries, the 95% upper bound on the error rate is about 3/n, and n here is a few dozen answers. Part of the rise is also that test was easier at retrieval: a gold control reached the context for 29 of 30 answerable test questions, against 27 of 30 on dev.

**8. Base text's lead shrank from +0.119 on dev to +0.043 on test. Was the dev result wrong?**
Not wrong, but probably optimistic. On test, the plain pipeline wrongly refused only 4 answerable questions, against 8 on dev, so there was less to fix, and base text fixed 2 of them. A system picked partly because it led on dev also tends to lead by less on fresh data (the winner's curse). Base text still wasn't worse on a single test question, cost no extra model call, and still refused all 20 unanswerable ones. So it stays in production, but I'd quote the smaller test lead, and note that its interval touches zero.

## Follow-ups from the quiz

Jude asked for all three questions with their answers instead of answering them, so this quiz isn't passed. These are the answers in plain words, starting with the terms they rely on.

**1. The test run crashed six times, and we restarted it each time. An interviewer says: "So you ran on the test set seven times, and your numbers aren't clean any more." Are they right?**

No. Seven starts made one run, and nobody saw a number in between.

- **The words.** A "look" at the test set means seeing a test number and being able to change something because of it. The LLM cache, `data/cache/llm.jsonl`, is a notebook with one line per finished model call. Each line holds a key made from the model's name and the exact prompt, and the reply. Before calling the model, the code checks the notebook, and if the prompt is there it reuses the reply instead of calling.
- **What happened.**
  - Start 1 ran the retrieval part and began answering. During test question 3, the Cursor API returned "Network request failed" and Python stopped. No results file was written, but the calls that had finished were already in the notebook.
  - Start 2 ran retrieval again, found questions 1 and 2 in the notebook (no calls), and carried on from question 3 until it crashed during question 14.
  - The next starts stopped during questions 24, 28, 39 and 41.
  - Start 7 finished all 50. Only then did it compute the metrics, print them and write `results/final_test.json`.
- **Why the numbers equal an unbroken run's.**
  - Every model call was made exactly once. A call either succeeded, so it was written down and reused, or failed, so nothing was written and it was made again on the next start.
  - Retrieval has no randomness: the same vectors and the same exact search give the same top 10 every time.
  - Grading is code, and the bootstrap's seed is fixed at 20261023, so the same answers give the same numbers.
- **Why it isn't a second look.**
  - Until start 7 finished, the only output was progress lines like `question 28/50`. No metric existed yet.
  - Nothing changed between starts: the same commit, the same prompts, the same production pick.
  - The restart policy was in `DECISIONS.md` before the run began.
- **What would have made it a second look.** Two cases:
  - The script prints test recall@10 per row before answering starts. After a crash, I switch production to hybrid because it looked better on test, and restart. Test has now changed a decision.
  - After the run, I dislike a number, delete `results/final_test.json` and run again with an empty cache, hoping for luckier replies. The reported number becomes the best of several tries. The script blocks this: it refuses to start once the file exists.

*An interviewer would push on:* model replies are random, so wouldn't an unbroken run have given different text? It could, but it too would have sampled each prompt once, so it's the same experiment. The intervals don't cover run-to-run model variation, which the README lists as a limitation.

**2. 35 of 346 dev-versus-test checks were flagged. Does that mean the test set disagrees with dev?**

No. The rule tells us where to look, and some flags come from luck alone. What matters is whether a flag changes a decision, and none does.

- **The words.**
  - A **check** is one setup, one metric and one query type, such as "row 2, normalized recall@5, all queries".
  - A **95% interval** is the range the test number could plausibly have taken with a different draw of test queries. The bootstrap finds it by resampling test's subcategories 1,000 times.
  - **The rule**, fixed before the run: flag a check when the dev number falls outside the test interval.
- **Why luck alone raises flags.** Picture two classes of equal ability taking the same exam. The second class's range allows for its own luck. The first class's score has luck in it too, so it lands outside the second class's range more often than 5% of the time, even though nothing is different. Also, many checks measure nearly the same thing: recall@5, normalized recall@5 and nDCG@10 all reward getting gold controls into the top 5, so one real wobble raises several flags at once.
- **One flag, worked through.** Take row 2, production's dense search, normalized recall@5 over all queries. Dev is 0.3774, and test is 0.3183 with interval [0.2577, 0.3771], so dev misses the interval by 0.0003. It has two causes:
  - **A real part.** On example queries, plain recall@5 fell from 0.279 on dev to 0.238 on test.
  - **A part from the answer key.** Normalized recall@5 divides the gold controls in the top 5 by the smaller of 5 and the number of gold controls. ID.IM-02, a dev query, has 40 gold controls. Its plain recall@5 can never exceed 5/40, but its normalized recall@5 can reach 5/5. So normalization lifts queries with big answer keys. Test's keys are smaller (its recall@5 ceiling is 0.843, against dev's 0.788), so normalization lifts test less.
  - **Why production doesn't care.** Production sends the top 10 to the model, and recall@10 was 0.420 on dev and 0.421 on test.
- **Which flag would have mattered.** One that reverses a decision. For example, the reranker helping on test, or hybrid beating dense with an interval above zero. Instead, the reranker hurt by −0.111 [−0.175, −0.055], and hybrid's edge was +0.015 [−0.021, +0.051].

*An interviewer would push on:* is there a better rule? You could compute an interval for the dev − test difference itself, which allows for both splits' luck, or correct for the number of checks. We kept the simple rule because it was fixed in advance, and every flag is explained above.

**3. The CI gate checks hybrid retrieval, but production uses dense alone. Why gate hybrid, and why did PR #1 fail the gate while every unit test passed?**

- **The words.**
  - A **unit test** checks one small function on made-up inputs. For example, `recall(["ac-3", "ia-2", "ac-2"], {"ac-2", "ia-2", "ac-3"}, 3) == 1` in `tests/test_metrics.py`.
  - **CI** is GitHub running our checks on every push and pull request.
  - The **gate** is a CI step that runs real retrieval on 30 real dev queries and fails if mean recall@10 falls more than 0.03 below the saved baseline, 0.4953.
  - The **fixture**, `data/ci/fixture.json.gz`, holds the vectors of every chunk and of the 30 queries, so CI never downloads or runs the embedding model.
- **Why hybrid.** Hybrid runs three parts: BM25 keyword search over Postgres's lexemes, pgvector cosine search, and RRF, which merges the two ranked lists into one. If any of the three breaks, the gate's recall drops, so one number guards all three. Gating dense alone would miss a broken BM25 or a broken merge, and both are still used by `/search` and the evaluations. The reranker stays out because it needs a large model download, and it's off in production anyway.
- **Why PR #1 failed only the gate.** The PR dropped the dense half of hybrid, so "hybrid" quietly became BM25 alone.
  - Every function still ran and still returned a ranked list of the right shape.
  - The fusion tests in `tests/test_fusion.py` still passed, because RRF itself was fine: they give it small ranked lists and check how it merges them. No unit test asks whether hybrid's output includes dense results.
  - The gate measures the outcome. With BM25 alone, recall@10 on the 30 queries fell below the floor of 0.4653 (0.4953 − 0.03), and CI turned red at the gate step ([run 41408595856](https://github.com/AntonyJudeShaman/controlfinder/actions/runs/41408595856)).

  Unit tests are like checking each part of a car: the engine turns over and the brakes squeeze. The gate is a test drive that notices the car got slow.
- **Why such a small tolerance is safe.** The fixture and the code are fixed, and the search is exact, so the gate gives the same number on every run. It moves only when the code or the data changes, so it can't fail at random. 0.03 is AGENTS.md's "3 points". The fixture also stores each chunk's text hash, so after a chunking change it refuses to load, instead of scoring new chunks against old vectors.

*An interviewer would push on:* what if you improve retrieval on purpose? The gate only fails on drops, so it passes. Then `make ci-baseline` rewrites `results/ci_baseline.json` in the same PR, so the floor rises with the improvement.
