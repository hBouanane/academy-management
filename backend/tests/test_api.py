"""API tests through TestClient on a temp database — written first (TDD)."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app

DH = 100


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def setup_class_and_student(client, subject="Math", teacher="Ahmed", student="Sami"):
    """Creates a class and a student at Primaire; returns (class_id, student_id)."""
    levels = client.get("/api/levels").json()
    primaire = next(level["id"] for level in levels if level["name"] == "Primaire")
    subject_id = client.post("/api/subjects", json={"name": subject}).json()["id"]
    teacher_id = client.post("/api/teachers", json={"name": teacher}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": primaire, "subject_id": subject_id, "teacher_id": teacher_id},
    ).json()["id"]
    student_id = client.post(
        "/api/students", json={"name": student, "level_id": primaire}
    ).json()["id"]
    return class_id, student_id


def enroll(client, student_id, class_ids, month="2026-09", price_dh=300):
    package = client.post(
        "/api/packages",
        json={"subject_count": len(class_ids), "monthly_price_centimes": price_dh * DH},
    ).json()
    response = client.post(
        "/api/enrollments",
        json={
            "student_id": student_id,
            "month": month,
            "package_id": package["id"],
            "class_ids": class_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestStructure:
    def test_health(self, client):
        assert client.get("/api/health").json()["status"] == "ok"

    def test_seeded_academy_with_default_split(self, client):
        (academy,) = client.get("/api/academies").json()
        assert academy["venue_bp"] == 3000
        assert academy["owner_bp"] == 1000
        assert academy["venue"]["name"] == "Salle principale"

    def test_academy_split_is_configurable(self, client):
        (academy,) = client.get("/api/academies").json()
        updated = client.patch(
            f"/api/academies/{academy['id']}",
            json={"venue_bp": 5000, "owner_bp": 3000, "name": "Excellence"},
        )
        assert updated.status_code == 200
        assert updated.json()["venue_bp"] == 5000
        assert updated.json()["name"] == "Excellence"

    def test_seeded_levels(self, client):
        names = [level["name"] for level in client.get("/api/levels").json()]
        assert names == ["Primaire", "Collège", "Lycée"]

    def test_crud_teacher_subject_class(self, client):
        class_id, _ = setup_class_and_student(client)
        (row,) = client.get("/api/classes").json()
        assert row["id"] == class_id
        assert row["subject_name"] == "Math"
        assert row["teacher_name"] == "Ahmed"
        assert row["level_name"] == "Primaire"

    def test_student_deactivation_is_soft(self, client):
        _, student_id = setup_class_and_student(client)
        response = client.patch(
            f"/api/students/{student_id}", json={"is_active": False}
        )
        assert response.status_code == 200
        assert client.get("/api/students").json() == []
        everyone = client.get("/api/students", params={"include_inactive": True}).json()
        assert [s["name"] for s in everyone] == ["Sami"]


class TestEnrollmentsAndPayments:
    def test_month_overview_shows_enrollment_and_payment_state(self, client):
        class_id, student_id = setup_class_and_student(client)
        enrollment_id = enroll(client, student_id, [class_id])
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["student_name"] == "Sami"
        assert row["enrollment"]["id"] == enrollment_id
        assert row["enrollment"]["net_centimes"] == 300 * DH
        assert row["enrollment"]["paid"] is False
        assert [c["subject_name"] for c in row["enrollment"]["classes"]] == ["Math"]

    def test_unenrolled_student_appears_without_enrollment(self, client):
        setup_class_and_student(client)
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["enrollment"] is None

    def test_payment_flow_pay_then_reverse(self, client):
        class_id, student_id = setup_class_and_student(client)
        enrollment_id = enroll(client, student_id, [class_id])

        paid = client.post("/api/payments", json={"enrollment_id": enrollment_id})
        assert paid.status_code == 201
        payment_id = paid.json()["payment_id"]
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["enrollment"]["paid"] is True

        again = client.post("/api/payments", json={"enrollment_id": enrollment_id})
        assert again.status_code == 409

        reversed_ = client.post(
            f"/api/payments/{payment_id}/reverse", json={"reason": "bounced"}
        )
        assert reversed_.status_code == 200
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["enrollment"]["paid"] is False

        double = client.post(f"/api/payments/{payment_id}/reverse", json={})
        assert double.status_code == 409

    def test_paying_unknown_enrollment_is_404(self, client):
        assert (
            client.post("/api/payments", json={"enrollment_id": 404}).status_code == 404
        )

    def test_adjustment_reduces_net_price(self, client):
        class_id, student_id = setup_class_and_student(client)
        enrollment_id = enroll(client, student_id, [class_id])
        response = client.post(
            f"/api/enrollments/{enrollment_id}/adjustments",
            json={"kind": "amount", "value": 50 * DH, "category": "discount"},
        )
        assert response.status_code == 201
        (row,) = client.get("/api/months/2026-09/overview").json()
        assert row["enrollment"]["net_centimes"] == 250 * DH

    def test_copy_month_skips_already_enrolled_and_inactive(self, client):
        class_id, student_id = setup_class_and_student(client)
        enroll(client, student_id, [class_id], month="2026-09")
        response = client.post(
            "/api/months/copy", json={"from_month": "2026-09", "to_month": "2026-10"}
        )
        assert response.status_code == 200
        assert response.json()["copied"] == 1
        (row,) = client.get("/api/months/2026-10/overview").json()
        assert row["enrollment"]["net_centimes"] == 300 * DH
        # Copying again copies nothing new.
        again = client.post(
            "/api/months/copy", json={"from_month": "2026-09", "to_month": "2026-10"}
        )
        assert again.json()["copied"] == 0


class TestReports:
    def test_monthly_report_and_arrears(self, client):
        class_id, student_id = setup_class_and_student(client)
        paid_enrollment = enroll(client, student_id, [class_id], month="2026-09")
        client.post("/api/payments", json={"enrollment_id": paid_enrollment})
        lina = client.post(
            "/api/students",
            json={
                "name": "Lina",
                "level_id": client.get("/api/levels").json()[0]["id"],
            },
        ).json()["id"]
        enroll(client, lina, [class_id], month="2026-08", price_dh=150)

        report = client.get(
            "/api/reports/monthly", params={"month": "2026-09"}
        ).json()
        assert report["cash_in"] == 300 * DH
        names = {t["name"]: t["total"] for t in report["totals"]}
        assert names["Ahmed"] == 180 * DH

        owing = client.get(
            "/api/reports/arrears", params={"up_to_month": "2026-09"}
        ).json()
        assert [(o["student_name"], o["total_owed"]) for o in owing] == [
            ("Lina", 150 * DH)
        ]
