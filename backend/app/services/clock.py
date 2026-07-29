"""The one place that knows what month it is — tests monkeypatch this."""

from datetime import datetime


def current_month() -> str:
    return datetime.now().strftime("%Y-%m")  # noqa: DTZ005 - client wall clock is the business truth
