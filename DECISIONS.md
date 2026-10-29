# Decisions

One row per decision, appended as we go. "Evidence" points at a file in `results/`, a check we ran, or the reason, if it was a judgment call.

| Date | Decision | Alternatives | Evidence |
|---|---|---|---|
| 2026-10-23 | Repo root is `RAG/controlfinder/` | `RAG/` workspace folder | Jude's choice |
| 2026-10-23 | No Jira ticket | Ticket on the work CEX board | Personal project |
| 2026-10-23 | Gold set uses only the `SP 800-53 Rev 5.2.0` references | Rev 5.1.1 only; union of both | The CSF 2.0 xlsx carries both versions side by side for the same subcategories; the OSCAL catalog's `metadata.version` is 5.2.0. Taking both would double-count. Counts are saved in Phase 2 |
| 2026-10-23 | Skip withdrawn CSF subcategory rows | Keep them as queries | They are CSF 1.1 rows marked `[Withdrawn: Incorporated into …]`, not CSF 2.0 outcomes |
| 2026-10-23 | Drop family-level references (`CP`, `IR`, `PT`) and log them | Expand each to every control in the family | One coarse reference would add a whole family to a subcategory's gold set and dominate its recall |
| 2026-10-23 | Remap references to withdrawn controls via OSCAL `incorporated-into` (RA-4 → RA-3) and log them | Drop them | In the pinned catalog, `ra-4` has `status = withdrawn` and `links: [{rel: incorporated-into, href: #ra-3}]`. Withdrawn controls aren't in the corpus, so the reference could never be retrieved |
| 2026-10-23 | Implementation examples come from column D of the same xlsx | A separate Implementation Examples download | Same rows as the gold set, so no join and no ID mismatch |
| 2026-10-23 | Pin the OSCAL catalog to oscal-content commit `f0de6d8d8c059d374f15e0ae07508d82e370fc1d` and check its sha256 | Download from `main` | The catalog's `last-modified` is 2026-10-22, one day before we started, still labeled 5.2.0: `main` changes under us |
| 2026-10-23 | Commit the CSF xlsx to `data/raw/` | Download at ingest time | Its endpoint (`csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all`) is unversioned |
| 2026-10-23 | FTS reports both an AND query (`plainto_tsquery`) and an OR query over the same lexemes, ranked by `ts_rank_cd` | AND only, as the prompt wrote; `websearch_to_tsquery` (also AND for unquoted words) | AND requires every query lexeme in one chunk, which long CSF sentences rarely satisfy. Measured in Phase 2 |
| 2026-10-23 | One partial HNSW index per strategy, `hnsw.ef_search` ≥ LIMIT | One global HNSW index; global index + `hnsw.iterative_scan`; one table per strategy | `results/ann_filter_demo.json`: a global index at the default `ef_search` returned a median of 7 of the 50 rows asked for; the partial index returned exactly 40 at the default and all 50 at `ef_search = 100`. Iterative scan also returned 50 and is compared on real data in Phase 2 |
| 2026-10-23 | Pass the strategy to SQL as a literal, never a bind parameter | Bind parameter | Checked with `PREPARE`: under `plan_cache_mode = force_custom_plan` the query uses `chunks_embedding_hnsw_a`; under `force_generic_plan` it falls back to `Seq Scan` + `Sort`. psycopg prepares a statement server-side after 5 runs, so a generic plan is possible in eval loops |
| 2026-10-23 | Always measure HNSW recall against exact search, and record which plan ran | Trust the index | `results/ann_filter_demo.json` `default_plan_with_partial_index`: at this table size the planner chooses `Limit > Sort > Seq Scan` (exact) unless the index is forced |
| 2026-10-23 | Strategy C retrieves deeper before parent-level dedup, so every system fills k unique parents | Take top-k chunks, then dedup | Several C chunks share a parent, so top-k chunks can collapse to fewer than k parents and unfairly lower C's recall@k |
| 2026-10-23 | Vector search and FTS in raw SQL; BM25 (`rank_bm25`), RRF and reranking in hand-written Python | Everything in SQL | `rank_bm25` is a Python library and the cross-encoder is a PyTorch model |
| 2026-10-23 | Cluster bootstrap: resample subcategories, not queries; paired for comparisons | Per-query bootstrap, as the prompt wrote | Example queries inherit their subcategory's gold set, so they are correlated; per-query resampling understates the variance. The resampling unit matches the split unit |
| 2026-10-23 | Report recall@k with its ceiling, plus normalized recall@k = hits@k / min(k, \|gold\|) | Plain recall@k only | A subcategory with more gold controls than k cannot reach recall@k = 1. Gold-set sizes are saved in Phase 2 |
| 2026-10-23 | Report `subcat` and `example` queries separately as well as combined | Combined only | Subcategory text and control text are both written by NIST, which may favor lexical matching; implementation examples read more like practitioner text |
| 2026-10-23 | Pre-register Phase 4/5 metric definitions (section below) | Define them after seeing results | Stops us from picking definitions that flatter the agent |
| 2026-10-23 | QA set: 60 answerable + 40 unanswerable, split 50/50 | 40 + 30 as the prompt wrote | More questions narrow the CIs. The set is still small, which the CIs will show |
| 2026-10-23 | Phase 4: solo rubric judging. Phase 5: pairwise in both orders | Pairwise in Phase 4 | Phase 4 has only one system, so there is nothing to compare pairwise |
| 2026-10-23 | Judge from a different model family than the generator if a key is provided; otherwise list self-preference bias as a limitation | Same-family judge, unmentioned | A judge tends to prefer outputs from its own model family |
| 2026-10-23 | Cache every LLM response and reranker score on disk | Call again on every run | The Anthropic API has no seed and temperature 0 isn't guaranteed deterministic; a cache makes reruns exact and cheap |
| 2026-10-23 | CI regression gate covers hybrid retrieval only | Include the reranker | The reranker would need a model download in CI, which the prompt rules out |
| 2026-10-23 | Image `pgvector/pgvector:0.8.7-pg16`, pinned by tag and multi-arch digest `sha256:7b822b0a…b90a` | Floating `pg16` tag | Newest pg16 tag at least 2 weeks old (pushed 2026-10-01); the digest guarantees the same bytes on arm64 and amd64 |
| 2026-10-23 | Exact `==` pins for direct deps plus `[tool.uv] exclude-newer = "2026-10-09T00:00:00Z"` | Pins for direct deps only | Applies the "at least 2 weeks old" rule to transitive deps too; `uv.lock` records the result |
| 2026-10-23 | Python 3.13 | 3.11, 3.12 | The local interpreter; satisfies `requires-python >= 3.11` |
| 2026-10-23 | Host port 5433 | 5432 | Avoids clashing with a locally installed Postgres |
| 2026-10-23 | Apply `schema.sql` from Python (`make schema`, idempotent) | Mount it into `docker-entrypoint-initdb.d` | Init scripts run only on an empty volume, and CI's Postgres service container can't mount them the same way |
| 2026-10-23 | Health check over TCP (`pg_isready -h 127.0.0.1`) | Default socket check | On first boot the image runs a temporary, socket-only server for init; a socket check can report ready too early |
| 2026-10-23 | `chunks.parent_control_id` is NOT NULL and equals `control_id` for base controls | NULL for base controls | Parent-level dedup becomes one column, with no COALESCE |
| 2026-10-23 | CHECK constraints: strategy allowlist; `is_enhancement` ⇔ `parent_id IS NOT NULL` | No constraints | A misspelled strategy would silently miss its partial index; every enhancement must have a parent |
| 2026-10-23 | `query_log.trace jsonb` added now | Add it in Phase 5 | Phase 5 must write the trace to `query_log`; adding it now avoids a migration |
| 2026-10-23 | Doc tables rendered from `results/` by `make docs`; a test fails if they drift | Paste tables by hand | Hard rule: tables are generated, never typed |
| 2026-10-29 | Clarify citation validity (pre-registered definition 4): a chunk covers its `control_id`, and a strategy B chunk also covers the enhancements merged into it | Leave "belongs to a chunk" as written | Found while walking through the schema: a B chunk holds its enhancements' text, but `control_id` names only the base control. Clarified before any QA question or answer exists, so no results were seen |

