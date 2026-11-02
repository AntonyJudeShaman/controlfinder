import { z } from "zod";
import {
  LatencySchema,
  MeanIntervalSchema,
  MetricTableSchema,
  PairedTableSchema,
  QueryTypeSchema,
  ResampledTableSchema,
} from "@/types/domain/metrics";

export const AblationRowSchema = z.object({
  row: z.number(),
  retrieval: z.string(),
  strategy: z.string(),
  rerank: z.boolean(),
  metrics: MetricTableSchema,
  retrieval_ms_p50: z.number(),
});
export type AblationRow = z.infer<typeof AblationRowSchema>;

export const AblationComparisonSchema = z.object({
  name: z.string(),
  a: z.number(),
  b: z.number(),
  metrics: PairedTableSchema,
});
export type AblationComparison = z.infer<typeof AblationComparisonSchema>;

export const BaselineSystemSchema = z.object({ metrics: MetricTableSchema, latency_ms_p50: z.number() });
export type BaselineSystem = z.infer<typeof BaselineSystemSchema>;

export const BaselineComparisonSchema = z.object({
  a: z.string(),
  b: z.string(),
  subcat: MeanIntervalSchema,
  example: MeanIntervalSchema,
  all: MeanIntervalSchema,
});
export type BaselineComparison = z.infer<typeof BaselineComparisonSchema>;

export const AnswerSystemSchema = z.object({ metrics: ResampledTableSchema, latency_ms: LatencySchema });
export type AnswerSystem = z.infer<typeof AnswerSystemSchema>;

const QueryCountsSchema = z.record(QueryTypeSchema, z.number());
const QuestionCountsSchema = z.object({ all: z.number(), answerable: z.number(), unanswerable: z.number() });

export const AblationsSchema = z.object({
  primary_metric: z.string(),
  queries: QueryCountsSchema,
  rows: z.array(AblationRowSchema),
  comparisons: z.array(AblationComparisonSchema),
  production: z.object({ pick: z.number(), rule: z.string() }),
});
export type Ablations = z.infer<typeof AblationsSchema>;

export const BaselinesSchema = z.object({
  strategy: z.string(),
  queries: QueryCountsSchema,
  systems: z.record(z.string(), BaselineSystemSchema),
  comparisons: z.array(BaselineComparisonSchema),
});
export type Baselines = z.infer<typeof BaselinesSchema>;

export const AgentRunSchema = z.object({
  questions: QuestionCountsSchema,
  systems: z.record(z.string(), AnswerSystemSchema),
  versus_pipeline: z.record(z.string(), ResampledTableSchema),
  production_pick: z.object({ pick: z.string() }),
  agent: z.object({ tau: z.number().nullable(), tau_rule: z.string() }),
});
export type AgentRun = z.infer<typeof AgentRunSchema>;

export const SweepPointSchema = z.object({
  tau: z.number().nullable(),
  answer_rate: z.number().nullable(),
  abstention_precision: z.number().nullable(),
  abstention_recall: z.number().nullable(),
  abstention_f1: z.number().nullable(),
  answer_accuracy: z.number().nullable(),
});
export type SweepPoint = z.infer<typeof SweepPointSchema>;

export const SweepSchema = z.object({
  questions: z.number(),
  rule: z.string(),
  chosen: SweepPointSchema,
  points: z.array(SweepPointSchema),
});
export type Sweep = z.infer<typeof SweepSchema>;

export const FinalTestSchema = z.object({
  retrieval: z.object({
    queries: QueryCountsSchema,
    baselines: z.record(z.string(), BaselineSystemSchema),
    baseline_comparisons: z.array(BaselineComparisonSchema),
    rows: z.array(AblationRowSchema),
    comparisons: z.array(AblationComparisonSchema),
    production: z.object({ row: z.number() }),
  }),
  generation: z.object({
    questions: QuestionCountsSchema,
    systems: z.record(z.string(), AnswerSystemSchema),
    versus_pipeline: z.record(z.string(), ResampledTableSchema),
    not_run: z.record(z.string(), z.string()),
  }),
});
export type FinalTest = z.infer<typeof FinalTestSchema>;

export interface ResultsData {
  ablations: Ablations;
  baselines: Baselines;
  agent: AgentRun;
  sweep: Sweep;
  finalTest: FinalTest | null;
}

export interface ResultsState {
  data: ResultsData | null;
  error: string | null;
  requested: boolean;
}

export type ResultsActions = {
  load: () => Promise<void>;
};
