"""Reductions (discounts, coupons, gifts) applied on top of a base split.

An adjustment never edits history: callers persist the result as new ledger
lines. A bearer's share may go negative — the ledger shows reality.
"""

from dataclasses import dataclass

from .money import Centimes, split_equally
from .splitting import Allocation, Beneficiary


@dataclass(frozen=True)
class Adjustment:
    reduction: Centimes  # positive amount taken off the student's price
    borne_by: tuple[Beneficiary, ...]  # default policy upstream: (owner,)


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
    cuts = _cut_per_bearer(adjustment)
    return tuple(_reduced(allocation, cuts) for allocation in allocations)


def _validate_bearers(
    allocations: tuple[Allocation, ...], bearers: tuple[Beneficiary, ...]
) -> None:
    present = {allocation.beneficiary for allocation in allocations}
    unknown = [bearer for bearer in bearers if bearer not in present]
    if unknown:
        raise ValueError(f"bearers without an allocation: {unknown}")


def _cut_per_bearer(adjustment: Adjustment) -> dict[Beneficiary, Centimes]:
    shares = split_equally(adjustment.reduction, len(adjustment.borne_by))
    return dict(zip(adjustment.borne_by, shares, strict=True))


def _reduced(allocation: Allocation, cuts: dict[Beneficiary, Centimes]) -> Allocation:
    cut = cuts.get(allocation.beneficiary, 0)
    if not cut:
        return allocation
    return Allocation(allocation.beneficiary, allocation.amount - cut)
