"""Render the tables in the docs from results/*.json, so no table is ever typed by hand.

A doc marks a generated region like this, and `make docs` rewrites what is between the
markers with the output of the renderer of the same name:

    <!-- BEGIN generated: ann_filter_demo -->
    <!-- END generated: ann_filter_demo -->

tests/test_docs_generated.py fails if any region is out of date with results/.
"""

import json
import re
from pathlib import Path

from controlfinder.ingest.ids import display_id, parent_control_id

RESULTS = Path("results")
DOC_PATHS = [*sorted(Path("docs/learn").glob("*.md")), Path("README.md")]
REGION = re.compile(r"(<!-- BEGIN generated: (\w+) -->).*?(<!-- END generated: \2 -->)", re.S)


def table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def ann_filter_demo() -> str:
    d = json.loads((RESULTS / "ann_filter_demo.json").read_text())
    rows = [
        [s["setup"], f"{s['rows_returned']['median']:g} ({s['rows_returned']['min']}–{s['rows_returned']['max']})",
         s["latency_ms_p50"], s["plan"]]
        for s in d["setups"]
    ]
    header = [f"Setup (top-{d['limit']} for {d['target_strategy']})", "Rows returned: median (min–max)",
              "p50 latency (ms)", "Plan"]
    return table(header, rows)


def corpus_counts() -> str:
    d = json.loads((RESULTS / "corpus_stats.json").read_text())
    w = d["withdrawn"]
    rows = [
        ["Families", d["families"]],
        ["Active base controls", d["base_controls"]],
        ["Active enhancements", d["enhancements"]],
        ["Withdrawn base controls (skipped)", w["base_controls"]],
        ["Withdrawn enhancements (skipped)", w["enhancements"]],
        *([f"Withdrawn, linked as `{relation}`" if relation != "none" else "Withdrawn, no replacement", n]
          for relation, n in w["by_relation"].items()),
        ["NIST ID labels checked against `normalize_control_id`", d["id_labels_checked"]],
    ]
    return table([f"SP 800-53 Rev {d['catalog']['version']} catalog", "Count"], rows)


def chunk_lengths() -> str:
    d = json.loads((RESULTS / "corpus_stats.json").read_text())
    limit = d["tokenizer"]["max_tokens"]
    rows = [
        [strategy, s["chunks"], s["min"], f"{s['median']:g}", f"{s['p90']:g}", f"{s['max']} (`{s['longest_chunk']}`)",
         f"{s['over_limit']} ({s['over_limit'] / s['chunks']:.0%})", f"{s['tokens_past_limit_share']:.1%}"]
        for strategy, s in d["token_lengths"].items()
    ]
    header = ["Strategy", "Chunks", "Min", "Median", "p90", "Max (chunk)", f"Over {limit} tokens",
              f"Share of all tokens past {limit}"]
    return table(header, rows)


QUERY_TYPES = ("subcat", "example", "all")
BASELINE_COLUMNS = ["recall@5", "recall@10", "recall@20", "norm_recall@10", "precision@5", "precision@10", "mrr",
                    "ndcg@10"]


def ci(m: dict) -> str:
    return f"{m['mean']:.3f} [{m['ci95'][0]:.3f}, {m['ci95'][1]:.3f}]"


def signed_ci(m: dict, places: int = 3) -> str:
    return f"{m['mean']:+.{places}f} [{m['ci95'][0]:+.{places}f}, {m['ci95'][1]:+.{places}f}]"


def goldset_counts() -> str:
    d = json.loads((RESULTS / "goldset_stats.json").read_text())
    rules, left_out, size = d["references_by_rule"], d["left_out"], d["gold_set_size"]
    rows = [
        ["Active subcategories", d["subcategories"]["active"]],
        ["Withdrawn subcategory rows (skipped)", left_out["withdrawn subcategory rows"]],
        ["Subcategories with at least one 800-53 base control", d["subcategories"]["mapped"]],
        ["Rev 5.2.0 references to a base control", rules["control"]],
        ["Rev 5.2.0 references to an enhancement (counted as its base control)", rules["enhancement"]],
        ["Rev 5.2.0 references to a withdrawn control (remapped)", rules["withdrawn"]],
        ["Rev 5.2.0 family-level references (dropped)", rules["family"]],
        ["References that repeated a control already in the gold set", d["duplicates_after_roll_up"]],
        ["Rev 5.1.1 references (ignored)", left_out["Rev 5.1.1 references"]],
        ["Rev 5.2.0 references on function or category rows (ignored)",
         left_out["Rev 5.2.0 references on function or category rows"]],
        ["Gold controls per subcategory: min / median / max", f"{size['min']} / {size['median']:g} / {size['max']}"],
        ["Implementation examples per subcategory: min / median / max",
         "{min} / {median:g} / {max}".format(**d["examples_per_subcategory"])],
        *([f"Subcategories with more than {k} gold controls", size[f"subcategories_over_{k}"]] for k in (5, 10, 20)),
    ]
    return table(["CSF 2.0 → SP 800-53 Rev 5.2.0 answer key", "Count"], rows)


def split_counts() -> str:
    s = json.loads((RESULTS / "goldset_stats.json").read_text())["split"]
    rows = [[name, s[name]["subcategories"], s[name]["subcat_queries"], s[name]["example_queries"],
             s[name]["subcat_queries"] + s[name]["example_queries"],
             ", ".join(f"{fn} {counts[name]}" for fn, counts in s["by_function"].items())]
            for name in ("dev", "test")]
    return table(["Split", "Subcategories", "`subcat` queries", "`example` queries", "All queries",
                  "Subcategories per CSF function"], rows)


