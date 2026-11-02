import { z } from "zod";

export const ControlBriefSchema = z.object({
  control_id: z.string(),
  display_id: z.string(),
  family: z.string().nullable(),
  title: z.string().nullable(),
});
export type ControlBrief = z.infer<typeof ControlBriefSchema>;
