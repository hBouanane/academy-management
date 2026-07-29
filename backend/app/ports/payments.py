"""Port between the payment service and whatever stores the data."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.adjustments import AdjustmentSpec
from app.domain.money import Centimes
from app.domain.splitting import Beneficiary


class UnknownEnrollmentError(LookupError):
    pass


class AlreadyPaidError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfiguredAdjustment:
    adjustment_id: int
    spec: AdjustmentSpec
    bearers: tuple[Beneficiary, ...]  # empty means the default bearer (owner)


@dataclass(frozen=True)
class EnrollmentContext:
    enrollment_id: int
    academy_id: int
    month: str
    price: Centimes
    venue_id: int
    owner_id: int
    venue_bp: int
    owner_bp: int
    subject_teachers: tuple[int, ...]  # one teacher per subject, class order
    adjustments: tuple[ConfiguredAdjustment, ...]


@dataclass(frozen=True)
class LedgerLine:
    entry_type: str  # 'payment_in' | 'allocation' | 'adjustment'
    amount: Centimes
    beneficiary: Beneficiary | None = None
    adjustment_id: int | None = None


class PaymentStore(Protocol):
    def enrollment_context(self, enrollment_id: int) -> EnrollmentContext | None: ...

    def record(
        self,
        context: EnrollmentContext,
        net_amount: Centimes,
        lines: Sequence[LedgerLine],
        paid_on: str | None,
    ) -> int: ...
