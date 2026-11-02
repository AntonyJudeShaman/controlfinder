export interface SweepSeries {
  name: string;
  points: { x: number; y: number | null }[];
  noGate: number | null;
}

export interface SweepChartProps {
  title: string;
  xLabel: string;
  series: SweepSeries[];
  chosenX: number | null;
}

export interface SweepGeometry {
  width: number;
  height: number;
  plotLeft: number;
  plotRight: number;
  plotTop: number;
  plotBottom: number;
  xTicks: { key: string; x: number; label: string }[];
  yTicks: { key: string; y: number; label: string }[];
  lines: { name: string; index: number; points: string; noGate: string }[];
  chosen: number | null;
}
