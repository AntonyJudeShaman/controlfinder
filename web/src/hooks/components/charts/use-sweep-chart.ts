import { useMemo } from "react";
import { sweepGeometry } from "@/lib/components/charts/sweep-chart-helpers";
import type { SweepGeometry, SweepSeries } from "@/types/components/charts/sweep-chart";

export function useSweepChart(series: SweepSeries[], chosenX: number | null): SweepGeometry {
  return useMemo(() => sweepGeometry(series, chosenX), [series, chosenX]);
}
