"""Adapter tests for the SQLite schema — written before schema.sql existed (TDD)."""

import sqlite3

import pytest

from app.adapters.sqlite.db import connect, init_db


@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def insert_minimal_enrollment(conn, month="2026-09"):
    academy = conn.execute("INSERT INTO academy (name) VALUES ('A')").lastrowid
    level = conn.execute(
        "INSERT INTO school_level (academy_id, name) VALUES (?, 'Primaire')", (academy,)
    ).lastrowid
    student = conn.execute(
        "INSERT INTO student (academy_id, level_id, name) VALUES (?, ?, 'Sami')",
        (academy, level),
    ).lastrowid
    package = conn.execute(
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes)"
        " VALUES (?, 2, 20000)",
        (academy,),
    ).lastrowid
    conn.execute(
        "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
        " VALUES (?, ?, ?, 20000)",
        (student, package, month),
    )
    return student, package


def test_init_db_is_idempotent(conn):
    init_db(conn)  # second run must not raise


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO student (academy_id, level_id, name) VALUES (99, 99, 'X')"
        )


def test_one_enrollment_per_student_per_month(conn):
    student, package = insert_minimal_enrollment(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
            " VALUES (?, ?, '2026-09', 20000)",
            (student, package),
        )


@pytest.mark.parametrize("bad_month", ["oct-2026", "2026-13", "2026-00", "2026-9"])
def test_month_format_is_checked(conn, bad_month):
    with pytest.raises(sqlite3.IntegrityError):
        insert_minimal_enrollment(conn, month=bad_month)


def test_students_carry_active_flag_for_soft_deactivation(conn):
    insert_minimal_enrollment(conn)
    conn.execute("UPDATE student SET is_active = 0")
    row = conn.execute("SELECT is_active FROM student").fetchone()
    assert row["is_active"] == 0


def test_ledger_rejects_unknown_entry_types(conn):
    academy = conn.execute("INSERT INTO academy (name) VALUES ('A')").lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ledger_entry (academy_id, month, entry_type, amount_centimes)"
            " VALUES (?, '2026-09', 'edit', 100)",
            (academy,),
        )
