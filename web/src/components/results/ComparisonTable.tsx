import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ComparisonTableProps } from "@/types/components/results/tables";

export function ComparisonTable({ rows, testRun }: ComparisonTableProps) {
  return (
    <div className="border-2 border-foreground bg-card shadow-brutal">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Difference</TableHead>
            <TableHead>Metric</TableHead>
            <TableHead>Dev</TableHead>
            <TableHead>Test</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="font-bold whitespace-normal">{row.name}</TableCell>
              <TableCell className="font-mono">{row.metric}</TableCell>
              {[row.dev, row.test].map((cell, index) => (
                <TableCell key={index === 0 ? "dev" : "test"} className="font-mono">
                  {cell ? (
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{cell.value}</span>
                      <span className="text-muted-foreground">{cell.ci}</span>
                      {cell.distinct ? <Badge variant="secondary">CI excludes 0</Badge> : null}
                    </div>
                  ) : (
                    <span className="text-muted-foreground">{testRun ? "not run" : "sealed"}</span>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
