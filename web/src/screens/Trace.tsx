"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBlock } from "@/components/layout/StatusBlock";
import { TraceSteps } from "@/components/trace/TraceSteps";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTrace } from "@/hooks/screens/use-trace";
import { cn } from "@/lib/utils";

export function Trace() {
  const controller = useTrace();
  const { logs, detail } = controller;
  return (
    <>
      <PageHeader kicker="Under the hood" title="Trace">
        Every request is logged with its per-stage latency. Pick one to replay the agent&apos;s steps: scope check,
        retrieve, grade the evidence, rewrite, generate, verify the citations, or refuse.
      </PageHeader>
      <div className="grid gap-8 lg:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-3 lg:sticky lg:top-6 lg:max-h-[calc(100svh-3rem)] lg:self-start">
          <Select value={controller.pipeline} onValueChange={controller.selectPipeline}>
            <SelectTrigger className="w-full" aria-label="Pipeline">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {controller.pipelines.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {logs.status !== "success" ? (
            <StatusBlock {...logs} />
          ) : logs.data.length === 0 ? (
            <Empty className="border-2 border-foreground bg-card">
              <EmptyHeader>
                <EmptyTitle>No requests yet</EmptyTitle>
                <EmptyDescription>Ask a question or run a search and it shows up here.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ol className="flex flex-col gap-2 overflow-y-auto pr-1">
              {logs.data.map((log) => (
                <li key={log.id}>
                  <button
                    type="button"
                    onClick={() => controller.selectLog(log.id)}
                    className={cn(
                      "flex w-full flex-col gap-1 border-2 border-foreground p-2 text-left transition-colors",
                      log.selected ? "bg-accent shadow-brutal-sm" : "bg-card hover:bg-muted",
                    )}
                  >
                    <span className="line-clamp-2 text-sm">{log.query}</span>
                    <span className="flex flex-wrap items-center gap-2 font-mono text-[0.7rem]">
                      <span>#{log.id}</span>
                      <span>{log.pipeline}</span>
                      <span className={log.answered ? undefined : "font-bold text-destructive"}>{log.decision}</span>
                      <span>{log.total}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </aside>
        <section className="flex flex-col gap-4 lg:self-start">
          {detail === null ? null : detail.status !== "success" ? (
            <StatusBlock {...detail} />
          ) : (
            <>
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={detail.data.answered ? "default" : "destructive"}>{detail.data.decision}</Badge>
                    <Badge variant="outline">{detail.data.pipeline}</Badge>
                    <Badge variant="outline">#{detail.data.id}</Badge>
                    <span className="font-mono text-xs text-muted-foreground">{detail.data.when}</span>
                  </div>
                  <CardTitle className="text-2xl font-bold tracking-tight">{detail.data.query}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-2">
                    {detail.data.latency.map((stage) => (
                      <Badge key={stage.stage} variant="outline">
                        {stage.stage} {stage.ms}
                      </Badge>
                    ))}
                  </div>
                  {detail.data.gate ? <p className="font-mono text-sm">{detail.data.gate}</p> : null}
                  {detail.data.retrieved.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {detail.data.retrieved.map((control) => (
                        <Badge key={control} variant="secondary">
                          {control}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
              {detail.data.steps.length > 0 ? (
                <TraceSteps steps={detail.data.steps} />
              ) : (
                <Empty className="border-2 border-dashed border-foreground bg-card">
                  <EmptyHeader>
                    <EmptyTitle>No steps</EmptyTitle>
                    <EmptyDescription>Searches log their stages but have no agent steps.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}
