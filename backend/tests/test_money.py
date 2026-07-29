import pytest

from app.domain.money import percent_of, split_equally


def test_percent_of_rounds_down():
    assert percent_of(100, 3333) == 33


def test_split_equally_exact():
    assert split_equally(300, 3) == [100, 100, 100]


def test_split_equally_gives_remainder_to_first_parts():
    assert split_equally(100, 3) == [34, 33, 33]


def test_split_equally_rejects_nonpositive_parts():
    with pytest.raises(ValueError):
        split_equally(100, 0)