def baseline_recall() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    rows = [[f"`{name}`", *(ci(s["metrics"][t]["recall@10"]) for t in QUERY_TYPES)] for name, s in d["systems"].items()]
    rows.append(["ceiling (best possible)", *(f"{d['ceilings'][t]['recall@10']:.3f}" for t in QUERY_TYPES)])
    return table(["recall@10: mean [95% CI]", *(f"`{t}` ({d['queries'][t]} queries)" for t in QUERY_TYPES)], rows)


def baseline_metrics() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    rows = []
    for t in QUERY_TYPES:
        rows += [[f"`{name}`", f"`{t}`", *(f"{s['metrics'][t][c]['mean']:.3f}" for c in BASELINE_COLUMNS)]
                 for name, s in d["systems"].items()]
        rows.append(["ceiling", f"`{t}`", *(f"{d['ceilings'][t][c]:.3f}" if c in d["ceilings"][t] else "–"
                                           for c in BASELINE_COLUMNS)])
    return table(["System", "Queries", *BASELINE_COLUMNS], rows)


def baseline_costs() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    rows = [[f"`{name}`", f"{s['latency_ms_p50']:.1f}", s["queries_short_of_20_parents"]] for name, s in d["systems"].items()]
    return table(["System", "p50 latency (ms)", f"Queries (of {d['queries']['all']}) with fewer than 20 parents"], rows)


def baseline_comparisons() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    rows = [[f"`{c['a']}` − `{c['b']}`", f"`{t}`", signed_ci(c[t]), "yes" if c[t]["ci95"][0] > 0 or c[t]["ci95"][1] < 0 else "no"]
            for c in d["comparisons"] for t in QUERY_TYPES]
    return table([f"{d['primary_metric']} difference", "Queries", "Mean [95% CI]", "CI excludes 0"], rows)


def hnsw_vs_exact() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    h = d["hnsw"]
    rows = [["no settings (the planner's own choice)", h["default_plan"], "–", "–", "–", "–", "–", "–"]]
    rows += [[s["setup"], s["plan"], f"{s['rows_returned']['median']:g} ({s['rows_returned']['min']}–{s['rows_returned']['max']})",
              s["queries_short_of_20_parents"], f"{s['chunk_recall@10_vs_exact']:.3f}",
              signed_ci(s["recall@10_minus_exact"], 4), signed_ci(s["recall@20_minus_exact"], 4),
              f"{s['latency_ms_p50']:.1f}"]
             for s in h["setups"]]
    header = [f"Dense search, LIMIT {d['fetch_depth']}", "Plan", "Rows returned: median (min–max)",
              "Queries with fewer than 20 parents", "Share of exact top-10 chunks found",
              "recall@10 minus exact [95% CI]", "recall@20 minus exact [95% CI]", "p50 latency (ms)"]
    return table(header, rows)


def dense_vs_bm25_examples() -> str:
    d = json.loads((RESULTS / "baselines_dev.json").read_text())
    rows = [[e["query"], e["text"], ", ".join(e["gold"]), f"`{e['found_by']}`", f"`{e['bm25_best_gold_chunk']}`",
             ", ".join(f"`{w}` ×{n}" for w, n in e["query_lexemes_in_it"].items())]
            for e in d["dense_vs_bm25_disagreements"]]
    return table(["Query", "Text", "Gold", "Found all of it (the other found none)", "Gold chunk BM25 scored highest",
                  "Query lexemes in that chunk"], rows)


def bm25_idf_floor() -> str:
    f = json.loads((RESULTS / "baselines_dev.json").read_text())["bm25_idf_floor"]
    rows = [[f"`{lexeme}`", n, f"{f['floored_idf']:.3f} (floored)"] for lexeme, n in f["floored_lexemes"].items()]
    rows += [[f"`{lexeme}`", v["chunks"], f"{v['idf']:.3f}"] for lexeme, v in f["rarer_lexemes_with_a_lower_idf"].items()]
    return table([f"Lexeme (strategy C, {f['chunks']:,} chunks)", "Chunks containing it", "IDF in `rank_bm25`"], rows)


ABLATION_SETUP = ["#", "Retrieval", "Chunking", "Rerank"]
ABLATION_COLUMNS = ["recall@5", "recall@10", "recall@20", "norm_recall@10", "precision@5", "mrr", "ndcg@10"]


def ablation_setup(r: dict) -> list:
    return [r["row"], f"`{r['retrieval']}`", r["strategy"], "yes" if r["rerank"] else "no"]


def excludes_zero(m: dict) -> bool:
    return m["ci95"][0] > 0 or m["ci95"][1] < 0


def ablation_rows() -> str:
    d = json.loads((RESULTS / "ablations_dev.json").read_text())
    rows = [[*ablation_setup(r), *(ci(r["metrics"][t]["recall@10"]) for t in QUERY_TYPES)] for r in d["rows"]]
    return table([*ABLATION_SETUP, *(f"recall@10, `{t}` ({d['queries'][t]} queries)" for t in QUERY_TYPES)], rows)


def ablation_metrics() -> str:
    d = json.loads((RESULTS / "ablations_dev.json").read_text())
    candidates = f"gold_among_the_{d['candidates']}_candidates"
    rows = [[*ablation_setup(r), *(f"{r['metrics']['all'][c]['mean']:.3f}" for c in ABLATION_COLUMNS), f"{r[candidates]:.3f}"]
            for r in d["rows"]]
    return table([*ABLATION_SETUP, *ABLATION_COLUMNS, f"Gold among the {d['candidates']} candidates"], rows)


def ablation_comparisons() -> str:
    d = json.loads((RESULTS / "ablations_dev.json").read_text())
    rows = [[f"{c['name']} (row {c['a']} − row {c['b']})", metric, f"`{t}`", signed_ci(by_type[t]),
             "yes" if excludes_zero(by_type[t]) else "no"]
            for c in d["comparisons"] for metric, by_type in c["metrics"].items() for t in QUERY_TYPES]
    return table(["Comparison", "Metric", "Queries", "Difference: mean [95% CI]", "CI excludes 0"], rows)


