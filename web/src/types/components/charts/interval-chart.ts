import type { Interval } from "@/types/domain/metrics";

export interface IntervalSeriesPoint {
  name: string;
  interval: Interval | null;
}

export interface IntervalChartRow {
  key: string;
  label: string;
  highlight: boolean;
  series: IntervalSeriesPoint[];
}

export interface IntervalChartProps {
  rows: IntervalChartRow[];
  title: string;
}

export interface IntervalMark {
  key: string;
  name: string;
  index: number;
  cx: number;
  x1: number;
  x2: number;
  y: number;
  label: string;
}

export interface IntervalGeometry {
  width: number;
  height: number;
  plotLeft: number;
  plotRight: number;
  plotTop: number;
  plotBottom: number;
  ticks: { key: string; x: number; label: string }[];
  rows: { key: string; label: string; y: number; highlight: boolean; marks: IntervalMark[] }[];
  legend: { name: string; index: number }[];
}
