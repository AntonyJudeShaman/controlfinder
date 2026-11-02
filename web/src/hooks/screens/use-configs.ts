import { useEffect, useReducer } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { sendRequest } from "@/core/api/client";
import { loading, mapLoadable, toLoadable } from "@/lib/domain/loadable-helpers";
import { withParams } from "@/lib/domain/url-helpers";
import {
  configsScreenReducer,
  configsView,
  knobParams,
  readKnobs,
  searchPath,
  searchView,
} from "@/lib/screens/configs-helpers";
import { useConfigsData, useConfigsError, useLoadConfigs } from "@/stores/modules/configs";
import { SearchResponseSchema } from "@/types/screens/configs";
import type { ConfigsController, ConfigsView, SearchResponse } from "@/types/screens/configs";
import type { SearchConfig } from "@/types/stores/modules/configs";

export function useConfigs(): ConfigsController {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const configs = useConfigsData();
  const configsError = useConfigsError();
  const loadConfigs = useLoadConfigs();
  const query = params.get("q") ?? "";
  const [state, dispatch] = useReducer(configsScreenReducer, { draft: query, search: null });

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  const knobs = configs
    ? readKnobs(
        { retrieval: params.get("retrieval"), strategy: params.get("strategy"), k: params.get("k"), rerank: params.get("rerank") },
        configs,
      )
    : null;
  const path = knobs && query.trim() ? searchPath(query.trim(), knobs) : null;

  useEffect(() => {
    if (!path) return;
    let live = true;
    void sendRequest(path, SearchResponseSchema).then((result) => {
      if (live) dispatch({ type: "search", key: path, result: toLoadable(result) });
    });
    return () => {
      live = false;
    };
  }, [path]);

  const go = (changes: Record<string, string | null>) =>
    router.replace(withParams(pathname, params.toString(), changes), { scroll: false });
  const setKnobs = (changes: Partial<SearchConfig>) => {
    if (knobs) go(knobParams({ ...knobs, ...changes }));
  };

  const view: ConfigsController["view"] =
    configs && knobs
      ? { status: "success", data: configsView(configs, knobs) }
      : configsError
        ? { status: "error", message: configsError }
        : loading<ConfigsView>();

  const searchResult = !path ? null : state.search?.key === path ? state.search.result : loading<SearchResponse>();
  const search = searchResult && mapLoadable(searchResult, searchView);

  return {
    view,
    draft: state.draft,
    search,
    changeDraft: (event) => dispatch({ type: "draft", value: event.target.value }),
    submit: (event) => {
      event.preventDefault();
      go({ q: state.draft.trim() || null });
    },
    setRetrieval: (value) => {
      if (value) setKnobs({ retrieval: value });
    },
    setStrategy: (value) => {
      if (value) setKnobs({ strategy: value });
    },
    setK: (value) => {
      const [k] = value;
      if (k !== undefined) setKnobs({ k });
    },
    setRerank: (checked) => setKnobs({ rerank: checked }),
    tryConfig: (config) =>
      setKnobs({ retrieval: config.retrieval, strategy: config.strategy, rerank: config.rerank }),
    resetToProduction: () => {
      if (configs) go(knobParams(configs.production.search));
    },
  };
}