def rerank_costs() -> str:
    d = json.loads((RESULTS / "ablations_dev.json").read_text())
    rows = []
    for r in d["rows"]:
        costs = ["–"] * 3
        if r["rerank"]:
            over, pairs = r["pairs_over_512_tokens"], r["pairs_reranked"]
            costs = [*(f"{r[k]['p50']:,.0f} / {r[k]['p95']:,.0f}" for k in ("rerank_ms", "total_ms")),
                     f"{over:,} of {pairs:,} ({over / pairs:.0%})"]
        rows.append([*ablation_setup(r), f"{r['retrieval_ms_p50']:.1f}", *costs])
    return table([*ABLATION_SETUP, "Retrieval p50 (ms)", "Rerank p50 / p95 (ms)", "Total p50 / p95 (ms)",
                  f"Pairs over {d['reranker']['max_length']} tokens"], rows)


def rerank_effect() -> str:
    e = json.loads((RESULTS / "ablations_dev.json").read_text())["rerank_effect_row_4"]
    enhancement, candidates = e["candidates_scored_on_an_enhancement_chunk"], e["candidates"]
    rows = [
        ["Queries with more gold controls in the top 10", e["queries_with_more_gold_in_the_top_10"]],
        ["Queries with fewer gold controls in the top 10", e["queries_with_less_gold_in_the_top_10"]],
        ["Queries with the same number", e["queries_unchanged"]],
        ["Gold candidates moved up", e["gold_candidates_moved_up"]],
        ["Gold candidates moved down", e["gold_candidates_moved_down"]],
        ["Gold candidates that kept their rank", e["gold_candidates_unmoved"]],
        ["Candidates judged on an enhancement's chunk", f"{enhancement:,} of {candidates:,} ({enhancement / candidates:.0%})"],
    ]
    return table(["Row 4: reranking row 3's 50 candidates", "Count"], rows)


def rerank_losses() -> str:
    e = json.loads((RESULTS / "ablations_dev.json").read_text())["rerank_effect_row_4"]

    def marked(parents: list[str], gold: list[str]) -> list[str]:
        return [f"**{p}**" if p in gold else p for p in parents]

    rows = [[x["query"], x["text"], ", ".join(x["gold"]), x["gold_in_top_10_change"],
             ", ".join(f"{p} (`{chunk}`)" for p, chunk in zip(marked(x["before_top5"], x["gold"]), x["before_top5_chunks"],
                                                             strict=True)),
             ", ".join(marked(x["after_top5"], x["gold"]))] for x in e["largest_losses"]]
    return table(["Query", "Text", "Gold", "Change in gold controls in the top 10",
                  "Top 5 before reranking (gold in bold), with the chunk the reranker read", "Top 5 after"], rows)


def production_pick() -> str:
    d = json.loads((RESULTS / "ablations_dev.json").read_text())
    p, by_row = d["production"], {r["row"]: r for r in d["rows"]}
    rows = [[*ablation_setup(by_row[v["row"]]), v["parts"], f"{by_row[v['row']]['metrics']['all']['recall@10']['mean']:.3f}",
             "best" if v["row"] == p["best_row"] else signed_ci(v["difference"]),
             "yes" if excludes_zero(v["difference"]) else "no", "**pick**" if v["row"] == p["pick"] else ""]
            for v in p["versus_best"]]
    return table([*ABLATION_SETUP, "Parts", "recall@10 (all)", "Minus the best row [95% CI]",
                  "Distinguishably worse", "Production"], rows)


QA_CATEGORIES = {
    "answerable": "SP 800-53 supports an answer; each lists {min}–{max} gold base controls",
    "other_framework": "Needs another framework's text (PCI DSS, ISO 27001, SOC 2, ...)",
    "internal_policy": "Needs one organization's own facts (\"Who is our CISO?\")",
    "legal": "Needs a legal conclusion",
    "trivia": "General knowledge unrelated to the catalog",
    "security_specifics": "Security facts the catalog doesn't hold (a CVE's score, product steps)",
}


def qa_counts() -> str:
    d = json.loads((RESULTS / "qa_stats.json").read_text())
    rows = [[f"`{category}`", meaning.format(**d["gold_set_size"]), d["by_category"][category]["dev"],
             d["by_category"][category]["test"]] for category, meaning in QA_CATEGORIES.items()]
    rows.append(["**all**", f"{d['distinct_gold_controls']} distinct gold controls from {d['families_in_gold']} families",
                 sum(v["dev"] for v in d["by_category"].values()), sum(v["test"] for v in d["by_category"].values())])
    return table(["Category", "What a question needs", "Dev", "Test (sealed)"], rows)


GENERATION_METRICS = {
    "abstention_precision": "Of the refusals, the share that were unanswerable questions",
    "abstention_recall": "Of the unanswerable questions, the share refused",
    "abstention_f1": "The two above combined (harmonic mean)",
    "answer_rate": "Of all questions, the share answered",
    "citation_precision": "Of all citations in answers, the share whose exact control was in the context",
    "gold_citation_recall": "Per answered answerable question, the share of its gold controls validly cited, averaged",
    "answer_accuracy": "Of answered answerable questions, the share with every citation valid and at least one gold",
    "faithfulness": "The judge's mean score from 1 to 5, over answered questions",
    "gold_in_context": "Of answerable questions, the share with a gold control among the 10 retrieved",
}
LATENCY_PARTS = {
    "retrieval": "Retrieval: embed the question, exact dense search",
    "generate": "Generation: one Cursor agent call",
    "retrieval_plus_generate": "Per question: retrieval + generation",
    "judge": "Judge call (evaluation only, not part of the pipeline)",
}


def generation() -> dict:
    return json.loads((RESULTS / "generation_dev.json").read_text())


