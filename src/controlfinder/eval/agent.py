"""`make agent-eval`: sweep the agent's threshold τ on dev, pick it, and compare three systems.

All three answer the same dev questions with the same retrieval, generator, prompt and judge:

- `pipeline`: Phase 4's plain pipeline, retrieve then generate. Its calls replay from the cache.
- `pipeline_base_text`: the same, with each enhancement's base control text put in front of it.
  Jude asked for this row after Phase 4 found that most wrong refusals had only a narrow
  enhancement in the context; it shows whether a small retrieval fix does what the agent does.
- `agent`: the LangGraph agent at the chosen τ.

The sweep runs the agent at every τ on the grid. The chosen τ has the highest dev abstention
F1, ties going to the lowest τ (pre-registered definition 9). Every model call is cached, so
each τ reuses the calls the others made and only new prompts cost anything. The systems are
compared with paired bootstrap intervals over questions, and the agent and the pipeline also
pairwise, in both orders (definition 7). The chosen τ's runs are written to query_log.
Writes results/threshold_sweep.json, results/threshold_sweep.png and results/agent_dev.json.
"""

import json
import math
import time
from collections import Counter
from functools import cache
from importlib.metadata import version
from pathlib import Path

from matplotlib.figure import Figure
from psycopg import Connection
from psycopg.types.json import Jsonb

from controlfinder.agent import prompts as agent_prompts
from controlfinder.agent.graph import LLM_NODES, MAX_GENERATIONS, MAX_REWRITES, Agent, Tools
from controlfinder.eval.ablations import p50_p95
from controlfinder.eval.baselines import rounded
from controlfinder.eval.bootstrap import N_RESAMPLES, SEED, paired_resample_ci, resample_ci
from controlfinder.eval.generation import (
    GENERATOR_MODEL,
    JUDGE_MODEL,
    STATISTICS,
    abstention_f1,
    answer_and_grade,
    average,
    counts,
    gold_coverage,
    grade_citations,
    judge_answer,
    sha256,
)
from controlfinder.eval.qa import Question, load_questions
from controlfinder.generation import judge, prompt
from controlfinder.generation.llm import LLM, PROVIDER
from controlfinder.index.db import connect
from controlfinder.ingest.ids import parent_control_id
from controlfinder.retrieval import rerank
from controlfinder.retrieval.production import K, STRATEGY, Production

SMALL_MODEL = "claude-haiku-5-5"
GRID = [None, *(n / 4 for n in range(-40, 41))]  # None turns the gate off; then -10 to 10 in steps of 0.25
TAU_RULE = "the highest dev abstention F1; ties go to the lowest τ, with no gate lowest of all"
SWEPT = ("answer_rate", "abstention_precision", "abstention_recall", "abstention_f1", "answer_accuracy")
SYSTEMS = ("pipeline", "pipeline_base_text", "agent")  # simplest first
COMPARED = ("abstention_f1", "answer_rate", "answer_accuracy", "faithfulness")
REASONS = ("out_of_scope", "weak_evidence", "generator_refused", "citations_failed")
LOGGED_AS = "agent/eval-dev"
OUT = Path("results/agent_dev.json")
SWEEP = Path("results/threshold_sweep.json")
PLOT = Path("results/threshold_sweep.png")
VERDICTS = ({"1": "agent", "2": "pipeline", "TIE": "tie"}, {"1": "pipeline", "2": "agent", "TIE": "tie"})


def agent_row(q: Question, state: dict) -> dict:
    """One agent run as a results row, scored by the same definitions as the pipeline's rows."""
    context = [c.control_id for c in state.get("retrieved", [])]
    trace = state["trace"]
    row = {"id": q.id, "question": q.question, "category": q.category, "answerable": q.answerable,
           "gold": list(q.gold), "decision": state["decision"], "reason": state.get("reason"),
           "answer": state.get("answer"), "queries_tried": state["queries_tried"], "rewrites": state["attempts"],
           "generations": state["generations"], "top_score": state.get("top_score"), "context": context,
           "gold_in_context": sorted({parent_control_id(c) for c in context} & set(q.gold)),
           "llm_calls": sum(s["node"] in LLM_NODES for s in trace), "latency_ms": sum(s["ms"] for s in trace),
           "trace": trace}
    if q.answerable:
        row["gold_coverage"] = gold_coverage(row)
    if row["decision"] == "answer":
        row |= grade_citations(q, row["answer"], context)
    return row


