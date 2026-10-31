"""Retrievers on hand-made chunks (rolled back afterwards) and dense search on the real index."""

import pytest

from controlfinder.index.db import connect
from controlfinder.retrieval import fetch_depth, fts
from controlfinder.retrieval.bm25 import BM25Index
from controlfinder.retrieval.dense import EXACT, plan, search
from controlfinder.retrieval.pipeline import Retriever

TEST_CHUNKS = {"T:1": "Quokka zebra habitat", "T:2": "Quokka habitat", "T:3": "Managing accounts and accounting"}


@pytest.fixture
def conn():
    with connect() as conn:
        conn.execute("INSERT INTO controls (id, family, title, statement, is_enhancement) "
                     "VALUES ('zz-1', 'ZZ', 'Test control', 'Test statement', false)")
        for chunk_id, text in TEST_CHUNKS.items():
            conn.execute("INSERT INTO chunks (chunk_id, strategy, control_id, parent_control_id, text) "
                         "VALUES (%s, 'C_separate', 'zz-1', 'zz-1', %s)", (chunk_id, text))
        yield conn
        conn.rollback()


@pytest.fixture
def embedded():
    with connect(autocommit=True) as conn:
        (n,) = conn.execute("SELECT count(*) FROM chunks WHERE strategy = 'C_separate' AND embedding IS NOT NULL").fetchone()
        if n == 0:
            pytest.skip("no embeddings: run `make embed`")
        yield conn


def test_fts_and_needs_every_lexeme_or_needs_one(conn):
    assert [h.chunk_id for h in fts.search(conn, "quokka zebras", "C_separate", "and", 10)] == ["T:1"]
    assert [h.chunk_id for h in fts.search(conn, "quokka zebras", "C_separate", "or", 10)] == ["T:1", "T:2"]


def test_fts_rejects_an_unknown_strategy(conn):
    with pytest.raises(ValueError):
        fts.search(conn, "quokka", "C", "or", 10)


def test_bm25_counts_the_same_lexemes_as_the_tsv_column(conn):
    index = BM25Index(conn, "C_separate")
    (tsv,) = conn.execute("SELECT tsv::text FROM chunks WHERE chunk_id = 'T:3'").fetchone()
    assert tsv == "'account':2,4 'manag':1"
    assert index.bm25.doc_freqs[index.chunk_ids.index("T:3")] == {"manag": 1, "account": 2}
    assert [h.chunk_id for h in index.search(conn, "quokka zebras", 10)][:2] == ["T:1", "T:2"]


def test_fetch_depth_is_k_when_every_parent_has_one_chunk(conn):
    assert fetch_depth(conn, "A_control_only", 20) == 20


def test_retriever_rolls_two_matching_chunks_up_to_one_parent(conn):
    hits = Retriever(conn, "C_separate").search("bm25", "quokka zebras", "")
    assert [(h.chunk_id, h.parent_control_id) for h in hits] == [("T:1", "zz-1")]


def test_hnsw_settings_survive_an_eval_loop(embedded):
    vectors = [v for (v,) in embedded.execute(
        "SELECT embedding::text FROM chunks WHERE strategy = 'C_separate' ORDER BY chunk_id LIMIT 12")]
    for v in vectors:  # enough runs for psycopg to prepare the statement
        assert len(search(embedded, v, "C_separate", 100, EXACT)) == 100
    hnsw = {"enable_seqscan": "off", "hnsw.ef_search": "40"}
    assert len(search(embedded, vectors[0], "C_separate", 100, hnsw)) == 40
    assert "chunks_embedding_hnsw_c" in plan(embedded, vectors[0], "C_separate", 100, hnsw)
    assert "Seq Scan" in plan(embedded, vectors[0], "C_separate", 100, EXACT)