def value_ci(m: dict) -> str:
    if m["value"] is None:
        return "undefined"
    return f"{m['value']:.3f}" + (f" [{m['ci95'][0]:.3f}, {m['ci95'][1]:.3f}]" if m["ci95"] else "")


def generation_metrics() -> str:
    metrics = generation()["metrics"]
    rows = [[f"`{name}`", meaning, value_ci(metrics[name]), metrics[name]["undefined_resamples"]]
            for name, meaning in GENERATION_METRICS.items()]
    return table(["Metric", "What it measures", "Value [95% CI]", "Resamples where undefined"], rows)


def abstention_matrix() -> str:
    c = generation()["abstention_counts"]
    return table(["Dev questions", "Refused", "Answered"],
                 [["Unanswerable", f"{c['tp']} (TP)", f"{c['fn']} (FN)"],
                  ["Answerable", f"{c['fp']} (FP)", f"{c['tn']} (TN)"]])


def abstention_by_category() -> str:
    rows = [[f"`{category}`", v["questions"], v["abstained"]] for category, v in generation()["abstained_by_category"].items()]
    return table(["Category", "Dev questions", "Refused"], rows)


COVERAGE_LABELS = {
    "base": "A gold control's own chunk",
    "enhancement_only": "Only chunks of a gold control's enhancements",
    "none": "No gold control at all",
}


def judge_scores() -> str:
    d = generation()
    probe = d["judge_probe"]
    rows = [["Answers as generated", *d["faithfulness_scores"].values()],
            [f"The same answers plus one planted claim ({probe['probed']} probed)", *probe["scores"].values()]]
    return table(["Judge score", *d["faithfulness_scores"]], rows)


def gold_coverage() -> str:
    rows = [[COVERAGE_LABELS[coverage], v["questions"], v["refused"], v["answered"], v["correct"]]
            for coverage, v in generation()["answerable_by_gold_coverage"].items()]
    return table(["What the 10 retrieved chunks held", "Answerable questions", "Refused", "Answered",
                  "Answered correctly"], rows)


def gold_chunks(row: dict) -> str:
    return ", ".join(display_id(c) for c in row["context"] if parent_control_id(c) in row["gold"]) or "none"


def wrong_refusals() -> str:
    rows = [[r["id"], r["question"], ", ".join(display_id(g) for g in r["gold"]), gold_chunks(r)]
            for r in generation()["per_question"] if r["answerable"] and r["decision"] == "abstain"]
    return table(["ID", "Answerable question the pipeline refused", "Gold", "Gold controls' chunks among the 10"], rows)


def incorrect_answers() -> str:
    rows = [[r["id"], r["question"], ", ".join(display_id(g) for g in r["gold"]), gold_chunks(r),
             ", ".join(display_id(c) for c in r["citations"])]
            for r in generation()["per_question"] if r.get("correct") is False]
    return table(["ID", "Question", "Gold", "Gold controls' chunks among the 10", "Cited instead"], rows)


def generation_costs() -> str:
    cost = generation()["cost"]
    rows = [[LATENCY_PARTS[part], f"{v['p50']:,.0f} / {v['p95']:,.0f}" if v else "–"]
            for part, v in cost["latency_ms"].items()]
    tokens = cost["generate_tokens_mean"]
    rows += [["Mean input tokens per generation call", f"{tokens['input_tokens']:,.0f}"],
             ["Mean output tokens per generation call", f"{tokens['output_tokens']:,.0f}"]]
    return table(["Cost", "p50 / p95 (ms), or mean"], rows)


SYSTEM_LABELS = {"pipeline": "Pipeline", "pipeline_base_text": "Pipeline + base text", "agent": "Agent"}
SWEPT = {"answer_rate": "Answer rate", "abstention_precision": "Abstention precision",
         "abstention_recall": "Abstention recall", "abstention_f1": "Abstention F1", "answer_accuracy": "Answer accuracy"}
REASON_LABELS = {
    "out_of_scope": "Refused: the scope check said off-topic",
    "weak_evidence": "Refused: evidence still below τ after 2 rewrites",
    "generator_refused": "Refused: the generator replied INSUFFICIENT_EVIDENCE",
    "citations_failed": "Refused: the citations failed the check twice",
}


def agent_results() -> dict:
    return json.loads((RESULTS / "agent_dev.json").read_text())


def three(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.3f}"


def delta_ci(m: dict) -> str:
    if m["value"] is None:
        return "undefined"
    return f"{m['value']:+.3f}" + (f" [{m['ci95'][0]:+.3f}, {m['ci95'][1]:+.3f}]" if m["ci95"] else "")


def tau_label(tau: float | None) -> str:
    return "no gate" if tau is None else f"{tau:.2f}"


def agent_graph() -> str:
    return f"```mermaid\n{agent_results()['agent']['graph_mermaid'].strip()}\n```"


def step_details(step: dict) -> str:
    parts = []
    for key, value in step.items():
        if key in ("node", "ms", "answer", "verdict"):
            continue
        if key in ("controls", "citations", "invalid"):
            value = ", ".join(map(display_id, value)) or "none"
        elif key == "closest":
            value = ", ".join(f"{display_id(c['control_id'])} ({c['score']:.2f})" for c in value) or "none"
        elif key == "tau":
            value = tau_label(value)
        elif isinstance(value, float):
            value = f"{value:.2f}"
        elif key == "query":
            value = f'"{value}"'
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(parts)


def example_traces() -> str:
    """The first answered question, the first answerable one the generator refused, and the first off-topic one."""
    runs = agent_results()["per_question"]["agent"]
    picks = [next((r for r in runs if test(r)), None) for test in (
        lambda r: r["decision"] == "answer",
        lambda r: r["answerable"] and r["reason"] == "generator_refused",
        lambda r: r["reason"] == "out_of_scope")]
    rows = [[f"{r['id']}: {r['question']}" if i == 0 else "", f"`{s['node']}`", f"{s['ms']:,.0f}", step_details(s)]
            for r in picks if r for i, s in enumerate(r["trace"])]
    return table(["Question", "Node", "ms", "What the step recorded"], rows)