def sweep(questions: list[Question], tools: Tools) -> tuple[list[dict], dict]:
    """The agent at every τ on the grid: one point of dev metrics per τ, and each τ's rows."""
    points, runs = [], {}
    for tau in GRID:
        agent, rows, start = Agent(tools, tau), [], time.perf_counter()
        for q in questions:
            asked = time.perf_counter()
            rows.append(agent_row(q, agent.run(q.question)))
            if time.perf_counter() - asked > 1:  # only runs that made a new model call take this long
                print(f"  tau {tau} {q.id} {rows[-1]['decision']} after {rows[-1]['rewrites']} rewrites", flush=True)
        runs[tau] = rows
        rewritten = [r for r in rows if r["rewrites"]]
        points.append({"tau": tau, **{name: STATISTICS[name](rows) for name in SWEPT},
                       "llm_calls_mean": average([r["llm_calls"] for r in rows]),
                       "rewrites_mean": average([r["rewrites"] for r in rows]),
                       "rewritten": len(rewritten),
                       "answered_after_rewrite": sum(r["decision"] == "answer" for r in rewritten),
                       "correct_after_rewrite": sum(r.get("correct", False) for r in rewritten)})
        print(f"tau {tau}: abstention F1 {points[-1]['abstention_f1']}, answer rate {points[-1]['answer_rate']}"
              f" ({time.perf_counter() - start:.0f} s)", flush=True)
    return points, runs


def pick_tau(points: list[dict]) -> dict:
    """Definition 9's rule. `points` run from no gate up, so the first best point has the lowest τ."""
    best = max(p["abstention_f1"] for p in points if p["abstention_f1"] is not None)
    return next(p for p in points if p["abstention_f1"] == best)


def pairwise(q: Question, agent_answer: str, pipeline_answer: str, agent_chunks: list[tuple[str, str]],
             pipeline_chunks: list[tuple[str, str]], grader: LLM) -> dict:
    """Definition 7: the agent's answer against the pipeline's, judged in both orders.

    A win counts only when both orders pick the same answer. Identical answers are a tie without
    a judge call. The judge sees the pipeline's controls, then any others the agent's answer had.
    """
    if agent_answer.strip() == pipeline_answer.strip():
        return {"id": q.id, "result": "tie", "identical": True}
    shown = {c for c, _ in pipeline_chunks}
    controls = [*pipeline_chunks, *[(c, text) for c, text in agent_chunks if c not in shown]]
    replies = [grader(judge.pairwise_prompt(q.question, controls, agent_answer, pipeline_answer)),
               grader(judge.pairwise_prompt(q.question, controls, pipeline_answer, agent_answer))]
    picks = [verdicts.get(judge.winner(reply.text)) for verdicts, reply in zip(VERDICTS, replies, strict=True)]
    result = picks[0] if picks[0] == picks[1] and picks[0] in ("agent", "pipeline") else "tie"
    return {"id": q.id, "result": result, "identical": False, "picks": picks,
            "judge_outputs": [reply.text for reply in replies]}


def pairwise_summary(results: list[dict]) -> dict:
    judged = [r for r in results if not r["identical"]]
    return {"both_answered": len(results), "identical_answers": len(results) - len(judged),
            "agent_wins": sum(r["result"] == "agent" for r in results),
            "pipeline_wins": sum(r["result"] == "pipeline" for r in results),
            "ties": sum(r["result"] == "tie" for r in results),
            "orders_disagreed": sum(r["picks"][0] != r["picks"][1] for r in judged),
            "unparsed_verdicts": sum(pick is None for r in judged for pick in r["picks"])}


def summary(rows: list[dict], llm_calls: list[int], latency_ms: list[float]) -> dict:
    return {"abstention_counts": counts(rows),
            "metrics": {name: resample_ci(rows, statistic) for name, statistic in STATISTICS.items()},
            "llm_calls_per_question": {"mean": average(llm_calls), "max": max(llm_calls)},
            "latency_ms": p50_p95(latency_ms)}


def production_pick(rows: dict[str, list[dict]]) -> dict:
    """The simplest system whose abstention F1 isn't distinguishably below the best one's: the
    paired 95% interval of its gap to the best reaches 0 (DECISIONS.md)."""
    f1 = {s: abstention_f1(rows[s]) for s in SYSTEMS}
    best = max(SYSTEMS, key=lambda s: -math.inf if f1[s] is None else f1[s])
    for system in SYSTEMS:
        gap = paired_resample_ci(rows[system], rows[best], abstention_f1)
        if system == best or (gap["ci95"] is not None and gap["ci95"][1] >= 0):
            return {"pick": system, "best": best, "abstention_f1": f1, "gap_to_best": gap}


