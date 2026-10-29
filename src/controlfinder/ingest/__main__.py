"""`make ingest`: fetch the pinned sources, parse, chunk, load Postgres, write corpus stats.

Every run replaces the controls and chunks tables, so the database always matches the pinned
sources. Embeddings live on the chunk rows and are replaced with them, so re-run `make embed`
after re-ingesting.
"""

import json
from pathlib import Path

from tokenizers import Tokenizer

from controlfinder.index.db import connect
from controlfinder.ingest.chunks import Chunk, build_chunks
from controlfinder.ingest.oscal import Control, parse_catalog
from controlfinder.ingest.sources import CATALOG, TOKENIZER, fetch
from controlfinder.ingest.stats import MAX_TOKENS, corpus_stats

OUT = Path("results/corpus_stats.json")


def load(controls: list[Control], chunks: list[Chunk]) -> None:
    """Replace both tables in one transaction. Base controls come first, so parent_id resolves."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE chunks, controls")
        cur.executemany(
            "INSERT INTO controls (id, family, title, statement, guidance, parent_id, is_enhancement)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [(c.id, c.family, c.title, c.statement, c.guidance, c.parent_id, c.is_enhancement) for c in controls],
        )
        cur.executemany(
            "INSERT INTO chunks (chunk_id, strategy, control_id, parent_control_id, text) VALUES (%s, %s, %s, %s, %s)",
            [(ch.chunk_id, ch.strategy, ch.control_id, ch.parent_control_id, ch.text) for ch in chunks],
        )


def main() -> None:
    catalog = json.loads(fetch(CATALOG).read_text())["catalog"]
    controls, withdrawn = parse_catalog(catalog)
    chunks = build_chunks(controls)
    if unrendered := [ch.chunk_id for ch in chunks if "{{" in ch.text]:
        raise RuntimeError(f"{len(unrendered)} chunks have unrendered placeholders, e.g. {unrendered[0]}")
    load(controls, chunks)
    stats = corpus_stats(catalog, controls, withdrawn, chunks, Tokenizer.from_file(str(fetch(TOKENIZER))))
    OUT.write_text(json.dumps(stats, indent=2) + "\n")

    print(f"parsed {stats['base_controls']} controls, {stats['enhancements']} enhancements; "
          f"skipped {len(withdrawn)} withdrawn")
    for strategy, s in stats["token_lengths"].items():
        print(f"{strategy}: {s['chunks']} chunks, {s['over_limit']} over {MAX_TOKENS} tokens")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
