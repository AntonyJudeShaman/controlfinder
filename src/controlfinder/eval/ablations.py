"""`make ablations`: hybrid search, reranking and chunking, one change at a time, on dev.

The rows follow AGENTS.md Phase 3 and the plan pre-registered in DECISIONS.md on 2026-10-30:
1 BM25, 2 dense, 3 hybrid RRF and 4 hybrid RRF + reranker, all on strategy C; 5 and 6 run the
best retrieval of rows 1-3 with the reranker on A and on B, and a row 7 runs it on C if it
isn't hybrid. Each row is scored like the Phase 2 baselines, on its top 20 parents, and rows 1
and 2 must reproduce Phase 2's BM25 and dense numbers before any reranking starts. The paired
comparisons and the production pick follow the pre-registered rules. Last, a look at what
reranking did to row 4's candidates. Reranker scores come from data/cache/rerank.jsonl when it
has them. Writes results/ablations_dev.json.
"""

import json
import platform
import statistics
import time
from pathlib import Path

import torch

from controlfinder import docgen
from controlfinder.eval.baselines import PRIMARY, TYPES, by_subcategory, rounded, summarize
from controlfinder.eval.bootstrap import N_RESAMPLES, SEED, paired_cluster_ci
from controlfinder.eval.goldset import Query, load_queries
from controlfinder.eval.metrics import DEPTH, query_metrics
from controlfinder.index.db import connect
from controlfinder.retrieval import dense, fusion
from controlfinder.retrieval.pipeline import CANDIDATES, Retriever, rerank
from controlfinder.retrieval.rerank import BATCH_SIZE, CACHE, MAX_LENGTH, MODEL, REVISION, Reranker

BASELINES = Path("results/baselines_dev.json")
OUT = Path("results/ablations_dev.json")
RERANK_METRICS = ("recall@10", "ndcg@10", "mrr", "precision@5")


def parts(row: dict) -> int:
    """How many parts a row runs: one or two retrievers, plus the reranker."""
    return (2 if row["retrieval"] == "hybrid" else 1) + row["rerank"]


def p50_p95(values: list[float]) -> dict:
    return {"p50": statistics.median(values), "p95": statistics.quantiles(values, n=20, method="inclusive")[-1]}


def run(retriever: Retriever, reranker: Reranker | None, retrieval: str, queries: list[Query],
        vectors: dict[str, str]) -> tuple[dict, dict, dict, dict]:
    """Per-query metrics on the top 20 parents, the row's latency and reranker stats, and per
    query the candidates before reranking and every parent's final order."""
    per_query, candidates, ranked, retrieve_ms, rerank_ms, scores, truncated = {}, {}, {}, [], [], [], 0
    start_row = time.perf_counter()
    for i, q in enumerate(queries, 1):
        start = time.perf_counter()
        hits = candidates[q.id] = retriever.search(retrieval, q.text, vectors[q.id])
        retrieve_ms.append((time.perf_counter() - start) * 1000)
        if reranker:
            hits, scored = rerank(reranker, q.text, hits, retriever.texts)
            rerank_ms.append(scored.ms)
            scores += scored.scores
            truncated += scored.truncated
            if i % 50 == 0:
                print(f"  {i}/{len(queries)} queries, {time.perf_counter() - start_row:.0f}s", flush=True)
        ranked[q.id] = [h.parent_control_id for h in hits]
        per_query[q.id] = query_metrics(ranked[q.id][:DEPTH], set(q.gold))
    info = {
        "retrieval_ms_p50": statistics.median(retrieve_ms),
        "queries_short_of_20_parents": sum(len(parents) < DEPTH for parents in ranked.values()),
        f"gold_among_the_{CANDIDATES}_candidates": statistics.fmean(
            len({h.parent_control_id for h in candidates[q.id]} & set(q.gold)) / len(q.gold) for q in queries),
    }
    if reranker:
        info |= {
            "rerank_ms": p50_p95(rerank_ms),
            "total_ms": p50_p95([a + b for a, b in zip(retrieve_ms, rerank_ms, strict=True)]),
            "pairs_reranked": len(scores),
            "pairs_over_512_tokens": truncated,
            "logit_range": [min(scores), max(scores)],
        }
    return per_query, info, candidates, ranked


def rerank_effect(queries: list[Query], candidates: dict, ranked: dict, enhancement_chunks: set[str]) -> dict:
    """What reranking did to the candidates: queries that gained or lost gold controls in the
    top 10, which way the gold candidates moved, and the queries that lost the most."""
    changes, moves = {}, []
    for q in queries:
        gold, before, after = set(q.gold), [h.parent_control_id for h in candidates[q.id]], ranked[q.id]
        changes[q.id] = len(set(after[:10]) & gold) - len(set(before[:10]) & gold)
        moves += [after.index(g) - before.index(g) for g in gold & set(before)]
    worst = sorted(queries, key=lambda q: (changes[q.id], q.id))[:5]
    return {
        "queries_with_more_gold_in_the_top_10": sum(c > 0 for c in changes.values()),
        "queries_with_less_gold_in_the_top_10": sum(c < 0 for c in changes.values()),
        "queries_unchanged": sum(c == 0 for c in changes.values()),
        "gold_candidates_moved_up": sum(m < 0 for m in moves),
        "gold_candidates_moved_down": sum(m > 0 for m in moves),
        "gold_candidates_unmoved": sum(m == 0 for m in moves),
        "candidates": sum(len(c) for c in candidates.values()),
        "candidates_scored_on_an_enhancement_chunk": sum(h.chunk_id in enhancement_chunks
                                                         for c in candidates.values() for h in c),
        "largest_losses": [{"query": q.id, "text": q.text, "gold": list(q.gold), "gold_in_top_10_change": changes[q.id],
                            "before_top5": [h.parent_control_id for h in candidates[q.id][:5]],
                            "before_top5_chunks": [h.chunk_id for h in candidates[q.id][:5]],
                            "after_top5": ranked[q.id][:5]} for q in worst],
    }