def agent_paths(rows: list[dict]) -> dict:
    answered = [r for r in rows if r["decision"] == "answer"]
    return {"abstained_because": {reason: sum(r["reason"] == reason for r in rows) for reason in REASONS},
            "answered_after_rewrites": {str(n): sum(r["rewrites"] == n for r in answered)
                                        for n in range(MAX_REWRITES + 1)},
            "questions_rewritten": sum(r["rewrites"] > 0 for r in rows),
            "citation_retries": sum(r["generations"] > 1 for r in rows)}


def decision_moves(rows: list[dict], baseline: list[dict]) -> dict:
    """How each question's decision changed from `baseline` to `rows`, for each kind of question."""
    moves = Counter((r["answerable"], b["decision"], r["decision"]) for r, b in zip(rows, baseline, strict=True))
    return {kind: {f"{before}_to_{after}": moves[(answerable, before, after)]
                   for before in ("answer", "abstain") for after in ("answer", "abstain")}
            for kind, answerable in (("answerable", True), ("unanswerable", False))}


def reported(rows: list[dict], nodes: tuple[str, ...]) -> set[str]:
    return {s["model"] for r in rows for s in r["trace"] if s["node"] in nodes}


def log_runs(conn: Connection, rows: list[dict], tau: float | None) -> None:
    """The chosen τ's dev runs into query_log, replacing the previous eval's rows."""
    with conn.transaction():
        conn.execute("DELETE FROM query_log WHERE pipeline = %s", (LOGGED_AS,))
        for r in rows:
            stages = Counter()
            for s in r["trace"]:
                stages[s["node"]] += s["ms"]
            conn.execute(
                "INSERT INTO query_log (query, pipeline, retrieved, scores, latency_ms, decision, trace)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (r["question"], LOGGED_AS, Jsonb(r["context"]), Jsonb({"top_score": r["top_score"], "tau": tau}),
                 Jsonb(dict(stages) | {"total": r["latency_ms"]}), r["decision"], Jsonb(r["trace"])))


def plot(points: list[dict], chosen: dict, questions: int) -> None:
    numeric = [p for p in points if p["tau"] is not None]
    fig = Figure(figsize=(9, 5))
    ax = fig.subplots()
    for name in SWEPT:
        ax.plot([p["tau"] for p in numeric], [math.nan if p[name] is None else p[name] for p in numeric], label=name)
    title = "The agent's evidence threshold τ, swept on dev"
    if chosen["tau"] is None:
        title += " (chosen: no gate)"
    else:
        ax.axvline(chosen["tau"], color="black", linestyle="--", label=f"chosen τ = {chosen['tau']}")
    ax.set(xlabel="τ: the reranker score the best retrieved chunk must reach",
           ylabel=f"value on the {questions} dev questions", title=title, ylim=(0, 1.05))
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left")
    fig.savefig(PLOT, dpi=150, bbox_inches="tight")


