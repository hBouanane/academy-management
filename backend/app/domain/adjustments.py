"""Reductions (discounts, coupons, gifts) applied on top of a base split.

An adjustment never edits history: callers persist the result as new ledger
lines. A bearer's share may go negative — the ledger shows reality.
"""

from dataclasses import dataclass

from .money import FULL_SHARE_BP, Centimes, percent_of, split_equally
from .splitting import Allocation, Beneficiary


@dataclass(frozen=True)
class Adjustment:
    reduction: Centimes  # positive amount taken off the student's price
    borne_by: tuple[Beneficiary, ...]  # default policy upstream: (owner,)
    # Explicit sponsor parts, aligned with borne_by; None = equal split.
    shares: tuple[Centimes, ...] | None = None


@dataclass(frozen=True)
class AdjustmentSpec:
    """A client-configured reduction, before it is resolved to centimes."""

    kind: str  # 'percent' | 'amount'
    value: int  # basis points or centimes
    scope: str  # 'package' | 'subject'
    subject_index: int | None = None  # position in the enrollment's subject order


def resolve_reduction(
    spec: AdjustmentSpec, *, price: Centimes, subject_count: int
) -> Centimes:
    base = _reduction_base(spec, price, subject_count)
    reduction = _reduction_amount(spec, base)
    if reduction > base:
        raise ValueError(f"reduction {reduction} exceeds its base {base}")
    return reduction


def _reduction_base(
    spec: AdjustmentSpec, price: Centimes, subject_count: int
) -> Centimes:
    if spec.scope == "package":
        return price
    if spec.subject_index is None:
        raise ValueError("subject-scoped adjustment needs a subject_index")
    return split_equally(price, subject_count)[spec.subject_index]


def _reduction_amount(spec: AdjustmentSpec, base: Centimes) -> Centimes:
    if spec.kind == "amount":
        return spec.value
    if spec.value > FULL_SHARE_BP:
        raise ValueError(f"percentage {spec.value} is over 100%")
    return percent_of(base, spec.value)


def apply_adjustments(
    allocations: tuple[Allocation, ...], adjustments: list[Adjustment]
) -> tuple[Allocation, ...]:
    for adjustment in adjustments:
        allocations = _apply_one(allocations, adjustment)
    return allocations


def _apply_one(
    allocations: tuple[Allocation, ...], adjustment: Adjustment
) -> tuple[Allocation, ...]:
    _validate_bearers(allocations, adjustment.borne_by)
    cuts = bearer_cuts(adjustment)
    return tuple(_reduced(allocation, cuts) for allocation in allocations)


def _validate_bearers(
    allocations: tuple[Allocation, ...], bearers: tuple[Beneficiary, ...]
) -> None:
    present = {allocation.beneficiary for allocation in allocations}
    unknown = [bearer for bearer in bearers if bearer not in present]
    if unknown:
        raise ValueError(f"bearers without an allocation: {unknown}")


def bearer_cuts(adjustment: Adjustment) -> dict[Beneficiary, Centimes]:
    """How much of the reduction each sponsor absorbs — their explicit share
    when given, an equal largest-remainder split otherwise."""
    if adjustment.shares is not None:
        return dict(zip(adjustment.borne_by, adjustment.shares, strict=True))
    shares = split_equally(adjustment.reduction, len(adjustment.borne_by))
    return dict(zip(adjustment.borne_by, shares, strict=True))


def _reduced(allocation: Allocation, cuts: dict[Beneficiary, Centimes]) -> Allocation:
    cut = cuts.get(allocation.beneficiary, 0)
    if not cut:
        return allocation
    return Allocation(allocation.beneficiary, allocation.amount - cut)
