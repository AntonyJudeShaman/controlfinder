import type { ChangeEvent, FormEvent } from "react";
import { z } from "zod";
import { ControlBriefSchema } from "@/types/domain/controls";
import type { ControlBrief } from "@/types/domain/controls";
import type { Keyed, Loadable } from "@/types/domain/loadable";
import { TraceStepSchema } from "@/types/domain/trace";
import type { TraceStepView } from "@/types/domain/trace";

export const AskResponseSchema = z.object({
  question: z.string(),
  system: z.string(),
  production: z.boolean(),
  decision: z.enum(["answer", "abstain"]),
  answer: z.string().nullable(),
  reason: z.string().nullable(),
  citations: z.array(ControlBriefSchema.extend({ valid: z.boolean() })),
  context: z.array(ControlBriefSchema),
  closest: z.array(ControlBriefSchema.extend({ score: z.number().nullable() })),
  trace: z.array(TraceStepSchema),
  llm_calls: z.number(),
  latency_ms: z.record(z.string(), z.number()),
  log_id: z.number(),
});
export type AskResponse = z.infer<typeof AskResponseSchema>;

export interface AskState {
  question: string;
  asked: Keyed<AskResponse> | null;
  pending: string | null;
  examples: Loadable<string[]>;
}

export type AskAction =
  | { type: "question"; value: string }
  | { type: "asking"; key: string; question: string }
  | { type: "answered"; key: string; result: Loadable<AskResponse> }
  | { type: "examples"; result: Loadable<string[]> };

export interface SystemOption {
  value: string;
  label: string;
  production: boolean;
}

export interface AskView {
  answered: boolean;
  system: string;
  production: boolean;
  answer: string | null;
  reason: string | null;
  citations: { control: ControlBrief; valid: boolean }[];
  context: ControlBrief[];
  closest: { control: ControlBrief; score: string }[];
  steps: TraceStepView[];
  llmCalls: number;
  latency: { stage: string; ms: string }[];
  logId: number;
}

export interface AskController {
  systems: Loadable<SystemOption[]>;
  system: string | null;
  question: string;
  busy: boolean;
  result: Loadable<AskView> | null;
  examples: Loadable<string[]>;
  setSystem: (value: string) => void;
  changeQuestion: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  submit: (event: FormEvent<HTMLFormElement>) => void;
  pickExample: (question: string) => void;
}
