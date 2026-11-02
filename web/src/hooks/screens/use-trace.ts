import { useEffect, useReducer } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { sendRequest } from "@/core/api/client";
import { loading, mapLoadable, toLoadable } from "@/lib/domain/loadable-helpers";
import { withParams } from "@/lib/domain/url-helpers";
import {
  ALL_PIPELINES,
  logDetailView,
  logRows,
  logsPath,
  pipelineOptions,
  traceReducer,
} from "@/lib/screens/trace-helpers";
import { LogDetailSchema, LogsResponseSchema } from "@/types/domain/logs";
import type { LogDetail, LogsResponse } from "@/types/domain/logs";
import type { TraceController } from "@/types/screens/trace";

export function useTrace(): TraceController {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [state, dispatch] = useReducer(traceReducer, { logs: null, detail: null });

  const pipeline = params.get("pipeline") ?? ALL_PIPELINES;
  const requestedId = params.get("id");
  const path = logsPath(pipeline);

  useEffect(() => {
    let live = true;
    void sendRequest(path, LogsResponseSchema).then((result) => {
      if (live) dispatch({ type: "logs", key: path, result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, [path]);

  const logs = state.logs?.result ?? loading<LogsResponse>();
  const firstId = logs.status === "success" ? logs.data.logs[0]?.id : undefined;
  const selectedId = requestedId ?? (firstId === undefined ? null : String(firstId));

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    void sendRequest(`/logs/${encodeURIComponent(selectedId)}`, LogDetailSchema).then((result) => {
      if (live) dispatch({ type: "detail", key: selectedId, result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, [selectedId]);

  const detail = !selectedId
    ? null
    : state.detail?.key === selectedId
      ? state.detail.result
      : loading<LogDetail>();
  const go = (changes: Record<string, string | null>) =>
    router.replace(withParams(pathname, params.toString(), changes), { scroll: false });

  return {
    pipelines: pipelineOptions(logs.status === "success" ? logs.data : null),
    pipeline,
    allPipelines: ALL_PIPELINES,
    logs: mapLoadable(logs, (data) => logRows(data, selectedId)),
    detail: detail && mapLoadable(detail, logDetailView),
    selectPipeline: (value) => go({ pipeline: value === ALL_PIPELINES ? null : value, id: null }),
    selectLog: (id) => go({ id }),
  };
}
