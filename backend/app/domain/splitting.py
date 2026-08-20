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
# A None teacher id means « sans professeur »: those days' share escrows to
# the académie (the owner) instead of any teacher.
TeacherWeights = tuple[tuple[tuple[int | None, int], ...], ...]


def split_payment(
    amount: Centimes,
    policy: SplitPolicy,
    *,
    venue_id: int,
    owner_id: int,
    subject_teachers: list[int | None],
    teacher_weights: TeacherWeights | None = None,
    subject_policies: tuple[SplitPolicy, ...] = (),
) -> tuple[Allocation, ...]:
    """subject_teachers holds one teacher id per subject; a teacher covering
    several of the student's subjects appears once per subject and earns
    one slice each, aggregated into a single allocation. teacher_weights,
    when given, splits each subject's slice among the teachers who actually
    taught that month; vacant portions (None) land on the owner."""
    if not subject_teachers:
        raise ValueError("a payment must cover at least one subject")
    if subject_policies and len(set(subject_policies)) > 1:
        return _split_per_subject(
            amount,
            subject_policies,
            venue_id=venue_id,
            owner_id=owner_id,
            subject_teachers=subject_teachers,
            teacher_weights=teacher_weights,
        )
    # Une seule repartition pour tout : le calcul d avant, au centime.
    policy = subject_policies[0] if subject_policies else policy
    venue_amount = percent_of(amount, policy.venue_bp)
    owner_amount = percent_of(amount, policy.owner_bp)
    teachers_total = amount - venue_amount - owner_amount
    totals = _teacher_totals(subject_teachers, teachers_total, teacher_weights)
    escrow = totals.pop(None, 0)
    return (
        Allocation(Beneficiary("venue", venue_id), venue_amount),
        Allocation(Beneficiary("owner", owner_id), owner_amount + escrow),
        *(
            Allocation(Beneficiary("teacher", teacher_id), total)
            for teacher_id, total in totals.items()
        ),
    )


def _split_per_subject(
    amount: Centimes,
    policies: tuple[SplitPolicy, ...],
    *,
    venue_id: int,
    owner_id: int,
    subject_teachers: list[int | None],
    teacher_weights: TeacherWeights | None,
) -> tuple[Allocation, ...]:
    """Les matieres ne se partagent pas pareil : on decoupe d abord le
    prix entre elles, puis chaque part suit sa propre regle."""
    slices = split_equally(amount, len(subject_teachers))
    venue_total = 0
    owner_total = 0
    totals: dict[int | None, Centimes] = {}
    for index, subject_slice in enumerate(slices):
        policy = policies[index]
        venue_part = percent_of(subject_slice, policy.venue_bp)
        owner_part = percent_of(subject_slice, policy.owner_bp)
        venue_total += venue_part
        owner_total += owner_part
        for teacher_id, part in _teacher_totals(
            [subject_teachers[index]],
            subject_slice - venue_part - owner_part,
            (teacher_weights[index],) if teacher_weights else None,
        ).items():
            totals[teacher_id] = totals.get(teacher_id, 0) + part
    escrow = totals.pop(None, 0)
    return (
        Allocation(Beneficiary("venue", venue_id), venue_total),
        Allocation(Beneficiary("owner", owner_id), owner_total + escrow),
        *(
            Allocation(Beneficiary("teacher", teacher_id), total)
            for teacher_id, total in totals.items()
        ),
    )


def _teacher_totals(
    subject_teachers: list[int | None],
    total: Centimes,
    teacher_weights: TeacherWeights | None,
) -> dict[int | None, Centimes]:
    slices = split_equally(total, len(subject_teachers))
    totals: dict[int | None, Centimes] = {}
    for index, subject_slice in enumerate(slices):
        entries = (
            teacher_weights[index]
            if teacher_weights is not None
            else ((subject_teachers[index], 1),)
        )
        for teacher_id, part in _proportional_parts(entries, subject_slice):
            totals[teacher_id] = totals.get(teacher_id, 0) + part
    return totals


def _proportional_parts(
    entries: tuple[tuple[int | None, int], ...], amount: Centimes
) -> list[tuple[int | None, Centimes]]:
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
