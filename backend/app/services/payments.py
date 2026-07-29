"""Application service: turn a payment into balanced, append-only ledger lines."""

from dataclasses import dataclass

from app.domain.adjustments import (
    Adjustment,
    apply_adjustments,
    bearer_cuts,
    resolve_reduction,
)
from app.domain.money import Centimes
from app.domain.splitting import (
    Allocation,
    Beneficiary,
    SplitPolicy,
    split_payment,
)
from app.ports.payments import (
    AlreadyReversedError,
    ConfiguredAdjustment,
    EnrollmentContext,
    LedgerLine,
    PaymentRecord,
    PaymentStore,
    ReversalStore,
    UnknownEnrollmentError,
    UnknownPaymentError,
)


class ReductionsExceedPriceError(ValueError):
    pass


@dataclass(frozen=True)
class PostedPayment:
    payment_id: int
    net_amount: Centimes
    lines: tuple[LedgerLine, ...]


def post_payment(
    store: PaymentStore, enrollment_id: int, paid_on: str | None = None
) -> PostedPayment:
    context = _context_or_raise(store, enrollment_id)
    allocations = _base_split(context)
    adjustments = _resolved_adjustments(context)
    apply_adjustments(allocations, [adj for _, adj in adjustments])  # validates bearers
    net_amount = _net_amount(context, adjustments)
    lines = _ledger_lines(net_amount, allocations, adjustments)
    payment_id = store.record(context, net_amount, lines, paid_on)
    return PostedPayment(payment_id, net_amount, lines)


def net_price(context: EnrollmentContext) -> Centimes:
    """What the student actually owes for this enrollment, after adjustments."""
    return _net_amount(context, _resolved_adjustments(context))


def validate_adjustment(
    context: EnrollmentContext, configured: ConfiguredAdjustment
) -> None:
    """Raise (ValueError family) if adding this adjustment would be unpostable."""
    from dataclasses import replace

    candidate = replace(context, adjustments=(*context.adjustments, configured))
    allocations = _base_split(candidate)
    adjustments = _resolved_adjustments(candidate)
    apply_adjustments(allocations, [adj for _, adj in adjustments])  # bearer check
    _net_amount(candidate, adjustments)  # over-reduction check


@dataclass(frozen=True)
class PreviewLine:
    beneficiary: Beneficiary
    base: Centimes
    adjustment: Centimes  # negative when this beneficiary bears reductions
    final: Centimes


@dataclass(frozen=True)
class ResolvedAdjustment:
    adjustment_id: int
    reduction: Centimes
    bearers: tuple[Beneficiary, ...]


@dataclass(frozen=True)
class PaymentPreview:
    price: Centimes
    net: Centimes
    lines: tuple[PreviewLine, ...]
    adjustments: tuple[ResolvedAdjustment, ...]


def payment_preview(store: PaymentStore, enrollment_id: int) -> PaymentPreview:
    """What paying this enrollment would post — shown to the user BEFORE money moves."""
    context = _context_or_raise(store, enrollment_id)
    allocations = _base_split(context)
    resolved = _resolved_adjustments(context)
    # Same validation as posting: a bearer who no longer holds an allocation
    # (e.g. the class teacher changed) must fail loudly here, never render a
    # split whose lines don't sum to the net.
    apply_adjustments(allocations, [adjustment for _, adjustment in resolved])
    cuts: dict[Beneficiary, Centimes] = {}
    for _, adjustment in resolved:
        for bearer, cut in bearer_cuts(adjustment).items():
            cuts[bearer] = cuts.get(bearer, 0) + cut
    lines = tuple(
        PreviewLine(
            beneficiary=allocation.beneficiary,
            base=allocation.amount,
            adjustment=-cuts.get(allocation.beneficiary, 0),
            final=allocation.amount - cuts.get(allocation.beneficiary, 0),
        )
        for allocation in allocations
    )
    return PaymentPreview(
        price=context.price,
        net=_net_amount(context, resolved),
        lines=lines,
        adjustments=tuple(
            ResolvedAdjustment(adjustment_id, adjustment.reduction, adjustment.borne_by)
            for adjustment_id, adjustment in resolved
        ),
    )