## Pre-registered definitions for Phases 4 and 5 (2026-10-23)

These were fixed before any QA question was drafted or any answer generated. Changing one after seeing results needs a new row in the table above, with the reason.

1. **Unanswerable.** A question is unanswerable if a correct answer needs facts that SP 800-53 Rev 5.2.0 doesn't contain: another framework's specifics (such as PCI DSS requirement numbers), a particular organization's internal policies, legal conclusions, or general trivia. If 800-53 controls support a correct answer, even a general one, the question is answerable. Jude's label is final.
2. **Decision.** Every system output is exactly one of `answer` or `abstain`. For both systems, an output whose text starts with the sentinel `INSUFFICIENT_EVIDENCE` is an abstention, and the generation prompt tells the model to emit exactly that sentinel. For the agent, a run that ends in the `abstain` node is also an abstention.
3. **Abstention metrics.** The positive class is "abstained". They are computed over all questions in the split, answerable and unanswerable:
   - TP: unanswerable and abstained. FP: answerable and abstained. FN: unanswerable and answered. TN: answerable and answered.
   - Abstention precision = TP / (TP + FP). Abstention recall = TP / (TP + FN). Abstention F1 = 2PR / (P + R).
   - If a denominator is 0, the metric is reported as undefined (null), never as 0 or 1.
   - Answer rate = answered / all questions.
4. **Citations.** A citation is a bracketed control ID in the answer, normalized with `normalize_control_id()`. A repeated ID in one answer counts once. Gold labels are normalized to base controls.
   - A citation is valid if its exact normalized ID (control or enhancement) is covered by a chunk passed to the generator. A chunk covers its `control_id`. A strategy B chunk also covers every active enhancement merged into it, that is, the controls whose `parent_id` is its `control_id`.
   - Citation precision = valid citations / all citations, pooled over all answered questions.
   - Gold-citation recall, per answered answerable question = |{parent(c) for each valid citation c} ∩ gold| / |gold|, averaged over those questions. `parent()` maps an enhancement to its base control. Invalid citations never count toward recall.
5. **Answer accuracy.** Computed over answerable questions that the system answered. An answer is correct if every citation is valid and at least one valid citation's parent is in the gold set. Answer accuracy = correct / answered answerable questions.
6. **Faithfulness (Phase 4).** An LLM judge scores each answered question from 1 to 5 against the exact context the generator saw. The rubric is committed before the first judged run, and raw judge outputs are stored.
7. **Pairwise (Phase 5).** On questions both systems answered, the judge compares the agent's answer with the pipeline's in both orders and also scores each one solo. A win counts only if both orders pick the same answer; anything else is a tie.
8. **Cost and latency.** "LLM calls per question" counts every call the design makes, including ones served from the cache. Latency p50/p95 per question comes from cold-cache runs. The cache stores each call's original latency, so a replay reports the same numbers.
9. **Threshold τ.** τ is chosen on dev only, and the selection criterion is written here before the sweep runs in Phase 5.
