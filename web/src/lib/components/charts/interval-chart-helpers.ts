import { formatNumber } from "@/lib/domain/metrics-helpers";
import type { IntervalChartRow, IntervalGeometry } from "@/types/components/charts/interval-chart";

const WIDTH = 720;
const LABEL_WIDTH = 200;
const ROW_HEIGHT = 34;
const TOP = 28;
const BOTTOM = 26;
const RIGHT = 24;

function niceStep(span: number): number {
  if (span <= 0.12) return 0.02;
  if (span <= 0.3) return 0.05;
  if (span <= 0.6) return 0.1;
  return 0.2;
}

export function intervalGeometry(rows: IntervalChartRow[]): IntervalGeometry {
  const values = rows.flatMap((row) =>
    row.series.flatMap((point) =>
      point.interval?.ci95 ? point.interval.ci95 : point.interval?.value != null ? [point.interval.value] : [],
    ),
  );
  const low = values.length ? Math.min(...values) : 0;
  const high = values.length ? Math.max(...values) : 1;
  const step = niceStep(high - low);
  const domainLow = Math.floor(low / step) * step;
  const domainHigh = Math.max(Math.ceil(high / step) * step, domainLow + step);
  const plotLeft = LABEL_WIDTH;
  const plotRight = WIDTH - RIGHT;
  const x = (value: number) => plotLeft + ((value - domainLow) / (domainHigh - domainLow)) * (plotRight - plotLeft);
  const tickCount = Math.round((domainHigh - domainLow) / step);
  const names = [...new Set(rows.flatMap((row) => row.series.map((point) => point.name)))];
  const spread = names.length > 1 ? 10 / (names.length - 1) : 0;
  const plotBottom = TOP + rows.length * ROW_HEIGHT;
  return {
    width: WIDTH,
    height: plotBottom + BOTTOM,
    plotLeft,
    plotRight,
    plotTop: TOP,
    plotBottom,
    ticks: Array.from({ length: tickCount + 1 }, (_, i) => {
      const value = domainLow + i * step;
      return { key: value.toFixed(3), x: x(value), label: formatNumber(value, 2) };
    }),
    rows: rows.map((row, rowIndex) => {
      const center = TOP + rowIndex * ROW_HEIGHT + ROW_HEIGHT / 2;
      return {
        key: row.key,
        label: row.label,
        y: center,
        highlight: row.highlight,
        marks: row.series.flatMap((point) => {
          const value = point.interval?.value;
          if (value === null || value === undefined) return [];
          const index = names.indexOf(point.name);
          const [lo, hi] = point.interval?.ci95 ?? [value, value];
          return [
            {
              key: `${row.key}-${point.name}`,
              name: point.name,
              index,
              cx: x(value),
              x1: x(lo),
              x2: x(hi),
              y: center - 5 + index * spread,
              label: `${point.name} ${formatNumber(value)} [${formatNumber(lo)}, ${formatNumber(hi)}]`,
            },
          ];
        }),
      };
    }),
    legend: names.map((name, index) => ({ name, index })),
  };
}
