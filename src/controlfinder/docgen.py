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


RENDERERS = {"ann_filter_demo": ann_filter_demo}


def render(text: str) -> str:
    return REGION.sub(lambda m: f"{m.group(1)}\n{RENDERERS[m.group(2)]()}\n{m.group(3)}", text)


def main() -> None:
    for path in DOC_PATHS:
        if path.exists() and (new := render(old := path.read_text())) != old:
            path.write_text(new)
            print(f"updated {path}")


if __name__ == "__main__":
    main()
