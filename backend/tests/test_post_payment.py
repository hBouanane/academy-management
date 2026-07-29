"""Service tests for post_payment, against a fake store — written first (TDD)."""

import pytest

from app.domain.adjustments import AdjustmentSpec
from app.domain.splitting import Beneficiary
from app.ports.payments import (
    AlreadyPaidError,
    ConfiguredAdjustment,
    EnrollmentContext,
    UnknownEnrollmentError,
)
from app.services.payments import ReductionsExceedPriceError, post_payment

DH = 100

VENUE = Beneficiary("venue", 5)
OWNER = Beneficiary("owner", 1)


def context(adjustments=(), price=300 * DH):
    return EnrollmentContext(
        enrollment_id=11,
        academy_id=1,
        month="2026-09",
        price=price,
        venue_id=5,
        owner_id=1,
        venue_bp=3000,
        owner_bp=1000,
        subject_teachers=(7, 8),
        adjustments=tuple(adjustments),
    )


class FakeStore:
    def __init__(self, ctx):
        self.ctx = ctx
        self.recorded = None

    def enrollment_context(self, enrollment_id):
        return self.ctx if enrollment_id == self.ctx.enrollment_id else None

    def record(self, ctx, net_amount, lines, paid_on):
        if self.recorded is not None:
            raise AlreadyPaidError(ctx.enrollment_id)
        self.recorded = (net_amount, lines, paid_on)
        return 99


def lines_by_type(lines):
    grouped = {}
    for line in lines:
        grouped.setdefault(line.entry_type, []).append(line)
    return grouped


def test_plain_payment_posts_cash_in_and_base_allocations():
    store = FakeStore(context())
    posted = post_payment(store, 11)
    assert posted.payment_id == 99
    grouped = lines_by_type(posted.lines)
    assert [line.amount for line in grouped["payment_in"]] == [300 * DH]
    allocation_amounts = {
        line.beneficiary: line.amount for line in grouped["allocation"]
    }
    assert allocation_amounts == {
        VENUE: 90 * DH,
        OWNER: 30 * DH,
        Beneficiary("teacher", 7): 90 * DH,
        Beneficiary("teacher", 8): 90 * DH,
    }
    assert "adjustment" not in grouped


def test_discount_reduces_cash_in_and_charges_the_bearer():
    discount = ConfiguredAdjustment(
        adjustment_id=3,
        spec=AdjustmentSpec(kind="amount", value=50 * DH, scope="package"),
        bearers=(OWNER,),
    )
    store = FakeStore(context(adjustments=[discount]))
    posted = post_payment(store, 11)
    grouped = lines_by_type(posted.lines)
    assert grouped["payment_in"][0].amount == 250 * DH
    adjustment_line = grouped["adjustment"][0]
    assert adjustment_line.beneficiary == OWNER
    assert adjustment_line.amount == -50 * DH
    assert adjustment_line.adjustment_id == 3


def test_gift_month_posts_zero_cash_in():
    gift = ConfiguredAdjustment(
        adjustment_id=4,
        spec=AdjustmentSpec(kind="percent", value=10_000, scope="package"),
        bearers=(OWNER,),
    )
    store = FakeStore(context(adjustments=[gift]))
    posted = post_payment(store, 11)
    grouped = lines_by_type(posted.lines)
    assert grouped["payment_in"][0].amount == 0
    assert grouped["adjustment"][0].amount == -300 * DH


def test_bearerless_adjustment_defaults_to_owner():
    discount = ConfiguredAdjustment(
        adjustment_id=5,
        spec=AdjustmentSpec(kind="amount", value=10 * DH, scope="package"),
        bearers=(),
    )
    store = FakeStore(context(adjustments=[discount]))
    posted = post_payment(store, 11)
    assert lines_by_type(posted.lines)["adjustment"][0].beneficiary == OWNER


def test_every_posting_balances():
    discount = ConfiguredAdjustment(
        adjustment_id=6,
        spec=AdjustmentSpec(
            kind="percent", value=3333, scope="subject", subject_index=0
        ),
        bearers=(OWNER, VENUE),
    )
    store = FakeStore(context(adjustments=[discount]))
    posted = post_payment(store, 11)
    grouped = lines_by_type(posted.lines)
    cash_in = sum(line.amount for line in grouped["payment_in"])
    paid_out = sum(
        line.amount for line in grouped["allocation"] + grouped.get("adjustment", [])
    )
    assert cash_in == paid_out


def test_unknown_enrollment_is_refused():
    store = FakeStore(context())
    with pytest.raises(UnknownEnrollmentError):
        post_payment(store, 404)


def test_reductions_beyond_the_price_are_refused():
    half_off = ConfiguredAdjustment(
        adjustment_id=7,
        spec=AdjustmentSpec(kind="percent", value=6000, scope="package"),
        bearers=(OWNER,),
    )
    store = FakeStore(context(adjustments=[half_off, half_off]))
    with pytest.raises(ReductionsExceedPriceError):
        post_payment(store, 11)
