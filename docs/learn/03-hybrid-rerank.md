# Phase 3: Hybrid search, reranking and ablations

## The short version

- **Hybrid search was the best setup, but not by enough to prove it.** BM25 and dense search merged with RRF scored 0.436 recall@10 over all dev queries, against 0.420 for dense search alone. The paired difference, +0.016, has a 95% CI of [−0.003, +0.036], which includes 0.
- **The cross-encoder reranker made every metric worse.** Reranking the hybrid top 50 cut recall@10 by 0.091 [−0.124, −0.061], and nDCG@10, MRR and precision@5 fell too, for both query types. It also added 1,661 ms per query (p50) on this laptop's CPU, where retrieval takes a few milliseconds.
- **Production is dense search alone, on strategy C.** That's what the rule we committed before the run picks: the simplest setup that isn't distinguishably worse than the best one.

Every metric below comes from `results/ablations_dev.json`, and `make docs` regenerates the tables.

## What we built

| File | What it is |
|---|---|
| `src/controlfinder/retrieval/fusion.py` | `rrf()`: reciprocal rank fusion of several rankings of parent controls |
| `src/controlfinder/retrieval/rerank.py` | `Reranker`: bge-reranker-base on CPU, with every query's scores and timing cached in `data/cache/rerank.jsonl` |
| `src/controlfinder/retrieval/pipeline.py` | `Retriever`: BM25, dense or hybrid search, each returning 50 distinct controls. `rerank()` reorders them by the cross-encoder's scores |
| `src/controlfinder/eval/ablations.py` | `make ablations`: runs the six rows on dev and writes `results/ablations_dev.json` |
| `data/cache/rerank.jsonl` | 1,008 cached reranker results, committed, so a fresh clone reproduces every number without the 1.1 GB model |
| `tests/test_fusion.py`, `test_rerank.py`, `test_retrieval.py` | RRF on hand-computed rankings, the cache with a fake model, and the roll-up from chunks to controls |

## How it works

### `make ablations`, step by step

1. **The rules came first.** The rows, the comparisons and the rule for picking the production setup went into `DECISIONS.md` in commit `8d16bb4`, before the first run, so the results couldn't shape them.
2. **Each retriever returns 50 controls.** BM25 and dense search fetch enough chunks to hold 50 distinct parent controls (504 chunks for C, 50 for A and B, which have one chunk per control), roll them up to their parents and keep the first 50. Each control keeps its best-ranked chunk.
3. **Hybrid merges the two lists with RRF** (explained below) and keeps the top 50.
4. **The reranker reorders those 50.** It reads each control's kept chunk together with the query, so every query costs exactly 50 (query, chunk) pairs, and sorts by its score.
5. **Score the top 20, exactly as in Phase 2.** Rows 1 and 2 must reproduce Phase 2's BM25 and dense numbers, or the run stops. They did.
6. **Compare and pick.** Paired cluster bootstrap for the three planned comparisons, then the pick rule.
7. **Look at what reranking changed:** which queries gained or lost gold controls, and which way they moved.

The reranker's scores and the time each query took go into `data/cache/rerank.jsonl`, keyed by a hash of the model, its version, the query and the chunk texts. A rerun reads them back: identical scores, the original latency, no model download.

## Results on dev

<!-- BEGIN generated: ablation_rows -->
| # | Retrieval | Chunking | Rerank | recall@10, `subcat` (75 queries) | recall@10, `example` (263 queries) | recall@10, `all` (338 queries) |
|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 0.461 [0.391, 0.538] | 0.346 [0.290, 0.408] | 0.372 [0.317, 0.433] |
| 2 | `dense` | C_separate | no | 0.501 [0.423, 0.577] | 0.397 [0.342, 0.459] | 0.420 [0.363, 0.479] |
| 3 | `hybrid` | C_separate | no | 0.517 [0.447, 0.585] | 0.413 [0.355, 0.478] | 0.436 [0.378, 0.497] |
| 4 | `hybrid` | C_separate | yes | 0.404 [0.334, 0.476] | 0.329 [0.283, 0.380] | 0.345 [0.299, 0.398] |
| 5 | `hybrid` | A_control_only | yes | 0.418 [0.352, 0.486] | 0.346 [0.295, 0.402] | 0.362 [0.311, 0.420] |
| 6 | `hybrid` | B_control_plus_enh | yes | 0.434 [0.363, 0.510] | 0.362 [0.304, 0.422] | 0.378 [0.322, 0.437] |
<!-- END generated: ablation_rows -->

