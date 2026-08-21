"""Round 26b : un mois passé à moitié payé reste un mois dû, partout.

Le rapport des impayés compte le reste (round 25b). Mais deux autres
endroits jugeaient encore un mois sur la seule existence d'un paiement :
la colonne « Impayés » de la liste des élèves, et le drapeau rouge du
tableau de bord.

Une famille qui règle 100 DH sur 300 n'y apparaissait donc pas en
retard, tandis que le rapport la réclamait. Trois écrans, deux réponses
opposées sur la même famille : celui qui les lit finit par ne croire
aucun des trois.
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


def past_month(client, paid=None, complete=False):
    """Un élève inscrit en août, vu depuis septembre."""
    level, class_id, _teacher, package = setup_base(client)
    student, enrollment = enroll(client, level, package, class_id, month="2026-08")
    if paid is not None:
        body = {"enrollment_id": enrollment, "paid_on": "2026-08-03"}
        if paid:
            body["amount_centimes"] = paid
        posted = client.post("/api/payments", json=body).json()
        if complete:
            client.post(f"/api/payments/{posted['payment_id']}/complete", json={})
    return student


def unpaid_count(client, student):
    listed = client.get("/api/students?month=2026-09").json()
    return next(s["unpaid_months"] for s in listed if s["id"] == student)


def flagged(client, student):
    rows = client.get("/api/months/2026-09/overview").json()
    return next(r["has_arrears"] for r in rows if r["student_id"] == student)


class TestTheUnpaidMonthsColumn:
    def test_a_month_never_paid_counts(self, client):
        assert unpaid_count(client, past_month(client)) == 1

    def test_a_month_fully_paid_does_not(self, client):
        assert unpaid_count(client, past_month(client, paid=0)) == 0

    def test_a_month_half_paid_counts(self, client):
        """Il reste 200 DH : le mois n'est pas réglé."""
        assert unpaid_count(client, past_month(client, paid=100 * DH)) == 1

    def test_a_completed_advance_does_not(self, client):
        student = past_month(client, paid=100 * DH, complete=True)
        assert unpaid_count(client, student) == 0


class TestTheRedFlag:
    def test_a_month_half_paid_is_flagged(self, client):
        assert flagged(client, past_month(client, paid=100 * DH)) is True

    def test_a_month_fully_paid_is_not(self, client):
        assert flagged(client, past_month(client, paid=0)) is False

    def test_a_month_never_paid_is_flagged(self, client):
        assert flagged(client, past_month(client)) is True

    def test_a_completed_advance_is_not(self, client):
        student = past_month(client, paid=100 * DH, complete=True)
        assert flagged(client, student) is False


class TestTheThreeScreensAgree:
    def test_the_report_and_the_column_say_the_same_thing(self, client):
        """C'est le point : plus de contradiction d'un écran à l'autre."""
        student = past_month(client, paid=100 * DH)

        owing = client.get("/api/reports/arrears?up_to_month=2026-09").json()
        mine = next(e for e in owing if e["student_id"] == student)

        assert mine["total_owed"] == 200 * DH
        assert unpaid_count(client, student) == 1
        assert flagged(client, student) is True
