import { create } from "zustand";
import { sendRequest } from "@/core/api/client";
import {
  AblationsSchema,
  AgentRunSchema,
  BaselinesSchema,
  FinalTestSchema,
  SweepSchema,
} from "@/types/stores/modules/results";
import type { ResultsActions, ResultsState } from "@/types/stores/modules/results";

const useResultsStore = create<ResultsState & ResultsActions>()((set, get) => ({
  data: null,
  error: null,
  requested: false,
  load: async () => {
    if (get().requested) return;
    set({ requested: true, error: null });
    const [ablations, baselines, agent, sweep, finalTest] = await Promise.all([
      sendRequest("/results/ablations_dev", AblationsSchema),
      sendRequest("/results/baselines_dev", BaselinesSchema),
      sendRequest("/results/agent_dev", AgentRunSchema),
      sendRequest("/results/threshold_sweep", SweepSchema),
      sendRequest("/results/final_test", FinalTestSchema),
    ]);
    if (!ablations.ok || !baselines.ok || !agent.ok || !sweep.ok) {
      const failed = [ablations, baselines, agent, sweep].find((result) => !result.ok);
      set({ error: failed && !failed.ok ? failed.error : "results unavailable", requested: false });
      return;
    }
    if (!finalTest.ok && finalTest.status !== 404) {
      set({ error: finalTest.error, requested: false });
      return;
    }
    set({
      data: {
        ablations: ablations.data,
        baselines: baselines.data,
        agent: agent.data,
        sweep: sweep.data,
        finalTest: finalTest.ok ? finalTest.data : null,
      },
    });
  },
}));

export const useResultsData = () => useResultsStore((state) => state.data);
export const useResultsError = () => useResultsStore((state) => state.error);
export const useLoadResults = () => useResultsStore((state) => state.load);
