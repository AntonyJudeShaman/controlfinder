"""Corpus statistics, with chunk lengths measured in the embedding model's own tokens.

bge-small-en-v1.5 reads at most 512 tokens and silently ignores the rest, so word or character
counts don't say what the model actually sees. We count with its tokenizer at the pinned
revision, including the [CLS] and [SEP] tokens it adds, and report per strategy how many chunks
go past the limit and what share of their tokens falls beyond it.
"""

from collections import Counter, defaultdict
from statistics import median, quantiles

from tokenizers import Tokenizer

from controlfinder.ingest.chunks import STRATEGIES, Chunk
from controlfinder.ingest.oscal import Control, Withdrawn, catalog_items
from controlfinder.ingest.sources import CATALOG, EMBED_MODEL, EMBED_REVISION

MAX_TOKENS = 512  # max_seq_length in the model's sentence_bert_config.json


def length_summary(lengths: dict[str, int]) -> dict:
    """Token-length distribution for one strategy, from {chunk_id: tokens}."""
    values = list(lengths.values())
    return {
        "chunks": len(values),
        "min": min(values),
        "median": median(values),
        "p90": round(quantiles(values, n=10, method="inclusive")[-1], 1),
        "max": max(values),
        "longest_chunk": max(lengths, key=lengths.get),
        "over_limit": sum(n > MAX_TOKENS for n in values),
        "tokens_past_limit_share": round(sum(max(0, n - MAX_TOKENS) for n in values) / sum(values), 4),
    }


def corpus_stats(
    catalog: dict, controls: list[Control], withdrawn: list[Withdrawn], chunks: list[Chunk], tokenizer: Tokenizer
) -> dict:
    lengths = defaultdict(dict)
    for chunk, encoding in zip(chunks, tokenizer.encode_batch([c.text for c in chunks])):
        lengths[chunk.strategy][chunk.chunk_id] = len(encoding.ids)
    return {
        "catalog": {
            "url": CATALOG.url,
            "sha256": CATALOG.sha256,
            "version": catalog["metadata"]["version"],
            "last_modified": catalog["metadata"]["last-modified"],
        },
        "tokenizer": {"model": EMBED_MODEL, "revision": EMBED_REVISION, "max_tokens": MAX_TOKENS},
        "families": len(catalog["groups"]),
        "base_controls": sum(not c.is_enhancement for c in controls),
        "enhancements": sum(c.is_enhancement for c in controls),
        "withdrawn": {
            "base_controls": sum(not w.is_enhancement for w in withdrawn),
            "enhancements": sum(w.is_enhancement for w in withdrawn),
            "by_relation": dict(sorted(Counter(w.relation or "none" for w in withdrawn).items())),
        },
        "id_labels_checked": sum(p["name"] == "label" for _, _, item in catalog_items(catalog) for p in item.get("props", [])),
        "token_lengths": {s: length_summary(lengths[s]) for s in STRATEGIES},
    }
