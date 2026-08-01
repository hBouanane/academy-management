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


# Per subject: (teacher_id, weight) pairs — arbitrary positive proportions.
# Used when a class changed hands mid-month (weights = days taught) or is
# co-taught (equal weights). None/one pair = the whole slice to one teacher.
TeacherWeights = tuple[tuple[tuple[int, int], ...], ...]


def split_payment(
    amount: Centimes,
    policy: SplitPolicy,
    *,
    venue_id: int,
    owner_id: int,
    subject_teachers: list[int],
    teacher_weights: TeacherWeights | None = None,
) -> tuple[Allocation, ...]:
    """subject_teachers holds one teacher id per subject; a teacher covering
    several of the student's subjects appears once per subject and earns
    one slice each, aggregated into a single allocation. teacher_weights,
    when given, splits each subject's slice among the teachers who actually
    taught that month."""
    if not subject_teachers:
        raise ValueError("a payment must cover at least one subject")
    venue_amount = percent_of(amount, policy.venue_bp)
    owner_amount = percent_of(amount, policy.owner_bp)
    teachers_total = amount - venue_amount - owner_amount
    return (
        Allocation(Beneficiary("venue", venue_id), venue_amount),
        Allocation(Beneficiary("owner", owner_id), owner_amount),
        *_teacher_allocations(subject_teachers, teachers_total, teacher_weights),
    )


def _teacher_allocations(
    subject_teachers: list[int],
    total: Centimes,
    teacher_weights: TeacherWeights | None,
) -> list[Allocation]:
    slices = split_equally(total, len(subject_teachers))
    totals: dict[int, Centimes] = {}
    for index, subject_slice in enumerate(slices):
        entries = (
            teacher_weights[index]
            if teacher_weights is not None
            else ((subject_teachers[index], 1),)
        )
        for teacher_id, part in _proportional_parts(entries, subject_slice):
            totals[teacher_id] = totals.get(teacher_id, 0) + part
    return [
        Allocation(Beneficiary("teacher", teacher_id), amount)
        for teacher_id, amount in totals.items()
    ]


def _proportional_parts(
    entries: tuple[tuple[int, int], ...], amount: Centimes
) -> list[tuple[int, Centimes]]:
    """Split `amount` by integer weights, exactly: floors first, then the
    flooring loss goes to the largest remainders (ties: first listed)."""
    weight_total = sum(weight for _, weight in entries)
    if weight_total <= 0:
        raise ValueError("teacher weights must be positive")
    floors = [(amount * weight) // weight_total for _, weight in entries]
    remainders = sorted(
        range(len(entries)),
        key=lambda i: (amount * entries[i][1]) % weight_total,
        reverse=True,
    )
    for offset in range(amount - sum(floors)):
        floors[remainders[offset % len(entries)]] += 1
    return [(entries[i][0], floors[i]) for i in range(len(entries))]
