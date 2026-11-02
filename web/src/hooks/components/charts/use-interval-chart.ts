import { useMemo } from "react";
import { intervalGeometry } from "@/lib/components/charts/interval-chart-helpers";
import type { IntervalChartRow, IntervalGeometry } from "@/types/components/charts/interval-chart";

export function useIntervalChart(rows: IntervalChartRow[]): IntervalGeometry {
  return useMemo(() => intervalGeometry(rows), [rows]);
}
