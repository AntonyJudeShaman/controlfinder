"use client";

import { ControlLink } from "@/components/controls/ControlLink";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBlock } from "@/components/layout/StatusBlock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useControls } from "@/hooks/screens/use-controls";

export function Controls() {
  const controls = useControls();
  const { list, detail, families } = controls;
  return (
    <>
      <PageHeader kicker="Catalog" title="Controls">
        The catalog the system searches: every NIST SP 800-53 Rev 5 control and enhancement, read from the database.
        Click a row to read its statement and guidance.
      </PageHeader>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-3">
            <Input
              className="max-w-sm"
              placeholder="AC-2, ac-2.1 or a word in the title"
              value={controls.query}
              onChange={controls.changeQuery}
              aria-label="Search controls"
            />
            <Select value={controls.family} onValueChange={controls.selectFamily}>
              <SelectTrigger className="w-48" aria-label="Family">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={controls.allFamilies}>All families</SelectItem>
                  {families.status === "success" &&
                    families.data.map((family) => (
                      <SelectItem key={family.family} value={family.family}>
                        {family.family} · {family.controls}
                      </SelectItem>
                    ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          {list.status !== "success" ? (
            <StatusBlock {...list} />
          ) : list.data.controls.length === 0 ? (
            <Empty className="border-2 border-foreground bg-card">
              <EmptyHeader>
                <EmptyTitle>No controls match</EmptyTitle>
                <EmptyDescription>Try an ID like AC-2 or a word from a title.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="border-2 border-foreground bg-card shadow-brutal">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Parent</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {list.data.controls.map((control) => (
                      <TableRow
                        key={control.control_id}
                        data-state={control.control_id === controls.selectedId ? "selected" : undefined}
                        onClick={() => controls.selectControl(control.control_id)}
                        className="cursor-pointer"
                      >
                        <TableCell className="font-mono font-bold">{control.display_id}</TableCell>
                        <TableCell className="whitespace-normal">{control.title}</TableCell>
                        <TableCell className="font-mono text-muted-foreground">{control.parent_id ?? ""}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="flex items-center justify-between gap-3 font-mono text-sm">
                <span>
                  {list.data.total} controls · page {controls.page} of {controls.pages}
                </span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={controls.previousPage} disabled={controls.page <= 1}>
                    Prev
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={controls.nextPage}
                    disabled={controls.page >= controls.pages}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </div>
          )}
        </section>
        <aside className="flex flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
          {detail === null ? (
            <Empty className="border-2 border-dashed border-foreground bg-card">
              <EmptyHeader>
                <EmptyTitle>Pick a control</EmptyTitle>
                <EmptyDescription>Its statement, guidance, parent and enhancements show up here.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : detail.status !== "success" ? (
            <StatusBlock {...detail} />
          ) : (
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{detail.data.display_id}</Badge>
                  <Badge variant="outline">{detail.data.family}</Badge>
                </div>
                <CardTitle className="text-2xl font-bold tracking-tight">{detail.data.title}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                <section className="flex flex-col gap-1">
                  <h3 className="font-mono text-xs font-bold tracking-widest uppercase">Statement</h3>
                  <p className="whitespace-pre-line">{detail.data.statement ?? "This item has no statement."}</p>
                </section>
                {detail.data.guidance ? (
                  <section className="flex flex-col gap-1">
                    <h3 className="font-mono text-xs font-bold tracking-widest uppercase">Guidance</h3>
                    <p className="whitespace-pre-line text-muted-foreground">{detail.data.guidance}</p>
                  </section>
                ) : null}
                {detail.data.parent ? (
                  <section className="flex flex-col gap-1">
                    <h3 className="font-mono text-xs font-bold tracking-widest uppercase">Parent</h3>
                    <ControlLink control={detail.data.parent} />
                  </section>
                ) : null}
                {detail.data.enhancements.length > 0 ? (
                  <section className="flex flex-col gap-2">
                    <h3 className="font-mono text-xs font-bold tracking-widest uppercase">
                      Enhancements · {detail.data.enhancements.length}
                    </h3>
                    {detail.data.enhancements.map((enhancement) => (
                      <ControlLink key={enhancement.control_id} control={enhancement} />
                    ))}
                  </section>
                ) : null}
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}
