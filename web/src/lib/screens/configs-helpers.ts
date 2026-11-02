import { formatCi, formatMs, formatNumber, humanize } from "@/lib/domain/metrics-helpers";
import { pickParam } from "@/lib/domain/url-helpers";
import type { Interval, IntervalCell } from "@/types/domain/metrics";
import type {
  ConfigsScreenAction,
  ConfigsScreenState,
  ConfigsView,
  KnobParams,
  SearchResponse,
  SearchView,
} from "@/types/screens/configs";
import type { ConfigsResponse, SearchConfig } from "@/types/stores/modules/configs";

export function configsScreenReducer(state: ConfigsScreenState, action: ConfigsScreenAction): ConfigsScreenState {
  switch (action.type) {
    case "draft":
      return { ...state, draft: action.value };
    case "search":
      return { ...state, search: { key: action.key, result: action.result } };
  }
}

export function readKnobs(params: KnobParams, configs: ConfigsResponse): SearchConfig {
  const production = configs.production.search;
  const { min, max } = configs.knobs.k;
  const k = Number(params.k);
  return {
    retrieval: pickParam(params.retrieval, configs.knobs.retrieval, production.retrieval),
    strategy: pickParam(params.strategy, configs.knobs.strategy, production.strategy),
    k: Number.isInteger(k) && k >= min && k <= max ? k : production.k,
    rerank: params.rerank === null ? production.rerank : params.rerank === "1",
  };
}

export function knobParams(config: SearchConfig): Record<string, string> {
  return {
    retrieval: config.retrieval,
    strategy: config.strategy,
    k: String(config.k),
    rerank: config.rerank ? "1" : "0",
  };
}

export function searchPath(query: string, config: SearchConfig): string {
  const params = new URLSearchParams({ q: query, ...knobParams(config) });
  return `/search?${params.toString()}`;
}

function cell(interval: Interval): IntervalCell {
  return { value: formatNumber(interval.value), ci: formatCi(interval) };
}

function sameConfig(a: SearchConfig, b: SearchConfig): boolean {
  return a.retrieval === b.retrieval && a.strategy === b.strategy && a.k === b.k && a.rerank === b.rerank;
}

export function configsView(configs: ConfigsResponse, current: SearchConfig): ConfigsView {
  const generationMetrics = Object.keys(configs.generation[0]?.dev ?? {});
  const cells = (table: Record<string, Interval>) =>
    generationMetrics.map((metric) => cell(table[metric] ?? { value: null, ci95: null }));
  return {
    metric: configs.metric,
    retrievalRule: configs.rules.retrieval,
    tauRule: configs.rules.tau,
    productionSearch: configs.production.search,
    productionSystem: humanize(configs.production.system),
    productionSystemDev: Object.entries(
      configs.generation.find((system) => system.system === configs.production.system)?.dev ?? {},
    ).map(([metric, interval]) => ({ metric: humanize(metric), cell: cell(interval) })),
    retrieval: configs.retrieval.map((config) => ({
      id: config.id,
      name: config.name,
      stage: config.phase === 2 ? "Phase 2 baseline" : "Phase 3 ablation",
      retrieval: config.retrieval,
      strategy: config.strategy,
      rerank: config.rerank,
      dev: cell(config.dev),
      test: config.test ? cell(config.test) : null,
      production: config.production,
      live: config.live,
      config,
    })),
    generationMetrics: generationMetrics.map(humanize),
    generation: configs.generation.map((system) => ({
      system: system.system,
      label: humanize(system.system),
      tau: system.tau === null ? "none" : formatNumber(system.tau, 2),
      production: system.production,
      splits: [
        { key: `${system.system}-dev`, split: "dev", first: true, cells: cells(system.dev) },
        { key: `${system.system}-test`, split: "test", first: false, cells: system.test ? cells(system.test) : null },
      ],
    })),
    knobs: {
      retrieval: configs.knobs.retrieval,
      strategy: configs.knobs.strategy,
      kMin: configs.knobs.k.min,
      kMax: configs.knobs.k.max,
      current,
      isProduction: sameConfig(current, configs.production.search),
    },
  };
}

export function searchView(response: SearchResponse): SearchView {
  return {
    query: response.query,
    scoreKind: humanize(response.score_kind),
    production: response.production,
    hits: response.hits.map((hit) => ({
      key: hit.chunk_id,
      rank: hit.rank,
      control: hit,
      score: formatNumber(hit.score, 4),
      text: hit.text.length > 360 ? `${hit.text.slice(0, 360)}…` : hit.text,
    })),
    latency: Object.entries(response.latency_ms).map(([stage, ms]) => ({ stage, ms: formatMs(ms) })),
  };
}
