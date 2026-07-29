import sqlite3

from .migrations import migrate


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    """Bring the database to the latest schema version (fresh or existing)."""
    migrate(connection)