def compare(per_query: dict, queries: list[Query], a: int, b: int, metric: str) -> dict:
    """Row a minus row b on `metric`, per query type, by paired cluster bootstrap."""
    return {t: paired_cluster_ci(by_subcategory(per_query[a], queries, t, metric),
                                 by_subcategory(per_query[b], queries, t, metric)) for t in TYPES}


def main() -> None:
    queries = load_queries("dev")
    phase2 = json.loads(BASELINES.read_text())["systems"]
    reranker = Reranker()
    with connect(autocommit=True) as conn:
        vectors = dict(zip([q.id for q in queries], dense.embed_queries(dense.load_model(), [q.text for q in queries]),
                           strict=True))
        retrievers, rows, per_query, lists = {}, [], {}, {}

        def add(number: int, retrieval: str, strategy: str, with_rerank: bool) -> None:
            print(f"row {number}: {retrieval}, {strategy}, rerank={with_rerank}", flush=True)
            if strategy not in retrievers:
                retrievers[strategy] = Retriever(conn, strategy)
            per_query[number], info, *lists[number] = run(retrievers[strategy], reranker if with_rerank else None,
                                                          retrieval, queries, vectors)
            rows.append({"row": number, "retrieval": retrieval, "strategy": strategy, "rerank": with_rerank,
                         "metrics": summarize(per_query[number], queries), **info})

        def recall10(row: dict) -> float:
            return row["metrics"]["all"][PRIMARY]["mean"]

        add(1, "bm25", "C_separate", False)
        add(2, "dense", "C_separate", False)
        for row, name in zip(rows, ("bm25", "dense"), strict=True):
            got, want = rounded(recall10(row)), phase2[name]["metrics"]["all"][PRIMARY]["mean"]
            if got != want:
                raise RuntimeError(f"row {row['row']} gives {PRIMARY} {got}, but Phase 2's {name} gave {want}")
        add(3, "hybrid", "C_separate", False)
        add(4, "hybrid", "C_separate", True)
        best_retrieval = max(rows[:3], key=recall10)["retrieval"]
        add(5, best_retrieval, "A_control_only", True)
        add(6, best_retrieval, "B_control_plus_enh", True)
        if best_retrieval != "hybrid":
            add(7, best_retrieval, "C_separate", True)
        depths = {s: r.depth for s, r in retrievers.items()}
        enhancement_chunks = {chunk_id for (chunk_id,) in conn.execute(
            "SELECT chunk_id FROM chunks WHERE control_id <> parent_control_id")}

    by_number = {r["row"]: r for r in rows}
    single = max(by_number[1], by_number[2], key=recall10)
    chunking = sorted((r for r in rows if r["retrieval"] == best_retrieval and r["rerank"]), key=recall10, reverse=True)
    comparisons = [
        ("hybrid vs best single retriever", 3, single["row"], (PRIMARY,)),
        ("reranker vs no reranker", 4, 3, RERANK_METRICS),
        ("best chunking vs runner-up", chunking[0]["row"], chunking[1]["row"], (PRIMARY,)),
    ]
    best = max(rows, key=recall10)
    versus_best = [{"row": r["row"], "parts": parts(r), "difference": compare(per_query, queries, r["row"],
                                                                              best["row"], PRIMARY)["all"]}
                   for r in rows]
    within_noise = [v for v in versus_best if v["difference"]["ci95"][0] <= 0 <= v["difference"]["ci95"][1]]
    pick = min(within_noise, key=lambda v: (v["parts"], -recall10(by_number[v["row"]])))

    OUT.write_text(json.dumps(rounded({
        "what": "Phase 3 ablations on the dev split: hybrid search, reranking and chunking, scored on parent controls",
        "split": "dev",
        "queries": {t: sum(t in ("all", q.type) for q in queries) for t in TYPES},
        "subcategories": len({q.subcategory for q in queries}),
        "parents_scored": DEPTH,
        "candidates": CANDIDATES,
        "fetch_depth": depths,
        "fusion": {"method": "RRF over each retriever's top parents", "k": fusion.K},
        "reranker": {
            "model": MODEL, "revision": REVISION, "max_length": MAX_LENGTH, "batch_size": BATCH_SIZE,
            "scores": "raw logits", "device": "cpu", "torch_threads": torch.get_num_threads(),
            "platform": platform.platform(), "cache": str(CACHE),
        },
        "bootstrap": {"unit": "subcategory", "resamples": N_RESAMPLES, "seed": SEED, "interval": "95% percentile"},
        "latency_note": "per query. retrieval: BM25 + dense + fusion, timed live, excluding query embedding."
                        " rerank: model time for the query's pairs on the run that filled the cache",
        "primary_metric": PRIMARY,
        "rows": rows,
        "comparisons": [{"name": name, "a": a, "b": b, "metrics": {m: compare(per_query, queries, a, b, m)
                                                                    for m in metrics}}
                        for name, a, b, metrics in comparisons],
        "rerank_effect_row_4": rerank_effect(queries, *lists[4], enhancement_chunks),
        "production": {
            "rule": "the simplest row (fewest parts) whose paired 95% CI of recall@10 minus the best row's includes 0;"
                    " among equally simple rows, the higher recall@10",
            "best_row": best["row"],
            "versus_best": versus_best,
            "pick": pick["row"],
        },
    }), indent=2) + "\n")
    print(docgen.ablation_rows())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
