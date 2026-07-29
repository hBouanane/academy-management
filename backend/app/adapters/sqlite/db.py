import sqlite3

from .migrations import migrate


def connect(path: str) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI opens/closes per-request connections
    # from different threadpool threads; each connection is still used by
    # one request at a time, so this is safe.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    """Bring the database to the latest schema version (fresh or existing)."""
    migrate(connection)
