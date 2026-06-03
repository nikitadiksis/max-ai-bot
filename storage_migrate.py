from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from storage_backend import create_storage_backend


TABLE_ORDER = (
    "users",
    "payment_requests",
    "usage_events",
    "promo_activations",
    "promo_bonus_grants",
    "processed_updates",
)

TABLE_ID_COLUMNS = {
    "payment_requests": "id",
    "usage_events": "id",
    "promo_activations": "id",
    "promo_bonus_grants": "id",
}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_table_rows(source_backend: Any, table: str) -> list[dict[str, Any]]:
    with source_backend.connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(row) for row in rows]


def truncate_target(target_backend: Any) -> None:
    with target_backend.connect() as conn:
        for table in reversed(TABLE_ORDER):
            conn.execute(f"DELETE FROM {table}")


def insert_rows(target_backend: Any, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(quote_ident(column) for column in columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"
    with target_backend.connect() as conn:
        for row in rows:
            conn.execute(sql, tuple(row.get(column) for column in columns))
        if target_backend.kind == "postgres":
            id_column = TABLE_ID_COLUMNS.get(table)
            if id_column:
                seq_name = f"{table}_{id_column}_seq"
                conn.execute(
                    f"SELECT setval(?, COALESCE((SELECT MAX({quote_ident(id_column)}) FROM {table}), 1), true)",
                    (seq_name,),
                )


def migrate(source_url: str, target_url: str) -> None:
    source_path = Path(os.getenv("SOURCE_DB_PATH", "data/bot.sqlite3"))
    target_path = Path(os.getenv("TARGET_DB_PATH", "data/bot.sqlite3"))
    source_backend = create_storage_backend(source_path, source_url)
    target_backend = create_storage_backend(target_path, target_url)
    truncate_target(target_backend)
    for table in TABLE_ORDER:
        rows = read_table_rows(source_backend, table)
        insert_rows(target_backend, table, rows)
        print(f"{table}: {len(rows)} rows")


def main() -> None:
    source_url = os.getenv("SOURCE_DATABASE_URL", "").strip()
    target_url = os.getenv("TARGET_DATABASE_URL", "").strip()
    source_path = os.getenv("SOURCE_DB_PATH", "data/bot.sqlite3").strip()
    target_path = os.getenv("TARGET_DB_PATH", "data/bot.sqlite3").strip()
    if not source_url and not source_path:
        raise SystemExit("Set SOURCE_DATABASE_URL or SOURCE_DB_PATH before running migration")
    if not target_url and not target_path:
        raise SystemExit("Set TARGET_DATABASE_URL or TARGET_DB_PATH before running migration")
    print("Target schema must already be initialized by the app before running this script.")
    migrate(source_url, target_url)


if __name__ == "__main__":
    main()
