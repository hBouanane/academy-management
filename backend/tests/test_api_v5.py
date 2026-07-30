"""Round 5: phone validation and future-month enrollment — written first (TDD)."""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


class TestPhoneValidation:
    def test_short_phone_is_refused_in_french(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        response = client.post(
            "/api/students",
            json={"name": "Sami", "level_id": level, "phone": "12345"},
        )
        assert response.status_code == 422
        assert "10 chiffres" in response.text

    def test_phone_is_normalized_to_ten_digits(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        response = client.post(
            "/api/students",
            json={"name": "Sami", "level_id": level, "phone": "06 61-23.45 67"},
        )
        assert response.status_code == 201, response.text
        (row,) = client.get("/api/students").json()
        assert row["phone"] == "0661234567"

    def test_teacher_phone_is_validated_too(self, client):
        response = client.post(
            "/api/teachers", json={"name": "Ahmed", "phone": "abcdefghij"}
        )
        assert response.status_code == 422

    def test_patch_phone_is_validated_and_emptying_still_clears(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        student = client.post(
            "/api/students",
            json={"name": "Lina", "level_id": level, "phone": "0661234567"},
        ).json()["id"]
        bad = client.patch(f"/api/students/{student}", json={"phone": "123"})
        assert bad.status_code == 422
        cleared = client.patch(f"/api/students/{student}", json={"phone": ""})
        assert cleared.status_code == 200, cleared.text
        (row,) = client.get("/api/students").json()
        assert row["phone"] is None


class TestStudentMonthStatus:
    def test_students_carry_their_status_for_the_viewed_month(self, client):
        # The Étudiants page must agree with the tableau de bord: same month,
        # same truth — enrolled+paid, enrolled+unpaid, or not enrolled.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/students", json={"name": "Lina", "level_id": level})
        client.post("/api/payments", json={"enrollment_id": enrollment})
        rows = {
            row["name"]: row
            for row in client.get("/api/students", params={"month": "2026-09"}).json()
        }
        assert rows["Sami"]["month_enrollment_id"] == enrollment
        assert rows["Sami"]["month_paid"] == 1
        assert rows["Lina"]["month_enrollment_id"] is None
        assert rows["Lina"]["month_paid"] == 0


class TestOverviewArrival:
    def test_overview_rows_expose_the_arrival_date(self, client):
        # The tableau de bord must explain a prorated price, not just show it.
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id, arrival_date="2026-09-25")
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["enrollment"]["arrival_date"] == "2026-09-25"
        assert row["enrollment"]["price_centimes"] == 99 * DH


class TestFutureEnrollment:
    def test_enrolling_a_coming_month_is_allowed(self, client):
        # The agenda: past months are locked, coming months are plannable.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")
        preview = client.get(f"/api/enrollments/{enrollment}/preview")
        assert preview.status_code == 200
        assert preview.json()["price_centimes"] == 300 * DH
