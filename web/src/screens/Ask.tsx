"use client";

import Link from "next/link";
import { ControlLink } from "@/components/controls/ControlLink";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBlock } from "@/components/layout/StatusBlock";
import { TraceSteps } from "@/components/trace/TraceSteps";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAsk } from "@/hooks/screens/use-ask";

export function Ask() {
  const controller = useAsk();
  const { systems, result, examples } = controller;
  return (
    <>
      <PageHeader kicker="Try it" title="Ask">
        Ask a question about NIST SP 800-53. You get an answer that cites controls, or a refusal when the evidence is
        not there. The dev questions below were answered during evaluation, so their answers come from the cache with
        no model call. A new question costs one model call on the pipelines and two or more on the agent.
      </PageHeader>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="flex flex-col gap-6">
          <form onSubmit={controller.submit}>
            <FieldGroup>
              <Field>
                <FieldLabel>System</FieldLabel>
                {systems.status !== "success" ? (
                  <StatusBlock {...systems} />
                ) : (
                  <ToggleGroup type="single" value={controller.system ?? ""} onValueChange={controller.setSystem}>
                    {systems.data.map((option) => (
                      <ToggleGroupItem key={option.value} value={option.value}>
                        {option.label}
                        {option.production ? " ★" : ""}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                )}
                <FieldDescription>★ marks the production system.</FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="question">Question</FieldLabel>
                <Textarea
                  id="question"
                  rows={3}
                  value={controller.question}
                  onChange={controller.changeQuestion}
                  placeholder="Which control covers locking an account after repeated failed logins?"
                />
              </Field>
              <Button type="submit" variant="secondary" disabled={controller.busy || !controller.system} className="w-fit">
                {controller.busy ? <Spinner data-icon="inline-start" /> : null}
                Ask
              </Button>
            </FieldGroup>
          </form>

          {result === null ? null : result.status !== "success" ? (
            <StatusBlock {...result} />
          ) : (
            <div className="flex flex-col gap-6">
              <Card className={result.data.answered ? undefined : "border-destructive"}>
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={result.data.answered ? "default" : "destructive"}>
                      {result.data.answered ? "answered" : "refused"}
                    </Badge>
                    <Badge variant="outline">{result.data.system}</Badge>
                    {result.data.production ? <Badge variant="secondary">production</Badge> : null}
                    <Badge variant="outline">model calls {result.data.llmCalls}</Badge>
                    <Link href={`/trace?id=${result.data.logId}`} className="font-mono text-xs underline">
                      log #{result.data.logId}
                    </Link>
                  </div>
                  <CardTitle className="text-2xl font-bold tracking-tight">
                    {result.data.answered ? "Answer" : `Refused: ${result.data.reason ?? "no reason given"}`}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {result.data.answer ? <p className="text-lg whitespace-pre-line">{result.data.answer}</p> : null}
                  {result.data.citations.length > 0 ? (
                    <section className="flex flex-col gap-2">
                      <h3 className="font-mono text-xs font-bold tracking-widest uppercase">Citations</h3>
                      {result.data.citations.map((citation) => (
                        <ControlLink key={citation.control.control_id} control={citation.control} invalid={!citation.valid} />
                      ))}
                    </section>
                  ) : null}
                  {result.data.closest.length > 0 ? (
                    <section className="flex flex-col gap-2">
                      <h3 className="font-mono text-xs font-bold tracking-widest uppercase">
                        Closest controls (reranker score)
                      </h3>
                      {result.data.closest.map((item) => (
                        <div key={item.control.control_id} className="flex items-center gap-3">
                          <span className="font-mono text-sm">{item.score}</span>
                          <ControlLink control={item.control} />
                        </div>
                      ))}
                    </section>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {result.data.latency.map((stage) => (
                      <Badge key={stage.stage} variant="outline">
                        {stage.stage} {stage.ms}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
              <section className="flex flex-col gap-3">
                <h2 className="text-2xl font-bold tracking-tighter uppercase">Context given to the model</h2>
                <div className="flex flex-col gap-2 border-2 border-foreground bg-card p-3">
                  {result.data.context.map((control) => (
                    <ControlLink key={control.control_id} control={control} />
                  ))}
                </div>
              </section>
              <section className="flex flex-col gap-3">
                <h2 className="text-2xl font-bold tracking-tighter uppercase">Steps</h2>
                <TraceSteps steps={result.data.steps} />
              </section>
            </div>
          )}
        </section>
        <aside className="flex flex-col gap-3 lg:sticky lg:top-6 lg:max-h-[calc(100svh-3rem)] lg:self-start">
          <h2 className="font-mono text-xs font-bold tracking-widest uppercase">Dev questions · cached</h2>
          {examples.status !== "success" ? (
            <StatusBlock {...examples} />
          ) : (
            <div className="flex flex-col gap-2 overflow-y-auto pr-1">
              {examples.data.map((question) => (
                <Button
                  key={question}
                  variant="outline"
                  className="h-auto justify-start py-2 text-left font-normal whitespace-normal normal-case"
                  disabled={controller.busy}
                  onClick={() => controller.pickExample(question)}
                >
                  {question}
                </Button>
              ))}
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
