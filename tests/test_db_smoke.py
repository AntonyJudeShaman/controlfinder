"""Smoke tests: the database is reachable and has what later phases rely on.

These fail loudly if Docker isn't up, the pgvector image is too old, or schema.sql didn't
apply. Each test runs in a transaction that is rolled back, so nothing is left behind.
"""

import pytest

from controlfinder.index.db import connect

STRATEGIES = ("A_control_only", "B_control_plus_enh", "C_separate")


@pytest.fixture
def conn():
    with connect() as conn:
        yield conn
        conn.rollback()


def test_pgvector_supports_iterative_index_scans(conn):
    (version,) = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert tuple(int(part) for part in version.split(".")) >= (0, 8, 0)
    # hnsw.* settings exist only once the extension library is loaded in this session;
    # before that, Postgres would accept any hnsw.foo as a placeholder and prove nothing.
    conn.execute("SELECT '[1,2,3]'::vector")
    (setting,) = conn.execute("SHOW hnsw.iterative_scan").fetchone()
    assert setting == "off"


def test_tables_exist(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert {"controls", "chunks", "query_log"} <= {name for (name,) in rows}


def test_tsv_is_generated_from_text(conn):
    conn.execute(
        "INSERT INTO controls (id, family, title, statement, is_enhancement) "
        "VALUES ('zz-1', 'zz', 'Test control', 'Test statement', false)"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, strategy, control_id, parent_control_id, text) "
        "VALUES ('test', 'C_separate', 'zz-1', 'zz-1', 'Managing accounts and accounting')"
    )
    (tsv,) = conn.execute("SELECT tsv::text FROM chunks WHERE chunk_id = 'test'").fetchone()
    # Stemming folds "accounts" and "accounting" into one lexeme; the stopword "and" is
    # dropped but still occupies position 3.
    assert tsv == "'account':2,4 'manag':1"


def test_one_hnsw_index_per_strategy(conn):
    rows = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks' AND indexdef LIKE '%USING hnsw%'"
    ).fetchall()
    for strategy in STRATEGIES:
        assert sum(f"'{strategy}'" in indexdef for (indexdef,) in rows) == 1
    assert all("vector_cosine_ops" in indexdef for (indexdef,) in rows)
