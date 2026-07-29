import sqlite3
from pathlib import Path

_SCHEMA = Path(__file__).joinpath("..", "migrations", "0001_initial.sql").resolve()


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA.read_text(encoding="utf-8"))
