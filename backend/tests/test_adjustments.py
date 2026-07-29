"""Tests for the adjustment engine (discounts, coupons, gifts as one mechanism)."""

import pytest

from app.domain.adjustments import (
    Adjustment,
    AdjustmentSpec,
    apply_adjustments,
    resolve_reduction,
)
from app.domain.splitting import Beneficiary, SplitPolicy, split_payment

DH = 100  # centimes per dirham

VENUE = Beneficiary("venue", 1)
OWNER = Beneficiary("owner", 1)


def base_allocations():
    policy = SplitPolicy(venue_bp=3000, owner_bp=1000)
    return split_payment(
        300 * DH, policy, venue_id=1, owner_id=1, subject_teachers=[7, 8]
    )


def amounts_by_beneficiary(allocations):
    return {a.beneficiary: a.amount for a in allocations}


def test_discount_borne_by_owner_only_by_default():
    adjusted = apply_adjustments(
        base_allocations(), [Adjustment(reduction=50 * DH, borne_by=(OWNER,))]
    )
    amounts = amounts_by_beneficiary(adjusted)
    assert (
        amounts[OWNER] == -20 * DH
    )  # 30 - 50: the ledger shows reality, even negative
    assert amounts[VENUE] == 90 * DH  # others untouched
    assert amounts[Beneficiary("teacher", 7)] == 90 * DH


def test_discount_shared_between_owner_and_venue():
    adjusted = apply_adjustments(
        base_allocations(), [Adjustment(reduction=50 * DH, borne_by=(OWNER, VENUE))]
    )
    amounts = amounts_by_beneficiary(adjusted)
    assert amounts[OWNER] == 5 * DH  # 30 - 25
    assert amounts[VENUE] == 65 * DH  # 90 - 25


def test_uneven_shared_reduction_uses_largest_remainder():
    adjusted = apply_adjustments(
        base_allocations(), [Adjustment(reduction=101, borne_by=(OWNER, VENUE))]
    )
    amounts = amounts_by_beneficiary(adjusted)
    assert amounts[OWNER] == 30 * DH - 51
    assert amounts[VENUE] == 90 * DH - 50


def test_multiple_adjustments_stack():
    adjusted = apply_adjustments(
        base_allocations(),
        [
            Adjustment(reduction=10 * DH, borne_by=(OWNER,)),
            Adjustment(reduction=20 * DH, borne_by=(Beneficiary("teacher", 7),)),
        ],
    )
    amounts = amounts_by_beneficiary(adjusted)
    assert amounts[OWNER] == 20 * DH
    assert amounts[Beneficiary("teacher", 7)] == 70 * DH


def test_bearer_must_hold_an_allocation():
    stranger = Beneficiary("teacher", 999)
    with pytest.raises(ValueError):
        apply_adjustments(
            base_allocations(), [Adjustment(reduction=10, borne_by=(stranger,))]
        )


def test_resolve_percent_of_package():
    spec = AdjustmentSpec(kind="percent", value=5000, scope="package")
    assert resolve_reduction(spec, price=300 * DH, subject_count=3) == 150 * DH


def test_resolve_amount_off_package():
    spec = AdjustmentSpec(kind="amount", value=50 * DH, scope="package")
    assert resolve_reduction(spec, price=300 * DH, subject_count=3) == 50 * DH


def test_resolve_percent_of_one_subject():
    # 300 DH over 3 subjects -> subject base 100 DH; 50% of it = 50 DH.
    spec = AdjustmentSpec(kind="percent", value=5000, scope="subject", subject_index=1)
    assert resolve_reduction(spec, price=300 * DH, subject_count=3) == 50 * DH


def test_resolve_subject_base_uses_deterministic_slices():
    # 100 centimes over 3 subjects -> slices 34/33/33; full gift of subject 0 = 34.
    spec = AdjustmentSpec(kind="percent", value=10000, scope="subject", subject_index=0)
    assert resolve_reduction(spec, price=100, subject_count=3) == 34


def test_resolve_refuses_reduction_beyond_its_base():
    spec = AdjustmentSpec(
        kind="amount", value=150 * DH, scope="subject", subject_index=0
    )
    with pytest.raises(ValueError):
        resolve_reduction(spec, price=300 * DH, subject_count=3)


def test_resolve_refuses_percent_over_100():
    spec = AdjustmentSpec(kind="percent", value=10001, scope="package")
    with pytest.raises(ValueError):
        resolve_reduction(spec, price=300 * DH, subject_count=3)


def test_resolve_subject_scope_requires_index():
    spec = AdjustmentSpec(kind="percent", value=1000, scope="subject")
    with pytest.raises(ValueError):
        resolve_reduction(spec, price=300 * DH, subject_count=3)


def test_adjustment_preserves_total_minus_reduction():
    adjusted = apply_adjustments(
        base_allocations(), [Adjustment(reduction=50 * DH, borne_by=(OWNER, VENUE))]
    )
    assert sum(a.amount for a in adjusted) == 300 * DH - 50 * DH