def tau_sweep() -> str:
    """One row per run of neighbouring τ values that gave the same results."""
    d = json.loads((RESULTS / "threshold_sweep.json").read_text())
    rescues = ["rewritten", "answered_after_rewrite", "correct_after_rewrite"]
    keys = [*SWEPT, "llm_calls_mean", *rescues]
    groups = []
    for p in d["points"]:
        if groups and None not in (p["tau"], groups[-1][0]["tau"]) and all(p[k] == groups[-1][0][k] for k in keys):
            groups[-1].append(p)
        else:
            groups.append([p])
    rows = []
    for group in groups:
        first, last = tau_label(group[0]["tau"]), tau_label(group[-1]["tau"])
        span = first if first == last else f"{first} to {last}"
        if d["chosen"]["tau"] in [p["tau"] for p in group]:
            span = f"**{span} (chosen)**" if first == last else f"**{span} (chosen: {tau_label(d['chosen']['tau'])})**"
        rows.append([span, *[three(group[0][k]) for k in SWEPT], f"{group[0]['llm_calls_mean']:.2f}",
                     " / ".join(str(group[0][k]) for k in rescues)])
    return table(["τ", *SWEPT.values(), "LLM calls per question", "Rewritten / then answered / correctly"], rows)


def tau_ranges(taus: list[float], step: float) -> str:
    spans = []
    for tau in sorted(taus):
        if spans and tau - spans[-1][1] <= step + 1e-9:
            spans[-1][1] = tau
        else:
            spans.append([tau, tau])
    return ", ".join(tau_label(a) if a == b else f"{tau_label(a)} to {tau_label(b)}" for a, b in spans)


def rewrite_answers() -> str:
    """Every question the agent answered only after a rewrite, at any τ, beside what the pipeline did."""
    d = json.loads((RESULTS / "threshold_sweep.json").read_text())
    pipeline = {r["id"]: r for r in agent_results()["per_question"]["pipeline"]}
    found: dict[str, list] = {}
    for p in d["points"]:
        for qid, correct in p["after_rewrite"].items():
            found.setdefault(qid, []).append((p["tau"], correct))
    rows = []
    for qid, hits in sorted(found.items()):
        verdicts = {correct for _, correct in hits}
        rows.append([qid, pipeline[qid]["question"], outcome(pipeline[qid]),
                     tau_ranges([tau for tau, _ in hits], d["grid"]["step"]),
                     "yes" if verdicts == {True} else ("no" if verdicts == {False} else "at some τ")])
    return table(["ID", "Question", "Pipeline", "τ values where a rewrite led to an answer", "Answer correct?"], rows)


def system_metrics() -> str:
    systems = agent_results()["systems"]
    rows = [["TP / FP / FN / TN",
             *[" / ".join(str(systems[s]["abstention_counts"][k]) for k in ("tp", "fp", "fn", "tn")) for s in SYSTEM_LABELS]]]
    rows += [[f"`{name}`", *[value_ci(systems[s]["metrics"][name]) for s in SYSTEM_LABELS]] for name in GENERATION_METRICS]
    return table(["Dev metric [95% CI]", *SYSTEM_LABELS.values()], rows)


def versus_pipeline() -> str:
    d = agent_results()["versus_pipeline"]
    rows = [[f"`{metric}`", *[delta_ci(d[s][metric]) for s in d]] for metric in d["agent"]]
    return table(["Metric", *[f"{SYSTEM_LABELS[s]} minus pipeline [95% CI]" for s in d]], rows)


def agent_pick() -> str:
    p = agent_results()["production_pick"]
    rows = []
    for s, label in SYSTEM_LABELS.items():
        gap = p["gaps_to_best"][s]
        within = "best" if s == p["best"] else ("yes" if gap["ci95"] and gap["ci95"][1] >= 0 else "no")
        rows.append([f"**{label} (pick)**" if s == p["pick"] else label, three(p["abstention_f1"][s]), delta_ci(gap), within])
    return table(["System, simplest first", "Abstention F1", "Minus the best's [95% CI]", "Within noise of the best?"], rows)


SCORE_GROUPS = {
    "answerable_pipeline_answer": "Answerable, answered by the pipeline",
    "answerable_pipeline_abstain": "Answerable, refused by the pipeline",
    "unanswerable": "Unanswerable",
}


def first_evidence_scores() -> str:
    d = agent_results()["first_evidence_scores"]
    rows = [[label, d[g]["questions"], d[g]["scored"],
             *["–" if d[g][k] is None else f"{d[g][k]:.2f}" for k in ("min", "median", "max")]]
            for g, label in SCORE_GROUPS.items()]
    return table(["Dev questions", "Questions", "Scored (not stopped as off-topic)", "Lowest", "Median", "Highest"], rows)


def system_costs() -> str:
    systems = agent_results()["systems"]
    rows = [[label, f"{systems[s]['llm_calls_per_question']['mean']:.2f} (max {systems[s]['llm_calls_per_question']['max']})",
             f"{systems[s]['latency_ms']['p50']:,.0f} / {systems[s]['latency_ms']['p95']:,.0f}"]
            for s, label in SYSTEM_LABELS.items()]
    return table(["System", "LLM calls per question: mean (max)", "Latency per question, p50 / p95 (ms)"], rows)


def agent_step_costs() -> str:
    d = agent_results()["agent_step_ms"]
    rows = [[f"`{node}`", v["steps"], f"{v['p50']:,.0f} / {v['p95']:,.0f}"] for node, v in d.items()]
    return table(["Agent node", "Steps run on dev", "Time per step, p50 / p95 (ms)"], rows)


