import type { Interval, MeanInterval } from "@/types/domain/metrics";

export function fromMean(interval: MeanInterval): Interval {
  return { value: interval.mean, ci95: interval.ci95 };
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

export function formatSigned(value: number | null, digits = 3): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function formatCi(interval: Interval, digits = 3): string {
  return interval.ci95 ? `[${interval.ci95[0].toFixed(digits)}, ${interval.ci95[1].toFixed(digits)}]` : "";
}

export function formatMs(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? "—" : `${Math.round(ms).toLocaleString("en-US")} ms`;
}

export function excludesZero(interval: Interval): boolean {
  return interval.ci95 !== null && (interval.ci95[0] > 0 || interval.ci95[1] < 0);
}

export function outsideInterval(value: number | null, interval: Interval | null): boolean {
  return value !== null && interval?.ci95 != null && (value < interval.ci95[0] || value > interval.ci95[1]);
}

export function humanize(name: string): string {
  return name.replaceAll("_", " ");
}
