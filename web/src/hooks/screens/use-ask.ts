import { useEffect, useReducer, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { postJson, sendRequest } from "@/core/api/client";
import { loading, mapLoadable, toLoadable } from "@/lib/domain/loadable-helpers";
import { withParams } from "@/lib/domain/url-helpers";
import {
  EXAMPLES_PIPELINE,
  INITIAL_ASK_STATE,
  askReducer,
  askView,
  exampleQuestions,
  systemOptions,
} from "@/lib/screens/ask-helpers";
import { useConfigsData, useConfigsError, useLoadConfigs } from "@/stores/modules/configs";
import { LogsResponseSchema } from "@/types/domain/logs";
import { AskResponseSchema } from "@/types/screens/ask";
import type { AskController, SystemOption } from "@/types/screens/ask";

export function useAsk(): AskController {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const configs = useConfigsData();
  const configsError = useConfigsError();
  const loadConfigs = useLoadConfigs();
  const [state, dispatch] = useReducer(askReducer, INITIAL_ASK_STATE);
  const counter = useRef(0);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  useEffect(() => {
    let live = true;
    void sendRequest(`/logs?pipeline=${encodeURIComponent(EXAMPLES_PIPELINE)}&limit=200`, LogsResponseSchema).then(
      (result) => {
        if (live) dispatch({ type: "examples", result: mapLoadable(toLoadable(result), exampleQuestions) });
      },
    );
    return () => {
      live = false;
    };
  }, []);

  const options = configs ? systemOptions(configs) : null;
  const requested = params.get("system");
  const system = options
    ? (options.find((option) => option.value === requested) ?? options.find((option) => option.production))?.value ??
      null
    : null;

  const ask = (question: string) => {
    const text = question.trim();
    if (!text || !system) return;
    counter.current += 1;
    const key = String(counter.current);
    dispatch({ type: "asking", key, question: text });
    void sendRequest("/ask", AskResponseSchema, postJson({ question: text, system })).then((result) =>
      dispatch({ type: "answered", key, result: toLoadable(result) }),
    );
  };

  return {
    systems: options
      ? { status: "success", data: options }
      : configsError
        ? { status: "error", message: configsError }
        : loading<SystemOption[]>(),
    system,
    question: state.question,
    busy: state.pending !== null,
    result: state.pending ? loading() : state.asked ? mapLoadable(state.asked.result, askView) : null,
    examples: state.examples,
    setSystem: (value) => {
      if (value) router.replace(withParams(pathname, params.toString(), { system: value }), { scroll: false });
    },
    changeQuestion: (event) => dispatch({ type: "question", value: event.target.value }),
    submit: (event) => {
      event.preventDefault();
      ask(state.question);
    },
    pickExample: ask,
  };
}
