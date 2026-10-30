"""`make baselines`: FTS (AND and OR), BM25 and dense search on the dev queries, strategy C.

Every system fetches enough chunks to fill 20 distinct parent controls (`fetch_depth`), rolls
them up to parents (first occurrence wins) and is scored on the top 20 parents. Metrics are
averaged per query type (subcat, example) and over all queries, with 95% cluster-bootstrap CIs,
and pairs of systems are compared with a paired cluster bootstrap. Dense search here is exact.
The same queries then run through the HNSW index under several settings, compared with exact
search. Also saved: the queries where dense and BM25 disagree completely, and the lexemes that
rank_bm25's IDF floor overweights. Writes results/baselines_dev.json.
"""

import json
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from controlfinder import docgen
from controlfinder.eval.bootstrap import N_RESAMPLES, SEED, cluster_ci, paired_cluster_ci
from controlfinder.eval.goldset import Query, load_queries
from controlfinder.eval.metrics import DEPTH, KS, dedup_parents, query_metrics, recall_ceiling
from controlfinder.index.db import connect
from controlfinder.retrieval import Hit, fetch_depth, fts
from controlfinder.retrieval.bm25 import BM25Index, lexemes
from controlfinder.retrieval.dense import EXACT, embed_queries, load_model, plan, search

STRATEGY = "C_separate"
TYPES = ("subcat", "example", "all")
PRIMARY = "recall@10"
COMPARISONS = [("fts_or", "fts_and"), ("bm25", "fts_or"), ("dense", "bm25")]  # each reported as a - b
OUT = Path("results/baselines_dev.json")


def by_subcategory(per_query: dict[str, dict], queries: list[Query], qtype: str, metric: str) -> dict[str, list]:
    grouped = defaultdict(list)
    for q in queries:
        if qtype in ("all", q.type):
            grouped[q.subcategory].append(per_query[q.id][metric])
    return grouped


def summarize(per_query: dict[str, dict], queries: list[Query]) -> dict:
    metrics = next(iter(per_query.values()))
    return {t: {m: cluster_ci(by_subcategory(per_query, queries, t, m)) for m in metrics} for t in TYPES}


def evaluate(retrieve: Callable[[Query], list[Hit]], queries: list[Query]) -> tuple[dict, dict, dict]:
    """Per-query metrics and top 20 parents, plus p50 latency and how many queries got fewer than 20."""
    per_query, ranked, latencies = {}, {}, []
    for q in queries:
        start = time.perf_counter()
        hits = retrieve(q)
        latencies.append((time.perf_counter() - start) * 1000)
        ranked[q.id] = dedup_parents(h.parent_control_id for h in hits)[:DEPTH]
        per_query[q.id] = query_metrics(ranked[q.id], set(q.gold))
    short = sum(len(parents) < DEPTH for parents in ranked.values())
    return per_query, ranked, {"latency_ms_p50": statistics.median(latencies), "queries_short_of_20_parents": short}


def disagreements(conn, queries: list[Query], ranked: dict[str, dict], index: BM25Index) -> list[dict]:
    """Queries where dense or BM25 has every gold control in its top 10 and the other has none,
    with the query lexemes found in the gold chunk BM25 scored highest."""
    out = []
    for q in queries:
        gold = set(q.gold)
        found = {name: len(set(ranked[name][q.id][:10]) & gold) for name in ("dense", "bm25")}
        if sorted(found.values()) != [0, len(gold)]:
            continue
        query_lexemes = lexemes(conn, q.text)
        scores = index.bm25.get_scores(query_lexemes)
        best = max((i for i, chunk_id in enumerate(index.chunk_ids) if index.parents[chunk_id] in gold),
                   key=lambda i: scores[i])
        counts = index.bm25.doc_freqs[best]
        out.append({
            "query": q.id, "text": q.text, "gold": list(q.gold), "found_by": max(found, key=found.get),
            **{f"{name}_top5": ranked[name][q.id][:5] for name in ("dense", "bm25")},
            "bm25_best_gold_chunk": index.chunk_ids[best],
            "query_lexemes_in_it": {w: counts[w] for w in dict.fromkeys(query_lexemes) if w in counts},
        })
    return out


