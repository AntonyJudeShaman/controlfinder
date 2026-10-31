"""Every LLM call goes through `LLM`: one provider function, and a cache on disk.

The provider is a Cursor SDK local agent (Jude's choice over an Anthropic key, recorded in
DECISIONS.md). An agent isn't a plain model call: by default it can read files, run commands and
search the web, and it loads the rules of the folder it runs in. For an honest test the model
must see nothing but our prompt, so every call offers no tools (`tools=[]`, which the SDK
documents as text-only), runs in a fresh empty folder, loads no settings, and fails if the
stream still shows a tool call.

The cache is data/cache/llm.jsonl, keyed by provider, model and the exact prompt. Each entry
keeps the original latency and token counts, so a replay reports the same numbers and needs no
key. Swapping providers means writing one function with `cursor_agent`'s signature and pointing
PROVIDER at it.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import NamedTuple

from cursor_sdk import Agent, AgentOptions, Cursor, LocalAgentOptions
from dotenv import find_dotenv, load_dotenv

CACHE = Path("data/cache/llm.jsonl")


class Reply(NamedTuple):
    text: str
    ms: float  # wall-clock latency of the original call
    model: str  # the model the provider reports it ran
    input_tokens: int | None
    output_tokens: int | None


def api_key() -> str:
    load_dotenv(find_dotenv(usecwd=True))
    if not (key := os.environ.get("CURSOR_API_KEY")):
        raise RuntimeError("CURSOR_API_KEY is not set: add a Cursor user API key to .env")
    return key


@cache
def check_model(model: str) -> None:
    """Raises unless the key's account offers `model`. Also starts the SDK's bridge before any timing."""
    offered = {m.id for m in Cursor.models.list(api_key=api_key())}
    if model not in offered:
        raise ValueError(f"{model!r} isn't offered to this key; it offers {sorted(offered)}")


def cursor_agent(model: str, prompt: str) -> Reply:
    """One text-only run of a Cursor SDK local agent, in an empty folder."""
    check_model(model)
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as empty, Agent.create(
        AgentOptions(model=model, api_key=api_key(), tools=[], local=LocalAgentOptions(cwd=empty))
    ) as agent:
        run = agent.send(prompt)
        tool_calls = [message.name for message in run.messages() if message.type == "tool_call"]
        result = run.wait()
    ms = (time.perf_counter() - start) * 1000
    if result.status != "finished" or tool_calls:
        raise RuntimeError(f"run {result.id} ended {result.status!r} with tool calls {tool_calls}")
    usage = result.usage
    return Reply(result.result or "", ms, result.model.id if result.model else model,
                 usage.input_tokens if usage else None, usage.output_tokens if usage else None)


Provider = Callable[[str, str], Reply]  # (model, prompt) -> Reply
PROVIDER: Provider = cursor_agent


class LLM:
    """`llm(prompt)` replays the cached reply if this provider and model have seen this exact prompt."""

    def __init__(self, model: str, provider: Provider = PROVIDER, cache: Path = CACHE):
        self.model, self.provider, self.cache = model, provider, cache
        lines = cache.read_text().splitlines() if cache.exists() else []
        self.entries = {entry["key"]: entry for entry in map(json.loads, lines)}

    def __call__(self, prompt: str) -> Reply:
        key = hashlib.sha256(json.dumps([self.provider.__name__, self.model, prompt]).encode()).hexdigest()
        if key not in self.entries:
            reply = self.provider(self.model, prompt)
            entry = {"key": key, "provider": self.provider.__name__, "requested_model": self.model,
                     "prompt": prompt, **reply._asdict()}
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with self.cache.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            self.entries[key] = entry
        entry = self.entries[key]
        return Reply(*(entry[field] for field in Reply._fields))
