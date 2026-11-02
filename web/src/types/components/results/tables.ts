import type { ComparisonView, TableRowView } from "@/types/screens/results";

export interface MetricTableProps {
  metrics: string[];
  rows: TableRowView[];
  first: string;
  second: string;
}

export interface ComparisonTableProps {
  rows: ComparisonView[];
  testRun: boolean;
}
