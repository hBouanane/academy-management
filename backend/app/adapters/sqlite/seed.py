"""Default state: one academy, one venue, the Moroccan school levels.

Mirrors the client's current Excel reality so the app works out of the box;
everything seeded here is editable through the app later. Formation is the
fourth niveau: vocational courses outside the school ladder.
"""

import sqlite3

# (name, teaching_annees): 0 = one teaching block, N = split into N années.
DEFAULT_LEVELS = (
    ("Primaire", 0),
    ("Collège", 3),
    ("Lycée", 3),
    ("Formation", 0),
)


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
        "INSERT INTO school_level (academy_id, name, sort_order, teaching_annees)"
        " VALUES (?, ?, ?, ?)",
        [
            (academy_id, name, order, annees)
            for order, (name, annees) in enumerate(DEFAULT_LEVELS)
        ],
    )
