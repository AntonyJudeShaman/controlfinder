import { z } from "zod";
import { IntervalSchema, ResampledTableSchema } from "@/types/domain/metrics";

export const SearchConfigSchema = z.object({
  retrieval: z.string(),
  strategy: z.string(),
  k: z.number(),
  rerank: z.boolean(),
});
export type SearchConfig = z.infer<typeof SearchConfigSchema>;

export const RetrievalConfigSchema = z.object({
  id: z.string(),
  phase: z.number(),
  name: z.string(),
  retrieval: z.string(),
  strategy: z.string(),
  rerank: z.boolean(),
  dev: IntervalSchema,
  test: IntervalSchema.nullable(),
  live: z.boolean(),
  production: z.boolean(),
});
export type RetrievalConfig = z.infer<typeof RetrievalConfigSchema>;

export const GenerationConfigSchema = z.object({
  system: z.string(),
  tau: z.number().nullable(),
  dev: ResampledTableSchema,
  test: ResampledTableSchema.nullable(),
  production: z.boolean(),
});
export type GenerationConfig = z.infer<typeof GenerationConfigSchema>;

export const ConfigsResponseSchema = z.object({
  metric: z.string(),
  retrieval: z.array(RetrievalConfigSchema),
  generation: z.array(GenerationConfigSchema),
  rules: z.object({ retrieval: z.string(), tau: z.string() }),
  knobs: z.object({
    retrieval: z.array(z.string()),
    strategy: z.array(z.string()),
    k: z.object({ min: z.number(), max: z.number(), default: z.number() }),
  }),
  production: z.object({ search: SearchConfigSchema, system: z.string() }),
});
export type ConfigsResponse = z.infer<typeof ConfigsResponseSchema>;

export interface ConfigsState {
  data: ConfigsResponse | null;
  error: string | null;
  requested: boolean;
}

export type ConfigsActions = {
  load: () => Promise<void>;
};
