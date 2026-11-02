import { z } from "zod";

export const ClosestControlSchema = z.object({ control_id: z.string(), score: z.number().nullable() });

export const TraceStepSchema = z.object({
  node: z.string(),
  ms: z.number(),
  verdict: z.boolean().nullable().optional(),
  reply: z.string().optional(),
  model: z.string().optional(),
  query: z.string().optional(),
  controls: z.array(z.string()).optional(),
  top_score: z.number().nullable().optional(),
  tau: z.number().nullable().optional(),
  strong: z.boolean().optional(),
  retry: z.boolean().optional(),
  answer: z.string().optional(),
  input_tokens: z.number().nullable().optional(),
  output_tokens: z.number().nullable().optional(),
  citations: z.array(z.string()).optional(),
  invalid: z.array(z.string()).optional(),
  ok: z.boolean().optional(),
  reason: z.string().nullable().optional(),
  closest: z.array(ClosestControlSchema).optional(),
});
export type TraceStep = z.infer<typeof TraceStepSchema>;

export type TraceTone = "neutral" | "pass" | "fail";

export interface TraceStepView {
  key: string;
  index: number;
  node: string;
  ms: string;
  tone: TraceTone;
  facts: { label: string; value: string }[];
  controls: string[];
  text: string | null;
}