def pairwise_results() -> str:
    p = agent_results()["pairwise"]
    return table(["Both answered", "Identical answers (ties, not judged)", "Agent wins", "Pipeline wins", "Ties",
                  "Orders disagreed", "Unreadable verdicts"],
                 [[p["both_answered"], p["identical_answers"], p["agent_wins"], p["pipeline_wins"], p["ties"],
                   p["orders_disagreed"], p["unparsed_verdicts"]]])


def agent_paths() -> str:
    d = agent_results()["agent_paths"]
    rows = [[REASON_LABELS[reason], n] for reason, n in d["abstained_because"].items()]
    rows += [[f"Answered after {n} rewrite{'' if n == '1' else 's'}", count] for n, count in d["answered_after_rewrites"].items()]
    rows += [["Questions rewritten at least once", d["questions_rewritten"]],
             ["Answers retried after failing the citation check", d["citation_retries"]]]
    return table(["How the agent's runs went (dev)", "Questions"], rows)


def decision_moves() -> str:
    d = agent_results()["decision_moves_from_pipeline"]
    rows = [[kind, label, *[d[s][kind][move] for s in d]]
            for kind in ("answerable", "unanswerable")
            for move, label in (("abstain_to_answer", "refused → answered"), ("answer_to_abstain", "answered → refused"))]
    return table(["Questions", "Change from the pipeline", *[SYSTEM_LABELS[s] for s in d]], rows)


def outcome(r: dict) -> str:
    if r["decision"] == "abstain":
        return f"refused ({r['reason'].replace('_', ' ')})" if r.get("reason") else "refused"
    text = "answered" if "correct" not in r else ("answered, correct" if r["correct"] else "answered, wrong")
    if not r["answerable"]:
        text += " (should have refused)"
    return text + (f", after {r['rewrites']} rewrite{'' if r['rewrites'] == 1 else 's'}" if r.get("rewrites") else "")


def changed_questions() -> str:
    """Every dev question on which the three systems didn't all end the same way."""
    per = agent_results()["per_question"]
    rows = [[p["id"], p["question"], "answerable" if p["answerable"] else f"`{p['category']}`", *map(outcome, (p, b, a))]
            for p, b, a in zip(per["pipeline"], per["pipeline_base_text"], per["agent"], strict=True)
            if len({(r["decision"], r.get("correct")) for r in (p, b, a)}) > 1]
    return table(["ID", "Question", "Kind", *SYSTEM_LABELS.values()], rows)


def final_test() -> dict:
    return json.loads((RESULTS / "final_test.json").read_text())


def dev_retrieval() -> tuple[dict, dict]:
    return (json.loads((RESULTS / "baselines_dev.json").read_text()),
            json.loads((RESULTS / "ablations_dev.json").read_text()))


def yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def final_retrieval() -> str:
    """Every retrieval setup on all queries: its dev number beside its one test run."""
    test, (base, abl) = final_test()["retrieval"], dev_retrieval()
    metric, on_test = abl["primary_metric"], {r["row"]: r for r in test["rows"]}
    rows = [[f"Phase 2 `{name}`", f"`{name}`", base["strategy"], "no", ci(s["metrics"]["all"][metric]),
             ci(test["baselines"][name]["metrics"]["all"][metric]), ""] for name, s in base["systems"].items()]
    rows += [[f"Phase 3 row {r['row']}", *ablation_setup(r)[1:], ci(r["metrics"]["all"][metric]),
              ci(on_test[r["row"]]["metrics"]["all"][metric]), "**yes**" if r["row"] == test["production"]["row"] else ""]
             for r in abl["rows"]]
    return table(["Setup", "Retrieval", "Chunking", "Rerank", f"{metric} dev ({abl['queries']['all']} queries) [95% CI]",
                  f"{metric} test ({test['queries']['all']} queries) [95% CI]", "Production"], rows)


def final_rows_by_type() -> str:
    test = final_test()["retrieval"]
    rows = [[*ablation_setup(r), *(ci(r["metrics"][t]["recall@10"]) for t in QUERY_TYPES)] for r in test["rows"]]
    return table([*ABLATION_SETUP, *(f"test recall@10, `{t}` ({test['queries'][t]} queries)" for t in QUERY_TYPES)], rows)


def final_rows_metrics() -> str:
    test = final_test()["retrieval"]
    rows = [[*ablation_setup(r), *(f"{r['metrics']['all'][c]['mean']:.3f}" for c in ABLATION_COLUMNS)] for r in test["rows"]]
    return table([*ABLATION_SETUP, *(f"test {c}" for c in ABLATION_COLUMNS)], rows)


def final_comparisons() -> str:
    """Dev's pre-registered differences on all queries, with the test interval beside dev's."""
    test, (base, abl) = final_test()["retrieval"], dev_retrieval()
    rows = []
    for c in base["comparisons"]:
        t = next(x for x in test["baseline_comparisons"] if (x["a"], x["b"]) == (c["a"], c["b"]))
        rows.append([f"`{c['a']}` − `{c['b']}`", base["primary_metric"], signed_ci(c["all"]), signed_ci(t["all"]),
                     yes_no(excludes_zero(c["all"])), yes_no(excludes_zero(t["all"]))])
    for c in abl["comparisons"]:
        t = next(x for x in test["comparisons"] if x["name"] == c["name"])
        rows += [[f"{c['name']} (row {c['a']} − row {c['b']})", metric, signed_ci(by_type["all"]),
                  signed_ci(t["metrics"][metric]["all"]), yes_no(excludes_zero(by_type["all"])),
                  yes_no(excludes_zero(t["metrics"][metric]["all"]))] for metric, by_type in c["metrics"].items()]
    production, best = test["production"]["row"], abl["production"]["best_row"]
    dev_versus_best = next(v["difference"] for v in abl["production"]["versus_best"] if v["row"] == production)
    for v in test["production"]["versus_rows"]:
        dev = dev_versus_best if v["row"] == best else None
        rows.append([f"production (row {production}) − row {v['row']}", abl["primary_metric"],
                     signed_ci(dev) if dev else "not computed on dev", signed_ci(v["difference"]["all"]),
                     yes_no(excludes_zero(dev)) if dev else "–", yes_no(excludes_zero(v["difference"]["all"]))])
    return table(["Difference, all queries", "Metric", "Dev [95% CI]", "Test [95% CI]", "Dev CI excludes 0",
                  "Test CI excludes 0"], rows)