How to read it:

- **Rows 1 and 2 are Phase 2's BM25 and dense baselines, reproduced.**
- **Row 3, hybrid, has the best scores** for every query type.
- **Rows 4 to 6 add the reranker, and all three score below row 3.**
- **Rows 5 and 6 use hybrid retrieval,** because it was the best of rows 1 to 3. So they differ from row 4 only in chunking.

Is a difference real, or luck? The three planned comparisons, each a paired cluster bootstrap:

<!-- BEGIN generated: ablation_comparisons -->
| Comparison | Metric | Queries | Difference: mean [95% CI] | CI excludes 0 |
|---|---|---|---|---|
| hybrid vs best single retriever (row 3 − row 2) | recall@10 | `subcat` | +0.016 [-0.030, +0.061] | no |
| hybrid vs best single retriever (row 3 − row 2) | recall@10 | `example` | +0.017 [-0.007, +0.039] | no |
| hybrid vs best single retriever (row 3 − row 2) | recall@10 | `all` | +0.016 [-0.003, +0.036] | no |
| reranker vs no reranker (row 4 − row 3) | recall@10 | `subcat` | -0.114 [-0.164, -0.069] | yes |
| reranker vs no reranker (row 4 − row 3) | recall@10 | `example` | -0.085 [-0.120, -0.054] | yes |
| reranker vs no reranker (row 4 − row 3) | recall@10 | `all` | -0.091 [-0.124, -0.061] | yes |
| reranker vs no reranker (row 4 − row 3) | ndcg@10 | `subcat` | -0.122 [-0.171, -0.071] | yes |
| reranker vs no reranker (row 4 − row 3) | ndcg@10 | `example` | -0.073 [-0.111, -0.044] | yes |
| reranker vs no reranker (row 4 − row 3) | ndcg@10 | `all` | -0.084 [-0.118, -0.057] | yes |
| reranker vs no reranker (row 4 − row 3) | mrr | `subcat` | -0.141 [-0.220, -0.061] | yes |
| reranker vs no reranker (row 4 − row 3) | mrr | `example` | -0.065 [-0.125, -0.013] | yes |
| reranker vs no reranker (row 4 − row 3) | mrr | `all` | -0.082 [-0.135, -0.038] | yes |
| reranker vs no reranker (row 4 − row 3) | precision@5 | `subcat` | -0.093 [-0.136, -0.051] | yes |
| reranker vs no reranker (row 4 − row 3) | precision@5 | `example` | -0.056 [-0.081, -0.033] | yes |
| reranker vs no reranker (row 4 − row 3) | precision@5 | `all` | -0.064 [-0.087, -0.043] | yes |
| best chunking vs runner-up (row 6 − row 5) | recall@10 | `subcat` | +0.016 [-0.013, +0.051] | no |
| best chunking vs runner-up (row 6 − row 5) | recall@10 | `example` | +0.015 [-0.009, +0.038] | no |
| best chunking vs runner-up (row 6 − row 5) | recall@10 | `all` | +0.015 [-0.004, +0.035] | no |
<!-- END generated: ablation_comparisons -->

- **Hybrid vs dense: not distinguishable.** The CI includes 0 for every query type.
- **Reranker vs none: distinguishable, in the wrong direction.** Every interval is below 0, for all four metrics and all three query types.
- **Best chunking vs runner-up: not distinguishable.** With the reranker on, B beat A by 0.015, but the CI includes 0.

Every metric, over all 338 dev queries:

