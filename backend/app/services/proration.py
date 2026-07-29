"""Arrival-date pricing: the month is divided into segments, each worth a
percentage of the package price. Default: thirds at 100% / 67% / 33%."""

from calendar import monthrange

from app.domain.money import Centimes, percent_of

DEFAULT_SEGMENTS_BP = (10_000, 6_700, 3_300)


def prorated_price(
    price: Centimes, segments_bp: tuple[int, ...], month: str, day: int
) -> Centimes:
    days_in_month = monthrange(int(month[:4]), int(month[5:7]))[1]
    segment_length = days_in_month / len(segments_bp)
    index = min(int((day - 1) / segment_length), len(segments_bp) - 1)
    return percent_of(price, segments_bp[index])
