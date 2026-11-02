"use client";

import { IntervalChart } from "@/components/charts/IntervalChart";
import { SweepChart } from "@/components/charts/SweepChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBlock } from "@/components/layout/StatusBlock";
import { ComparisonTable } from "@/components/results/ComparisonTable";
import { MetricTable } from "@/components/results/MetricTable";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Field, FieldLabel } from "@/components/ui/field";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useResults } from "@/hooks/screens/use-results";

export function Results() {
  const { view, setSplit, setType } = useResults();
  if (view.status !== "success") {
    return (
      <>
        <PageHeader kicker="Evidence" title="Results" />
        <StatusBlock {...view} />
      </>
    );
  }
  const results = view.data;
  return (
    <>
      <PageHeader kicker="Evidence" title="Results">
        Every metric with its 95% bootstrap interval, read from the JSON files in results/. Dev numbers chose every
        setting; the sealed test split was run once at the end to check them.
      </PageHeader>

      <div className="flex flex-wrap items-end gap-6 border-2 border-foreground bg-card p-4 shadow-brutal">
        <Field className="w-fit">
          <FieldLabel>Split</FieldLabel>
          <ToggleGroup type="single" value={results.split} onValueChange={setSplit}>
            {results.splits.map((split) => (
              <ToggleGroupItem key={split} value={split}>
                {split}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        <Field className="w-fit">
          <FieldLabel>Query type</FieldLabel>
          <ToggleGroup type="single" value={results.type} onValueChange={setType}>
            {results.types.map((type) => (
              <ToggleGroupItem key={type} value={type}>
                {type}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        <Badge variant="outline">{results.queries}</Badge>
        {results.testRun ? null : <Badge variant="destructive">test split still sealed</Badge>}
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Retrieval · ablation rows</h2>
        <MetricTable metrics={results.retrievalMetrics} rows={results.retrievalRows} first="Row" second="Setup" />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Retrieval · phase 2 baselines</h2>
        <MetricTable metrics={results.retrievalMetrics} rows={results.baselineRows} first="System" second="Chunks" />
      </section>

      <IntervalChart rows={results.recallChart} title={`${results.primaryMetric} · dev vs test · ${results.type}`} />

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Paired differences</h2>
        <p className="max-w-3xl text-muted-foreground">
          Each row is one system minus another on the same queries. A difference counts as real only when its interval
          leaves out zero.
        </p>
        <ComparisonTable rows={results.comparisons} testRun={results.testRun} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Answering systems</h2>
        <MetricTable metrics={results.generationMetrics} rows={results.generationRows} first="System" second="Split" />
        {results.notRun.length > 0 ? (
          <Alert>
            <AlertTitle>Not run on test</AlertTitle>
            <AlertDescription>
              <ul className="flex flex-col gap-1">
                {results.notRun.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
      </section>

      <IntervalChart rows={results.generationChart} title="answering systems · dev vs test" />

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Versus the plain pipeline</h2>
        <ComparisonTable rows={results.versus} testRun={results.testRun} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Evidence gate sweep (dev)</h2>
        <p className="max-w-3xl text-muted-foreground">
          {results.sweep.rule} Chosen: {results.sweep.chosen}.
        </p>
        <SweepChart
          title="agent metrics as the evidence threshold τ rises"
          xLabel="τ (reranker logit)"
          series={results.sweep.series}
          chosenX={results.sweep.chosenX}
        />
      </section>

      {results.testRun ? (
        <section className="flex flex-col gap-3">
          <h2 className="text-3xl font-bold tracking-tighter uppercase">Where test disagrees with dev</h2>
          <p className="max-w-3xl text-muted-foreground">
            Metrics whose dev number falls outside the test 95% interval. The reasons are discussed in
            docs/learn/06.
          </p>
          {results.shifts.length === 0 ? (
            <Alert>
              <AlertTitle>None</AlertTitle>
              <AlertDescription>Every dev number falls inside its test interval.</AlertDescription>
            </Alert>
          ) : (
            <div className="border-2 border-foreground bg-card shadow-brutal">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>What</TableHead>
                    <TableHead>Metric</TableHead>
                    <TableHead>Dev</TableHead>
                    <TableHead>Test</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {results.shifts.map((shift) => (
                    <TableRow key={shift.key}>
                      <TableCell className="font-bold">{shift.what}</TableCell>
                      <TableCell className="font-mono">{shift.metric}</TableCell>
                      <TableCell className="font-mono">{shift.dev}</TableCell>
                      <TableCell className="font-mono">
                        <span className="font-bold">{shift.test.value}</span>{" "}
                        <span className="text-muted-foreground">{shift.test.ci}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-3xl font-bold tracking-tighter uppercase">Latency</h2>
        <div className="border-2 border-foreground bg-card shadow-brutal">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stage</TableHead>
                <TableHead>Split</TableHead>
                <TableHead>p50</TableHead>
                <TableHead>p95</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.latency.map((row) => (
                <TableRow key={row.key}>
                  <TableCell className="font-bold">{row.label}</TableCell>
                  <TableCell className="font-mono uppercase">{row.split}</TableCell>
                  <TableCell className="font-mono">{row.p50}</TableCell>
                  <TableCell className="font-mono">{row.p95}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </>
  );
}
