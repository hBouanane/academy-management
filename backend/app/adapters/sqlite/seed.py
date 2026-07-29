"""Default state: one academy, one venue, the three Moroccan school levels.

Mirrors the client's current Excel reality so the app works out of the box;
everything seeded here is editable through the app later.
"""

import sqlite3

DEFAULT_LEVELS = ("Primaire", "Collège", "Lycée")


def seed_default_academy(
    connection: sqlite3.Connection,
    *,
    name: str = "Mon académie",
    venue_name: str = "Salle principale",
) -> int:
    existing = _existing_academy_id(connection)
    if existing is not None:
        return existing
    academy_id = _insert_academy(connection, name)
    _insert_venue(connection, academy_id, venue_name)
    _insert_levels(connection, academy_id)
    connection.commit()
    return academy_id


def _existing_academy_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute("SELECT id FROM academy ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


def _insert_academy(connection: sqlite3.Connection, name: str) -> int:
    return connection.execute(
        "INSERT INTO academy (name) VALUES (?)", (name,)
    ).lastrowid


def _insert_venue(connection: sqlite3.Connection, academy_id: int, name: str) -> None:
    connection.execute(
        "INSERT INTO venue (academy_id, name) VALUES (?, ?)", (academy_id, name)
    )


def _insert_levels(connection: sqlite3.Connection, academy_id: int) -> None:
    connection.executemany(
        "INSERT INTO school_level (academy_id, name, sort_order) VALUES (?, ?, ?)",
        [(academy_id, level, order) for order, level in enumerate(DEFAULT_LEVELS)],
    )
