"""`make final-test`: the one run on the sealed test split, in Phase 6.

Everything here was fixed in DECISIONS.md on 2026-11-02, before the split was unsealed.
Retrieval: Phase 2's four baselines and Phase 3's six rows, read from the dev results and run
the same way, with dev's comparison pairs and production (row 2) against every other row, so
nothing is chosen on test. Generation: the plain pipeline and the pipeline with base text
answer the 50 test questions and code grades them (definitions 2 to 5 and 8). The agent and
the faithfulness judge stay dev-only, to save model calls. It refuses to start once
results/final_test.json exists, because the test split is run once; a re-run needs a
DECISIONS.md row and the old file moved away by hand. No metric is printed until the end.
"""

import json
import statistics
from pathlib import Path

from controlfinder.eval.ablations import OUT as ABLATIONS_DEV
from controlfinder.eval.ablations import compare, p50_p95, run
from controlfinder.eval.agent import decision_moves
from controlfinder.eval.baselines import (COMPARISONS, PRIMARY, STRATEGY, TYPES, by_subcategory, evaluate, rounded,
                                          summarize, systems)
from controlfinder.eval.bootstrap import N_RESAMPLES, SEED, paired_cluster_ci, paired_resample_ci
from controlfinder.eval.generation import GENERATOR_MODEL, STATISTICS, answer_and_grade, retrieve
from controlfinder.eval.generation import summarize as summarize_answers
from controlfinder.eval.goldset import Query, load_queries
from controlfinder.eval.metrics import DEPTH, KS, recall_ceiling
from controlfinder.eval.qa import Question, load_questions
from controlfinder.generation.llm import LLM
from controlfinder.index.db import connect
from controlfinder.retrieval import fetch_depth
from controlfinder.retrieval.bm25 import BM25Index
from controlfinder.retrieval.dense import embed_queries, load_model
from controlfinder.retrieval.pipeline import Retriever
from controlfinder.retrieval.production import K, Production
from controlfinder.retrieval.rerank import Reranker

OUT = Path("results/final_test.json")
SYSTEMS = ("pipeline", "pipeline_base_text")
COMPARED = ("abstention_f1", "answer_rate", "answer_accuracy")
BOOTSTRAP = {"resamples": N_RESAMPLES, "seed": SEED, "interval": "95% percentile"}


def test_retrieval(queries: list[Query]) -> dict:
    """The baselines and ablation rows on the test queries, with dev's comparisons."""
    dev = json.loads(ABLATIONS_DEV.read_text())
    reranker = Reranker()
    with connect(autocommit=True) as conn:
        vectors = dict(zip([q.id for q in queries], embed_queries(load_model(), [q.text for q in queries]),
                           strict=True))
        depth = fetch_depth(conn, STRATEGY, DEPTH)
        baselines, baseline_per_query = {}, {}
        for name, search in systems(conn, vectors, BM25Index(conn, STRATEGY), depth).items():
            print(f"baseline {name}", flush=True)
            baseline_per_query[name], _, info = evaluate(search, queries)
            baselines[name] = {**info, "metrics": summarize(baseline_per_query[name], queries)}
        retrievers, rows, per_query = {}, [], {}
        for d in dev["rows"]:
            print(f"row {d['row']}: {d['retrieval']}, {d['strategy']}, rerank={d['rerank']}", flush=True)
            retriever = retrievers.setdefault(d["strategy"], Retriever(conn, d["strategy"]))
            per_query[d["row"]], info, _, _ = run(retriever, reranker if d["rerank"] else None, d["retrieval"],
                                                   queries, vectors)
            rows.append({"row": d["row"], "retrieval": d["retrieval"], "strategy": d["strategy"], "rerank": d["rerank"],
                         "metrics": summarize(per_query[d["row"]], queries), **info})
    for row, name in zip(rows[:2], ("bm25", "dense"), strict=True):
        got, want = (rounded(r["metrics"]["all"][PRIMARY]["mean"]) for r in (row, baselines[name]))
        if got != want:
            raise RuntimeError(f"row {row['row']} gives {PRIMARY} {got} on test, but the {name} baseline gave {want}")
    production = dev["production"]["pick"]
    return {
        "queries": {t: sum(t in ("all", q.type) for q in queries) for t in TYPES},
        "subcategories": len({q.subcategory for q in queries}),
        "strategy": STRATEGY,
        "fetch_depth": depth,
        "parents_scored": DEPTH,
        "bootstrap": {"unit": "subcategory"} | BOOTSTRAP,
        "ceilings": {t: {f"recall@{k}": statistics.fmean(recall_ceiling(set(q.gold), k)
                                                         for q in queries if t in ("all", q.type))
                         for k in KS} for t in TYPES},
        "primary_metric": PRIMARY,
        "baselines": baselines,
        "baseline_comparisons": [
            {"a": a, "b": b, **{t: paired_cluster_ci(by_subcategory(baseline_per_query[a], queries, t, PRIMARY),
                                                     by_subcategory(baseline_per_query[b], queries, t, PRIMARY))
                                for t in TYPES}}
            for a, b in COMPARISONS
        ],
        "rows": rows,
        "comparisons": [{"name": c["name"], "a": c["a"], "b": c["b"],
                         "metrics": {m: compare(per_query, queries, c["a"], c["b"], m) for m in c["metrics"]}}
                        for c in dev["comparisons"]],
        "production": {"row": production, "chosen_on": "dev",
                       "versus_rows": [{"row": r["row"], "difference": compare(per_query, queries, production,
                                                                               r["row"], PRIMARY)}
                                       for r in rows if r["row"] != production]},
    }


