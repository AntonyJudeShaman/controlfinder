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