def final_generation() -> str:
    """The pre-registered answer metrics per system: dev beside test. The agent ran on dev only."""
    test, dev = final_test()["generation"], agent_results()["systems"]
    metrics = list(test["versus_pipeline"]["pipeline_base_text"])
    rows = [[label, *[cell for m in metrics for cell in (value_ci(dev[s]["metrics"][m]),
                                                          value_ci(test["systems"][s]["metrics"][m])
                                                          if s in test["systems"] else "not run (dev only)")]]
            for s, label in SYSTEM_LABELS.items()]
    return table(["System", *[f"`{m}` {split}" for m in metrics for split in ("dev", "test")]], rows)


def final_generation_metrics() -> str:
    test, dev = final_test()["generation"], agent_results()["systems"]
    systems = list(test["systems"])
    rows = [["TP / FP / FN / TN", *[" / ".join(str(r[s]["abstention_counts"][k]) for k in ("tp", "fp", "fn", "tn"))
                                     for s in systems for r in (dev, test["systems"])]]]
    rows += [[f"`{name}`", *[value_ci(r[s]["metrics"][name]) for s in systems for r in (dev, test["systems"])]]
             for name in GENERATION_METRICS if name in test["systems"][systems[0]]["metrics"]]
    return table(["Metric [95% CI]", *[f"{SYSTEM_LABELS[s]}, {split}" for s in systems for split in ("dev", "test")]], rows)


def final_versus() -> str:
    test, dev = final_test()["generation"]["versus_pipeline"], agent_results()["versus_pipeline"]
    rows = [[f"`{m}`", delta_ci(dev["pipeline_base_text"][m]), delta_ci(test["pipeline_base_text"][m]),
             delta_ci(dev["agent"][m]), "not run"] for m in test["pipeline_base_text"]]
    return table(["Metric", "Base text − pipeline, dev [95% CI]", "Base text − pipeline, test [95% CI]",
                  "Agent − pipeline, dev [95% CI]", "Agent − pipeline, test"], rows)


def final_decision_moves() -> str:
    d = final_test()["generation"]["decision_moves_from_pipeline"]["pipeline_base_text"]
    rows = [[kind, label, d[kind][move]] for kind in ("answerable", "unanswerable")
            for move, label in (("abstain_to_answer", "refused → answered"), ("answer_to_abstain", "answered → refused"))]
    return table(["Test questions", "Change from the pipeline", "Pipeline + base text"], rows)


def final_costs() -> str:
    test, dev = final_test(), agent_results()["systems"]
    abl = dev_retrieval()[1]
    on_test = {r["row"]: r for r in test["retrieval"]["rows"]}

    def retrieval(r: dict) -> str:
        first = f"{r['retrieval_ms_p50']:,.1f}"
        return f"{first} + {r['rerank_ms']['p50']:,.0f} rerank" if r["rerank"] else first

    rows = [[f"Row {r['row']} ({r['retrieval']}{', reranked' if r['rerank'] else ''}), p50", retrieval(r),
             retrieval(on_test[r["row"]])] for r in abl["rows"]]
    rows += [[f"{SYSTEM_LABELS[s]}: retrieval + generation, p50 / p95",
              f"{dev[s]['latency_ms']['p50']:,.0f} / {dev[s]['latency_ms']['p95']:,.0f}",
              f"{v['latency_ms']['p50']:,.0f} / {v['latency_ms']['p95']:,.0f}"] for s, v in test["generation"]["systems"].items()]
    return table(["Latency (ms)", "Dev", "Test"], rows)


def final_shifts() -> str:
    """Every test result whose dev point estimate falls outside its test 95% interval: the pre-registered rule."""
    test, (base, abl), agent = final_test(), dev_retrieval(), agent_results()
    found, checked = [], 0

    def check(what: str, metric: str, queries: str, dev: float | None, interval: dict, signed: bool = False) -> None:
        nonlocal checked
        if dev is None or not interval["ci95"]:
            return
        checked += 1
        if interval["ci95"][0] <= dev <= interval["ci95"][1]:
            return
        point = interval.get("mean", interval.get("value"))
        if "mean" in interval:
            shown = signed_ci(interval) if signed else ci(interval)
        else:
            shown = delta_ci(interval) if signed else value_ci(interval)
        found.append([what, metric, queries, f"{dev:+.3f}" if signed else f"{dev:.3f}", shown,
                      "higher" if point > dev else "lower"])

    retrieval = test["retrieval"]
    for name, s in base["systems"].items():
        for t in QUERY_TYPES:
            for metric, m in s["metrics"][t].items():
                check(f"`{name}`", metric, t, m["mean"], retrieval["baselines"][name]["metrics"][t][metric])
    on_test = {r["row"]: r for r in retrieval["rows"]}
    for r in abl["rows"]:
        for t in QUERY_TYPES:
            for metric, m in r["metrics"][t].items():
                check(f"row {r['row']}", metric, t, m["mean"], on_test[r["row"]]["metrics"][t][metric])
    for c in base["comparisons"]:
        tc = next(x for x in retrieval["baseline_comparisons"] if (x["a"], x["b"]) == (c["a"], c["b"]))
        for t in QUERY_TYPES:
            check(f"`{c['a']}` − `{c['b']}`", base["primary_metric"], t, c[t]["mean"], tc[t], signed=True)
    for c in abl["comparisons"]:
        tc = next(x for x in retrieval["comparisons"] if x["name"] == c["name"])
        for metric, by_type in c["metrics"].items():
            for t in QUERY_TYPES:
                check(f"row {c['a']} − row {c['b']}", metric, t, by_type[t]["mean"], tc["metrics"][metric][t], signed=True)
    generation = test["generation"]
    for s, v in generation["systems"].items():
        for metric, m in v["metrics"].items():
            check(SYSTEM_LABELS[s], metric, "QA", agent["systems"][s]["metrics"][metric]["value"], m)
    for metric, m in generation["versus_pipeline"]["pipeline_base_text"].items():
        check("Pipeline + base text − pipeline", metric, "QA",
              agent["versus_pipeline"]["pipeline_base_text"][metric]["value"], m, signed=True)
    if not found:
        return f"In all {checked} checks, the dev point estimate falls inside its test 95% interval."
    return (f"{len(found)} of {checked} checks have the dev point estimate outside its test 95% interval:\n\n"
            + table(["What", "Metric", "Queries", "Dev", "Test [95% CI]", "Test is"], found))


