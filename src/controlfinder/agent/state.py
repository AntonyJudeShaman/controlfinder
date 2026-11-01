"""The agent's state: one dict that LangGraph passes from node to node.

A node returns only the fields it changes, and LangGraph merges them in. Fields marked with
`operator.add` are appended to instead of replaced: `queries_tried` keeps every query sent to
retrieval, and `trace` keeps one entry per node run, which is the step-by-step record written
to query_log. The first nine fields are the ones AGENTS.md lists; the rest carry what the
routing and the final response need.
"""

import operator
from typing import Annotated, NamedTuple, TypedDict


class Chunk(NamedTuple):
    control_id: str
    text: str
    score: float | None  # the reranker's score for (the question, this text); None until graded


class State(TypedDict, total=False):
    question: str
    queries_tried: Annotated[list[str], operator.add]
    retrieved: list[Chunk]  # the latest retrieval, best first
    top_score: float
    attempts: int  # rewrites so far
    decision: str  # 'answer' or 'abstain'
    answer: str | None
    citations: list[str]
    trace: Annotated[list[dict], operator.add]
    in_scope: bool
    generations: int
    citations_ok: bool
    reason: str | None  # why it abstained: out_of_scope, weak_evidence, generator_refused, citations_failed
    closest: list[Chunk]  # the best-scored chunks over all retrievals, returned with an abstention
