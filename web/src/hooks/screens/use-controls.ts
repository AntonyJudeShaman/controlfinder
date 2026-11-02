import { useEffect, useReducer } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { sendRequest } from "@/core/api/client";
import { loading, toLoadable } from "@/lib/domain/loadable-helpers";
import { withParams } from "@/lib/domain/url-helpers";
import {
  ALL_FAMILIES,
  INITIAL_CONTROLS_STATE,
  controlsPath,
  controlsReducer,
  pageCount,
} from "@/lib/screens/controls-helpers";
import { ControlDetailSchema, ControlsResponseSchema, FamiliesResponseSchema } from "@/types/screens/controls";
import type { ControlDetail, ControlsController, ControlsResponse } from "@/types/screens/controls";

export function useControls(): ControlsController {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [state, dispatch] = useReducer(controlsReducer, INITIAL_CONTROLS_STATE);

  const family = params.get("family") ?? ALL_FAMILIES;
  const query = params.get("q") ?? "";
  const selectedId = params.get("id");
  const page = Math.max(1, Number(params.get("page")) || 1);
  const listPath = controlsPath(family, query, page);

  useEffect(() => {
    let live = true;
    void sendRequest("/families", FamiliesResponseSchema).then((result) => {
      if (live) dispatch({ type: "families", result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    void sendRequest(listPath, ControlsResponseSchema).then((result) => {
      if (live) dispatch({ type: "list", key: listPath, result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, [listPath]);

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    void sendRequest(`/controls/${encodeURIComponent(selectedId)}`, ControlDetailSchema).then((result) => {
      if (live) dispatch({ type: "detail", key: selectedId, result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, [selectedId]);

  const go = (changes: Record<string, string | null>) =>
    router.replace(withParams(pathname, params.toString(), changes), { scroll: false });

  const list = state.list?.result ?? loading<ControlsResponse>();
  const total = list.status === "success" ? list.data.total : 0;
  const detail = !selectedId
    ? null
    : state.detail?.key === selectedId
      ? state.detail.result
      : loading<ControlDetail>();

  return {
    families: state.families,
    list,
    detail,
    family,
    allFamilies: ALL_FAMILIES,
    query,
    selectedId,
    page,
    pages: pageCount(total),
    selectFamily: (value) => go({ family: value === ALL_FAMILIES ? null : value, page: null }),
    changeQuery: (event) => go({ q: event.target.value, page: null }),
    selectControl: (controlId) => go({ id: controlId }),
    previousPage: () => go({ page: String(Math.max(1, page - 1)) }),
    nextPage: () => go({ page: String(Math.min(pageCount(total), page + 1)) }),
  };
}
