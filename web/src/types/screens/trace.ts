import type { Keyed, Loadable } from "@/types/domain/loadable";
import type { LogDetail, LogsResponse } from "@/types/domain/logs";
import type { TraceStepView } from "@/types/domain/trace";

export interface TraceState {
  logs: Keyed<LogsResponse> | null;
  detail: Keyed<LogDetail> | null;
}

export type TraceAction =
  | { type: "logs"; key: string; result: Loadable<LogsResponse> }
  | { type: "detail"; key: string; result: Loadable<LogDetail> };

export interface LogRowView {
  id: string;
  query: string;
  pipeline: string;
  decision: string;
  answered: boolean;
  total: string;
  selected: boolean;
}

export interface LogDetailView {
  id: number;
  query: string;
  pipeline: string;
  when: string;
  decision: string;
  answered: boolean;
  latency: { stage: string; ms: string }[];
  retrieved: string[];
  gate: string | null;
  steps: TraceStepView[];
}

export interface TraceController {
  pipelines: { value: string; label: string }[];
  pipeline: string;
  allPipelines: string;
  logs: Loadable<LogRowView[]>;
  detail: Loadable<LogDetailView> | null;
  selectPipeline: (value: string) => void;
  selectLog: (id: string) => void;
}