def threshold_chart() -> str:
    """Line charts of the dev τ sweep for the README; the grid is even, so a numeric x-axis places every point."""
    d = json.loads((RESULTS / "threshold_sweep.json").read_text())
    grid, no_gate = d["grid"], next(p for p in d["points"] if p["tau"] is None)
    points = [p for p in d["points"] if p["tau"] is not None]
    charts = []
    for key in ("abstention_f1", "answer_rate"):
        values = ", ".join(f"{p[key]:.3f}" for p in points)
        charts.append(f'```mermaid\nxychart-beta\n    title "{SWEPT[key]} on dev by τ (no gate: {no_gate[key]:.3f})"\n'
                      f'    x-axis "τ, the reranker-logit gate" {grid["from"]:g} --> {grid["to"]:g}\n'
                      f'    y-axis "{SWEPT[key]}" 0 --> 1\n    line [{values}]\n```')
    return "\n\n".join(charts)


def ci_gate() -> str:
    d = json.loads((RESULTS / "ci_baseline.json").read_text())
    return table(["CI gate", "Value"], [[k, v] for k, v in d.items() if not isinstance(v, (dict, list))])


def query_log_report() -> str:
    d = json.loads((RESULTS / "query_log_report.json").read_text())["pipelines"]
    rows = [[f"`{pipeline}`", r["requests"],
             "–" if r["abstention_rate"] is None else f"{r['abstention_rate']:.3f} ({r['abstained']} of {r['decided']})",
             "<br>".join(f"{stage} {p['p50']:,.0f} / {p['p95']:,.0f}" for stage, p in r["latency_ms"].items())]
            for pipeline, r in d.items()]
    return table(["Pipeline", "Requests", "Abstention rate", "Stage: p50 / p95 (ms)"], rows)


RENDERERS = {
    "ann_filter_demo": ann_filter_demo,
    "corpus_counts": corpus_counts,
    "chunk_lengths": chunk_lengths,
    "goldset_counts": goldset_counts,
    "split_counts": split_counts,
    "baseline_recall": baseline_recall,
    "baseline_metrics": baseline_metrics,
    "baseline_costs": baseline_costs,
    "baseline_comparisons": baseline_comparisons,
    "hnsw_vs_exact": hnsw_vs_exact,
    "dense_vs_bm25_examples": dense_vs_bm25_examples,
    "bm25_idf_floor": bm25_idf_floor,
    "ablation_rows": ablation_rows,
    "ablation_metrics": ablation_metrics,
    "ablation_comparisons": ablation_comparisons,
    "rerank_costs": rerank_costs,
    "rerank_effect": rerank_effect,
    "rerank_losses": rerank_losses,
    "production_pick": production_pick,
    "qa_counts": qa_counts,
    "generation_metrics": generation_metrics,
    "abstention_matrix": abstention_matrix,
    "abstention_by_category": abstention_by_category,
    "judge_scores": judge_scores,
    "gold_coverage": gold_coverage,
    "wrong_refusals": wrong_refusals,
    "incorrect_answers": incorrect_answers,
    "generation_costs": generation_costs,
    "agent_graph": agent_graph,
    "example_traces": example_traces,
    "tau_sweep": tau_sweep,
    "rewrite_answers": rewrite_answers,
    "system_metrics": system_metrics,
    "versus_pipeline": versus_pipeline,
    "agent_pick": agent_pick,
    "first_evidence_scores": first_evidence_scores,
    "system_costs": system_costs,
    "agent_step_costs": agent_step_costs,
    "pairwise_results": pairwise_results,
    "agent_paths": agent_paths,
    "decision_moves": decision_moves,
    "changed_questions": changed_questions,
    "final_retrieval": final_retrieval,
    "final_rows_by_type": final_rows_by_type,
    "final_rows_metrics": final_rows_metrics,
    "final_comparisons": final_comparisons,
    "final_generation": final_generation,
    "final_generation_metrics": final_generation_metrics,
    "final_versus": final_versus,
    "final_decision_moves": final_decision_moves,
    "final_costs": final_costs,
    "final_shifts": final_shifts,
    "threshold_chart": threshold_chart,
    "ci_gate": ci_gate,
    "query_log_report": query_log_report,
}


def render(text: str) -> str:
    return REGION.sub(lambda m: f"{m.group(1)}\n{RENDERERS[m.group(2)]()}\n{m.group(3)}", text)


def main() -> None:
    for path in DOC_PATHS:
        if path.exists() and (new := render(old := path.read_text())) != old:
            path.write_text(new)
            print(f"updated {path}")


if __name__ == "__main__":
    main()