<!-- BEGIN generated: ablation_metrics -->
| # | Retrieval | Chunking | Rerank | recall@5 | recall@10 | recall@20 | norm_recall@10 | precision@5 | mrr | ndcg@10 | Gold among the 50 candidates |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 0.269 | 0.372 | 0.488 | 0.400 | 0.220 | 0.475 | 0.336 | 0.655 |
| 2 | `dense` | C_separate | no | 0.303 | 0.420 | 0.537 | 0.453 | 0.266 | 0.554 | 0.397 | 0.704 |
| 3 | `hybrid` | C_separate | no | 0.314 | 0.436 | 0.548 | 0.473 | 0.277 | 0.565 | 0.411 | 0.713 |
| 4 | `hybrid` | C_separate | yes | 0.232 | 0.345 | 0.499 | 0.379 | 0.213 | 0.483 | 0.327 | 0.713 |
| 5 | `hybrid` | A_control_only | yes | 0.255 | 0.362 | 0.501 | 0.398 | 0.229 | 0.504 | 0.346 | 0.670 |
| 6 | `hybrid` | B_control_plus_enh | yes | 0.268 | 0.378 | 0.525 | 0.410 | 0.232 | 0.494 | 0.349 | 0.705 |
<!-- END generated: ablation_metrics -->

The last column is the share of gold controls anywhere among the 50 candidates. A reranker only reorders its candidates, so it can't find a gold control that isn't among them. Row 4 reranks the same 50 candidates as row 3, which hold 0.713 of the gold controls, yet it puts fewer of them in the top 10: 0.345 against 0.436.

### What it costs

<!-- BEGIN generated: rerank_costs -->
| # | Retrieval | Chunking | Rerank | Retrieval p50 (ms) | Rerank p50 / p95 (ms) | Total p50 / p95 (ms) | Pairs over 512 tokens |
|---|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 1.6 | – | – | – |
| 2 | `dense` | C_separate | no | 2.6 | – | – | – |
| 3 | `hybrid` | C_separate | no | 4.3 | – | – | – |
| 4 | `hybrid` | C_separate | yes | 4.4 | 1,661 / 1,841 | 1,667 / 1,845 | 2,343 of 16,900 (14%) |
| 5 | `hybrid` | A_control_only | yes | 2.6 | 1,791 / 1,960 | 1,794 / 1,962 | 4,855 of 16,900 (29%) |
| 6 | `hybrid` | B_control_plus_enh | yes | 2.5 | 2,127 / 2,249 | 2,129 / 2,251 | 10,961 of 16,900 (65%) |
<!-- END generated: rerank_costs -->

- **Retrieval takes 1.6 to 4.4 ms per query. Reranking takes 1.7 to 2.1 seconds at p50,** so it is almost all of the total.
- **B is the slowest to rerank because its chunks are the longest.** 65% of its pairs are over the 512-token limit and get cut, against 14% for C. A cut pair is shortened from the end of the chunk, so the reranker never reads the rest.

### Why reranking lost

A cross-encoder making things worse is unusual, so we checked for a bug first. Our `CrossEncoder` setup gives the same scores as running the model directly through `transformers`, and for an account-management query it ranks AC-2 Account Management far above physical access and cryptography controls. The model works. Then we looked at what it changed in row 4:

<!-- BEGIN generated: rerank_effect -->
| Row 4: reranking row 3's 50 candidates | Count |
|---|---|
| Queries with more gold controls in the top 10 | 45 |
| Queries with fewer gold controls in the top 10 | 137 |
| Queries with the same number | 156 |
| Gold candidates moved up | 575 |
| Gold candidates moved down | 808 |
| Gold candidates that kept their rank | 128 |
| Candidates judged on an enhancement's chunk | 8,770 of 16,900 (52%) |
<!-- END generated: rerank_effect -->

It lowered the number of gold controls in the top 10 three times as often as it raised it. These are the five queries where it lost the most:

