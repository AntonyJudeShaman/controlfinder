import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TraceStepsProps } from "@/types/components/trace/trace-steps";

const TONE_CLASSES = {
  neutral: "bg-card",
  pass: "bg-accent",
  fail: "bg-destructive text-white",
};

export function TraceSteps({ steps }: TraceStepsProps) {
  return (
    <ol className="flex flex-col">
      {steps.map((step) => (
        <li key={step.key} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3">
          <div className="flex flex-col items-center">
            <span
              className={cn(
                "flex size-10 items-center justify-center border-2 border-foreground font-mono font-bold",
                TONE_CLASSES[step.tone],
              )}
            >
              {step.index}
            </span>
            <span className="w-0.5 flex-1 bg-foreground" />
          </div>
          <div className="mb-4 flex flex-col gap-2 border-2 border-foreground bg-card p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-lg font-bold uppercase">{step.node}</span>
              <Badge variant="outline">{step.ms}</Badge>
            </div>
            {step.facts.length > 0 ? (
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
                {step.facts.map((fact) => (
                  <div key={fact.label} className="contents">
                    <dt className="font-mono text-xs text-muted-foreground">{fact.label}</dt>
                    <dd className="font-mono break-words">{fact.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {step.controls.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {step.controls.map((control) => (
                  <Badge key={control} variant="outline">
                    {control}
                  </Badge>
                ))}
              </div>
            ) : null}
            {step.text ? (
              <p className="border-l-4 border-foreground bg-muted p-2 text-sm whitespace-pre-line">{step.text}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
