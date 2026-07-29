"""Sponsors, proration and table aggregates — written first (TDD)."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def setup_base(client):
    levels = client.get("/api/levels").json()
    level = next(lv["id"] for lv in levels if lv["name"] == "Primaire")
    subject = client.post("/api/subjects", json={"name": "Math"}).json()["id"]
    teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": level, "subject_id": subject, "teacher_id": teacher},
    ).json()["id"]
    package = client.post(
        "/api/packages",
        json={
            "subject_count": 1,
            "monthly_price_centimes": 300 * DH,
            "level_id": level,
        },
    ).json()["id"]
    return level, class_id, teacher, package


def enroll(client, level, package, class_id, name="Sami", month="2026-09", **extra):
    student = client.post(
        "/api/students", json={"name": name, "level_id": level}
    ).json()["id"]
    response = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": month,
            "package_id": package,
            "class_ids": [class_id],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return student, response.json()["id"]


class TestSponsorShares:
    def test_sponsors_cover_explicit_parts_of_the_total(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 30 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 70 * DH},
                ],
            },
        )
        assert response.status_code == 201, response.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        lines = {line["name"]: line for line in preview["lines"]}
        assert lines["Mon académie"]["final_centimes"] == 0  # 30 - 30
        assert lines["Ahmed"]["final_centimes"] == 110 * DH  # 180 - 70
        assert preview["net_centimes"] == 200 * DH

    def test_sponsor_shares_may_be_percentages_of_the_total(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_bp": 2500},
                    {"kind": "teacher", "ref_id": teacher, "share_bp": 7500},
                ],
            },
        )
        assert response.status_code == 201, response.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        (adjustment,) = preview["adjustments"]
        shares = {b["name"]: b["share_centimes"] for b in adjustment["bearers"]}
        assert shares == {"Mon académie": 25 * DH, "Ahmed": 75 * DH}

    def test_mismatched_sponsor_parts_are_refused(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 30 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 30 * DH},
                ],
            },
        )
        assert response.status_code == 422
        assert "somme" in response.json()["detail"].lower()


class TestProration:
    def test_arrival_in_a_later_segment_prices_proportionally(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-15"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        # Default thirds: day 15 of 30 -> 2nd segment -> 67% of 300 = 201 DH.
        assert preview["price_centimes"] == 20100

    def test_first_segment_pays_full_price(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-05"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["price_centimes"] == 300 * DH

    def test_proration_segments_are_configurable(self, client):
        (academy,) = client.get("/api/academies").json()
        updated = client.patch(
            f"/api/academies/{academy['id']}",
            json={"proration_bp": [10000, 5000]},  # halves: 100% then 50%
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["proration_bp"] == [10000, 5000]
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-20"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["price_centimes"] == 150 * DH


class TestTableAggregates:
    def test_teachers_carry_monthly_earnings_and_subjects(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        (row,) = client.get("/api/teachers", params={"month": "2026-09"}).json()
        assert row["earned_centimes"] == 180 * DH
        assert row["subjects"] == "Math"

    def test_classes_carry_enrolled_count(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)
        (row,) = client.get("/api/classes", params={"month": "2026-09"}).json()
        assert row["enrolled_count"] == 1

    def test_subjects_carry_levels_and_class_count(self, client):
        setup_base(client)
        (row,) = client.get("/api/subjects").json()
        assert row["class_count"] == 1
        assert row["levels"] == "Primaire"

    def test_students_carry_unpaid_months_count(self, client, monkeypatch):
        level, class_id, _, package = setup_base(client)
        monkeypatch.setattr(clock, "current_month", lambda: "2026-08")
        student, _ = enroll(client, level, package, class_id, month="2026-08")
        monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
        (row,) = client.get("/api/students", params={"month": "2026-09"}).json()
        assert row["unpaid_months"] == 1
        overview_row = client.get("/api/months/2026-09/overview").json()[0]
        assert overview_row["has_arrears"] is True
        assert overview_row["student_id"] == student
