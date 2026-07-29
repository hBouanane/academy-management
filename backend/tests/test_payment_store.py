"""Integration tests: post_payment through the real SQLite store — written first."""

import pytest

from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.adapters.sqlite.seed import seed_default_academy
from app.ports.payments import AlreadyPaidError
from app.services.payments import post_payment

DH = 100


@pytest.fixture
def conn():
    connection = connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def build_scenario(conn, *, teacher_names=("Ahmed", "Sara"), price=300 * DH):
    """One student enrolled in one subject per teacher, 2026-09, package price given."""
    academy_id = seed_default_academy(conn)
    level_id = conn.execute("SELECT id FROM school_level LIMIT 1").fetchone()["id"]
    class_ids = []
    for i, teacher_name in enumerate(teacher_names):
        subject_id = conn.execute(
            "INSERT INTO subject (academy_id, name) VALUES (?, ?)",
            (academy_id, f"Subject {i}"),
        ).lastrowid
        teacher_id = conn.execute(
            "INSERT INTO teacher (academy_id, name) VALUES (?, ?)",
            (academy_id, teacher_name),
        ).lastrowid
        class_ids.append(
            conn.execute(
                "INSERT INTO class_group (academy_id, level_id, subject_id, teacher_id)"
                " VALUES (?, ?, ?, ?)",
                (academy_id, level_id, subject_id, teacher_id),
            ).lastrowid
        )
    student_id = conn.execute(
        "INSERT INTO student (academy_id, level_id, name) VALUES (?, ?, 'Sami')",
        (academy_id, level_id),
    ).lastrowid
    package_id = conn.execute(
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes)"
        " VALUES (?, ?, ?)",
        (academy_id, len(teacher_names), price),
    ).lastrowid
    enrollment_id = conn.execute(
        "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
        " VALUES (?, ?, '2026-09', ?)",
        (student_id, package_id, price),
    ).lastrowid
    for class_id in class_ids:
        conn.execute(
            "INSERT INTO enrollment_class (enrollment_id, class_id) VALUES (?, ?)",
            (enrollment_id, class_id),
        )
    return {
        "academy_id": academy_id,
        "enrollment_id": enrollment_id,
        "class_ids": class_ids,
    }


def add_adjustment(
    conn, enrollment_id, *, scope="package", class_id=None, kind="amount", value=50 * DH
):
    return conn.execute(
        "INSERT INTO adjustment (enrollment_id, scope, class_id, kind, value, category)"
        " VALUES (?, ?, ?, ?, ?, 'discount')",
        (enrollment_id, scope, class_id, kind, value),
    ).lastrowid


def test_context_is_assembled_from_the_schema(conn):
    ids = build_scenario(conn)
    context = SqlitePaymentStore(conn).enrollment_context(ids["enrollment_id"])
    assert context.price == 300 * DH
    assert context.month == "2026-09"
    assert (context.venue_bp, context.owner_bp) == (3000, 1000)
    assert len(context.subject_teachers) == 2
    assert context.academy_id == ids["academy_id"]


def test_missing_enrollment_yields_none(conn):
    build_scenario(conn)
    assert SqlitePaymentStore(conn).enrollment_context(404) is None


def test_posting_writes_payment_and_balanced_ledger(conn):
    ids = build_scenario(conn)
    posted = post_payment(SqlitePaymentStore(conn), ids["enrollment_id"])
    payment = conn.execute("SELECT * FROM payment").fetchone()
    assert payment["amount_centimes"] == 300 * DH
    assert posted.payment_id == payment["id"]
    cash_in = conn.execute(
        "SELECT SUM(amount_centimes) FROM ledger_entry WHERE entry_type = 'payment_in'"
    ).fetchone()[0]
    paid_out = conn.execute(
        "SELECT SUM(amount_centimes) FROM ledger_entry WHERE entry_type != 'payment_in'"
    ).fetchone()[0]
    assert cash_in == 300 * DH
    assert cash_in == paid_out
    months = {row["month"] for row in conn.execute("SELECT month FROM ledger_entry")}
    assert months == {"2026-09"}


def test_double_posting_is_refused_and_ledger_untouched(conn):
    ids = build_scenario(conn)
    store = SqlitePaymentStore(conn)
    post_payment(store, ids["enrollment_id"])
    before = conn.execute("SELECT COUNT(*) FROM ledger_entry").fetchone()[0]
    with pytest.raises(AlreadyPaidError):
        post_payment(store, ids["enrollment_id"])
    after = conn.execute("SELECT COUNT(*) FROM ledger_entry").fetchone()[0]
    assert after == before


def test_bearerless_adjustment_charges_the_owner(conn):
    ids = build_scenario(conn)
    adjustment_id = add_adjustment(conn, ids["enrollment_id"], value=50 * DH)
    post_payment(SqlitePaymentStore(conn), ids["enrollment_id"])
    line = conn.execute(
        "SELECT * FROM ledger_entry WHERE entry_type = 'adjustment'"
    ).fetchone()
    assert line["beneficiary_kind"] == "owner"
    assert line["amount_centimes"] == -50 * DH
    assert line["adjustment_id"] == adjustment_id
    net = conn.execute("SELECT amount_centimes FROM payment").fetchone()[0]
    assert net == 250 * DH


def test_subject_scoped_adjustment_resolves_against_that_subject(conn):
    ids = build_scenario(conn)  # 300 DH over 2 subjects -> 150 DH per subject
    add_adjustment(
        conn,
        ids["enrollment_id"],
        scope="subject",
        class_id=ids["class_ids"][1],
        kind="percent",
        value=10_000,
    )
    post_payment(SqlitePaymentStore(conn), ids["enrollment_id"])
    line = conn.execute(
        "SELECT amount_centimes FROM ledger_entry WHERE entry_type = 'adjustment'"
    ).fetchone()
    assert line["amount_centimes"] == -150 * DH
