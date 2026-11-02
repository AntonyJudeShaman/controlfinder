import type { ChangeEvent } from "react";
import { z } from "zod";
import { ControlBriefSchema } from "@/types/domain/controls";
import type { Keyed, Loadable } from "@/types/domain/loadable";

export const FamiliesResponseSchema = z.array(z.object({ family: z.string(), controls: z.number() }));
export type Family = z.infer<typeof FamiliesResponseSchema>[number];

export const ControlsResponseSchema = z.object({
  total: z.number(),
  controls: z.array(ControlBriefSchema.extend({ parent_id: z.string().nullable() })),
});
export type ControlsResponse = z.infer<typeof ControlsResponseSchema>;

export const ControlDetailSchema = ControlBriefSchema.extend({
  statement: z.string().nullable(),
  guidance: z.string().nullable(),
  parent: ControlBriefSchema.nullable(),
  enhancements: z.array(ControlBriefSchema),
});
export type ControlDetail = z.infer<typeof ControlDetailSchema>;

export interface ControlsState {
  families: Loadable<Family[]>;
  list: Keyed<ControlsResponse> | null;
  detail: Keyed<ControlDetail> | null;
}

export type ControlsAction =
  | { type: "families"; result: Loadable<Family[]> }
  | { type: "list"; key: string; result: Loadable<ControlsResponse> }
  | { type: "detail"; key: string; result: Loadable<ControlDetail> };

export interface ControlsController {
  families: Loadable<Family[]>;
  list: Loadable<ControlsResponse>;
  detail: Loadable<ControlDetail> | null;
  family: string;
  allFamilies: string;
  query: string;
  selectedId: string | null;
  page: number;
  pages: number;
  selectFamily: (value: string) => void;
  changeQuery: (event: ChangeEvent<HTMLInputElement>) => void;
  selectControl: (controlId: string) => void;
  previousPage: () => void;
  nextPage: () => void;
}