<!-- BEGIN generated: rerank_losses -->
| Query | Text | Gold | Change in gold controls in the top 10 | Top 5 before reranking (gold in bold), with the chunk the reranker read | Top 5 after |
|---|---|---|---|---|---|
| ID.IM-02 | Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties | ac-1, at-1, au-1, ca-1, ca-2, ca-5, ca-7, ca-8, cm-1, cp-1, cp-2, cp-4, ia-1, ir-1, ir-3, ir-4, ir-8, ma-1, mp-1, pe-1, pl-1, pl-2, pm-1, pm-31, pm-4, ps-1, pt-1, ra-1, ra-3, ra-5, ra-7, sa-1, sa-11, sa-8, sc-1, si-1, si-2, si-4, sr-1, sr-5 | -4 | **ca-8** (`C:ca-8.2`), **ca-2** (`C:ca-2.2`), sr-6 (`C:sr-6.1`), at-3 (`C:at-3.3`), pm-14 (`C:pm-14`) | cp-8, sr-7, **ca-2**, cp-3, sc-38 |
| PR.DS-10 | The confidentiality, integrity, and availability of data-in-use are protected | ac-2, ac-3, ac-4, au-13, au-9, ca-3, cp-9, sa-8, sc-11, sc-13, sc-24, sc-32, sc-39, sc-4, sc-40, sc-43, sc-7, si-10, si-16, si-3, si-4, si-7 | -4 | sc-8 (`C:sc-8`), sc-28 (`C:sc-28`), ac-17 (`C:ac-17.2`), **sa-8** (`C:sa-8.20`), **au-9** (`C:au-9.3`) | sc-8, au-4, **cp-9**, sc-37, sc-36 |
| DE.CM-01 | Networks and network services are monitored to find potentially adverse events | ac-2, au-12, ca-7, cm-3, sc-5, sc-7, si-4 | -3 | **si-4** (`C:si-4.25`), **sc-5** (`C:sc-5`), **sc-7** (`C:sc-7.15`), **ca-7** (`C:ca-7.4`), ir-4 (`C:ir-4.14`) | si-7, ra-5, ac-4, **sc-5**, ir-5 |
| DE.CM-01/ex1 | Monitor DNS, BGP, and other network services for adverse events | ac-2, au-12, ca-7, cm-3, sc-5, sc-7, si-4 | -3 | **sc-7** (`C:sc-7.4`), **si-4** (`C:si-4.25`), **sc-5** (`C:sc-5.3`), sc-20 (`C:sc-20`), sc-22 (`C:sc-22`) | **sc-7**, sr-4, sc-20, si-2, au-2 |
| DE.CM-09/ex3 | Monitor software configurations for deviations from security baselines | ac-4, ac-9, au-12, ca-7, cm-10, cm-11, cm-3, cm-6, sc-34, sc-35, si-4, si-7 | -3 | cm-2 (`C:cm-2.2`), **cm-6** (`C:cm-6`), **cm-3** (`C:cm-3.3`), **cm-11** (`C:cm-11.3`), sa-4 (`C:sa-4.5`) | ac-16, **cm-6**, ra-9, cm-9, si-3 |
<!-- END generated: rerank_losses -->

Two likely reasons:

1. **NIST's answer key is broad, and the reranker is literal.** ID.IM-02, "Improvements are identified from security tests and exercises…", maps to 40 controls, including the first control of all 20 families, which in 19 of them is "Policy and Procedures". A cross-encoder answers a narrower question: does this one passage say what this sentence says? Fusion's order is the agreement of two different retrievers. The reranker replaces it with one model's opinion.
2. **In strategy C, it judged each control by one chunk, often a narrow enhancement.** 52% of the candidates came with an enhancement's chunk. For DE.CM-01, "Networks and network services are monitored to find potentially adverse events", fusion ranked SI-4 System Monitoring first, but the chunk it kept was `C:si-4.25`, SI-4(25) "Optimize Network Traffic Analysis". On that chunk alone the reranker wasn't convinced, and SI-4 fell out of the top 5. Rows 5 and 6 judge every control on a chunk that starts with its own base text, and they scored higher than row 4 (0.362 and 0.378, against 0.345). Both are still distinguishably below row 3 (table below).

One caveat: some of the reranker's picks may be reasonable controls NIST didn't map, the gold-set limitation from Phase 2, so its real loss may be smaller than measured. But every row is scored against the same answer key, so the comparison is fair.

### The production pick

