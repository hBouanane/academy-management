"""Application service: turn a payment into balanced, append-only ledger lines."""

from dataclasses import dataclass

from app.domain.adjustments import (
    Adjustment,
    apply_adjustments,
    bearer_cuts,
    resolve_reduction,
)
from app.domain.money import Centimes, percent_of
from app.domain.splitting import (
    Allocation,
    Beneficiary,
    SplitPolicy,
    _proportional_parts,
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


class AvanceOutOfRangeError(ValueError):
    pass


@dataclass(frozen=True)
class PostedPayment:
    payment_id: int
    net_amount: Centimes
    lines: tuple[LedgerLine, ...]


def post_payment(
    store: PaymentStore,
    enrollment_id: int,
    paid_on: str | None = None,
    amount: Centimes | None = None,
) -> PostedPayment:
    """amount < net posts an avance: every beneficiary is allocated his FULL
    share, the shortfall sits on the owner ('avance' line) until completed."""
    context = _context_or_raise(store, enrollment_id)
    allocations = _base_split(context)
    adjustments = _resolved_adjustments(context)
    apply_adjustments(allocations, [adj for _, adj in adjustments])  # bearer check
    net_amount = _net_amount(context, adjustments)
    cash = net_amount if amount is None else amount
    # Un mois offert ne coûte rien : 0 est alors le seul montant valable.
    # Sinon l'étudiant paie entre un centime et le net — jamais davantage.
    if amount is not None and not (
        0 <= amount <= net_amount and (amount > 0 or net_amount == 0)
    ):
        raise AvanceOutOfRangeError(
            f"le montant doit être entre {0 if net_amount == 0 else 0.01:.2f}"
            f" et {net_amount / 100:.2f} DH (le net dû) —"
            f" reçu {amount / 100:.2f} DH"
        )
    lines = _ledger_lines(cash, net_amount, allocations, adjustments, context)
    payment_id = store.record(context, cash, lines, paid_on, due=net_amount)
    return PostedPayment(payment_id, net_amount, lines)


def complete_payment(
    store: PaymentStore, payment_id: int, amount: Centimes | None = None
) -> Centimes:
    """A later installment on an avance: cash in, straight back to the owner
    who fronted it. Returns the amount posted."""
    state = store.avance_state(payment_id)
    if state is None:
        raise UnknownPaymentError(f"no payment {payment_id}")
    if state["reversed"]:
        raise AlreadyReversedError(f"payment {payment_id} is reversed")
    remaining = state["due"] - state["cash"]
    installment = remaining if amount is None else amount
    if not 0 < installment <= remaining:
        raise AvanceOutOfRangeError(
            f"il reste {remaining / 100:.2f} DH à compléter —"
            f" impossible d'encaisser {installment / 100:.2f} DH"
        )
    owner = Beneficiary("owner", state["owner_id"])
    lines = (
        LedgerLine("payment_in", installment),
        LedgerLine("avance", installment, beneficiary=owner),
    )
    store.record_completion(state, lines)
    return installment


class AlreadyGuaranteedError(RuntimeError):
    pass


@dataclass(frozen=True)
class PostedGuarantee:
    amount: Centimes
    shares: tuple[tuple[int, Centimes], ...]  # (teacher_id, amount)


def guarantee_unpaid(
    store: PaymentStore,
    enrollment_id: int,
    present_until: str | None = None,
    never_came: bool = False,
) -> PostedGuarantee:
    """The professor is paid for the days he taught even when the student
    never paid: the académie fronts it and LA SALLE TAKES THE HIT WITH IT —
    with nothing collected, the salle receives nothing. No cash moves; only
    who-earned-what does, so the month stays an impayé."""
    context = _context_or_raise(store, enrollment_id)
    if context.guaranteed:
        raise AlreadyGuaranteedError(
            f"enrollment {enrollment_id} is already guaranteed"
        )
    shares = () if never_came else _guaranteed_shares(context, present_until)
    total = sum(amount for _, amount in shares)
    owner = Beneficiary("owner", context.owner_id)
    lines = tuple(
        line
        for teacher_id, amount in shares
        for line in (
            LedgerLine("guarantee", amount, Beneficiary("teacher", teacher_id)),
            LedgerLine("guarantee", -amount, owner),
        )
    )
    store.record_guarantee(context, present_until, total, lines)
    return PostedGuarantee(total, shares)


def _guaranteed_shares(
    context: EnrollmentContext, present_until: str | None
) -> tuple[tuple[int, Centimes], ...]:
    """Each professor's share of this month, prorated by the days the student
    actually attended (largest remainder, so the parts sum exactly)."""
    from calendar import monthrange

    allocations = _base_split(context)
    adjustments = _resolved_adjustments(context)
    apply_adjustments(allocations, [adjustment for _, adjustment in adjustments])
    finals = _final_amounts(allocations, adjustments)
    entries = tuple(
        (beneficiary.ref_id, amount)
        for beneficiary, amount in finals.items()
        if beneficiary.kind == "teacher" and amount > 0
    )
    if not entries:
        return ()
    days = monthrange(int(context.month[:4]), int(context.month[5:7]))[1]
    present = days if present_until is None else int(present_until[8:10])
    total = sum(amount for _, amount in entries) * present // days
    if total <= 0:
        return ()
    return tuple(_proportional_parts(entries, total))


def teacher_parts_per_class(
    context: EnrollmentContext,
) -> dict[tuple[int, int], Centimes]:
    """(rang de la classe, professeur) → ce qu'il touche sur CETTE classe.

    Même calcul que le partage global, mais sans agréger : c'est ce qui
    permet à une fiche de paie de détailler classe par classe une somme qui
    tombe juste. Les réductions portées par un professeur sont réparties sur
    ses classes au prorata (largest remainder : le total reste exact)."""
    from app.domain.money import split_equally

    policy = SplitPolicy(venue_bp=context.venue_bp, owner_bp=context.owner_bp)
    teachers_total = (
        context.price
        - percent_of(context.price, policy.venue_bp)
        - percent_of(context.price, policy.owner_bp)
    )
    raw: dict[tuple[int, int], Centimes] = {}
    for index, subject_slice in enumerate(
        split_equally(teachers_total, len(context.subject_teachers))
    ):
        entries = (
            context.teacher_weights[index]
            if context.teacher_weights is not None
            else ((context.subject_teachers[index], 1),)
        )
        for teacher_id, part in _proportional_parts(entries, subject_slice):
            if teacher_id is None:  # jours vacants : l'académie encaisse
                continue
            raw[(index, teacher_id)] = raw.get((index, teacher_id), 0) + part

    allocations = _base_split(context)
    adjustments = _resolved_adjustments(context)
    apply_adjustments(allocations, [adjustment for _, adjustment in adjustments])
    finals = _final_amounts(allocations, adjustments)
    scaled: dict[tuple[int, int], Centimes] = {}
    for teacher_id in {teacher for _, teacher in raw}:
        keys = [key for key in raw if key[1] == teacher_id]
        weights = tuple((key[0], raw[key]) for key in sorted(keys))
        final = max(finals.get(Beneficiary("teacher", teacher_id), 0), 0)
        if sum(weight for _, weight in weights) <= 0 or final <= 0:
            continue
        for index, amount in _proportional_parts(weights, final):
            scaled[(index, teacher_id)] = amount
    return scaled


def _final_amounts(
    allocations: tuple[Allocation, ...],
    adjustments: list[tuple[int, Adjustment]],
) -> dict[Beneficiary, Centimes]:
    """What each beneficiary really keeps: his allocation minus the
    reductions he bears."""
    cuts: dict[Beneficiary, Centimes] = {}
    for _, adjustment in adjustments:
        for bearer, cut in bearer_cuts(adjustment).items():
            cuts[bearer] = cuts.get(bearer, 0) + cut
    return {
        allocation.beneficiary: allocation.amount - cuts.get(allocation.beneficiary, 0)
        for allocation in allocations
    }


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
    shares: tuple[Centimes, ...]  # resolved per-sponsor parts (explicit or equal)


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
            ResolvedAdjustment(
                adjustment_id,
                adjustment.reduction,
                adjustment.borne_by,
                tuple(bearer_cuts(adjustment)[b] for b in adjustment.borne_by),
            )
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
        teacher_weights=context.teacher_weights,
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
    if configured.category == "gift" and not configured.bearers:
        # Mois offert: EVERYONE forgoes proportionally — professors, salle
        # and académie all land on zero for a 100% gift. Nobody earns.
        allocations = _base_split(context)
        return Adjustment(
            reduction=reduction,
            borne_by=tuple(a.beneficiary for a in allocations),
            shares=_proportional_shares(allocations, reduction),
        )
    bearers = configured.bearers or (Beneficiary("owner", context.owner_id),)
    shares = _resolve_shares(configured, reduction)
    return Adjustment(reduction=reduction, borne_by=bearers, shares=shares)


def _proportional_shares(
    allocations: tuple[Allocation, ...], reduction: Centimes
) -> tuple[Centimes, ...]:
    """Split the reduction across all beneficiaries, weighted by what each
    receives; flooring loss goes to the largest remainders so the parts
    always sum exactly (a full gift therefore zeroes every share)."""
    total = sum(allocation.amount for allocation in allocations)
    if total == 0:
        return tuple(0 for _ in allocations)
    raw = [(a.amount * reduction) // total for a in allocations]
    by_remainder = sorted(
        range(len(allocations)),
        key=lambda i: (allocations[i].amount * reduction) % total,
        reverse=True,
    )
    for offset in range(reduction - sum(raw)):
        raw[by_remainder[offset % len(by_remainder)]] += 1
    return tuple(raw)


def _resolve_shares(
    configured: ConfiguredAdjustment, reduction: Centimes
) -> tuple[Centimes, ...] | None:
    """Sponsor parts: explicit centimes, or a percentage of the reduction.

    Percentages are floored, then the flooring loss (at most one centime per
    percentage entry) is given back to the largest percentage shares — so
    40%/60% or thirds always land exactly on the reduction. Any remaining
    difference is a genuine user error and is refused."""
    spec = configured.shares_spec
    if spec is None or all(c is None and bp is None for c, bp in spec):
        return None
    if any(c is None and bp is None for c, bp in spec):
        raise ValueError(
            "chaque sponsor doit indiquer sa part (montant ou pourcentage)"
        )
    resolved = [
        c if c is not None else percent_of(reduction, bp or 0) for c, bp in spec
    ]
    percent_indexes = sorted(
        (i for i, (c, _) in enumerate(spec) if c is None),
        key=lambda i: resolved[i],
        reverse=True,
    )
    difference = reduction - sum(resolved)
    if difference != 0 and percent_indexes and 0 < difference <= len(percent_indexes):
        for offset in range(difference):  # give the flooring loss back
            resolved[percent_indexes[offset % len(percent_indexes)]] += 1
        difference = 0
    if difference != 0:
        raise ValueError(
            f"la somme des parts ({sum(resolved) / 100:.2f} DH) doit égaler"
            f" la réduction ({reduction / 100:.2f} DH)"
        )
    return tuple(resolved)


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
    cash: Centimes,
    net_amount: Centimes,
    allocations: tuple[Allocation, ...],
    adjustments: list[tuple[int, Adjustment]],
    context: EnrollmentContext,
) -> tuple[LedgerLine, ...]:
    front = net_amount - cash  # avance: the owner fronts what's missing
    lines = (
        LedgerLine("payment_in", cash),
        *_allocation_lines(allocations),
        *_adjustment_lines(adjustments),
        *(
            (LedgerLine("avance", -front, Beneficiary("owner", context.owner_id)),)
            if front > 0
            else ()
        ),
        *_recovery_lines(context, allocations, adjustments),
    )
    _check_balance(lines)
    return lines


def _recovery_lines(
    context: EnrollmentContext,
    allocations: tuple[Allocation, ...],
    adjustments: list[tuple[int, Adjustment]],
) -> list[LedgerLine]:
    """The month was guaranteed and is now collected: the académie takes its
    advance back out of THIS payment — capped at what the professor earns
    here, because money already given to a professor is never clawed back."""
    if not context.guaranteed:
        return []
    finals = _final_amounts(allocations, adjustments)
    owner = Beneficiary("owner", context.owner_id)
    lines: list[LedgerLine] = []
    for teacher_id, guaranteed in context.guaranteed:
        beneficiary = Beneficiary("teacher", teacher_id)
        recovered = min(guaranteed, max(finals.get(beneficiary, 0), 0))
        if recovered <= 0:
            continue
        lines.append(LedgerLine("guarantee", -recovered, beneficiary))
        lines.append(LedgerLine("guarantee", recovered, owner))
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
