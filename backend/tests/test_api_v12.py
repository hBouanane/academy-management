"""Round 13 : la fiche d'une classe, et le remboursement visible côté élève.

Quand une classe est archivée, l'élève qui avait payé n'est pas simplement
« Payé » : il attend son argent. Son mois doit le dire.
"""

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


def month_row(client, student_id, month="2026-09"):
    rows = client.get(f"/api/months/{month}/overview").json()
    return next(r for r in rows if r["student_id"] == student_id)


class TestClassProfile:
    def test_the_class_tells_its_whole_story(self, client):
        level, class_id, teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        profile = client.get(f"/api/classes/{class_id}/profile?month=2026-09")
        assert profile.status_code == 200, profile.text
        data = profile.json()
        assert data["subject_name"] == "Math"
        assert data["level_name"] == "Primaire"
        assert data["teacher_id"] == teacher
        assert data["teacher_name"] == "Ahmed"
        assert data["enrolled_count"] == 1
        assert [row["student_id"] for row in data["students"]] == [student]
        # Un seul professeur pour l'instant, depuis toujours.
        (period,) = data["assignments"]
        assert period["teacher_name"] == "Ahmed"
        assert period["from_date"] is None and period["to_date"] is None

    def test_the_handover_shows_who_taught_when(self, client):
        _, class_id, _, _ = setup_base(client)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        client.post(
            f"/api/classes/{class_id}/replace-teacher",
            json={"date": "2026-09-21", "successor_id": sara},
        )
        data = client.get(f"/api/classes/{class_id}/profile?month=2026-09").json()
        assert data["teacher_name"] == "Sara"
        periods = [
            (row["teacher_name"], row["from_date"], row["to_date"])
            for row in data["assignments"]
        ]
        assert periods == [
            ("Ahmed", None, "2026-09-20"),
            ("Sara", "2026-09-21", None),
        ]

    def test_a_vacant_class_says_so(self, client):
        _, class_id, _, _ = setup_base(client)
        client.post(
            f"/api/classes/{class_id}/vacate-teacher", json={"date": "2026-09-11"}
        )
        data = client.get(f"/api/classes/{class_id}/profile?month=2026-09").json()
        assert data["teacher_id"] is None
        assert data["teacher_name"] is None

    def test_restoring_a_class_puts_its_professor_back_in_charge(self, client):
        # Archiver ferme la période d'enseignement ; restaurer doit la
        # rouvrir, sinon la fiche dit qu'il a arrêté alors qu'il enseigne.
        _, class_id, _, _ = setup_base(client)
        client.post(
            f"/api/classes/{class_id}/archive",
            json={"date": "2026-09-15", "refunds": []},
        )
        client.patch(f"/api/classes/{class_id}", json={"is_active": True})
        data = client.get(f"/api/classes/{class_id}/profile?month=2026-09").json()
        assert data["teacher_name"] == "Ahmed"
        assert data["assignments"][-1]["to_date"] is None  # de nouveau en cours

    def test_unknown_class_is_404(self, client):
        assert client.get("/api/classes/999/profile?month=2026-09").status_code == 404


class TestRefundVisibleOnTheStudent:
    def test_an_archived_class_leaves_the_month_paid_and_owed_back(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        client.post(
            f"/api/classes/{class_id}/archive",
            json={
                "date": "2026-09-15",
                "refunds": [{"enrollment_id": enrollment, "percent_bp": 7000}],
            },
        )
        row = month_row(client, student)["enrollment"]
        assert row["paid"] is True
        assert row["refund_pending_centimes"] == 210 * DH  # 70% de 300
        assert row["refunded_centimes"] == 0
        # Le profil de l'élève le dit aussi, mois par mois.
        profile = client.get(f"/api/students/{student}/profile").json()
        assert profile["months"][0]["refund_pending_centimes"] == 210 * DH

    def test_once_handed_back_it_shows_as_refunded(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        client.post(
            f"/api/classes/{class_id}/archive",
            json={
                "date": "2026-09-15",
                "refunds": [{"enrollment_id": enrollment, "percent_bp": 10000}],
            },
        )
        (refund,) = client.get("/api/refunds").json()
        client.post(f"/api/refunds/{refund['id']}/settle")
        row = month_row(client, student)["enrollment"]
        assert row["refund_pending_centimes"] == 0
        assert row["refunded_centimes"] == 300 * DH

    def test_a_month_without_refund_stays_silent(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        row = month_row(client, student)["enrollment"]
        assert row["refund_pending_centimes"] == 0
        assert row["refunded_centimes"] == 0