<!-- BEGIN generated: production_pick -->
| # | Retrieval | Chunking | Rerank | Parts | recall@10 (all) | Minus the best row [95% CI] | Distinguishably worse | Production |
|---|---|---|---|---|---|---|---|---|
| 1 | `bm25` | C_separate | no | 1 | 0.372 | -0.065 [-0.087, -0.042] | yes |  |
| 2 | `dense` | C_separate | no | 1 | 0.420 | -0.016 [-0.036, +0.003] | no | **pick** |
| 3 | `hybrid` | C_separate | no | 2 | 0.436 | best | no |  |
| 4 | `hybrid` | C_separate | yes | 3 | 0.345 | -0.091 [-0.124, -0.061] | yes |  |
| 5 | `hybrid` | A_control_only | yes | 3 | 0.362 | -0.074 [-0.105, -0.042] | yes |  |
| 6 | `hybrid` | B_control_plus_enh | yes | 3 | 0.378 | -0.059 [-0.088, -0.030] | yes |  |
<!-- END generated: production_pick -->

Row 3 has the best score. Row 2 uses one retriever instead of two, and its difference from row 3 includes 0, so the rule picks row 2. Every reranked row is distinguishably worse than row 3.

## Concepts

### RRF: merging two rankings without comparing their scores

Two judges rank the same cakes. One gives points out of 1,000, the other out of 1. Adding their points would let the first judge decide everything. Our retrievers have the same problem: a BM25 score is a sum over the query's words, so it has no fixed maximum and grows with longer queries, while cosine similarity stays between −1 and 1.

RRF ignores the points and uses only the places. A control's score is the sum, over the lists it appears in, of 1 / (60 + its place). With lists `[a, b, c]` and `[b, c, d]` (a case in `tests/test_fusion.py`):

- b: 1/62 + 1/61 = 0.0325
- c: 1/63 + 1/62 = 0.0320
- a: 1/61 = 0.0164
- d: 1/63 = 0.0159

So b wins: both lists like it.

Why k = 60? It flattens the top. First place is worth 1/61 = 0.0164 and tenth place 1/70 = 0.0143, barely less. A control both lists put tenth (2/70 = 0.0286) beats one that a single list puts first. Agreement wins. With k = 0, first place would be worth 1 and tenth place 0.1, so one list's favorite would dominate. We use the 60 from the original paper and don't tune it.

We fuse controls, not chunks. In C, a top 50 of chunks can hold far fewer than 50 controls, because one control has many chunks. Fusing each retriever's top 50 controls gives every strategy the same 50 candidates.

> **Interview version:** RRF fuses rankings by position: each document scores the sum of 1/(k + rank) over the lists it's in, with k = 60. It ignores raw scores because they aren't on comparable scales. BM25 is an unbounded sum that grows with query length, and cosine similarity sits between −1 and 1. k = 60 flattens the top, so a document both retrievers like beats one that only one of them ranks first.

### Bi-encoder vs cross-encoder

Picture a library. The **bi-encoder** (bge-small, our embedder) writes an index card for every book once, ahead of time, and one for your question when you ask. Finding books means comparing cards, which is fast, because the books' cards already exist. But each card was written without knowing your question.

The **cross-encoder** (bge-reranker-base) is a librarian who reads your question and a book side by side, so every word of the question can be checked against every word of the book. That's far more careful, but nothing can be prepared ahead: she has to reread every book for every question. So she only reads the 50 books the index cards found.

The classic recipe is "recall from the cheap model, precision from the expensive one". The cheap first stage casts a wide net, and the expensive second stage sorts the catch. Here the second stage disagreed with NIST's answer key more often than the first stage did, so the recipe didn't pay off on this task. It's a reason to measure rather than assume.

> **Interview version:** A bi-encoder embeds the query and each document separately, so document vectors are precomputed and search is a fast vector comparison, but the two texts never see each other. A cross-encoder runs the query and one document through the model together, so attention spans both texts. It's more accurate in general, but it costs a full model run per pair at query time, so it only reranks the first stage's top candidates. On our data it cost 1.7 seconds per query for 50 pairs and lowered recall@10 by 0.091.

### Latency vs quality, in numbers

Dense retrieval takes 2.6 ms per query (p50) and hybrid 4.3 ms. The reranker adds 1,661 ms on C, and the 95th percentile is 1,841 ms. On this data it also lowered recall@10 by 0.091. Even if it had raised recall by that much, you'd still ask whether the gain is worth almost two seconds per question, and Phase 5's agent may retrieve up to three times per question. We didn't measure it on a GPU, which would likely be much faster.

