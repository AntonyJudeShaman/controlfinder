"""The API on the real database, with fake models: no model call, no download.

The fake embedder returns AC-2's own stored vector for every query, so dense search must put
AC-2 first. The fake generator cites AC-2, or refuses when the question asks it to. Rows the
tests write to query_log are deleted afterwards.
"""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from controlfinder.api.app import create_app
from controlfinder.api.backend import Backend
from controlfinder.generation.llm import LLM, Reply
from controlfinder.generation.prompt import SENTINEL
from controlfinder.index.db import connect
from controlfinder.obs.report import summarize
from controlfinder.retrieval.rerank import Reranker


class FakeEmbedder:
    def __init__(self, vector: list[float]):
        self.vector = np.array(vector, dtype=np.float32)

    def encode(self, texts, batch_size, normalize_embeddings):
        return np.stack([self.vector for _ in texts])


class FakeCrossEncoder:
    def predict(self, pairs, batch_size, show_progress_bar):
        return [float(len(text.split())) for _, text in pairs]

    def tokenizer(self, query, text, verbose):
        return {"input_ids": (query + " " + text).split()}


def fake_model(model: str, prompt: str) -> Reply:
    if "IN_SCOPE or OUT_OF_SCOPE" in prompt:
        text = "IN_SCOPE"
    elif "please refuse" in prompt:
        text = f"{SENTINEL}: the controls don't say."
    else:
        text = "Manage the accounts [AC-2]."
    return Reply(text, 5.0, model, 10, 5)


@pytest.fixture
def client(tmp_path):
    with connect(autocommit=True) as conn:
        (vector,) = conn.execute("SELECT embedding::text FROM chunks WHERE chunk_id = 'C:ac-2'").fetchone()
        (last_id,) = conn.execute("SELECT coalesce(max(id), 0) FROM query_log").fetchone()
        app = create_app(lambda c: Backend(c, FakeEmbedder(json.loads(vector)),
                                           Reranker(tmp_path / "rerank.jsonl", load=FakeCrossEncoder),
                                           lambda model: LLM(model, fake_model, tmp_path / "llm.jsonl")))
        with TestClient(app) as test_client:
            yield test_client
        conn.execute("DELETE FROM query_log WHERE id > %s", (last_id,))


def logged(client: TestClient, log_id: int) -> dict:
    return client.get(f"/logs/{log_id}").json()


def test_search_defaults_to_production_and_logs_each_stage(client):
    body = client.get("/search", params={"q": "who may have an account?"}).json()
    assert body["production"] and body["score_kind"] == "cosine"
    assert [h["display_id"] for h in body["hits"]][0] == "AC-2" and len(body["hits"]) == 10
    row = logged(client, body["log_id"])
    assert row["pipeline"] == "search/dense/C_separate"
    assert set(row["latency_ms"]) == {"embed", "retrieve", "total", "wall"}
    assert row["retrieved"] == [h["parent_id"] for h in body["hits"]]


