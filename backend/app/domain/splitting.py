"""Splits one student payment into per-beneficiary allocations.

The invariant that everything else relies on: allocations always sum
exactly to the paid amount — every centime lands somewhere, deterministically.
"""

from dataclasses import dataclass

from .money import Centimes, FULL_SHARE_BP, percent_of, split_equally


@dataclass(frozen=True)
class Beneficiary:
    kind: str  # 'venue' | 'owner' | 'teacher'
    ref_id: int


@dataclass(frozen=True)
class Allocation:
    beneficiary: Beneficiary
    amount: Centimes


@dataclass(frozen=True)
class SplitPolicy:
    venue_bp: int
    owner_bp: int

    def __post_init__(self) -> None:
        if min(self.venue_bp, self.owner_bp) < 0:
            raise ValueError("shares cannot be negative")
        if self.venue_bp + self.owner_bp > FULL_SHARE_BP:
            raise ValueError("venue and owner shares exceed 100%")


def split_payment(
    amount: Centimes,
    policy: SplitPolicy,
    *,
    venue_id: int,
    owner_id: int,
    teacher_ids: list[int],
) -> tuple[Allocation, ...]:
    _validate_teachers(teacher_ids)
    venue_amount = percent_of(amount, policy.venue_bp)
    owner_amount = percent_of(amount, policy.owner_bp)
    teachers_total = amount - venue_amount - owner_amount
    return (
        Allocation(Beneficiary("venue", venue_id), venue_amount),
        Allocation(Beneficiary("owner", owner_id), owner_amount),
        *_teacher_allocations(teacher_ids, teachers_total),
    )


def _validate_teachers(teacher_ids: list[int]) -> None:
    if not teacher_ids:
        raise ValueError("a payment must have at least one teacher")
    if len(set(teacher_ids)) != len(teacher_ids):
        raise ValueError(f"duplicate teachers in {teacher_ids}")


def _teacher_allocations(
    teacher_ids: list[int], total: Centimes
) -> list[Allocation]:
    shares = split_equally(total, len(teacher_ids))
    return [
        Allocation(Beneficiary("teacher", teacher_id), share)
        for teacher_id, share in zip(teacher_ids, shares)
    ]
