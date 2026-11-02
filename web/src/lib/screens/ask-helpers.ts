import { formatMs, formatNumber, humanize } from "@/lib/domain/metrics-helpers";
import { traceStepView } from "@/lib/domain/trace-helpers";
import type { LogsResponse } from "@/types/domain/logs";
import type { AskAction, AskResponse, AskState, AskView, SystemOption } from "@/types/screens/ask";
import type { ConfigsResponse } from "@/types/stores/modules/configs";

export const EXAMPLES_PIPELINE = "agent/eval-dev";

export const INITIAL_ASK_STATE: AskState = { question: "", asked: null, pending: null, examples: { status: "loading" } };

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "question":
      return { ...state, question: action.value };
    case "asking":
      return { ...state, question: action.question, pending: action.key };
    case "answered":
      return action.key === state.pending
        ? { ...state, pending: null, asked: { key: action.key, result: action.result } }
        : state;
    case "examples":
      return { ...state, examples: action.result };
  }
}

export function systemOptions(configs: ConfigsResponse): SystemOption[] {
  return configs.generation.map((system) => ({
    value: system.system,
    label: humanize(system.system),
    production: system.production,
  }));
}

export function exampleQuestions(logs: LogsResponse): string[] {
  return [...new Set(logs.logs.map((log) => log.query))].sort((a, b) => a.localeCompare(b));
}

export function askView(response: AskResponse): AskView {
  return {
    answered: response.decision === "answer",
    system: humanize(response.system),
    production: response.production,
    answer: response.answer,
    reason: response.reason ? humanize(response.reason) : null,
    citations: response.citations.map((citation) => ({ control: citation, valid: citation.valid })),
    context: response.context,
    closest: response.closest.map((control) => ({ control, score: formatNumber(control.score, 2) })),
    steps: response.trace.map(traceStepView),
    llmCalls: response.llm_calls,
    latency: Object.entries(response.latency_ms).map(([stage, ms]) => ({ stage, ms: formatMs(ms) })),
    logId: response.log_id,
  };
}
