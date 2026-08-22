"""The dashboard names the student in full.

The overview carried only the family name, so the busiest screen in the
application showed « Bennis » while every other screen showed « Khadija
Bennis ». Two brothers in the same academy were indistinguishable there --
and picking the wrong one means taking the wrong family's money.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.services import clock


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


class TestTheOverviewNamesHimInFull:
    def test_the_first_name_travels_with_the_row(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        client.patch(f"/api/students/{student}", json={"first_name": "Khadija"})

        rows = client.get("/api/months/2026-09/overview").json()
        mine = next(row for row in rows if row["student_id"] == student)

        assert mine["first_name"] == "Khadija"
        assert mine["student_name"] == "Sami"

    def test_a_student_without_a_first_name_is_still_listed(self, client):
        """Older records have none: the screen falls back to the family
        name rather than showing « null »."""
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)

        rows = client.get("/api/months/2026-09/overview").json()
        mine = next(row for row in rows if row["student_id"] == student)

        assert mine["first_name"] is None
