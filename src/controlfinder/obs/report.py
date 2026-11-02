"""`make report`: p50 and p95 latency per stage, and the abstention rate, from query_log.

Rows are grouped by pipeline: the API's (`search/...`, `ask/...`) and the agent's dev eval runs
(`agent/eval-dev`). A stage's percentiles cover the rows that ran it. The abstention rate counts
only rows with a decision, so searches don't dilute it. It prints a table and writes
results/query_log_report.json, so a number quoted from the log comes from a saved run.
"""

import json
import statistics
from pathlib import Path

from controlfinder.eval.baselines import rounded
from controlfinder.index.db import connect

OUT = Path("results/query_log_report.json")


def percentiles(values: list[float]) -> dict:
    if len(values) == 1:
        return {"p50": values[0], "p95": values[0]}
    return {"p50": statistics.median(values), "p95": statistics.quantiles(values, n=20, method="inclusive")[-1]}


def summarize(rows: list[tuple[str, dict, str | None]]) -> dict:
    """Per pipeline: requests, each stage's p50/p95 and the abstention rate, from (pipeline, latency_ms, decision) rows."""
    out = {}
    for pipeline in sorted({p for p, _, _ in rows}):
        group = [(latency, decision) for p, latency, decision in rows if p == pipeline]
        stages: dict[str, list[float]] = {}
        for latency, _ in group:
            for stage, ms in latency.items():
                stages.setdefault(stage, []).append(ms)
        decided = [decision for _, decision in group if decision is not None]
        out[pipeline] = {"requests": len(group),
                         "latency_ms": {stage: percentiles(ms) for stage, ms in stages.items()},
                         "decided": len(decided),
                         "abstained": sum(d == "abstain" for d in decided),
                         "abstention_rate": sum(d == "abstain" for d in decided) / len(decided) if decided else None}
    return out


def main() -> None:
    with connect() as conn:
        rows = conn.execute("SELECT pipeline, latency_ms, decision FROM query_log ORDER BY id").fetchall()
    report = rounded(summarize(rows))
    OUT.write_text(json.dumps({"what": "p50/p95 latency per stage and the abstention rate, per pipeline, from query_log",
                               "pipelines": report}, indent=2) + "\n")
    for pipeline, r in report.items():
        rate = "n/a" if r["abstention_rate"] is None else f"{r['abstention_rate']:.3f} ({r['abstained']} of {r['decided']})"
        print(f"\n{pipeline}: {r['requests']} requests, abstention rate {rate}")
        print(f"  {'stage':<18}{'p50 ms':>10}{'p95 ms':>10}")
        for stage, p in r["latency_ms"].items():
            print(f"  {stage:<18}{p['p50']:>10.1f}{p['p95']:>10.1f}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