def test_search_knobs_change_the_setup(client):
    body = client.get("/search", params={"q": "account management", "retrieval": "hybrid", "k": 5,
                                         "rerank": True}).json()
    assert not body["production"] and body["score_kind"] == "rerank_logit" and len(body["hits"]) == 5
    scores = [h["score"] for h in body["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert "rerank" in logged(client, body["log_id"])["latency_ms"]


@pytest.mark.parametrize("params", [{"retrieval": "fts"}, {"k": 0}, {"k": 51}, {"strategy": "D"}, {"q": ""}])
def test_search_rejects_unknown_knobs(client, params):
    assert client.get("/search", params={"q": "x"} | params).status_code == 422


def test_ask_defaults_to_the_production_pick_and_checks_citations(client):
    body = client.post("/ask", json={"question": "How should accounts be managed?"}).json()
    assert body["system"] == "pipeline_base_text" and body["production"]
    assert body["decision"] == "answer" and body["llm_calls"] == 1
    assert body["citations"] == [{"control_id": "ac-2", "display_id": "AC-2", "title": "Account Management",
                                  "family": "AC", "valid": True}]
    assert [s["node"] for s in body["trace"]] == ["retrieve", "generate", "verify_citations"]
    row = logged(client, body["log_id"])
    assert row["pipeline"] == "ask/pipeline_base_text" and row["decision"] == "answer"
    assert set(row["latency_ms"]) == {"retrieve", "generate", "verify_citations", "total", "wall"}


def test_ask_reports_a_refusal(client):
    body = client.post("/ask", json={"question": "Do this one? please refuse", "system": "pipeline"}).json()
    assert body["decision"] == "abstain" and body["reason"] == "generator_refused" and body["citations"] == []
    assert [s["node"] for s in body["trace"]] == ["retrieve", "generate"]
    assert logged(client, body["log_id"])["decision"] == "abstain"


def test_ask_agent_logs_every_step(client):
    body = client.post("/ask", json={"question": "How should accounts be managed?", "system": "agent"}).json()
    assert body["decision"] == "answer" and body["llm_calls"] == 2
    assert [s["node"] for s in body["trace"]] == ["scope_check", "retrieve", "grade_evidence", "generate",
                                                  "verify_citations"]
    row = logged(client, body["log_id"])
    assert row["pipeline"] == "ask/agent" and row["trace"] == body["trace"]


def test_ask_rejects_an_unknown_system(client):
    assert client.post("/ask", json={"question": "x", "system": "oracle"}).status_code == 422


def test_controls_browse_search_and_detail(client):
    listed = client.get("/controls", params={"family": "ac", "limit": 3}).json()
    assert [c["display_id"] for c in listed["controls"]] == ["AC-1", "AC-2", "AC-2(1)"]
    assert "ac-2.3" in [c["control_id"] for c in client.get("/controls", params={"q": "AC-2(3)"}).json()["controls"]]
    detail = client.get("/controls/AC-2").json()
    assert detail["statement"] and detail["parent"] is None and detail["enhancements"][0]["display_id"] == "AC-2(1)"
    assert client.get("/controls/AC-2(1)").json()["parent"]["display_id"] == "AC-2"
    assert client.get("/controls/nonsense").status_code == 404


def test_results_serves_only_results_files(client):
    assert "ablations_dev" in client.get("/results").json()
    assert client.get("/results/ablations_dev").json()["split"] == "dev"
    assert client.get("/results/pyproject").status_code == 404
    assert client.get("/results/Not-A-Name").status_code == 404


def test_configs_mark_one_production_setup_each(client):
    body = client.get("/configs").json()
    [retrieval] = [c for c in body["retrieval"] if c["production"]]
    assert (retrieval["retrieval"], retrieval["strategy"], retrieval["rerank"]) == ("dense", "C_separate", False)
    assert [g["system"] for g in body["generation"] if g["production"]] == ["pipeline_base_text"]


def test_logs_list_the_newest_first(client):
    first = client.get("/search", params={"q": "one"}).json()["log_id"]
    second = client.get("/search", params={"q": "two"}).json()["log_id"]
    listed = client.get("/logs", params={"pipeline": "search/dense/C_separate", "limit": 2}).json()
    assert [r["id"] for r in listed["logs"]] == [second, first]
    assert client.get("/logs/0").status_code == 404


def test_report_percentiles_and_abstention_rate():
    report = summarize([("ask/x", {"generate": 10.0, "total": 10.0}, "answer"),
                        ("ask/x", {"generate": 30.0, "total": 30.0}, "abstain"),
                        ("search/y", {"retrieve": 5.0}, None)])
    assert report["ask/x"]["latency_ms"]["generate"]["p50"] == 20.0
    assert report["ask/x"]["abstention_rate"] == 0.5
    assert report["search/y"] == {"requests": 1, "latency_ms": {"retrieve": {"p50": 5.0, "p95": 5.0}},
                                  "decided": 0, "abstained": 0, "abstention_rate": None}
