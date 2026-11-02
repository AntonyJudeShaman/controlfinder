"""What the API does besides HTTP: search, answer, browse the catalog, and read results and logs.

`Backend` holds one database connection and creates each model on first use, unless it's given
one, which is how the tests run with no model call or download. Search runs any Phase 3 setup
(retriever, chunking strategy, k, reranker), production by default. Answers come from the plain
pipeline, the pipeline with base text or the agent at Phase 5's τ, and the default is Phase 5's
production pick, both read from results/agent_dev.json. Each search and answer writes a
query_log row. Its stage latencies follow definition 8 (retrieval timed live, model stages at
their original call's time); `wall` is the request's own time, which a cache hit makes short.
"""

import json
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from psycopg import Connection
from sentence_transformers import SentenceTransformer

from controlfinder.agent.graph import LLM_NODES, Agent, Tools, step
from controlfinder.eval.agent import SMALL_MODEL
from controlfinder.eval.generation import GENERATOR_MODEL
from controlfinder.generation import citations, prompt
from controlfinder.generation.llm import LLM
from controlfinder.ingest.ids import display_id, normalize_control_id
from controlfinder.obs import log_request
from controlfinder.retrieval import dense
from controlfinder.retrieval.pipeline import Retriever, rerank
from controlfinder.retrieval.production import K, STRATEGY, Production
from controlfinder.retrieval.rerank import Reranker

RESULTS = Path("results")
METRIC = "recall@10"
GENERATION_METRICS = ("abstention_f1", "answer_rate", "answer_accuracy", "citation_precision")
SCORE_KIND = {"bm25": "bm25", "dense": "cosine", "hybrid": "rrf"}
PRODUCTION_SEARCH = {"retrieval": "dense", "strategy": STRATEGY, "k": K, "rerank": False}
_ID = re.compile(r"([a-z]{2})-(\d+)(?:\.(\d+))?")


def since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def catalog_order(control_id: str) -> tuple[str, int, int]:
    family, number, enhancement = _ID.fullmatch(control_id).groups()
    return family, int(number), int(enhancement or 0)


def read_result(name: str) -> dict | None:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def interval(ci: dict) -> dict:
    """A metric and its 95% interval, from either bootstrap's output."""
    return {"value": ci["mean"] if "mean" in ci else ci["value"], "ci95": ci["ci95"]}


