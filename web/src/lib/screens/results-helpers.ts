import {
  excludesZero,
  formatCi,
  formatMs,
  formatNumber,
  formatSigned,
  fromMean,
  humanize,
  outsideInterval,
} from "@/lib/domain/metrics-helpers";
import { QueryTypeSchema, SplitSchema } from "@/types/domain/metrics";
import type { Interval, IntervalCell, MeanInterval, MetricTable, QueryType, Split } from "@/types/domain/metrics";
import type { ComparisonView, DiffCell, LatencyView, ResultsView, ShiftView, TableRowView } from "@/types/screens/results";
import { SweepPointSchema } from "@/types/stores/modules/results";
import type { AblationRow, ResultsData, SweepPoint } from "@/types/stores/modules/results";

const EMPTY: Interval = { value: null, ci95: null };

function mean(interval: MeanInterval | undefined): Interval {
  return interval ? fromMean(interval) : EMPTY;
}

function cell(interval: Interval | undefined): IntervalCell {
  const safe = interval ?? EMPTY;
  return { value: formatNumber(safe.value), ci: formatCi(safe) };
}

function diff(interval: Interval | undefined): DiffCell {
  const safe = interval ?? EMPTY;
  return { value: formatSigned(safe.value), ci: formatCi(safe), distinct: excludesZero(safe) };
}

function rowDetail(row: AblationRow): string {
  return `${row.retrieval} · ${row.strategy}${row.rerank ? " · reranked" : ""}`;
}

function sweepMetrics(): (keyof Omit<SweepPoint, "tau">)[] {
  return SweepPointSchema.keyof()
    .options.flatMap((key) => (key === "tau" ? [] : [key]));
}

