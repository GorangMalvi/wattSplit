"""
Create or update the wattSplit tables in Supabase from schema.sql.

Usage (safe to re-run):
    python -m app.init_schema
    docker compose exec backend python -m app.init_schema
"""
from __future__ import annotations

import psycopg

from . import db


def main() -> None:
    sql = db.SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(db.database_url(), prepare_threshold=None) as conn:
        conn.execute(sql)
    print(f"Applied {db.SCHEMA_PATH.name}")


if __name__ == "__main__":
    main()
