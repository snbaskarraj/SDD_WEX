"""DuckDB over the parquet portfolio."""

from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

from fleetline.generate import TABLES, generate_dataset
from fleetline.paths import data_dir

_LOCK = threading.Lock()


def _ready(directory: Path) -> bool:
    return all((directory / f"{table}.parquet").exists() for table in TABLES)


def ensure_data(directory: Path | None = None) -> Path:
    target = directory or data_dir()
    if not _ready(target):
        generate_dataset(target)
    return target


def _python(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        return item()
    return value


class Store:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.con = duckdb.connect()
        self.lock = threading.Lock()
        for table in TABLES:
            path = (directory / f"{table}.parquet").as_posix().replace("'", "''")
            self.con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path}')")

    def query(self, sql: str, params: list[object]) -> list[dict]:
        with self.lock:
            cursor = self.con.execute(sql, params)
            columns = [item[0] for item in cursor.description]
            return [
                {column: _python(value) for column, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]

    def counts(self) -> dict[str, int]:
        with self.lock:
            return {
                table: int(self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in TABLES
            }


def open_store() -> Store:
    with _LOCK:
        return Store(ensure_data())
