"""Cross-encoder reranking with bge-reranker-base, cached on disk.

The embedder (bge-small) is a bi-encoder: it turns the query and each chunk into vectors
separately, so chunk vectors are computed once at ingest and a search only compares vectors.
A cross-encoder reads the query and one chunk together in a single pass, so every query word
can attend to every chunk word. That judges relevance much better, but nothing can be computed
ahead of time: every (query, chunk) pair is a full model run. So it only reorders the top 50.

Scores are the model's raw logits, higher meaning more relevant. They rank exactly like the
model's default sigmoid, which in float32 is exactly 1.0 for every logit of 17 or more and so
would tie the most confident pairs. A pair longer than 512 tokens loses the end of its chunk.

Each query's scores are appended to data/cache/rerank.jsonl, keyed by a hash of the model, its
revision, the length limit, the query and the chunk texts in order, together with the model's
time on the run that computed them. A rerun returns identical scores and the original latency.
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import torch
from sentence_transformers import CrossEncoder

MODEL = "BAAI/bge-reranker-base"
REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
MAX_LENGTH = 512
BATCH_SIZE = 32
CACHE = Path("data/cache/rerank.jsonl")


class Scored(NamedTuple):
    scores: list[float]
    ms: float  # the model's time for all the pairs, on the run that computed them
    truncated: int  # pairs over MAX_LENGTH tokens, cut from the chunk's end


def load_model() -> CrossEncoder:
    model = CrossEncoder(MODEL, revision=REVISION, device="cpu", max_length=MAX_LENGTH,
                         activation_fn=torch.nn.Identity())
    model.predict([("warm", "up")], show_progress_bar=False)  # the first call is slow; keep it out of the timings
    return model


class Reranker:
    """Scores (query, text) pairs, from the cache when it has them. The model loads on first use."""

    def __init__(self, cache: Path = CACHE, load: Callable[[], CrossEncoder] = load_model):
        self.cache, self.load, self.model = cache, load, None
        lines = cache.read_text().splitlines() if cache.exists() else []
        self.entries = {entry["key"]: entry for entry in map(json.loads, lines)}

    def score(self, query: str, texts: list[str]) -> Scored:
        key = hashlib.sha256(json.dumps([MODEL, REVISION, MAX_LENGTH, query, texts]).encode()).hexdigest()
        if key not in self.entries:
            self.entries[key] = self._compute(key, query, texts)
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with self.cache.open("a") as f:
                f.write(json.dumps(self.entries[key]) + "\n")
        entry = self.entries[key]
        return Scored(entry["scores"], entry["ms"], entry["truncated"])

    def _compute(self, key: str, query: str, texts: list[str]) -> dict:
        if self.model is None:
            self.model = self.load()
        start = time.perf_counter()
        scores = self.model.predict([(query, text) for text in texts], batch_size=BATCH_SIZE, show_progress_bar=False)
        ms = (time.perf_counter() - start) * 1000
        lengths = [len(self.model.tokenizer(query, text, verbose=False)["input_ids"]) for text in texts]
        return {"key": key, "query": query, "scores": [float(s) for s in scores], "ms": ms,
                "truncated": sum(n > MAX_LENGTH for n in lengths)}
