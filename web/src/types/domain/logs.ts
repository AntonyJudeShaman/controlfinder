import { z } from "zod";
import { TraceStepSchema } from "@/types/domain/trace";

export const LogSummarySchema = z.object({
  id: z.number(),
  ts: z.string(),
  query: z.string(),
  pipeline: z.string(),
  decision: z.string().nullable(),
  latency_ms: z.record(z.string(), z.number()),
});
export type LogSummary = z.infer<typeof LogSummarySchema>;

export const LogsResponseSchema = z.object({
  pipelines: z.array(z.object({ pipeline: z.string(), requests: z.number() })),
  logs: z.array(LogSummarySchema),
});
export type LogsResponse = z.infer<typeof LogsResponseSchema>;

export const LogDetailSchema = LogSummarySchema.extend({
  retrieved: z.array(z.string()).nullable(),
  scores: z
    .union([
      z.array(z.number()),
      z.object({ top_score: z.number().nullable().optional(), tau: z.number().nullable().optional() }),
    ])
    .nullable(),
  trace: z.array(TraceStepSchema).nullable(),
});
export type LogDetail = z.infer<typeof LogDetailSchema>;