def main() -> None:
    questions = load_questions("dev")
    small, generator, grader = LLM(SMALL_MODEL), LLM(GENERATOR_MODEL), LLM(JUDGE_MODEL)
    with connect(autocommit=True) as conn:
        production = Production(conn)
        retrieve = cache(production)
        tools = Tools(retrieve, rerank.Reranker().score, small, generator)
        points, runs = sweep(questions, tools)
        chosen = pick_tau(points)

        rows = {"pipeline": [], "pipeline_base_text": [], "agent": runs[chosen["tau"]]}
        for n, (q, r) in enumerate(zip(questions, rows["agent"], strict=True), 1):
            if r["decision"] == "answer":
                r |= judge_answer(q, retrieve(r["queries_tried"][-1]).chunks, r["answer"], grader)
            context = retrieve(q.question)
            for system, chunks in (("pipeline", context.chunks),
                                   ("pipeline_base_text", production.with_base_text(context.chunks))):
                rows[system].append(answer_and_grade(q, chunks, generator, grader) | {"retrieval_ms": context.ms})
            print(f"{n}/{len(questions)} {q.id}: " + ", ".join(f"{s} {rows[s][n - 1]['decision']}" for s in SYSTEMS),
                  flush=True)
        pairs = [pairwise(q, a["answer"], p["answer"], retrieve(a["queries_tried"][-1]).chunks,
                          retrieve(q.question).chunks, grader)
                 for q, a, p in zip(questions, rows["agent"], rows["pipeline"], strict=True)
                 if a["decision"] == p["decision"] == "answer"]
        log_runs(conn, rows["agent"], chosen["tau"])
        graph = Agent(tools, chosen["tau"]).graph.get_graph().draw_mermaid()

    plain = {s: ([1] * len(rows[s]), [r["retrieval_ms"] + r["generate_ms"] for r in rows[s]]) for s in SYSTEMS[:2]}
    costs = plain | {"agent": ([r["llm_calls"] for r in rows["agent"]], [r["latency_ms"] for r in rows["agent"]])}
    SWEEP.write_text(json.dumps(rounded({
        "what": "The agent's dev metrics at every τ on the grid", "split": "dev", "questions": len(questions),
        "grid": {"no_gate": True, "from": GRID[1], "to": GRID[-1], "step": GRID[2] - GRID[1]},
        "rule": TAU_RULE, "chosen": chosen, "points": points}), indent=2) + "\n")
    plot(points, chosen, len(questions))
    out = {
        "what": "The plain pipeline, the pipeline with base control text, and the LangGraph agent on the dev questions",
        "split": "dev",
        "questions": {"all": len(questions), "answerable": sum(q.answerable for q in questions),
                      "unanswerable": sum(not q.answerable for q in questions)},
        "retrieval": {"retrieval": "dense", "strategy": STRATEGY, "search": "exact", "parents_in_context": K},
        "models": {"provider": PROVIDER.__name__, "sdk": f"cursor-sdk {version('cursor-sdk')}",
                   "langgraph": version("langgraph"), "scope_check_and_rewrite": SMALL_MODEL,
                   "generator": GENERATOR_MODEL, "judge": JUDGE_MODEL,
                   "reported": {"scope_check_and_rewrite": sorted(reported(rows["agent"], ("scope_check", "rewrite"))),
                                "generator": sorted(reported(rows["agent"], ("generate",))
                                                    | {r["generator_model"] for s in SYSTEMS[:2] for r in rows[s]}),
                                "judge": sorted({r["judge_model"] for s in SYSTEMS for r in rows[s] if "judge_model" in r})}},
        "prompts": {name: sha256(text) for name, text in (
            ("scope", agent_prompts.SCOPE), ("rewrite", agent_prompts.REWRITE), ("retry", agent_prompts.RETRY),
            ("generate", prompt.GENERATE), ("judge", judge.JUDGE), ("pairwise", judge.PAIRWISE))},
        "agent": {"max_rewrites": MAX_REWRITES, "max_generations": MAX_GENERATIONS,
                  "grader": {"model": rerank.MODEL, "revision": rerank.REVISION,
                             "evidence": "the highest raw logit for (the original question, each context chunk)"},
                  "tau": chosen["tau"], "tau_rule": TAU_RULE, "graph_mermaid": graph},
        "bootstrap": {"unit": "question", "resamples": N_RESAMPLES, "seed": SEED, "interval": "95% percentile",
                      "comparisons": "paired: both systems on the same resampled questions"},
        "systems": {s: summary(rows[s], *costs[s]) for s in SYSTEMS},
        "versus_pipeline": {s: {m: paired_resample_ci(rows[s], rows["pipeline"], STATISTICS[m]) for m in COMPARED}
                            for s in SYSTEMS[1:]},
        "production_pick": production_pick(rows),
        "pairwise": pairwise_summary(pairs) | {"per_question": pairs},
        "agent_paths": agent_paths(rows["agent"]),
        "decision_moves_from_pipeline": {s: decision_moves(rows[s], rows["pipeline"]) for s in SYSTEMS[1:]},
        "per_question": rows,
    }
    OUT.write_text(json.dumps(rounded(out), indent=2) + "\n")
    print(json.dumps(rounded({"tau": chosen["tau"], "production_pick": out["production_pick"]["pick"],
                              **{s: {m: out["systems"][s]["metrics"][m]["value"] for m in COMPARED} for s in SYSTEMS},
                              "pairwise": pairwise_summary(pairs)}), indent=2))
    print(f"wrote {SWEEP}, {PLOT} and {OUT}")


if __name__ == "__main__":
    main()
