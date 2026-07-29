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


class UnknownPaymentError(LookupError):
    pass


class AlreadyReversedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfiguredAdjustment:
    adjustment_id: int
    spec: AdjustmentSpec
    bearers: tuple[Beneficiary, ...]  # empty means the default bearer (owner)
    # Per-sponsor parts aligned with bearers: (share_centimes, share_bp) each,
    # (None, None) meaning "equal split". None entirely = legacy equal split.
    shares_spec: tuple[tuple[int | None, int | None], ...] | None = None


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


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: int
    enrollment_id: int
    academy_id: int
    month: str
    reversed: bool
    lines: tuple[LedgerLine, ...]  # the payment's original (non-reversal) lines


class PaymentStore(Protocol):
    def enrollment_context(self, enrollment_id: int) -> EnrollmentContext | None: ...

    def record(
        self,
        context: EnrollmentContext,
        net_amount: Centimes,
        lines: Sequence[LedgerLine],
        paid_on: str | None,
    ) -> int: ...


class ReversalStore(Protocol):
    def payment_record(self, payment_id: int) -> PaymentRecord | None: ...

    def record_reversal(
        self,
        payment_record: PaymentRecord,
        lines: Sequence[LedgerLine],
        reason: str | None,
    ) -> None: ...