export function resultsView(data: ResultsData, requestedSplit: Split, type: QueryType): ResultsView {
  const test = data.finalTest;
  const split: Split = test ? requestedSplit : "dev";
  const primary = data.ablations.primary_metric;
  const productionRow = data.ablations.production.pick;
  const productionSystem = data.agent.production_pick.pick;
  const rows = split === "test" && test ? test.retrieval.rows : data.ablations.rows;
  const baselines = split === "test" && test ? test.retrieval.baselines : data.baselines.systems;
  const retrievalMetrics = Object.keys(data.ablations.rows[0]?.metrics.all ?? {});
  const tableCells = (table: MetricTable) => retrievalMetrics.map((metric) => cell(mean(table[type][metric])));
  const queryCount = split === "test" && test ? test.retrieval.queries[type] : data.ablations.queries[type];

  const recallChart = [
    ...Object.entries(data.baselines.systems).map(([name, system]) => ({
      key: `baseline-${name}`,
      label: `${name} (phase 2)`,
      highlight: false,
      series: [
        { name: "dev", interval: mean(system.metrics[type][primary]) },
        { name: "test", interval: test ? mean(test.retrieval.baselines[name]?.metrics[type][primary]) : null },
      ],
    })),
    ...data.ablations.rows.map((row) => ({
      key: `row-${row.row}`,
      label: `row ${row.row} · ${row.retrieval}${row.rerank ? " + rerank" : ""}`,
      highlight: row.row === productionRow,
      series: [
        { name: "dev", interval: mean(row.metrics[type][primary]) },
        {
          name: "test",
          interval: test ? mean(test.retrieval.rows.find((r) => r.row === row.row)?.metrics[type][primary]) : null,
        },
      ],
    })),
  ];

  const comparisons: ComparisonView[] = [
    ...data.baselines.comparisons.map((comparison) => {
      const onTest = test?.retrieval.baseline_comparisons.find((c) => c.a === comparison.a && c.b === comparison.b);
      return {
        key: `${comparison.a}-${comparison.b}`,
        name: `${comparison.a} − ${comparison.b}`,
        metric: primary,
        dev: diff(fromMean(comparison[type])),
        test: onTest ? diff(fromMean(onTest[type])) : null,
      };
    }),
    ...data.ablations.comparisons.flatMap((comparison) =>
      Object.entries(comparison.metrics).map(([metric, byType]) => {
        const onTest = test?.retrieval.comparisons.find((c) => c.name === comparison.name)?.metrics[metric];
        return {
          key: `${comparison.name}-${metric}`,
          name: `${comparison.name} (row ${comparison.a} − row ${comparison.b})`,
          metric,
          dev: diff(mean(byType[type])),
          test: onTest ? diff(mean(onTest[type])) : null,
        };
      }),
    ),
  ];

  const devSystems = Object.entries(data.agent.systems);
  const generationMetrics = Object.keys(devSystems[0]?.[1].metrics ?? {});
  const generationRows: TableRowView[] = devSystems.flatMap(([system, devRun]) => {
    const testRun = test?.generation.systems[system];
    const row = (splitName: Split, metrics: Record<string, Interval>) => ({
      key: `${system}-${splitName}`,
      label: humanize(system),
      detail: splitName,
      production: system === productionSystem,
      cells: generationMetrics.map((metric) => cell(metrics[metric])),
    });
    return testRun ? [row("dev", devRun.metrics), row("test", testRun.metrics)] : [row("dev", devRun.metrics)];
  });

  const comparedMetrics = Object.keys(Object.values(data.agent.versus_pipeline)[0] ?? {});
  const shareMetrics = comparedMetrics.filter((metric) =>
    devSystems.every(([, run]) => (run.metrics[metric]?.value ?? 0) <= 1),
  );
  const generationChart = shareMetrics.flatMap((metric) =>
    devSystems.map(([system, run]) => ({
      key: `${metric}-${system}`,
      label: `${humanize(metric)} · ${humanize(system)}`,
      highlight: system === productionSystem,
      series: [
        { name: "dev", interval: run.metrics[metric] ?? EMPTY },
        { name: "test", interval: test?.generation.systems[system]?.metrics[metric] ?? null },
      ],
    })),
  );

  const versus: ComparisonView[] = Object.entries(data.agent.versus_pipeline).flatMap(([system, metrics]) =>
    Object.entries(metrics).map(([metric, interval]) => {
      const onTest = test?.generation.versus_pipeline[system]?.[metric];
      return {
        key: `${system}-${metric}`,
        name: `${humanize(system)} − pipeline`,
        metric: humanize(metric),
        dev: diff(interval),
        test: onTest ? diff(onTest) : null,
      };
    }),
  );

  const gated = data.sweep.points.filter((point) => point.tau !== null);
  const noGate = data.sweep.points.find((point) => point.tau === null);
  const sweepSeries = sweepMetrics().map((metric) => ({
    name: humanize(metric),
    points: gated.map((point) => ({ x: point.tau ?? 0, y: point[metric] })),
    noGate: noGate ? noGate[metric] : null,
  }));

  const shifts: ShiftView[] = test
    ? [
        ...Object.entries(data.baselines.systems).flatMap(([name, system]) => {
          const dev = system.metrics.all[primary]?.mean ?? null;
          const onTest = mean(test.retrieval.baselines[name]?.metrics.all[primary]);
          return outsideInterval(dev, onTest)
            ? [{ key: `shift-${name}`, what: name, metric: primary, dev: formatNumber(dev), test: cell(onTest) }]
            : [];
        }),
        ...data.ablations.rows.flatMap((row) => {
          const dev = row.metrics.all[primary]?.mean ?? null;
          const onTest = mean(test.retrieval.rows.find((r) => r.row === row.row)?.metrics.all[primary]);
          return outsideInterval(dev, onTest)
            ? [{ key: `shift-row-${row.row}`, what: `row ${row.row}`, metric: primary, dev: formatNumber(dev), test: cell(onTest) }]
            : [];
        }),
        ...devSystems.flatMap(([system, run]) =>
          Object.entries(test.generation.systems[system]?.metrics ?? {}).flatMap(([metric, onTest]) => {
            const dev = run.metrics[metric]?.value ?? null;
            return outsideInterval(dev, onTest)
              ? [{ key: `shift-${system}-${metric}`, what: humanize(system), metric: humanize(metric), dev: formatNumber(dev), test: cell(onTest) }]
              : [];
          }),
        ),
      ]
    : [];

  const latency: LatencyView[] = [
    ...data.ablations.rows.flatMap((row) => {
      const onTest = test?.retrieval.rows.find((r) => r.row === row.row);
      const entry = (splitName: string, p50: number) => ({
        key: `latency-row-${row.row}-${splitName}`,
        label: `row ${row.row} retrieval`,
        split: splitName,
        p50: formatMs(p50),
        p95: "—",
      });
      return onTest ? [entry("dev", row.retrieval_ms_p50), entry("test", onTest.retrieval_ms_p50)] : [entry("dev", row.retrieval_ms_p50)];
    }),
    ...devSystems.flatMap(([system, run]) => {
      const onTest = test?.generation.systems[system];
      const entry = (splitName: string, p50: number, p95: number) => ({
        key: `latency-${system}-${splitName}`,
        label: `${humanize(system)} answer`,
        split: splitName,
        p50: formatMs(p50),
        p95: formatMs(p95),
      });
      return onTest
        ? [entry("dev", run.latency_ms.p50, run.latency_ms.p95), entry("test", onTest.latency_ms.p50, onTest.latency_ms.p95)]
        : [entry("dev", run.latency_ms.p50, run.latency_ms.p95)];
    }),
  ];

  return {
    splits: test ? SplitSchema.options : ["dev"],
    split,
    types: QueryTypeSchema.options,
    type,
    testRun: test !== null,
    queries: `${queryCount} ${type === "all" ? "" : `${type} `}queries`,
    retrievalMetrics,
    retrievalRows: rows.map((row) => ({
      key: `row-${row.row}`,
      label: `row ${row.row}`,
      detail: rowDetail(row),
      production: row.row === productionRow,
      cells: tableCells(row.metrics),
    })),
    baselineRows: Object.entries(baselines).map(([name, system]) => ({
      key: name,
      label: name,
      detail: `phase 2 · ${data.baselines.strategy}`,
      production: false,
      cells: tableCells(system.metrics),
    })),
    recallChart,
    primaryMetric: primary,
    comparisons,
    generationMetrics: generationMetrics.map(humanize),
    generationRows,
    generationChart,
    versus,
    notRun: test ? Object.entries(test.generation.not_run).map(([what, why]) => `${humanize(what)}: ${why}`) : [],
    sweep: {
      series: sweepSeries,
      chosenX: data.sweep.chosen.tau,
      rule: data.sweep.rule,
      chosen: data.sweep.chosen.tau === null ? "no gate" : `τ = ${formatNumber(data.sweep.chosen.tau, 2)}`,
    },
    shifts,
    latency,
  };
}
