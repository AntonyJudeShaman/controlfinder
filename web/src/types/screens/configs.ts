import type { ChangeEvent, FormEvent } from "react";
import { z } from "zod";
import { ControlBriefSchema } from "@/types/domain/controls";
import type { ControlBrief } from "@/types/domain/controls";
import type { Keyed, Loadable } from "@/types/domain/loadable";
import type { IntervalCell } from "@/types/domain/metrics";
import { SearchConfigSchema } from "@/types/stores/modules/configs";
import type { RetrievalConfig, SearchConfig } from "@/types/stores/modules/configs";

export const SearchHitSchema = ControlBriefSchema.extend({
  rank: z.number(),
  parent_id: z.string(),
  chunk_id: z.string(),
  score: z.number(),
  text: z.string(),
});

export const SearchResponseSchema = z.object({
  query: z.string(),
  config: SearchConfigSchema,
  production: z.boolean(),
  score_kind: z.string(),
  hits: z.array(SearchHitSchema),
  latency_ms: z.record(z.string(), z.number()),
  log_id: z.number(),
});
export type SearchResponse = z.infer<typeof SearchResponseSchema>;

export interface ConfigsScreenState {
  draft: string;
  search: Keyed<SearchResponse> | null;
}

export type ConfigsScreenAction =
  | { type: "draft"; value: string }
  | { type: "search"; key: string; result: Loadable<SearchResponse> };

export interface KnobParams {
  retrieval: string | null;
  strategy: string | null;
  k: string | null;
  rerank: string | null;
}

export interface RetrievalRowView {
  id: string;
  name: string;
  stage: string;
  retrieval: string;
  strategy: string;
  rerank: boolean;
  dev: IntervalCell;
  test: IntervalCell | null;
  production: boolean;
  live: boolean;
  config: RetrievalConfig;
}

export interface GenerationSplitView {
  key: string;
  split: string;
  first: boolean;
  cells: IntervalCell[] | null;
}

export interface GenerationRowView {
  system: string;
  label: string;
  tau: string;
  production: boolean;
  splits: GenerationSplitView[];
}

export interface KnobsView {
  retrieval: string[];
  strategy: string[];
  kMin: number;
  kMax: number;
  current: SearchConfig;
  isProduction: boolean;
}

export interface HitView {
  key: string;
  rank: number;
  control: ControlBrief;
  score: string;
  text: string;
}

export interface SearchView {
  query: string;
  scoreKind: string;
  production: boolean;
  hits: HitView[];
  latency: { stage: string; ms: string }[];
}

export interface ConfigsView {
  metric: string;
  retrievalRule: string;
  tauRule: string;
  productionSearch: SearchConfig;
  productionSystem: string;
  productionSystemDev: { metric: string; cell: IntervalCell }[];
  retrieval: RetrievalRowView[];
  generationMetrics: string[];
  generation: GenerationRowView[];
  knobs: KnobsView;
}

export interface ConfigsController {
  view: Loadable<ConfigsView>;
  draft: string;
  search: Loadable<SearchView> | null;
  changeDraft: (event: ChangeEvent<HTMLInputElement>) => void;
  submit: (event: FormEvent<HTMLFormElement>) => void;
  setRetrieval: (value: string) => void;
  setStrategy: (value: string) => void;
  setK: (value: number[]) => void;
  setRerank: (checked: boolean) => void;
  tryConfig: (config: RetrievalConfig) => void;
  resetToProduction: () => void;
}
