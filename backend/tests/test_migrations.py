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
    # A database created before the runner existed: the v1 schema is present
    # but user_version was never set — exactly what _v1 fixtures simulate.
    from pathlib import Path

    import app.adapters.sqlite.migrations as m

    conn.executescript(
        Path(m.__file__).with_name("0001_initial.sql").read_text(encoding="utf-8")
    )
    conn.execute("PRAGMA user_version = 0")
    applied = migrate(conn)
    assert applied == latest_version()
    assert user_version(conn) == latest_version()
    assert {"motif", "payment"} <= table_names(conn)


def test_database_from_a_newer_app_version_is_refused(conn):
    conn.execute(f"PRAGMA user_version = {latest_version() + 1}")
    with pytest.raises(MigrationError):
        migrate(conn)


def test_latest_version_matches_migration_files():
    assert latest_version() >= 2


def _v1_database_with_a_payment(conn):
    """Simulate a client database created before migration 0002 existed."""
    from pathlib import Path

    import app.adapters.sqlite.migrations as m

    conn.executescript(
        Path(m.__file__).with_name("0001_initial.sql").read_text(encoding="utf-8")
    )
    conn.execute("PRAGMA user_version = 1")
    academy = conn.execute("INSERT INTO academy (name) VALUES ('A')").lastrowid
    level = conn.execute(
        "INSERT INTO school_level (academy_id, name) VALUES (?, 'P')", (academy,)
    ).lastrowid
    student = conn.execute(
        "INSERT INTO student (academy_id, level_id, name) VALUES (?, ?, 'S')",
        (academy, level),
    ).lastrowid
    package = conn.execute(
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes)"
        " VALUES (?, 1, 100)",
        (academy,),
    ).lastrowid
    enrollment = conn.execute(
        "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
        " VALUES (?, ?, '2026-09', 100)",
        (student, package),
    ).lastrowid
    payment = conn.execute(
        "INSERT INTO payment (enrollment_id, amount_centimes) VALUES (?, 100)",
        (enrollment,),
    ).lastrowid
    conn.execute(
        "INSERT INTO ledger_entry (academy_id, month, entry_type, amount_centimes,"
        " payment_id) VALUES (?, '2026-09', 'payment_in', 100, ?)",
        (academy, payment),
    )
    return enrollment


def test_migration_0002_preserves_existing_payments(conn):
    _v1_database_with_a_payment(conn)
    migrate(conn)
    row = conn.execute("SELECT * FROM payment").fetchone()
    assert row["amount_centimes"] == 100
    assert row["reversed_at"] is None
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    ledger = conn.execute("SELECT payment_id FROM ledger_entry").fetchone()
    assert ledger["payment_id"] == row["id"]


def test_migration_0002_rebuild_is_transactional():
    from pathlib import Path

    import app.adapters.sqlite.migrations as m

    script = (
        Path(m.__file__)
        .with_name("0002_reversible_payments.sql")
        .read_text(encoding="utf-8")
    )
    # Crash-safety recipe: the rebuild must be one explicit transaction.
    assert "BEGIN;" in script and "COMMIT;" in script
    assert script.index("BEGIN;") < script.index("DROP TABLE payment")
    assert script.index("DROP TABLE payment") < script.index("COMMIT;")


def test_migration_0002_allows_repost_only_after_reversal(conn):
    import sqlite3

    enrollment = _v1_database_with_a_payment(conn)
    migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO payment (enrollment_id, amount_centimes) VALUES (?, 100)",
            (enrollment,),
        )
    conn.execute("UPDATE payment SET reversed_at = datetime('now')")
    conn.execute(
        "INSERT INTO payment (enrollment_id, amount_centimes) VALUES (?, 100)",
        (enrollment,),
    )
