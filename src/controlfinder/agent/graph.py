"""The agent graph: check scope, retrieve, grade the evidence, rewrite at most twice, generate,
verify the citations, or abstain.

LangGraph runs only this layer; retrieval stays hand-written (`retrieval.production`). What the
graph adds over calling functions in a row is structure you can see and test. Every route is
an edge chosen by a small function of the state (the `after_*` methods), the rewrite loop is a
cycle in the graph, and its bound, MAX_REWRITES, is checked in that edge's function. No model
output can extend the loop, because no prompt is involved in deciding whether it continues.
Every node appends one entry to the trace, so any run can be replayed step by step.

The evidence grade is the reranker's best score for the original question over the retrieved
chunks. It's compared with τ (`tau`). `tau=None` turns the gate off.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from controlfinder.agent import prompts
from controlfinder.agent.state import Chunk, State
from controlfinder.generation import citations, prompt
from controlfinder.generation.llm import LLM
from controlfinder.retrieval.production import Context
from controlfinder.retrieval.rerank import Scored

MAX_REWRITES = 2
MAX_GENERATIONS = 2  # the first answer, and one retry if its citations fail the check
CLOSEST = 3  # controls returned with an abstention
LLM_NODES = ("scope_check", "rewrite", "generate")


@dataclass(frozen=True)
class Tools:
    retrieve: Callable[[str], Context]
    grade: Callable[[str, list[str]], Scored]  # the reranker: (question, texts) -> their scores
    small: LLM  # the scope check and the rewrites
    generator: LLM


def step(node: str, ms: float, **details) -> dict:
    return {"node": node, "ms": ms, **details}


class Agent:
    def __init__(self, tools: Tools, tau: float | None):
        self.tools, self.tau = tools, tau
        self.gate = -math.inf if tau is None else tau
        graph = StateGraph(State)
        for node in (self.scope_check, self.retrieve, self.grade_evidence, self.rewrite,
                     self.generate, self.verify_citations, self.abstain):
            graph.add_node(node.__name__, node)
        graph.add_edge(START, "scope_check")
        graph.add_conditional_edges("scope_check", self.after_scope, ["retrieve", "abstain"])
        graph.add_edge("retrieve", "grade_evidence")
        graph.add_conditional_edges("grade_evidence", self.after_grade, ["generate", "rewrite", "abstain"])
        graph.add_edge("rewrite", "retrieve")
        graph.add_conditional_edges("generate", self.after_generate, ["verify_citations", "abstain"])
        graph.add_conditional_edges("verify_citations", self.after_verify, ["generate", "abstain", END])
        graph.add_edge("abstain", END)
        self.graph = graph.compile()

    def run(self, question: str) -> State:
        return self.graph.invoke({"question": question, "queries_tried": [question], "attempts": 0,
                                  "generations": 0, "closest": [], "trace": []})

    def scope_check(self, state: State) -> dict:
        reply = self.tools.small(prompts.SCOPE.format(question=state["question"]))
        verdict = prompts.scope_verdict(reply.text)
        return {"in_scope": verdict is not False,
                "trace": [step("scope_check", reply.ms, verdict=verdict, reply=reply.text, model=reply.model)]}

    def after_scope(self, state: State) -> str:
        return "retrieve" if state["in_scope"] else "abstain"

    def retrieve(self, state: State) -> dict:
        query = state["queries_tried"][-1]
        context = self.tools.retrieve(query)
        return {"retrieved": [Chunk(control_id, text, None) for control_id, text in context.chunks],
                "trace": [step("retrieve", context.ms, query=query, controls=[c for c, _ in context.chunks])]}

    def grade_evidence(self, state: State) -> dict:
        scored = self.tools.grade(state["question"], [c.text for c in state["retrieved"]])
        graded = [c._replace(score=s) for c, s in zip(state["retrieved"], scored.scores, strict=True)]
        top = max(scored.scores)
        seen = {c.control_id: c for c in [*state["closest"], *graded]}
        return {"retrieved": graded, "top_score": top,
                "closest": sorted(seen.values(), key=lambda c: -c.score)[:CLOSEST],
                "trace": [step("grade_evidence", scored.ms, top_score=top, tau=self.tau, strong=top >= self.gate)]}

    def after_grade(self, state: State) -> str:
        if state["top_score"] >= self.gate:
            return "generate"
        return "rewrite" if state["attempts"] < MAX_REWRITES else "abstain"

    def rewrite(self, state: State) -> dict:
        reply = self.tools.small(prompts.rewrite_prompt(state["question"], state["queries_tried"]))
        query = prompts.rewritten_query(reply.text) or state["question"]
        return {"queries_tried": [query], "attempts": state["attempts"] + 1,
                "trace": [step("rewrite", reply.ms, query=query, model=reply.model)]}

    def generate(self, state: State) -> dict:
        chunks = [(c.control_id, c.text) for c in state["retrieved"]]
        text = prompt.generation_prompt(state["question"], chunks)
        if state["generations"]:
            in_context = {c for c, _ in chunks}
            text = prompts.retry_prompt(text, [c for c in state["citations"] if c not in in_context])
        reply = self.tools.generator(text)
        return {"answer": reply.text, "generations": state["generations"] + 1,
                "trace": [step("generate", reply.ms, retry=state["generations"] > 0, answer=reply.text,
                               model=reply.model, input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)]}

    def after_generate(self, state: State) -> str:
        return "abstain" if prompt.abstained(state["answer"]) else "verify_citations"

    def verify_citations(self, state: State) -> dict:
        start = time.perf_counter()
        in_context = {c.control_id for c in state["retrieved"]}
        cited = citations.cited(state["answer"])
        invalid = [c for c in cited if c not in in_context]
        ok = bool(cited) and not invalid
        update = {"citations": cited, "citations_ok": ok,
                  "trace": [step("verify_citations", (time.perf_counter() - start) * 1000,
                                 citations=cited, invalid=invalid, ok=ok)]}
        if ok:
            update["decision"] = "answer"
        return update

    def after_verify(self, state: State) -> str:
        if state["citations_ok"]:
            return END
        return "generate" if state["generations"] < MAX_GENERATIONS else "abstain"

    def abstain(self, state: State) -> dict:
        reason = self.reason(state)
        closest = [{"control_id": c.control_id, "score": c.score} for c in state["closest"]]
        return {"decision": "abstain", "answer": None, "reason": reason,
                "trace": [step("abstain", 0.0, reason=reason, closest=closest)]}

    def reason(self, state: State) -> str:
        """Which edge led here, read back from the state those edges were chosen on."""
        if not state["in_scope"]:
            return "out_of_scope"
        if state["top_score"] < self.gate:
            return "weak_evidence"
        return "generator_refused" if prompt.abstained(state["answer"]) else "citations_failed"