class Backend:
    def __init__(self, conn: Connection, embedder: SentenceTransformer | None = None, reranker: Reranker | None = None,
                 llm: Callable[[str], LLM] = LLM):
        self.conn, self._embedder, self._reranker, self._llm = conn, embedder, reranker, llm
        self._production: Production | None = None
        self.retrievers: dict[str, Retriever] = {}
        self.llms: dict[str, LLM] = {}
        self.controls = {cid: {"family": family, "title": title, "parent_id": parent}
                         for cid, family, title, parent in conn.execute("SELECT id, family, title, parent_id FROM controls")}
        self.control_of = dict(conn.execute("SELECT chunk_id, control_id FROM chunks").fetchall())
        agent = read_result("agent_dev")
        self.production_system, self.tau = agent["production_pick"]["pick"], agent["agent"]["tau"]

    @property
    def embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = dense.load_model()
            dense.embed_queries(self._embedder, ["warm up"])  # the first call is slow; keep it out of the timings
        return self._embedder

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            self._reranker = Reranker()
        return self._reranker

    @property
    def production(self) -> Production:
        if self._production is None:
            self._production = Production(self.conn, self.embedder)
        return self._production

    def retriever(self, strategy: str) -> Retriever:
        if strategy not in self.retrievers:
            self.retrievers[strategy] = Retriever(self.conn, strategy)
        return self.retrievers[strategy]

    def llm(self, model: str) -> LLM:
        if model not in self.llms:
            self.llms[model] = self._llm(model)
        return self.llms[model]

    def brief(self, control_id: str) -> dict:
        control = self.controls.get(control_id, {})
        return {"control_id": control_id, "display_id": display_id(control_id), "title": control.get("title"),
                "family": control.get("family")}

    def search(self, query: str, retrieval: str, strategy: str, k: int, with_rerank: bool) -> dict:
        retriever = self.retriever(strategy)
        embedder = self.embedder if retrieval != "bm25" else None
        start = time.perf_counter()
        latency, vector = {}, ""
        if embedder:
            [vector] = dense.embed_queries(embedder, [query])
            latency["embed"] = since(start)
        searched = time.perf_counter()
        hits = retriever.search(retrieval, query, vector)
        latency["retrieve"] = since(searched)
        if with_rerank:
            hits, scored = rerank(self.reranker, query, hits, retriever.texts)
            latency["rerank"] = scored.ms
        hits = hits[:k]
        latency |= {"total": sum(latency.values()), "wall": since(start)}
        config = {"retrieval": retrieval, "strategy": strategy, "k": k, "rerank": with_rerank}
        log_id = log_request(self.conn, query, f"search/{retrieval}/{strategy}" + ("/rerank" if with_rerank else ""),
                             latency, [h.parent_control_id for h in hits], [h.score for h in hits])
        return {"query": query, "config": config, "production": config == PRODUCTION_SEARCH,
                "score_kind": "rerank_logit" if with_rerank else SCORE_KIND[retrieval],
                "hits": [self.brief(self.control_of[h.chunk_id]) | {"rank": rank, "parent_id": h.parent_control_id,
                                                                    "chunk_id": h.chunk_id, "score": h.score,
                                                                    "text": retriever.texts[h.chunk_id]}
                         for rank, h in enumerate(hits, 1)],
                "latency_ms": latency, "log_id": log_id}

    def ask(self, question: str, system: str | None) -> dict:
        system = system or self.production_system
        production = self.production
        start = time.perf_counter()
        out = (self.ask_agent(question, production) if system == "agent"
               else self.ask_pipeline(question, production, system == "pipeline_base_text"))
        latency = out.pop("latency")
        latency |= {"total": sum(latency.values()), "wall": since(start)}
        log_id = log_request(self.conn, question, f"ask/{system}", latency, [c["control_id"] for c in out["context"]],
                             out.pop("scores"), out["decision"], out["trace"])
        return {"question": question, "system": system, "production": system == self.production_system, **out,
                "latency_ms": latency, "log_id": log_id}

    def ask_pipeline(self, question: str, production: Production, base_text: bool) -> dict:
        context = production(question)
        chunks = production.with_base_text(context.chunks) if base_text else context.chunks
        ids = [control_id for control_id, _ in chunks]
        reply = self.llm(GENERATOR_MODEL)(prompt.generation_prompt(question, chunks))
        trace = [step("retrieve", context.ms, query=question, controls=ids),
                 step("generate", reply.ms, model=reply.model, answer=reply.text,
                      input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)]
        latency = {"retrieve": context.ms, "generate": reply.ms}
        answered = not prompt.abstained(reply.text)
        cited, invalid = [], []
        if answered:
            checked = time.perf_counter()
            cited = citations.cited(reply.text)
            invalid = [c for c in cited if c not in ids]
            latency["verify_citations"] = since(checked)
            trace.append(step("verify_citations", latency["verify_citations"], citations=cited, invalid=invalid,
                              ok=not invalid))
        return {"decision": "answer" if answered else "abstain", "answer": reply.text,
                "reason": None if answered else "generator_refused",
                "citations": [self.brief(c) | {"valid": c not in invalid} for c in cited],
                "context": [self.brief(c) for c in ids], "closest": [], "trace": trace, "llm_calls": 1,
                "scores": None, "latency": latency}

    def ask_agent(self, question: str, production: Production) -> dict:
        tools = Tools(production, self.reranker.score, self.llm(SMALL_MODEL), self.llm(GENERATOR_MODEL))
        state = Agent(tools, self.tau).run(question)
        stages = Counter()
        for s in state["trace"]:
            stages[s["node"]] += s["ms"]
        retrieved = [chunk.control_id for chunk in state.get("retrieved", [])]
        return {"decision": state["decision"], "answer": state.get("answer"), "reason": state.get("reason"),
                "citations": [self.brief(c) | {"valid": c in retrieved} for c in state.get("citations", [])],
                "context": [self.brief(c) for c in retrieved],
                "closest": [self.brief(chunk.control_id) | {"score": chunk.score} for chunk in state.get("closest", [])],
                "trace": state["trace"], "llm_calls": sum(s["node"] in LLM_NODES for s in state["trace"]),
                "scores": {"top_score": state.get("top_score"), "tau": self.tau}, "latency": dict(stages)}

    def list_controls(self, family: str | None, q: str | None, limit: int, offset: int) -> dict:
        ids = sorted(self.controls, key=catalog_order)
        if family:
            ids = [c for c in ids if self.controls[c]["family"].lower() == family.lower()]
        if q:
            try:
                exact = normalize_control_id(q)
            except ValueError:
                exact = None
            needle = q.lower()
            ids = [c for c in ids if exact in (c, self.controls[c]["parent_id"])
                   or needle in c or needle in self.controls[c]["title"].lower()]
        return {"total": len(ids),
                "controls": [self.brief(c) | {"parent_id": self.controls[c]["parent_id"]} for c in ids[offset:offset + limit]]}

    def families(self) -> list[dict]:
        counts = Counter(c["family"] for c in self.controls.values())
        return [{"family": family, "controls": n} for family, n in sorted(counts.items())]

    def control(self, raw_id: str) -> dict | None:
        try:
            control_id = normalize_control_id(raw_id)
        except ValueError:
            return None
        row = self.conn.execute("SELECT statement, guidance FROM controls WHERE id = %s", (control_id,)).fetchone()
        if row is None:
            return None
        parent = self.controls[control_id]["parent_id"]
        return self.brief(control_id) | {
            "statement": row[0], "guidance": row[1], "parent": self.brief(parent) if parent else None,
            "enhancements": [self.brief(c) for c in sorted(self.controls, key=catalog_order)
                             if self.controls[c]["parent_id"] == control_id]}

    def results(self) -> list[str]:
        return sorted(path.stem for path in RESULTS.glob("*.json"))

    def result(self, name: str) -> dict | None:
        return read_result(name) if re.fullmatch(r"[a-z0-9_]+", name) else None

    def configs(self) -> dict:
        """Every retrieval setup and answering system tested, its dev and test numbers, and which is production."""
        baselines, ablations, agent, final = (read_result(n) for n in ("baselines_dev", "ablations_dev", "agent_dev",
                                                                       "final_test"))
        test_retrieval = final["retrieval"] if final else None
        test_generation = final["generation"]["systems"] if final else {}
        retrieval = [{"id": f"phase2-{name}", "phase": 2, "name": name, "retrieval": name, "strategy": baselines["strategy"],
                      "rerank": False, "dev": interval(system["metrics"]["all"][METRIC]),
                      "test": interval(test_retrieval["baselines"][name]["metrics"]["all"][METRIC]) if final else None,
                      "live": name in SCORE_KIND, "production": False}
                     for name, system in baselines["systems"].items()]
        for row in ablations["rows"]:
            test_row = next(r for r in test_retrieval["rows"] if r["row"] == row["row"]) if final else None
            retrieval.append({"id": f"phase3-row{row['row']}", "phase": 3, "name": f"row {row['row']}",
                              "retrieval": row["retrieval"], "strategy": row["strategy"], "rerank": row["rerank"],
                              "dev": interval(row["metrics"]["all"][METRIC]),
                              "test": interval(test_row["metrics"]["all"][METRIC]) if test_row else None,
                              "live": True, "production": row["row"] == ablations["production"]["pick"]})
        generation = [{"system": s, "tau": agent["agent"]["tau"] if s == "agent" else None,
                       "dev": {m: interval(agent["systems"][s]["metrics"][m]) for m in GENERATION_METRICS},
                       "test": ({m: interval(test_generation[s]["metrics"][m]) for m in GENERATION_METRICS}
                                if s in test_generation else None),
                       "production": s == self.production_system}
                      for s in agent["systems"]]
        return {"metric": METRIC, "k": K, "retrieval": retrieval, "generation": generation,
                "rules": {"retrieval": ablations["production"]["rule"], "tau": agent["agent"]["tau_rule"]}}

    def logs(self, pipeline: str | None, limit: int) -> dict:
        rows = self.conn.execute(
            "SELECT id, ts, query, pipeline, decision, latency_ms FROM query_log"
            " WHERE %(pipeline)s::text IS NULL OR pipeline = %(pipeline)s ORDER BY id DESC LIMIT %(limit)s",
            {"pipeline": pipeline, "limit": limit}).fetchall()
        pipelines = self.conn.execute("SELECT pipeline, count(*) FROM query_log GROUP BY pipeline ORDER BY pipeline")
        return {"pipelines": [{"pipeline": p, "requests": n} for p, n in pipelines],
                "logs": [{"id": i, "ts": ts.isoformat(), "query": q, "pipeline": p, "decision": d, "latency_ms": ms}
                         for i, ts, q, p, d, ms in rows]}

    def log(self, log_id: int) -> dict | None:
        row = self.conn.execute("SELECT id, ts, query, pipeline, retrieved, scores, latency_ms, decision, trace"
                                " FROM query_log WHERE id = %s", (log_id,)).fetchone()
        if row is None:
            return None
        keys = ("id", "ts", "query", "pipeline", "retrieved", "scores", "latency_ms", "decision", "trace")
        return dict(zip(keys, row, strict=True)) | {"ts": row[1].isoformat()}
