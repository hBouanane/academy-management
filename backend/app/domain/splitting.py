"""Splits one student payment into per-beneficiary allocations.

The invariant that everything else relies on: allocations always sum
exactly to the paid amount — every centime lands somewhere, deterministically.
"""

from dataclasses import dataclass

from .money import FULL_SHARE_BP, Centimes, percent_of, split_equally


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
    subject_teachers: list[int],
) -> tuple[Allocation, ...]:
    """subject_teachers holds one teacher id per subject; a teacher covering
    several of the student's subjects appears once per subject and earns
    one slice each, aggregated into a single allocation."""
    if not subject_teachers:
        raise ValueError("a payment must cover at least one subject")
    venue_amount = percent_of(amount, policy.venue_bp)
    owner_amount = percent_of(amount, policy.owner_bp)
    teachers_total = amount - venue_amount - owner_amount
    return (
        Allocation(Beneficiary("venue", venue_id), venue_amount),
        Allocation(Beneficiary("owner", owner_id), owner_amount),
        *_teacher_allocations(subject_teachers, teachers_total),
    )


def _teacher_allocations(
    subject_teachers: list[int], total: Centimes
) -> list[Allocation]:
    slices = split_equally(total, len(subject_teachers))
    totals: dict[int, Centimes] = {}
    for teacher_id, subject_slice in zip(subject_teachers, slices, strict=True):
        totals[teacher_id] = totals.get(teacher_id, 0) + subject_slice
    return [
        Allocation(Beneficiary("teacher", teacher_id), amount)
        for teacher_id, amount in totals.items()
    ]
