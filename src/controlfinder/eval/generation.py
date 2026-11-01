"""`make generate`: the plain pipeline answers the dev questions, then code and a judge grade it.

For each question, production retrieval (Phase 3's pick: dense search over strategy C, exact)
returns the top K parents, each with its best chunk. The generator answers from those chunks
alone, code checks the citations, and a judge from another model family scores faithfulness
against the same chunks. The metrics follow pre-registered definitions 2 to 6 and 8 in
DECISIONS.md, each with a 95% bootstrap interval over questions. A probe then re-judges each
answer with one planted unsupported claim, to check that the judge can tell. Every model call
is cached, so a re-run replays the same answers, scores and latencies. Writes
results/generation_dev.json.
"""

import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from controlfinder.eval.ablations import p50_p95
from controlfinder.eval.baselines import rounded
from controlfinder.eval.bootstrap import N_RESAMPLES, SEED, resample_ci
from controlfinder.eval.qa import UNANSWERABLE, Question, load_questions
from controlfinder.generation import citations, judge, prompt
from controlfinder.generation.llm import LLM, PROVIDER
from controlfinder.index.db import connect
from controlfinder.ingest.ids import display_id, parent_control_id
from controlfinder.retrieval.production import K, STRATEGY, Context, Production

GENERATOR_MODEL = "claude-sonnet-5-5"
JUDGE_MODEL = "gpt-5.6-sol"
OUT = Path("results/generation_dev.json")
PLANT_DETAIL = "47 days"
PLANT = f"This must be repeated at least every {PLANT_DETAIL} [{{citation}}]."


def retrieve(questions: list[Question]) -> dict[str, Context]:
    """Each question's context from production retrieval, and the time it took to get."""
    with connect(autocommit=True) as conn:
        production = Production(conn)
        return {q.id: production(q.question) for q in questions}


COVERAGE = ("base", "enhancement_only", "none")


def gold_coverage(row: dict) -> str:
    """What the context held of the gold controls: a base control's own chunk ('base'), only chunks
    of their enhancements ('enhancement_only'), or nothing ('none')."""
    if set(row["gold"]) & set(row["context"]):
        return "base"
    return "enhancement_only" if row["gold_in_context"] else "none"


def answer_and_grade(q: Question, chunks: list[tuple[str, str]], generator: LLM, grader: LLM) -> dict:
    """One question's answer, its citation check and its faithfulness score, as a results row."""
    reply = generator(prompt.generation_prompt(q.question, chunks))
    context_ids = [control_id for control_id, _ in chunks]
    row = {"id": q.id, "question": q.question, "category": q.category, "answerable": q.answerable,
           "gold": list(q.gold), "context": context_ids,
           "gold_in_context": sorted({parent_control_id(c) for c in context_ids} & set(q.gold)),
           "decision": "abstain" if prompt.abstained(reply.text) else "answer", "answer": reply.text,
           "generate_ms": reply.ms, "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
           "generator_model": reply.model}
    if q.answerable:
        row["gold_coverage"] = gold_coverage(row)
    if row["decision"] == "answer":
        row |= grade_citations(q, reply.text, context_ids) | judge_answer(q, chunks, reply.text, grader)
    return row


def grade_citations(q: Question, answer: str, context_ids: list[str]) -> dict:
    """An answered question's citation fields (definitions 4 and 5)."""
    check = citations.check(answer, set(context_ids), q.gold)
    fields = {"citations": check.citations, "valid": check.valid, "gold_cited": check.gold_cited}
    if q.answerable:
        fields |= {"gold_recall": len(check.gold_cited) / len(q.gold),
                   "correct": len(check.valid) == len(check.citations) and bool(check.gold_cited)}
    return fields


def judge_answer(q: Question, chunks: list[tuple[str, str]], answer: str, grader: LLM) -> dict:
    """The faithfulness judge's score for an answer, against the chunks it was written from."""
    verdict = grader(judge.judge_prompt(q.question, chunks, answer))
    return {"faithfulness": judge.score(verdict.text), "judge_output": verdict.text,
            "judge_ms": verdict.ms, "judge_model": verdict.model}


def judge_probe(rows: list[dict], contexts: dict[str, Context], grader: LLM) -> dict:
    """Each answered question again, with one planted claim its context doesn't support: does the judge notice?

    Added after the first run, when the judge gave all 22 answers a 5 (DECISIONS.md): a judge that
    never reads would give the same scores. Questions whose context contains the planted detail
    are skipped and counted.
    """
    probes, skipped = [], 0
    for r in rows:
        if r["decision"] != "answer" or not r["valid"]:
            continue
        chunks = contexts[r["id"]].chunks
        if any(PLANT_DETAIL in text for _, text in chunks):
            skipped += 1
            continue
        planted = f"{r['answer'].rstrip()} {PLANT.format(citation=display_id(r['valid'][0]))}"
        verdict = grader(judge.judge_prompt(r["question"], chunks, planted))
        probes.append({"id": r["id"], "score": judge.score(verdict.text), "judge_output": verdict.text})
    scores = [p["score"] for p in probes]
    return {"plant": PLANT, "probed": len(probes), "skipped_detail_in_context": skipped,
            "scores": {str(s): scores.count(s) for s in range(1, 6)} | {"unparsed": scores.count(None)},
            "scored_below_5": ratio(sum(s is not None and s < 5 for s in scores), len(probes)),
            "per_question": probes}


def ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def average(values: list[float]) -> float | None:
    return mean(values) if values else None


