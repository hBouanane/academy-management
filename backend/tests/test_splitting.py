"""Tests for the payment split engine â€” written before the implementation (TDD)."""

import pytest

from app.domain.splitting import Beneficiary, SplitPolicy, split_payment

DH = 100  # centimes per dirham

VENUE = Beneficiary("venue", 1)
OWNER = Beneficiary("owner", 1)


def seed_policy() -> SplitPolicy:
    # Client's seed configuration: venue 30%, owner 10%, teachers share the rest.
    return SplitPolicy(venue_bp=3000, owner_bp=1000)


def amounts_by_beneficiary(allocations):
    return {a.beneficiary: a.amount for a in allocations}


def test_seed_case_300dh_three_teachers():
    allocations = split_payment(
        300 * DH, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[7, 8, 9]
    )
    amounts = amounts_by_beneficiary(allocations)
    assert amounts[VENUE] == 90 * DH
    assert amounts[OWNER] == 30 * DH
    assert amounts[Beneficiary("teacher", 7)] == 60 * DH
    assert amounts[Beneficiary("teacher", 8)] == 60 * DH
    assert amounts[Beneficiary("teacher", 9)] == 60 * DH


def test_single_teacher_takes_whole_teacher_share():
    allocations = split_payment(
        250 * DH, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[4]
    )
    assert amounts_by_beneficiary(allocations)[Beneficiary("teacher", 4)] == 150 * DH


@pytest.mark.parametrize("amount", [1, 99, 10_001, 33_333, 250 * DH + 1])
def test_allocations_always_sum_to_exact_amount(amount):
    allocations = split_payment(
        amount, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[1, 2, 3]
    )
    assert sum(a.amount for a in allocations) == amount


def test_requires_at_least_one_subject():
    with pytest.raises(ValueError):
        split_payment(
            100 * DH, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[]
        )


def test_teacher_with_two_subjects_earns_two_slices():
    # 300 DH, teacher share 180: subjects are math+physics (teacher 7) and English
    # (teacher 8) -> 7 gets 2/3 of 180, 8 gets 1/3.
    allocations = split_payment(
        300 * DH, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[7, 7, 8]
    )
    amounts = amounts_by_beneficiary(allocations)
    assert amounts[Beneficiary("teacher", 7)] == 120 * DH
    assert amounts[Beneficiary("teacher", 8)] == 60 * DH


def test_one_allocation_per_teacher_even_with_multiple_subjects():
    allocations = split_payment(
        300 * DH, seed_policy(), venue_id=1, owner_id=1, subject_teachers=[7, 7, 8]
    )
    teacher_allocations = [a for a in allocations if a.beneficiary.kind == "teacher"]
    assert len(teacher_allocations) == 2


def test_policy_rejects_shares_over_100_percent():
    with pytest.raises(ValueError):
        SplitPolicy(venue_bp=6000, owner_bp=5000)


def test_policy_rejects_negative_shares():
    with pytest.raises(ValueError):
        SplitPolicy(venue_bp=-1, owner_bp=1000)
