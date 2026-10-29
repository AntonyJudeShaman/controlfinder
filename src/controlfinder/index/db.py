"""The one place that knows how to reach Postgres and how to create the schema.

Ingest, retrieval, eval and the API all get their connections from `connect()`, so the
DATABASE_URL lookup lives in a single spot. Run as a module to apply schema.sql.
"""

import os
from pathlib import Path

import psycopg
from dotenv import find_dotenv, load_dotenv

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_url() -> str:
    load_dotenv(find_dotenv(usecwd=True))
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set: copy .env.example to .env or export it.")
    return url


def connect(**kwargs) -> psycopg.Connection:
    return psycopg.connect(database_url(), **kwargs)


def apply_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA_PATH.read_text())


if __name__ == "__main__":
    apply_schema()
    print(f"applied {SCHEMA_PATH.name}")
