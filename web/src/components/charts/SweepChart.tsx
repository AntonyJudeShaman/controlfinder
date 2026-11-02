import { useSweepChart } from "@/hooks/components/charts/use-sweep-chart";
import { cn } from "@/lib/utils";
import type { SweepChartProps } from "@/types/components/charts/sweep-chart";

const LINE_CLASSES = ["stroke-foreground", "stroke-chart-4", "stroke-chart-3", "stroke-chart-5", "stroke-chart-2"];
const SWATCH_CLASSES = ["bg-foreground", "bg-chart-4", "bg-chart-3", "bg-chart-5", "bg-chart-2"];

export function SweepChart({ title, xLabel, series, chosenX }: SweepChartProps) {
  const geometry = useSweepChart(series, chosenX);
  return (
    <figure className="flex flex-col gap-3 border-2 border-foreground bg-card p-3 shadow-brutal">
      <figcaption className="font-mono text-xs font-bold tracking-widest">{title}</figcaption>
      <svg viewBox={`0 0 ${geometry.width} ${geometry.height}`} className="w-full" role="img" aria-label={title}>
        {geometry.yTicks.map((tick) => (
          <g key={tick.key}>
            <line
              x1={geometry.plotLeft}
              x2={geometry.plotRight}
              y1={tick.y}
              y2={tick.y}
              className="stroke-foreground/15"
            />
            <text x={geometry.plotLeft - 6} y={tick.y + 4} textAnchor="end" className="fill-foreground font-mono text-[11px]">
              {tick.label}
            </text>
          </g>
        ))}
        {geometry.xTicks.map((tick) => (
          <text
            key={tick.key}
            x={tick.x}
            y={geometry.plotBottom + 16}
            textAnchor="middle"
            className="fill-foreground font-mono text-[11px]"
          >
            {tick.label}
          </text>
        ))}
        <text
          x={(geometry.plotLeft + geometry.plotRight) / 2}
          y={geometry.height - 4}
          textAnchor="middle"
          className="fill-foreground font-mono text-[11px]"
        >
          {xLabel}
        </text>
        <rect
          x={geometry.plotLeft}
          y={geometry.plotTop}
          width={geometry.plotRight - geometry.plotLeft}
          height={geometry.plotBottom - geometry.plotTop}
          fill="none"
          strokeWidth="2"
          className="stroke-foreground"
        />
        {geometry.chosen !== null ? (
          <line
            x1={geometry.chosen}
            x2={geometry.chosen}
            y1={geometry.plotTop}
            y2={geometry.plotBottom}
            strokeWidth="2"
            strokeDasharray="6 4"
            className="stroke-destructive"
          />
        ) : null}
        {geometry.lines.map((line) => (
          <polyline
            key={line.name}
            points={line.points}
            fill="none"
            strokeWidth="2.5"
            strokeLinejoin="round"
            className={LINE_CLASSES[line.index]}
          />
        ))}
      </svg>
      <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs">
        {geometry.lines.map((line) => (
          <span key={line.name} className="flex items-center gap-2">
            <span className={cn("h-1 w-5", SWATCH_CLASSES[line.index])} />
            {line.name} · no gate {line.noGate}
          </span>
        ))}
      </div>
    </figure>
  );
}
