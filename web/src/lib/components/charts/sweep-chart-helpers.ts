import { formatNumber } from "@/lib/domain/metrics-helpers";
import type { SweepGeometry, SweepSeries } from "@/types/components/charts/sweep-chart";

const WIDTH = 720;
const HEIGHT = 320;
const LEFT = 44;
const RIGHT = 16;
const TOP = 16;
const BOTTOM = 36;

export function sweepGeometry(series: SweepSeries[], chosenX: number | null): SweepGeometry {
  const xs = series.flatMap((line) => line.points.map((point) => point.x));
  const xLow = xs.length ? Math.min(...xs) : 0;
  const xHigh = xs.length ? Math.max(...xs) : 1;
  const plotLeft = LEFT;
  const plotRight = WIDTH - RIGHT;
  const plotTop = TOP;
  const plotBottom = HEIGHT - BOTTOM;
  const x = (value: number) => plotLeft + ((value - xLow) / (xHigh - xLow || 1)) * (plotRight - plotLeft);
  const y = (value: number) => plotBottom - value * (plotBottom - plotTop);
  const xStep = Math.max(1, Math.round((xHigh - xLow) / 8));
  const firstTick = Math.ceil(xLow / xStep) * xStep;
  return {
    width: WIDTH,
    height: HEIGHT,
    plotLeft,
    plotRight,
    plotTop,
    plotBottom,
    xTicks: Array.from({ length: Math.floor((xHigh - firstTick) / xStep) + 1 }, (_, i) => {
      const value = firstTick + i * xStep;
      return { key: String(value), x: x(value), label: String(value) };
    }),
    yTicks: [0, 0.25, 0.5, 0.75, 1].map((value) => ({ key: String(value), y: y(value), label: formatNumber(value, 2) })),
    lines: series.map((line, index) => ({
      name: line.name,
      index,
      points: line.points
        .flatMap((point) => (point.y === null ? [] : [`${x(point.x).toFixed(1)},${y(point.y).toFixed(1)}`]))
        .join(" "),
      noGate: formatNumber(line.noGate),
    })),
    chosen: chosenX === null ? null : x(chosenX),
  };
}
