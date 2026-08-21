"""The school year: a bounded season, and nothing else.

Nothing here reads or writes: it counts months. Knowing which months
make up a season, and which season holds a given month, needs no
database at all -- and can therefore be verified without standing one up.
"""

Month = str  # 'YYYY-MM'


def _ordinal(month: Month) -> int:
    """A month becomes a number, so December and January follow one
    another on their own, with nobody having to think about it."""
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _month(ordinal: int) -> Month:
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def months_between(start: Month, end: Month) -> list[Month]:
    """Every month of the season, first to last inclusive.

    An end placed before the start yields no months rather than an
    endless loop: an empty season is visible, a hang is not.
    """
    return [_month(o) for o in range(_ordinal(start), _ordinal(end) + 1)]


def year_holding(years: list[dict], month: Month) -> dict | None:
    """The season holding this month -- or none.

    Summer belongs to nobody when the school year stops in June.
    Inventing a season for it would push takings into a report that does
    not expect them.
    """
    for year in years:
        if year["start_month"] <= month <= year["end_month"]:
            return year
    return None