### What it means when a difference falls inside the CI

Hybrid beat dense by 0.016, with a 95% CI of [−0.003, +0.036]. Picture rerunning the whole study with a different 75 subcategories: the gain would move around, and the interval shows how far. It could plausibly be slightly negative or as high as +0.036. Zero is inside it, so we can't claim hybrid is better.

It does **not** mean they're equal. "Not proven better" isn't "proven the same". With more subcategories, the interval would shrink, and +0.016 might turn out real. For the reranker it's the other way around: the whole interval, [−0.124, −0.061], is below 0, so on this data it really is worse.

> **Interview version:** A paired 95% CI that contains zero means the data can't distinguish the two systems: the observed gain is within what resampling subcategories produces by chance. It's absence of evidence, not evidence of no effect. With 75 dev subcategories, our intervals are a few points wide, so a 1.6-point gain can't be resolved. That's why I pick the simpler system unless the complex one is distinguishably better.

## Decisions

Each of these has a row in `DECISIONS.md`.

- **The ablation plan, the comparisons and the pick rule were committed before the first run.**
- **BM25, not FTS, is the keyword half of hybrid.** It beat FTS-OR in Phase 2.
- **RRF fuses parent rankings, with k = 60, not tuned.**
- **The reranker reads one chunk per control:** 50 pairs per query for every strategy, so their cost and quality compare like for like.
- **Reranker: bge-reranker-base at a pinned revision, on CPU, with raw logits.**
- **Reranker scores and timings are cached and committed.**
- **Row 6 was re-timed** after the overnight run was slowed down (next section).
- **Production is dense search alone, on strategy C,** by the pre-registered rule. Phase 5 brings the reranker back only as a grader.

## Gotchas we hit

1. **The overnight run got throttled.** Partway through row 6, the run slowed down several times over, while rows 4 and 5 had kept a steady pace (the numbers are in `DECISIONS.md`). Most likely macOS slowed background work after the display slept. We deleted row 6's cache entries and re-ran them with `caffeinate -dims` keeping the Mac awake. Every score came out identical, and only the timings changed. Long benchmarks need a machine that stays awake, and a log that shows the rate over time, not just the total.
2. **A pipe hid the progress.** The first run's output went through `grep` to drop warnings, and `grep` holds its output in a buffer when it isn't writing to a screen, so nothing appeared for minutes. `grep --line-buffered` fixed it.
3. **One chunk per control can misjudge a control.** In C, SI-4 System Monitoring was judged by its narrow enhancement SI-4(25).
4. **The sigmoid worry didn't come up.** We used raw logits because float32 rounds the sigmoid of any logit from 17 up to exactly 1.0, but no dev logit went above 7.03. It cost nothing, but it changed nothing here either.
5. **Two dev query texts appear twice** (in different subcategories), so the cache has 1,008 entries, not 3 × 338. The second copy reads the first one's result.

## Interview questions

**1. Walk me through your retrieval pipeline.**
BM25 over Postgres's lexemes and exact dense search with bge-small each return their top 50 distinct controls. Hybrid fuses them with RRF at k = 60, and an optional cross-encoder reorders the 50. I scored six setups on 338 dev queries. Hybrid was best at 0.436 recall@10, but only 0.016 above dense alone, with a CI that includes zero. The reranker lowered recall@10 by 0.091. So production is dense alone: it's the simplest setup that isn't distinguishably worse than the best.

**2. Why RRF instead of adding the scores?**
The scores aren't on the same scale. A BM25 score is an unbounded sum that grows with the query's length, while cosine similarity stays between −1 and 1, so adding them lets one retriever decide. RRF only uses ranks: 1/(60 + rank), summed over the lists. k = 60 makes tenth place worth almost as much as first, so a control both retrievers like beats one that only one of them ranks first.

**3. How does a bi-encoder differ from a cross-encoder?**
A bi-encoder embeds the query and each chunk separately, so chunk vectors are computed once and search is a fast vector comparison. A cross-encoder reads the query and a chunk together, so it can compare every word against every word. It's more accurate in general but needs a full model run per pair at query time: 1.7 seconds for 50 pairs on my laptop's CPU, against 2.6 ms for dense retrieval. So it only reranks the first stage's top 50.

