"""Money lives as integer centimes; percentages as integer basis points (10000 = 100%)."""

Centimes = int

FULL_SHARE_BP = 10_000


def percent_of(amount: Centimes, basis_points: int) -> Centimes:
    return amount * basis_points // FULL_SHARE_BP


def split_equally(amount: Centimes, parts: int) -> list[Centimes]:
    """Largest-remainder split: the first `amount % parts` parts get one extra centime."""
    if parts <= 0:
        raise ValueError(f"parts must be positive, got {parts}")
    base, extra = divmod(amount, parts)
    return [base + 1 if i < extra else base for i in range(parts)]
