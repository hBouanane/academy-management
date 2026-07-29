"""Versioned schema migrations on SQLite's built-in PRAGMA user_version.

Files in this package named NNNN_description.sql are applied in order.
A database at version N receives exactly the migrations above N; after
each successful script, user_version is bumped to that migration's number.
"""

import sqlite3
from pathlib import Path

_HERE = Path(__file__).parent


class MigrationError(RuntimeError):
    pass


def migrate(connection: sqlite3.Connection) -> int:
    """Bring the database to the latest schema version; returns that version."""
    current = _current_version(connection)
    target = latest_version()
    if current > target:
        raise MigrationError(
            f"database is at version {current}, but this app only knows {target};"
            " it was created by a newer release"
        )
    for version, path in _pending(current):
        _apply(connection, version, path)
    return target


def latest_version() -> int:
    return max(version for version, _ in _migration_files())


def _current_version(connection: sqlite3.Connection) -> int:
    return connection.execute("PRAGMA user_version").fetchone()[0]


def _migration_files() -> list[tuple[int, Path]]:
    files = sorted(_HERE.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise MigrationError(f"no migration files found in {_HERE}")
    return [(int(path.name[:4]), path) for path in files]


def _pending(current: int) -> list[tuple[int, Path]]:
    return [(version, path) for version, path in _migration_files() if version > current]


def _apply(connection: sqlite3.Connection, version: int, path: Path) -> None:
    connection.executescript(path.read_text(encoding="utf-8"))
    connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
