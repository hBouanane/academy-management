"""Tests for the default-state seed: one academy, one venue, three levels."""

import pytest

from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.seed import DEFAULT_LEVELS, seed_default_academy


@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def test_seed_creates_one_academy_one_venue_three_levels(conn):
    academy_id = seed_default_academy(conn)
    assert conn.execute("SELECT COUNT(*) FROM academy").fetchone()[0] == 1
    venues = conn.execute(
        "SELECT COUNT(*) FROM venue WHERE academy_id = ?", (academy_id,)
    ).fetchone()[0]
    assert venues == 1
    levels = [
        (r["name"], r["teaching_annees"])
        for r in conn.execute(
            "SELECT name, teaching_annees FROM school_level"
            " WHERE academy_id = ? ORDER BY sort_order",
            (academy_id,),
        )
    ]
    assert levels == list(DEFAULT_LEVELS)


def test_seed_split_defaults_are_30_10(conn):
    academy_id = seed_default_academy(conn)
    row = conn.execute(
        "SELECT venue_bp, owner_bp FROM academy WHERE id = ?", (academy_id,)
    ).fetchone()
    assert (row["venue_bp"], row["owner_bp"]) == (3000, 1000)


def test_seed_is_idempotent(conn):
    first = seed_default_academy(conn)
    second = seed_default_academy(conn)
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM academy").fetchone()[0] == 1