def counts(rows: list[dict]) -> dict:
    """Definition 3's confusion counts; the positive class is 'abstained'."""
    def n(answerable: bool, decision: str) -> int:
        return sum(r["answerable"] == answerable and r["decision"] == decision for r in rows)
    return {"tp": n(False, "abstain"), "fp": n(True, "abstain"), "fn": n(False, "answer"), "tn": n(True, "answer")}


def abstention_precision(rows):
    c = counts(rows)
    return ratio(c["tp"], c["tp"] + c["fp"])


def abstention_recall(rows):
    c = counts(rows)
    return ratio(c["tp"], c["tp"] + c["fn"])


def abstention_f1(rows):
    p, r = abstention_precision(rows), abstention_recall(rows)
    return None if p is None or r is None else ratio(2 * p * r, p + r)


def citation_precision(rows):
    answered = [r for r in rows if r["decision"] == "answer"]
    return ratio(sum(len(r["valid"]) for r in answered), sum(len(r["citations"]) for r in answered))


STATISTICS = {
    "abstention_precision": abstention_precision,
    "abstention_recall": abstention_recall,
    "abstention_f1": abstention_f1,
    "answer_rate": lambda rows: ratio(sum(r["decision"] == "answer" for r in rows), len(rows)),
    "citation_precision": citation_precision,
    "gold_citation_recall": lambda rows: average([r["gold_recall"] for r in rows if "gold_recall" in r]),
    "answer_accuracy": lambda rows: average([r["correct"] for r in rows if "correct" in r]),
    "faithfulness": lambda rows: average([r["faithfulness"] for r in rows if r.get("faithfulness") is not None]),
    "gold_in_context": lambda rows: average([bool(r["gold_in_context"]) for r in rows if r["answerable"]]),
}


def summarize(rows: list[dict]) -> dict:
    answered = [r for r in rows if r["decision"] == "answer"]
    return {
        "abstention_counts": counts(rows),
        "metrics": {name: resample_ci(rows, statistic) for name, statistic in STATISTICS.items()},
        "faithfulness_scores": {str(s): sum(r["faithfulness"] == s for r in answered) for s in range(1, 6)}
                               | {"unparsed": sum(r["faithfulness"] is None for r in answered)},
        "abstained_by_category": {category: {"questions": sum(r["category"] == category for r in rows),
                                             "abstained": sum(r["category"] == category and r["decision"] == "abstain"
                                                              for r in rows)}
                                  for category in ("answerable", *UNANSWERABLE)},
        "answerable_by_gold_coverage": {
            coverage: {"questions": len(group), "refused": sum(r["decision"] == "abstain" for r in group),
                       "answered": sum(r["decision"] == "answer" for r in group),
                       "correct": sum(r.get("correct") is True for r in group)}
            for coverage in COVERAGE for group in [[r for r in rows if r.get("gold_coverage") == coverage]]},
    }


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> None:
    questions = load_questions("dev")
    contexts = retrieve(questions)
    generator, grader = LLM(GENERATOR_MODEL), LLM(JUDGE_MODEL)
    rows = []
    for n, q in enumerate(questions, 1):
        rows.append(answer_and_grade(q, contexts[q.id].chunks, generator, grader) | {"retrieval_ms": contexts[q.id].ms})
        print(f"{n}/{len(questions)} {q.id} {rows[-1]['decision']}", flush=True)

    answered = [r for r in rows if r["decision"] == "answer"]
    out = {
        "what": "The plain pipeline (retrieve, then generate) on the dev questions, graded by code and a judge",
        "split": "dev",
        "questions": {"all": len(rows), "answerable": sum(r["answerable"] for r in rows),
                      "unanswerable": sum(not r["answerable"] for r in rows)},
        "retrieval": {"retrieval": "dense", "strategy": STRATEGY, "search": "exact", "parents_in_context": K},
        "generator": {"provider": PROVIDER.__name__, "sdk": f"cursor-sdk {version('cursor-sdk')}",
                      "requested_model": GENERATOR_MODEL, "models_reported": sorted({r["generator_model"] for r in rows})},
        "judge": {"provider": PROVIDER.__name__, "requested_model": JUDGE_MODEL,
                  "models_reported": sorted({r["judge_model"] for r in answered})},
        "prompts": {"generate_sha256": sha256(prompt.GENERATE), "judge_sha256": sha256(judge.JUDGE)},
        "bootstrap": {"unit": "question", "resamples": N_RESAMPLES, "seed": SEED, "interval": "95% percentile"},
        **summarize(rows),
        "judge_probe": judge_probe(rows, contexts, grader),
        "cost": {
            "llm_calls_per_question": {"generate": 1, "judge_per_answered_question": 1},
            "latency_ms": {"retrieval": p50_p95([r["retrieval_ms"] for r in rows]),
                           "generate": p50_p95([r["generate_ms"] for r in rows]),
                           "retrieval_plus_generate": p50_p95([r["retrieval_ms"] + r["generate_ms"] for r in rows]),
                           "judge": p50_p95([r["judge_ms"] for r in answered]) if answered else None},
            "generate_tokens_mean": {side: average([r[side] for r in rows if r[side] is not None])
                                     for side in ("input_tokens", "output_tokens")},
        },
        "per_question": rows,
    }
    OUT.write_text(json.dumps(rounded(out), indent=2) + "\n")
    print(json.dumps(rounded({"abstention_counts": out["abstention_counts"],
                              **{k: v["value"] for k, v in out["metrics"].items()}}), indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
