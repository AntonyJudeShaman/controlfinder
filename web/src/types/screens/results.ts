import type { IntervalChartRow } from "@/types/components/charts/interval-chart";
import type { SweepSeries } from "@/types/components/charts/sweep-chart";
import type { Loadable } from "@/types/domain/loadable";
import type { IntervalCell, QueryType, Split } from "@/types/domain/metrics";

export interface DiffCell extends IntervalCell {
  distinct: boolean;
}

export interface TableRowView {
  key: string;
  label: string;
  detail: string;
  production: boolean;
  cells: IntervalCell[];
}

export interface ComparisonView {
  key: string;
  name: string;
  metric: string;
  dev: DiffCell;
  test: DiffCell | null;
}

export interface ShiftView {
  key: string;
  what: string;
  metric: string;
  dev: string;
  test: IntervalCell;
}

export interface LatencyView {
  key: string;
  label: string;
  split: string;
  p50: string;
  p95: string;
}

export interface ResultsView {
  splits: Split[];
  split: Split;
  types: QueryType[];
  type: QueryType;
  testRun: boolean;
  queries: string;
  retrievalMetrics: string[];
  retrievalRows: TableRowView[];
  baselineRows: TableRowView[];
  recallChart: IntervalChartRow[];
  primaryMetric: string;
  comparisons: ComparisonView[];
  generationMetrics: string[];
  generationRows: TableRowView[];
  generationChart: IntervalChartRow[];
  versus: ComparisonView[];
  notRun: string[];
  sweep: { series: SweepSeries[]; chosenX: number | null; rule: string; chosen: string };
  shifts: ShiftView[];
  latency: LatencyView[];
}

export interface ResultsController {
  view: Loadable<ResultsView>;
  setSplit: (value: string) => void;
  setType: (value: string) => void;
}
