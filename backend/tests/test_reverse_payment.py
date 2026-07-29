"""Service tests for reverse_payment, against a fake store — written first (TDD)."""

import pytest

from app.domain.splitting import Beneficiary
from app.ports.payments import (
    AlreadyReversedError,
    LedgerLine,
    PaymentRecord,
    UnknownPaymentError,
)
from app.services.payments import reverse_payment

DH = 100

OWNER = Beneficiary("owner", 1)
TEACHER = Beneficiary("teacher", 7)


def record(reversed_=False):
    return PaymentRecord(
        payment_id=42,
        enrollment_id=11,
        academy_id=1,
        month="2026-09",
        reversed=reversed_,
        lines=(
            LedgerLine("payment_in", 250 * DH),
            LedgerLine("allocation", 90 * DH, beneficiary=TEACHER),
            LedgerLine("adjustment", -50 * DH, beneficiary=OWNER, adjustment_id=3),
        ),
    )


class FakeStore:
    def __init__(self, payment_record):
        self.payment = payment_record
        self.reversal = None

    def payment_record(self, payment_id):
        return self.payment if payment_id == self.payment.payment_id else None

    def record_reversal(self, payment_record, lines, reason):
        self.reversal = (payment_record.payment_id, lines, reason)


def test_reversal_mirrors_every_line_negated():
    store = FakeStore(record())
    reversed_payment = reverse_payment(store, 42, reason="wrong amount")
    amounts = [(line.entry_type, line.amount) for line in reversed_payment.lines]
    assert amounts == [
        ("reversal", -250 * DH),
        ("reversal", -90 * DH),
        ("reversal", 50 * DH),
    ]
    assert store.reversal == (42, reversed_payment.lines, "wrong amount")


def test_reversal_preserves_beneficiaries_and_adjustment_refs():
    store = FakeStore(record())
    reversed_payment = reverse_payment(store, 42)
    adjustment_mirror = reversed_payment.lines[2]
    assert adjustment_mirror.beneficiary == OWNER
    assert adjustment_mirror.adjustment_id == 3


def test_net_effect_of_payment_plus_reversal_is_zero():
    store = FakeStore(record())
    reversed_payment = reverse_payment(store, 42)
    original = sum(line.amount for line in record().lines)
    mirrored = sum(line.amount for line in reversed_payment.lines)
    assert original + mirrored == 0


def test_unknown_payment_is_refused():
    store = FakeStore(record())
    with pytest.raises(UnknownPaymentError):
        reverse_payment(store, 404)


def test_double_reversal_is_refused():
    store = FakeStore(record(reversed_=True))
    with pytest.raises(AlreadyReversedError):
        reverse_payment(store, 42)