**4. Your reranker made results worse. How do you know it isn't a bug?**
I checked the wiring: my setup gives the same scores as the model run directly through `transformers`, and it ranks AC-2 Account Management far above unrelated controls for an account-management query. The scores repeat exactly: re-running every strategy-B query gave identical scores. Then I looked at what it changed. It lowered the number of gold controls in the top 10 on 137 of 338 queries and raised it on 45, and the drop shows up on recall@10, nDCG@10, MRR and precision@5, for both query types, with every CI below zero.

**5. Why did it lose?**
Two likely reasons. NIST's mapping is broad: ID.IM-02 maps to 40 controls, including the first control of all 20 families, mostly "Policy and Procedures", while the cross-encoder judges whether one passage says what the sentence says. And in strategy C, it judged each control by one chunk, an enhancement 52% of the time. For DE.CM-01, about network monitoring, SI-4 System Monitoring was first after fusion, but the reranker read only SI-4(25), "Optimize Network Traffic Analysis", and SI-4 fell out of the top 5. Some of its picks may be unmapped but reasonable, so the real loss may be smaller than measured, but every setup faces the same key.

**6. Hybrid was your best row. Why ship dense alone?**
Because I can't show hybrid is better. The paired difference is +0.016 recall@10, with a 95% CI of [−0.003, +0.036]. I committed the rule before running anything: take the simplest setup that isn't distinguishably worse than the best. It's the same idea as the one-standard-error rule. BM25 is cheap, and it may matter for questions full of acronyms or control IDs, which this set barely has. If Phase 4's questions show that, I'd revisit it, with a new decision row.

**7. What does the reranker cost?**
On this laptop's CPU, 1,661 ms per query at p50 and 1,841 ms at p95 for 50 pairs on strategy C, and 2,127 ms at p50 on B, whose chunks are longest. Retrieval itself takes 1.6 to 4.4 ms. Long chunks get cut at 512 tokens: 14% of pairs on C, 65% on B.

**8. Which chunking strategy won?**
None, distinguishably. As planned, chunking was compared with the reranker on: B beat A by 0.015, CI [−0.004, +0.035]. C did worst under reranking (0.345), likely in part because the reranker judged C controls by single enhancement chunks. Since production drops the reranker, it stays on C, the strategy Phase 2 measured. Dense alone wasn't run on A or B.

## Follow-ups from the quiz

**Why does RRF merge by position instead of adding the scores?**
Because the scores are on different scales. A BM25 score is a sum over the query's words, so it has no fixed maximum and grows with longer queries, while a cosine similarity always sits between −1 and 1. Adding them is like adding one judge's points out of 1,000 to another's out of 1: the first judge decides everything. RRF uses only places. Each list gives a control 1/(60 + its place), and the two are added. A control both lists put 10th gets 2/70 = 0.029, more than a control only one list put 1st, 1/61 = 0.016, so agreement wins.

**What's the difference between a bi-encoder and a cross-encoder, and why use both?**
A bi-encoder, our embedder, turns the question and each chunk into vectors separately. The chunk vectors are made once, ahead of time, so a search only compares vectors and takes milliseconds. A cross-encoder, the reranker, reads the question and one chunk together. That's more careful, but it needs a full model run for every pair, at question time. So the usual recipe is that the fast model fetches 50 candidates (recall) and the slow one sorts them (precision). Here the slow one cost 1,661 ms per question at p50 for 50 pairs and lowered recall@10 by 0.091, so the recipe has to be measured on your own data, not assumed.

**Hybrid beat dense by 0.016. Why did we ship dense alone?**
Because 0.016 is inside the noise. The paired 95% CI runs from −0.003 to +0.036, so with a different set of 75 subcategories the gain could plausibly be zero or slightly negative. That doesn't prove the two are equal; it means this data can't tell them apart. Before running anything, we committed a rule: pick the simplest setup that isn't distinguishably worse than the best. Dense alone uses one retriever instead of two, so it wins under that rule. The reranker is the opposite case: its whole interval, [−0.124, −0.061], is below zero, so it really is worse on this data.
