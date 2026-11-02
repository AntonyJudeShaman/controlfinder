import type { ControlsAction, ControlsState } from "@/types/screens/controls";

export const PAGE_SIZE = 100;
export const ALL_FAMILIES = "all";

export const INITIAL_CONTROLS_STATE: ControlsState = { families: { status: "loading" }, list: null, detail: null };

export function controlsReducer(state: ControlsState, action: ControlsAction): ControlsState {
  switch (action.type) {
    case "families":
      return { ...state, families: action.result };
    case "list":
      return { ...state, list: { key: action.key, result: action.result } };
    case "detail":
      return { ...state, detail: { key: action.key, result: action.result } };
  }
}

export function controlsPath(family: string, query: string, page: number): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  if (family !== ALL_FAMILIES) params.set("family", family);
  if (query.trim()) params.set("q", query.trim());
  return `/controls?${params.toString()}`;
}

export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}
