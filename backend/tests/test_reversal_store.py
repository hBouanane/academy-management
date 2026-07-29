"""Integration: reverse_payment through the real SQLite store — written first."""

import pytest

from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.ports.payments import AlreadyReversedError, UnknownPaymentError
from app.services.payments import post_payment, reverse_payment
from tests.support import DH, Scenario


@pytest.fixture
def scenario():
    conn = connect(":memory:")
    init_db(conn)
    yield Scenario(conn)
    conn.close()


def posted_payment(scenario, price=300, month="2026-09"):
    math = scenario.add_class("Math", "Ahmed", "Primaire")
    student = scenario.add_student("Sami", "Primaire")
    enrollment = scenario.enroll(student, month, [math], price)
    store = SqlitePaymentStore(scenario.conn)
    return store, enrollment, post_payment(store, enrollment).payment_id


def test_reversal_zeroes_every_beneficiary_and_cash(scenario):
    store, _, payment_id = posted_payment(scenario)
    reverse_payment(store, payment_id, reason="posted by mistake")
    rows = scenario.conn.execute(
        """
        SELECT COALESCE(beneficiary_kind, 'cash') AS who,
               SUM(amount_centimes) AS net
        FROM ledger_entry GROUP BY beneficiary_kind, beneficiary_id
        """
    ).fetchall()
    assert all(row["net"] == 0 for row in rows)
    reversed_at = scenario.conn.execute(
        "SELECT reversed_at FROM payment WHERE id = ?", (payment_id,)
    ).fetchone()[0]
    assert reversed_at is not None


def test_reversal_lines_carry_the_reason(scenario):
    store, _, payment_id = posted_payment(scenario)
    reverse_payment(store, payment_id, reason="wrong month")
    notes = {
        row["note"]
        for row in scenario.conn.execute(
            "SELECT note FROM ledger_entry WHERE entry_type = 'reversal'"
        )
    }
    assert notes == {"wrong month"}


def test_double_reversal_is_refused(scenario):
    store, _, payment_id = posted_payment(scenario)
    reverse_payment(store, payment_id)
    with pytest.raises(AlreadyReversedError):
        reverse_payment(store, payment_id)


def test_unknown_payment_is_refused(scenario):
    store = SqlitePaymentStore(scenario.conn)
    with pytest.raises(UnknownPaymentError):
        reverse_payment(store, 404)


def test_enrollment_can_be_posted_again_after_reversal(scenario):
    store, enrollment, payment_id = posted_payment(scenario)
    reverse_payment(store, payment_id)
    second = post_payment(store, enrollment)
    assert second.payment_id != payment_id
    cash_in = scenario.conn.execute(
        "SELECT SUM(amount_centimes) FROM ledger_entry WHERE entry_type IN"
        " ('payment_in', 'reversal') AND beneficiary_kind IS NULL"
    ).fetchone()[0]
    assert cash_in == 300 * DH  # first in, reversed out, second in
