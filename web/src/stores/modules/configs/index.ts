import { create } from "zustand";
import { sendRequest } from "@/core/api/client";
import { ConfigsResponseSchema } from "@/types/stores/modules/configs";
import type { ConfigsActions, ConfigsState } from "@/types/stores/modules/configs";

const useConfigsStore = create<ConfigsState & ConfigsActions>()((set, get) => ({
  data: null,
  error: null,
  requested: false,
  load: async () => {
    if (get().requested) return;
    set({ requested: true, error: null });
    const result = await sendRequest("/configs", ConfigsResponseSchema);
    if (result.ok) set({ data: result.data });
    else set({ error: result.error, requested: false });
  },
}));

export const useConfigsData = () => useConfigsStore((state) => state.data);
export const useConfigsError = () => useConfigsStore((state) => state.error);
export const useLoadConfigs = () => useConfigsStore((state) => state.load);
