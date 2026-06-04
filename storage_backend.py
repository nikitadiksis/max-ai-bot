from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
import sqlite3

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg = None
    dict_row = None


StorageRow = Mapping[str, Any] | sqlite3.Row


def _translate_placeholders(sql: str) -> str:
    result: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                result.append("''")
                i += 2
                continue
            in_single = not in_single
            result.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            result.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            result.append("%s")
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


class CursorAdapter:
    @property
    def rowcount(self) -> int:
        raise NotImplementedError

    def fetchone(self) -> StorageRow | None:
        raise NotImplementedError

    def fetchall(self) -> list[StorageRow]:
        raise NotImplementedError


class SQLiteCursorAdapter(CursorAdapter):
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self.cursor = cursor

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    def fetchone(self) -> StorageRow | None:
        return self.cursor.fetchone()

    def fetchall(self) -> list[StorageRow]:
        return self.cursor.fetchall()


class PostgresCursorAdapter(CursorAdapter):
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    def fetchone(self) -> StorageRow | None:
        return self.cursor.fetchone()

    def fetchall(self) -> list[StorageRow]:
        return self.cursor.fetchall()


class ConnectionAdapter:
    def execute(self, sql: str, params: Iterable[Any] | None = None) -> CursorAdapter:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> ConnectionAdapter:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


class SQLiteConnectionAdapter(ConnectionAdapter):
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> CursorAdapter:
        cursor = self.conn.execute(sql, tuple(params or ()))
        return SQLiteCursorAdapter(cursor)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


class PostgresConnectionAdapter(ConnectionAdapter):
    def __init__(self, database_url: str) -> None:
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self.conn = psycopg.connect(database_url, row_factory=dict_row)

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> CursorAdapter:
        cursor = self.conn.cursor()
        try:
            cursor.execute(_translate_placeholders(sql), tuple(params or ()))
        except Exception as exc:
            if is_unique_violation(exc):
                raise sqlite3.IntegrityError(str(exc)) from exc
            raise
        return PostgresCursorAdapter(cursor)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


@dataclass(slots=True)
class StorageBackend:
    kind: str
    db_path: Path
    database_url: str = ""

    def connect(self) -> ConnectionAdapter:
        if self.kind == "postgres":
            return PostgresConnectionAdapter(self.database_url)
        return SQLiteConnectionAdapter(self.db_path)

    @property
    def label(self) -> str:
        if self.kind == "postgres":
            return self.database_url or "postgres"
        return str(self.db_path)

    def exists(self) -> bool:
        if self.kind == "postgres":
            return bool(self.database_url)
        return self.db_path.exists()

    def size_bytes(self) -> int:
        if self.kind == "postgres":
            return 0
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    def backup_suffix(self) -> str:
        return ".json" if self.kind == "postgres" else ".sqlite3"


def create_storage_backend(db_path: Path, database_url: str) -> StorageBackend:
    url = (database_url or "").strip()
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return StorageBackend(kind="postgres", db_path=db_path, database_url=url)
    return StorageBackend(kind="sqlite", db_path=db_path, database_url="")


def is_unique_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    sqlstate = getattr(exc, "sqlstate", "")
    if sqlstate == "23505":
        return True
    message = str(exc).lower()
    return "unique constraint" in message or "duplicate key" in message
