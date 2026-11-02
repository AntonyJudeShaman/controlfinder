import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { loading } from "@/lib/domain/loadable-helpers";
import { pickParam, withParams } from "@/lib/domain/url-helpers";
import { resultsView } from "@/lib/screens/results-helpers";
import { useLoadResults, useResultsData, useResultsError } from "@/stores/modules/results";
import { QueryTypeSchema, SplitSchema } from "@/types/domain/metrics";
import type { ResultsController, ResultsView } from "@/types/screens/results";

export function useResults(): ResultsController {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const data = useResultsData();
  const error = useResultsError();
  const load = useLoadResults();

  useEffect(() => {
    void load();
  }, [load]);

  const split = pickParam(params.get("split"), SplitSchema.options, "test");
  const type = pickParam(params.get("type"), QueryTypeSchema.options, "all");
  const view = useMemo(() => (data ? resultsView(data, split, type) : null), [data, split, type]);
  const go = (changes: Record<string, string | null>) =>
    router.replace(withParams(pathname, params.toString(), changes), { scroll: false });

  return {
    view: view
      ? { status: "success", data: view }
      : error
        ? { status: "error", message: error }
        : loading<ResultsView>(),
    setSplit: (value) => {
      if (value) go({ split: value });
    },
    setType: (value) => {
      if (value) go({ type: value });
    },
  };
}
