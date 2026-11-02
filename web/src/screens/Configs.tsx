"use client";

import { ControlLink } from "@/components/controls/ControlLink";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBlock } from "@/components/layout/StatusBlock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useConfigs } from "@/hooks/screens/use-configs";

export function Configs() {
  const controller = useConfigs();
  const { view, search } = controller;
  return (
    <>
      <PageHeader kicker="Setups" title="Configs">
        Every retrieval setup and answering system that was tested, its score on the dev split and on the sealed test
        split, and the one production uses. The knobs at the bottom run real searches against the local index (no
        language model involved).
      </PageHeader>
      {view.status !== "success" ? (
        <StatusBlock {...view} />
      ) : (
        <>
          <section className="grid gap-6 md:grid-cols-2">
            <Card className="bg-accent">
              <CardHeader>
                <CardDescription className="font-mono text-xs font-bold tracking-widest text-foreground uppercase">
                  Production retrieval
                </CardDescription>
                <CardTitle className="text-3xl font-bold tracking-tight uppercase">
                  {view.data.productionSearch.retrieval} · {view.data.productionSearch.strategy}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-2">
                  <Badge>k = {view.data.productionSearch.k}</Badge>
                  <Badge variant="outline">{view.data.productionSearch.rerank ? "reranked" : "no reranker"}</Badge>
                </div>
                <p>{view.data.retrievalRule}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardDescription className="font-mono text-xs font-bold tracking-widest text-foreground uppercase">
                  Production answering system
                </CardDescription>
                <CardTitle className="text-3xl font-bold tracking-tight uppercase">{view.data.productionSystem}</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
                  {view.data.productionSystemDev.map((item) => (
                    <div key={item.metric} className="contents">
                      <dt className="font-mono text-xs uppercase">dev {item.metric}</dt>
                      <dd className="font-mono">
                        <span className="font-bold">{item.cell.value}</span>{" "}
                        <span className="text-muted-foreground">{item.cell.ci}</span>
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-3xl font-bold tracking-tighter uppercase">Retrieval setups · {view.data.metric}</h2>
            <div className="border-2 border-foreground bg-card shadow-brutal">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Setup</TableHead>
                    <TableHead>Retriever</TableHead>
                    <TableHead>Chunking</TableHead>
                    <TableHead>Reranker</TableHead>
                    <TableHead>Dev</TableHead>
                    <TableHead>Test</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {view.data.retrieval.map((row) => (
                    <TableRow key={row.id} data-state={row.production ? "selected" : undefined}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-bold">{row.name}</span>
                          <span className="font-mono text-xs text-muted-foreground">{row.stage}</span>
                        </div>
                      </TableCell>
                      <TableCell className="font-mono">{row.retrieval}</TableCell>
                      <TableCell className="font-mono">{row.strategy}</TableCell>
                      <TableCell className="font-mono">{row.rerank ? "yes" : "no"}</TableCell>
                      <TableCell className="font-mono">
                        <span className="font-bold">{row.dev.value}</span>{" "}
                        <span className="text-muted-foreground">{row.dev.ci}</span>
                      </TableCell>
                      <TableCell className="font-mono">
                        {row.test ? (
                          <>
                            <span className="font-bold">{row.test.value}</span>{" "}
                            <span className="text-muted-foreground">{row.test.ci}</span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">not run</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-2">
                          {row.production ? <Badge>production</Badge> : null}
                          {row.live ? (
                            <Button variant="outline" size="sm" onClick={() => controller.tryConfig(row.config)}>
                              Try
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-3xl font-bold tracking-tighter uppercase">Answering systems</h2>
            <p className="max-w-3xl text-muted-foreground">Agent evidence gate τ: {view.data.tauRule}</p>
            <div className="border-2 border-foreground bg-card shadow-brutal">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>System</TableHead>
                    <TableHead>Split</TableHead>
                    {view.data.generationMetrics.map((metric) => (
                      <TableHead key={metric}>{metric}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {view.data.generation.flatMap((system) =>
                    system.splits.map(({ key, split, first, cells }) => (
                      <TableRow key={key} data-state={system.production ? "selected" : undefined}>
                        <TableCell>
                          {first ? (
                            <div className="flex flex-col gap-1">
                              <span className="font-bold">{system.label}</span>
                              <span className="font-mono text-xs text-muted-foreground">τ {system.tau}</span>
                              {system.production ? <Badge>production</Badge> : null}
                            </div>
                          ) : null}
                        </TableCell>
                        <TableCell className="font-mono uppercase">{split}</TableCell>
                        {cells
                          ? cells.map((cell, index) => (
                              <TableCell key={view.data.generationMetrics[index]} className="font-mono">
                                <span className="font-bold">{cell.value}</span>{" "}
                                <span className="text-muted-foreground">{cell.ci}</span>
                              </TableCell>
                            ))
                          : view.data.generationMetrics.map((metric) => (
                              <TableCell key={metric} className="font-mono text-muted-foreground">
                                dev only
                              </TableCell>
                            ))}
                      </TableRow>
                    )),
                  )}
                </TableBody>
              </Table>
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
            <Card className="lg:self-start">
              <CardHeader>
                <CardTitle className="text-2xl font-bold tracking-tight uppercase">Live knobs</CardTitle>
                <CardDescription>
                  {view.data.knobs.isProduction ? "This is the production setup." : "Not the production setup."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FieldGroup>
                  <Field>
                    <FieldLabel>Retriever</FieldLabel>
                    <ToggleGroup
                      type="single"
                      value={view.data.knobs.current.retrieval}
                      onValueChange={controller.setRetrieval}
                    >
                      {view.data.knobs.retrieval.map((option) => (
                        <ToggleGroupItem key={option} value={option}>
                          {option}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </Field>
                  <Field>
                    <FieldLabel>Chunking</FieldLabel>
                    <ToggleGroup
                      type="single"
                      orientation="vertical"
                      value={view.data.knobs.current.strategy}
                      onValueChange={controller.setStrategy}
                    >
                      {view.data.knobs.strategy.map((option) => (
                        <ToggleGroupItem key={option} value={option}>
                          {option}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </Field>
                  <Field>
                    <FieldLabel>k = {view.data.knobs.current.k}</FieldLabel>
                    <Slider
                      value={[view.data.knobs.current.k]}
                      min={view.data.knobs.kMin}
                      max={view.data.knobs.kMax}
                      step={1}
                      onValueChange={controller.setK}
                    />
                    <FieldDescription>How many controls come back.</FieldDescription>
                  </Field>
                  <Field orientation="horizontal">
                    <Switch
                      id="rerank"
                      checked={view.data.knobs.current.rerank}
                      onCheckedChange={controller.setRerank}
                    />
                    <FieldLabel htmlFor="rerank">Cross-encoder reranker</FieldLabel>
                  </Field>
                  <Button variant="outline" onClick={controller.resetToProduction} disabled={view.data.knobs.isProduction}>
                    Reset to production
                  </Button>
                </FieldGroup>
              </CardContent>
            </Card>
            <div className="flex flex-col gap-4">
              <form onSubmit={controller.submit} className="flex gap-3">
                <Input
                  placeholder="e.g. how do we lock accounts after failed logins?"
                  value={controller.draft}
                  onChange={controller.changeDraft}
                  aria-label="Search query"
                />
                <Button type="submit" variant="secondary">
                  Search
                </Button>
              </form>
              {search === null ? (
                <Empty className="border-2 border-dashed border-foreground bg-card">
                  <EmptyHeader>
                    <EmptyTitle>Type a question</EmptyTitle>
                    <EmptyDescription>Change any knob and the search reruns with the new setup.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : search.status !== "success" ? (
                <StatusBlock {...search} />
              ) : (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-2">
                    {search.data.production ? <Badge>production setup</Badge> : null}
                    {search.data.latency.map((stage) => (
                      <Badge key={stage.stage} variant="outline">
                        {stage.stage} {stage.ms}
                      </Badge>
                    ))}
                  </div>
                  <ol className="flex flex-col gap-3">
                    {search.data.hits.map((hit) => (
                      <li key={hit.key} className="flex flex-col gap-2 border-2 border-foreground bg-card p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-2xl font-bold">{hit.rank}</span>
                            <ControlLink control={hit.control} />
                          </div>
                          <span className="font-mono text-sm">
                            {search.data.scoreKind} {hit.score}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">{hit.text}</p>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}
