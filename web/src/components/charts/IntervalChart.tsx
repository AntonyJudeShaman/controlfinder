import { useIntervalChart } from "@/hooks/components/charts/use-interval-chart";
import { cn } from "@/lib/utils";
import type { IntervalChartProps } from "@/types/components/charts/interval-chart";

const MARK_CLASSES = ["fill-foreground stroke-foreground", "fill-accent stroke-foreground", "fill-chart-4 stroke-foreground"];

export function IntervalChart({ rows, title }: IntervalChartProps) {
  const geometry = useIntervalChart(rows);
  return (
    <figure className="flex flex-col gap-2 border-2 border-foreground bg-card p-3 shadow-brutal">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-xs font-bold tracking-widest uppercase">{title}</span>
        <span className="flex gap-3 font-mono text-xs">
          {geometry.legend.map((item) => (
            <span key={item.name} className="flex items-center gap-1">
              <svg viewBox="0 0 10 10" className="size-3">
                <rect x="1" y="1" width="8" height="8" strokeWidth="1.5" className={MARK_CLASSES[item.index]} />
              </svg>
              {item.name}
            </span>
          ))}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${geometry.width} ${geometry.height}`} className="w-full" role="img" aria-label={title}>
        {geometry.ticks.map((tick) => (
          <g key={tick.key}>
            <line
              x1={tick.x}
              x2={tick.x}
              y1={geometry.plotTop}
              y2={geometry.plotBottom}
              className="stroke-foreground/15"
            />
            <text x={tick.x} y={geometry.plotBottom + 16} textAnchor="middle" className="fill-foreground font-mono text-[11px]">
              {tick.label}
            </text>
          </g>
        ))}
        {geometry.rows.map((row) => (
          <g key={row.key}>
            {row.highlight ? (
              <rect
                x={0}
                y={row.y - 16}
                width={geometry.width}
                height={32}
                className="fill-accent/40"
              />
            ) : null}
            <text x={8} y={row.y + 4} className={cn("fill-foreground text-[12px]", row.highlight && "font-bold")}>
              {row.label}
            </text>
            {row.marks.map((mark) => (
              <g key={mark.key}>
                <title>{mark.label}</title>
                <line x1={mark.x1} x2={mark.x2} y1={mark.y} y2={mark.y} strokeWidth="2" className="stroke-foreground" />
                <line x1={mark.x1} x2={mark.x1} y1={mark.y - 4} y2={mark.y + 4} strokeWidth="2" className="stroke-foreground" />
                <line x1={mark.x2} x2={mark.x2} y1={mark.y - 4} y2={mark.y + 4} strokeWidth="2" className="stroke-foreground" />
                <rect
                  x={mark.cx - 4.5}
                  y={mark.y - 4.5}
                  width={9}
                  height={9}
                  strokeWidth="1.5"
                  className={MARK_CLASSES[mark.index]}
                />
              </g>
            ))}
          </g>
        ))}
      </svg>
    </figure>
  );
}
