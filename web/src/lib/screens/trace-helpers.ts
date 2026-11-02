import { displayControlId } from "@/lib/domain/controls-helpers";
import { formatMs, formatNumber } from "@/lib/domain/metrics-helpers";
import { traceStepView } from "@/lib/domain/trace-helpers";
import type { LogDetail, LogsResponse } from "@/types/domain/logs";
import type { LogDetailView, LogRowView, TraceAction, TraceState } from "@/types/screens/trace";

export const ALL_PIPELINES = "all";

export function traceReducer(state: TraceState, action: TraceAction): TraceState {
  switch (action.type) {
    case "logs":
      return { ...state, logs: { key: action.key, result: action.result } };
    case "detail":
      return { ...state, detail: { key: action.key, result: action.result } };
  }
}

export function logsPath(pipeline: string): string {
  const params = new URLSearchParams({ limit: "200" });
  if (pipeline !== ALL_PIPELINES) params.set("pipeline", pipeline);
  return `/logs?${params.toString()}`;
}

export function pipelineOptions(logs: LogsResponse | null): { value: string; label: string }[] {
  const total = logs ? logs.pipelines.reduce((sum, p) => sum + p.requests, 0) : 0;
  return [
    { value: ALL_PIPELINES, label: `all pipelines · ${total}` },
    ...(logs?.pipelines ?? []).map((p) => ({ value: p.pipeline, label: `${p.pipeline} · ${p.requests}` })),
  ];
}

export function logRows(logs: LogsResponse, selectedId: string | null): LogRowView[] {
  return logs.logs.map((log) => ({
    id: String(log.id),
    query: log.query,
    pipeline: log.pipeline,
    decision: log.decision ?? "search",
    answered: log.decision !== "abstain",
    total: formatMs(log.latency_ms.total),
    selected: String(log.id) === selectedId,
  }));
}

export function logDetailView(log: LogDetail): LogDetailView {
  const scores = log.scores && !Array.isArray(log.scores) ? log.scores : null;
  return {
    id: log.id,
    query: log.query,
    pipeline: log.pipeline,
    when: new Date(log.ts).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }),
    decision: log.decision ?? "search",
    answered: log.decision !== "abstain",
    latency: Object.entries(log.latency_ms).map(([stage, ms]) => ({ stage, ms: formatMs(ms) })),
    retrieved: (log.retrieved ?? []).map(displayControlId),
    gate: scores
      ? `top score ${formatNumber(scores.top_score, 4)} · τ ${scores.tau === null || scores.tau === undefined ? "none" : formatNumber(scores.tau, 2)}`
      : null,
    steps: (log.trace ?? []).map(traceStepView),
  };
}
