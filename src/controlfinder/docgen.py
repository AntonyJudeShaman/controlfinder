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


RENDERERS = {"ann_filter_demo": ann_filter_demo, "corpus_counts": corpus_counts, "chunk_lengths": chunk_lengths}


def render(text: str) -> str:
    return REGION.sub(lambda m: f"{m.group(1)}\n{RENDERERS[m.group(2)]()}\n{m.group(3)}", text)


def main() -> None:
    for path in DOC_PATHS:
        if path.exists() and (new := render(old := path.read_text())) != old:
            path.write_text(new)
            print(f"updated {path}")


if __name__ == "__main__":
    main()
