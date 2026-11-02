"""Production retrieval, the Phase 3 pick: exact dense search over strategy C, top K parents.

The plain pipeline, the agent and the API all retrieve through `Production`, so the same query
always gets the same context. Each of the K controls comes with the chunk it was ranked by,
which in strategy C is either the control's own text or one of its enhancements'. Phase 4
found that a narrow enhancement alone often isn't enough to answer from, so `with_base_text`
puts the base control's own chunk in front of each enhancement: the "base text" system that
Phase 5 measures next to the pipeline and the agent.
"""

import time
from typing import NamedTuple

from psycopg import Connection
from sentence_transformers import SentenceTransformer

from controlfinder.ingest.ids import parent_control_id
from controlfinder.retrieval import dense
from controlfinder.retrieval.pipeline import Retriever

STRATEGY = "C_separate"
K = 10  # parents in the context


class Context(NamedTuple):
    chunks: list[tuple[str, str]]  # (control_id, text), best first
    ms: float  # embedding the query, then the search


class Production:
    """Callable on a query: its top K parents' chunks. Loads the embedder once, unless given one."""

    def __init__(self, conn: Connection, model: SentenceTransformer | None = None):
        self.model = model or dense.load_model()
        dense.embed_queries(self.model, ["warm up"])  # the first call is slow; keep it out of the timings
        self.retriever = Retriever(conn, STRATEGY)
        self.control_of = dict(conn.execute("SELECT chunk_id, control_id FROM chunks WHERE strategy = %s",
                                            (STRATEGY,)).fetchall())

    def __call__(self, query: str) -> Context:
        start = time.perf_counter()
        [vector] = dense.embed_queries(self.model, [query])
        hits = self.retriever.search("dense", query, vector)[:K]
        chunks = [(self.control_of[h.chunk_id], self.retriever.texts[h.chunk_id]) for h in hits]
        return Context(chunks, (time.perf_counter() - start) * 1000)

    def with_base_text(self, chunks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return with_base_text(chunks, {c: self.retriever.texts[f"C:{c}"] for c in base_ids(chunks)})


def base_ids(chunks: list[tuple[str, str]]) -> list[str]:
    """The base controls of the enhancements among `chunks`."""
    return [parent_control_id(c) for c, _ in chunks if parent_control_id(c) != c]


def with_base_text(chunks: list[tuple[str, str]], base_texts: dict[str, str]) -> list[tuple[str, str]]:
    """Each enhancement's chunk preceded by its base control's own chunk.

    A base control and its enhancement never both come back, since retrieval keeps one chunk per
    base control, so nothing is added twice.
    """
    out = []
    for control_id, text in chunks:
        base = parent_control_id(control_id)
        if base != control_id:
            out.append((base, base_texts[base]))
        out.append((control_id, text))
    return out