@dataclass(frozen=True)
class ReversedPayment:
    payment_id: int
    lines: tuple[LedgerLine, ...]


def reverse_payment(
    store: ReversalStore, payment_id: int, reason: str | None = None
) -> ReversedPayment:
    """Un-post the append-only way: mirror every line, never edit history."""
    record = _record_or_raise(store, payment_id)
    if record.reversed:
        raise AlreadyReversedError(f"payment {payment_id} is already reversed")
    lines = _mirror_lines(record)
    store.record_reversal(record, lines, reason)
    return ReversedPayment(payment_id, lines)


def _record_or_raise(store: ReversalStore, payment_id: int) -> PaymentRecord:
    record = store.payment_record(payment_id)
    if record is None:
        raise UnknownPaymentError(f"no payment {payment_id}")
    return record


def _mirror_lines(record: PaymentRecord) -> tuple[LedgerLine, ...]:
    return tuple(
        LedgerLine(
            "reversal",
            -line.amount,
            beneficiary=line.beneficiary,
            adjustment_id=line.adjustment_id,
        )
        for line in record.lines
    )


def _context_or_raise(store: PaymentStore, enrollment_id: int) -> EnrollmentContext:
    context = store.enrollment_context(enrollment_id)
    if context is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    return context


def _base_split(context: EnrollmentContext) -> tuple[Allocation, ...]:
    policy = SplitPolicy(venue_bp=context.venue_bp, owner_bp=context.owner_bp)
    return split_payment(
        context.price,
        policy,
        venue_id=context.venue_id,
        owner_id=context.owner_id,
        subject_teachers=list(context.subject_teachers),
    )


def _resolved_adjustments(
    context: EnrollmentContext,
) -> list[tuple[int, Adjustment]]:
    return [
        (configured.adjustment_id, _resolve_one(configured, context))
        for configured in context.adjustments
    ]


def _resolve_one(
    configured: ConfiguredAdjustment, context: EnrollmentContext
) -> Adjustment:
    reduction = resolve_reduction(
        configured.spec,
        price=context.price,
        subject_count=len(context.subject_teachers),
    )
    bearers = configured.bearers or (Beneficiary("owner", context.owner_id),)
    return Adjustment(reduction=reduction, borne_by=bearers)


def _net_amount(
    context: EnrollmentContext, adjustments: list[tuple[int, Adjustment]]
) -> Centimes:
    total_reduction = sum(adj.reduction for _, adj in adjustments)
    if total_reduction > context.price:
        raise ReductionsExceedPriceError(
            f"reductions {total_reduction} exceed price {context.price}"
        )
    return context.price - total_reduction


def _ledger_lines(
    net_amount: Centimes,
    allocations: tuple[Allocation, ...],
    adjustments: list[tuple[int, Adjustment]],
) -> tuple[LedgerLine, ...]:
    lines = (
        LedgerLine("payment_in", net_amount),
        *_allocation_lines(allocations),
        *_adjustment_lines(adjustments),
    )
    _check_balance(lines)
    return lines


def _allocation_lines(allocations: tuple[Allocation, ...]) -> list[LedgerLine]:
    return [
        LedgerLine("allocation", allocation.amount, beneficiary=allocation.beneficiary)
        for allocation in allocations
    ]


def _adjustment_lines(
    adjustments: list[tuple[int, Adjustment]],
) -> list[LedgerLine]:
    return [
        LedgerLine("adjustment", -cut, beneficiary=bearer, adjustment_id=adjustment_id)
        for adjustment_id, adjustment in adjustments
        for bearer, cut in bearer_cuts(adjustment).items()
    ]


def _check_balance(lines: tuple[LedgerLine, ...]) -> None:
    cash_in = sum(line.amount for line in lines if line.entry_type == "payment_in")
    paid_out = sum(line.amount for line in lines if line.entry_type != "payment_in")
    if cash_in != paid_out:
        raise RuntimeError(f"unbalanced posting: in {cash_in}, out {paid_out}")
