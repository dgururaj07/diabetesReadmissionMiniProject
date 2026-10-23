import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ENV_PATH = Path(__file__).parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _connect() -> psycopg.Connection:
    load_env()
    # libpq reads PGHOST, PGPORT, PGDATABASE, PGUSER and PGPASSWORD from the environment.
    return psycopg.connect(row_factory=dict_row, connect_timeout=5)


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    with _connect() as conn:
        return conn.execute(sql, params).fetchone()
