"""Tests for the user_version migration runner — written first (TDD)."""

import pytest

from app.adapters.sqlite.db import connect
from app.adapters.sqlite.migrations import (
    MigrationError,
    latest_version,
    migrate,
)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def user_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def table_names(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_fresh_database_migrates_to_latest_version(conn):
    applied = migrate(conn)
    assert user_version(conn) == latest_version()
    assert applied == latest_version()
    assert {"academy", "student", "enrollment", "ledger_entry"} <= table_names(conn)


def test_migrate_twice_applies_nothing_new(conn):
    migrate(conn)
    tables_before = table_names(conn)
    migrate(conn)
    assert user_version(conn) == latest_version()
    assert table_names(conn) == tables_before


def test_partially_migrated_database_gets_only_missing_steps(conn):
    # A database created before the runner existed: schema present, version 0.
    migrate(conn)
    conn.execute("PRAGMA user_version = 0")
    applied = migrate(conn)
    assert applied == latest_version()
    assert user_version(conn) == latest_version()


def test_database_from_a_newer_app_version_is_refused(conn):
    conn.execute(f"PRAGMA user_version = {latest_version() + 1}")
    with pytest.raises(MigrationError):
        migrate(conn)


def test_latest_version_matches_migration_files():
    assert latest_version() >= 1