def hnsw_vs_exact(conn, queries: list[Query], vectors: dict[str, str], depth: int, exact: dict) -> dict:
    """Each HNSW setup's rows returned, overlap with the exact top 10, and recall@10/@20 change."""
    setups = {
        "hnsw, ef_search=40 (default)": {"enable_seqscan": "off"},
        f"hnsw, ef_search={depth}": {"enable_seqscan": "off", "hnsw.ef_search": str(depth)},
        "hnsw, ef_search=1000": {"enable_seqscan": "off", "hnsw.ef_search": "1000"},
        "hnsw, ef_search=40, iterative_scan=strict_order": {"enable_seqscan": "off", "hnsw.iterative_scan": "strict_order"},
        "hnsw, ef_search=40, iterative_scan=relaxed_order": {"enable_seqscan": "off", "hnsw.iterative_scan": "relaxed_order"},
    }
    exact_top10 = {q.id: {h.chunk_id for h in search(conn, vectors[q.id], STRATEGY, 10, EXACT)} for q in queries}
    probe = vectors[queries[0].id]
    out = {"default_plan": plan(conn, probe, STRATEGY, depth, {}), "setups": []}
    for label, settings in {"exact (index scans off)": EXACT, **setups}.items():
        rows, overlap = [], []

        def retrieve(q: Query, settings=settings) -> list[Hit]:
            # relaxed_order may return rows slightly out of order; re-sorting by score fixes that.
            hits = sorted(search(conn, vectors[q.id], STRATEGY, depth, settings), key=lambda h: -h.score)
            rows.append(len(hits))
            overlap.append(len({h.chunk_id for h in hits[:10]} & exact_top10[q.id]) / 10)
            return hits

        per_query, _, info = evaluate(retrieve, queries)
        out["setups"].append({
            "setup": label,
            "plan": plan(conn, probe, STRATEGY, depth, settings),
            "rows_returned": {"min": min(rows), "median": statistics.median(rows), "max": max(rows)},
            "chunk_recall@10_vs_exact": statistics.fmean(overlap),
            **{f"{m}_minus_exact": paired_cluster_ci(by_subcategory(per_query, queries, "all", m),
                                                     by_subcategory(exact, queries, "all", m))
               for m in ("recall@10", "recall@20")},
            **info,
        })
    return out


def bm25_idf_floor(index: BM25Index) -> dict:
    """rank_bm25 swaps a negative IDF (lexeme in over half the chunks) for epsilon x the mean IDF."""
    bm = index.bm25
    df = Counter(lexeme for doc in bm.doc_freqs for lexeme in doc)
    floor = bm.epsilon * bm.average_idf
    by_df = sorted(df, key=lambda lexeme: (-df[lexeme], lexeme))
    return {
        "k1": bm.k1, "b": bm.b, "epsilon": bm.epsilon, "chunks": bm.corpus_size,
        "mean_chunk_lexemes": bm.avgdl, "mean_idf": bm.average_idf, "floored_idf": floor,
        "floored_lexemes": {lexeme: df[lexeme] for lexeme in by_df if df[lexeme] > bm.corpus_size / 2},
        "rarer_lexemes_with_a_lower_idf": {lexeme: {"chunks": df[lexeme], "idf": bm.idf[lexeme]} for lexeme in by_df
                                           if df[lexeme] <= bm.corpus_size / 2 and bm.idf[lexeme] < floor},
    }


def rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def main() -> None:
    queries = load_queries("dev")
    model = load_model()
    with connect(autocommit=True) as conn:
        (missing,) = conn.execute("SELECT count(*) FROM chunks WHERE embedding IS NULL").fetchone()
        if missing:
            raise RuntimeError(f"{missing} chunks have no embedding: run `make embed`")
        depth = fetch_depth(conn, STRATEGY, DEPTH)
        vectors = dict(zip([q.id for q in queries], embed_queries(model, [q.text for q in queries]), strict=True))
        bm25 = BM25Index(conn, STRATEGY)
        systems = {
            "fts_and": lambda q: fts.search(conn, q.text, STRATEGY, "and", depth),
            "fts_or": lambda q: fts.search(conn, q.text, STRATEGY, "or", depth),
            "bm25": lambda q: bm25.search(conn, q.text, depth),
            "dense": lambda q: search(conn, vectors[q.id], STRATEGY, depth, EXACT),
        }
        per_query, ranked, results = {}, {}, {}
        for name, retrieve in systems.items():
            per_query[name], ranked[name], info = evaluate(retrieve, queries)
            results[name] = {**info, "metrics": summarize(per_query[name], queries)}
        examples = disagreements(conn, queries, ranked, bm25)
        hnsw = hnsw_vs_exact(conn, queries, vectors, depth, per_query["dense"])

    OUT.write_text(json.dumps(rounded({
        "what": "Phase 2 baselines on the dev split, strategy C, scored on parent controls",
        "split": "dev",
        "strategy": STRATEGY,
        "queries": {t: sum(t in ("all", q.type) for q in queries) for t in TYPES},
        "subcategories": len({q.subcategory for q in queries}),
        "fetch_depth": depth,
        "parents_scored": DEPTH,
        "bootstrap": {"unit": "subcategory", "resamples": N_RESAMPLES, "seed": SEED, "interval": "95% percentile"},
        "latency_note": "p50 per query, retrieval only: dense excludes embedding the query, BM25 excludes building the index",
        "ceilings": {t: {f"recall@{k}": statistics.fmean(recall_ceiling(set(q.gold), k)
                                                         for q in queries if t in ("all", q.type))
                         for k in KS} for t in TYPES},
        "systems": results,
        "primary_metric": PRIMARY,
        "comparisons": [
            {"a": a, "b": b, **{t: paired_cluster_ci(by_subcategory(per_query[a], queries, t, PRIMARY),
                                                     by_subcategory(per_query[b], queries, t, PRIMARY)) for t in TYPES}}
            for a, b in COMPARISONS
        ],
        "dense_vs_bm25_disagreements": examples,
        "hnsw": hnsw,
        "bm25_idf_floor": bm25_idf_floor(bm25),
    }), indent=2) + "\n")
    print(docgen.baseline_recall())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