def test_generation(questions: list[Question]) -> dict:
    """The plain pipeline and the pipeline with base text on the test questions, graded by code."""
    generator = LLM(GENERATOR_MODEL)
    contexts = retrieve(questions)
    rows = {s: [] for s in SYSTEMS}
    with connect(autocommit=True) as conn:
        production = Production(conn)
        for n, q in enumerate(questions, 1):
            context = contexts[q.id]
            for system, chunks in (("pipeline", context.chunks),
                                   ("pipeline_base_text", production.with_base_text(context.chunks))):
                rows[system].append(answer_and_grade(q, chunks, generator, None) | {"retrieval_ms": context.ms})
            print(f"question {n}/{len(questions)}", flush=True)
    return {
        "questions": {"all": len(questions), "answerable": sum(q.answerable for q in questions),
                      "unanswerable": sum(not q.answerable for q in questions)},
        "retrieval": {"retrieval": "dense", "strategy": STRATEGY, "search": "exact", "parents_in_context": K},
        "generator": GENERATOR_MODEL,
        "reported_models": sorted({r["generator_model"] for s in SYSTEMS for r in rows[s]}),
        "not_run": {"agent": "dev-only (DECISIONS.md, 2026-11-02): on dev it gave the pipeline's answers word for word",
                    "faithfulness": "dev-only (DECISIONS.md, 2026-11-02): the judge gave every dev answer a 5"},
        "bootstrap": {"unit": "question"} | BOOTSTRAP,
        "systems": {s: summarize_answers(rows[s]) | {
            "llm_calls_per_question": 1,
            "latency_ms": p50_p95([r["retrieval_ms"] + r["generate_ms"] for r in rows[s]])} for s in SYSTEMS},
        "versus_pipeline": {"pipeline_base_text": {m: paired_resample_ci(rows["pipeline_base_text"], rows["pipeline"],
                                                                         STATISTICS[m]) for m in COMPARED}},
        "decision_moves_from_pipeline": {"pipeline_base_text": decision_moves(rows["pipeline_base_text"],
                                                                              rows["pipeline"])},
        "per_question": rows,
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists: the test split has had its one run. A re-run needs a DECISIONS.md row first")
    out = {
        "what": "The one run on the sealed test split, as pre-registered in DECISIONS.md on 2026-11-02",
        "split": "test",
        "retrieval": test_retrieval(load_queries("test")),
        "generation": test_generation(load_questions("test")),
    }
    OUT.write_text(json.dumps(rounded(out), indent=2) + "\n")
    retrieval, generation = out["retrieval"], out["generation"]
    print(json.dumps(rounded({
        PRIMARY: {f"row {r['row']}": r["metrics"]["all"][PRIMARY] for r in retrieval["rows"]},
        **{s: {m: generation["systems"][s]["metrics"][m]["value"] for m in COMPARED} for s in SYSTEMS},
    }), indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
