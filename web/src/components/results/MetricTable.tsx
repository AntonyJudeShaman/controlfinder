import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MetricTableProps } from "@/types/components/results/tables";

export function MetricTable({ metrics, rows, first, second }: MetricTableProps) {
  return (
    <div className="border-2 border-foreground bg-card shadow-brutal">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{first}</TableHead>
            <TableHead>{second}</TableHead>
            {metrics.map((metric) => (
              <TableHead key={metric}>{metric}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key} data-state={row.production ? "selected" : undefined}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <span className="font-bold">{row.label}</span>
                  {row.production ? <Badge>production</Badge> : null}
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">{row.detail}</TableCell>
              {row.cells.map((cell, index) => (
                <TableCell key={metrics[index]} className="font-mono">
                  <div className="flex flex-col">
                    <span className="font-bold">{cell.value}</span>
                    <span className="text-[0.7rem] text-muted-foreground">{cell.ci}</span>
                  </div>
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
