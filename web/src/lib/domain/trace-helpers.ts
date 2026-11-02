import { displayControlId } from "@/lib/domain/controls-helpers";
import { formatMs, formatNumber, humanize } from "@/lib/domain/metrics-helpers";
import type { TraceStep, TraceStepView, TraceTone } from "@/types/domain/trace";

function yesNo(value: boolean | undefined): string {
  return value ? "yes" : "no";
}

function ids(controls: string[] | undefined): string {
  return controls && controls.length ? controls.map(displayControlId).join(", ") : "none";
}

function tone(step: TraceStep): TraceTone {
  if (step.node === "abstain") return "fail";
  if (step.node === "grade_evidence") return step.strong ? "pass" : "fail";
  if (step.node === "verify_citations") return step.ok ? "pass" : "fail";
  if (step.node === "scope_check") return step.verdict === false ? "fail" : "pass";
  return "neutral";
}

function facts(step: TraceStep): { label: string; value: string }[] {
  switch (step.node) {
    case "scope_check":
      return [
        { label: "verdict", value: step.verdict === null ? "unclear, treated as in scope" : step.verdict ? "in scope" : "out of scope" },
        { label: "model", value: step.model ?? "—" },
      ];
    case "retrieve":
      return [{ label: "query", value: step.query ?? "—" }];
    case "grade_evidence":
      return [
        { label: "top reranker score", value: formatNumber(step.top_score, 4) },
        { label: "τ", value: step.tau === null || step.tau === undefined ? "none (no gate)" : formatNumber(step.tau, 2) },
        { label: "strong enough", value: yesNo(step.strong) },
      ];
    case "rewrite":
      return [
        { label: "new query", value: step.query ?? "—" },
        { label: "model", value: step.model ?? "—" },
      ];
    case "generate":
      return [
        { label: "retry", value: yesNo(step.retry) },
        { label: "model", value: step.model ?? "—" },
        { label: "tokens in / out", value: `${step.input_tokens ?? "—"} / ${step.output_tokens ?? "—"}` },
      ];
    case "verify_citations":
      return [
        { label: "cited", value: ids(step.citations) },
        { label: "not in context", value: ids(step.invalid) },
        { label: "all citations valid", value: yesNo(step.ok) },
      ];
    case "abstain":
      return [{ label: "reason", value: humanize(step.reason ?? "unknown") }];
    default:
      return [];
  }
}

function controls(step: TraceStep): string[] {
  if (step.node === "retrieve") return (step.controls ?? []).map(displayControlId);
  if (step.node === "abstain") {
    return (step.closest ?? []).map((c) => `${displayControlId(c.control_id)} ${formatNumber(c.score, 2)}`);
  }
  return [];
}

export function traceStepView(step: TraceStep, index: number): TraceStepView {
  return {
    key: `${index}-${step.node}`,
    index: index + 1,
    node: humanize(step.node),
    ms: formatMs(step.ms),
    tone: tone(step),
    facts: facts(step),
    controls: controls(step),
    text: step.node === "generate" ? (step.answer ?? null) : step.node === "scope_check" ? (step.reply ?? null) : null,
  };
}
