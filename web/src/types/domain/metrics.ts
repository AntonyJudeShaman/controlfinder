import { z } from "zod";

export const CiSchema = z.tuple([z.number(), z.number()]);

export const IntervalSchema = z.object({
  value: z.number().nullable(),
  ci95: CiSchema.nullable(),
});
export type Interval = z.infer<typeof IntervalSchema>;

export interface IntervalCell {
  value: string;
  ci: string;
}

export const MeanIntervalSchema = z.object({ mean: z.number(), ci95: CiSchema });
export type MeanInterval = z.infer<typeof MeanIntervalSchema>;

export const LatencySchema = z.object({ p50: z.number(), p95: z.number() });
export type Latency = z.infer<typeof LatencySchema>;

export const QueryTypeSchema = z.enum(["all", "subcat", "example"]);
export type QueryType = z.infer<typeof QueryTypeSchema>;

export const SplitSchema = z.enum(["dev", "test"]);
export type Split = z.infer<typeof SplitSchema>;

export const MetricTableSchema = z.record(QueryTypeSchema, z.record(z.string(), MeanIntervalSchema));
export type MetricTable = z.infer<typeof MetricTableSchema>;

export const PairedTableSchema = z.record(z.string(), z.record(QueryTypeSchema, MeanIntervalSchema));
export type PairedTable = z.infer<typeof PairedTableSchema>;

export const ResampledTableSchema = z.record(z.string(), IntervalSchema);
export type ResampledTable = z.infer<typeof ResampledTableSchema>;
