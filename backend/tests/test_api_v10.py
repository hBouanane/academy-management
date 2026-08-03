"""Round 11: the month's rhythm — students pay at the start, professors are
paid at the end.

  « Garantie professeur » : an unpaid student never costs the professor. He
  is paid for the days he actually taught; the académie fronts it and LA
  SALLE TAKES THE HIT WITH IT (nothing collected ⇒ nothing for the salle).
  Cash stays at zero — only who-earned-what moves.

  « Versements » : what the owner actually handed each professor, tracked
  apart from the ledger (earning and paying out are two different moments).
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base
from test_api_v8 import monkeypatch_month

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def totals(client, month="2026-09"):
    report = client.get(f"/api/reports/monthly?month={month}").json()
    return {(t["kind"], t["ref_id"]): t["total"] for t in report["totals"]}


def cash_in(client, month="2026-09"):
    return client.get(f"/api/reports/monthly?month={month}").json()["cash_in"]


def academy_id(client):
    return client.get("/api/academies").json()[0]["id"]


def overview_row(client, student_id, month="2026-09"):
    rows = client.get(f"/api/months/{month}/overview").json()
    return next(r for r in rows if r["student_id"] == student_id)


# --- 1. La garantie professeur ---------------------------------------------


class TestGuarantee:
    def test_full_month_pays_the_teacher_and_the_academie_fronts_alone(self, client):
        # 300 DH : salle 30%, académie 10%, professeur 60% = 180 DH.
        # Rien encaissé ⇒ le professeur touche ses 180, l'académie les avance,
        # et la salle ne reçoit RIEN (elle encaisse le coup avec l'académie).
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        assert response.status_code == 200, response.text
        assert response.json()["amount_centimes"] == 180 * DH
        money = totals(client)
        assert money[("teacher", teacher)] == 180 * DH
        assert money[("owner", academy_id(client))] == -180 * DH
        assert ("venue", 1) not in money  # la salle ne touche rien
        assert cash_in(client) == 0  # aucun argent n'est entré

    def test_presence_until_the_15th_guarantees_only_those_days(self, client):
        # Septembre = 30 jours ; présent 15 jours ⇒ la moitié de 180 DH.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"present_until": "2026-09-15"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["amount_centimes"] == 90 * DH
        money = totals(client)
        assert money[("teacher", teacher)] == 90 * DH
        assert money[("owner", academy_id(client))] == -90 * DH

    def test_never_came_pays_nobody_and_can_stop_the_student(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"never_came": True, "stop": True},
        )
        assert response.status_code == 200, response.text
        assert response.json()["amount_centimes"] == 0
        assert totals(client) == {}  # personne n'a rien gagné
        # Arrêté : le mois suivant ne le reprend pas.
        monkeypatch_month(client, "2026-10")
        assert overview_row(client, student, "2026-10")["enrollment"] is None

    def test_a_guaranteed_month_is_still_an_impaye(self, client):
        # Garantir protège le professeur ; ça n'efface pas la dette.
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        row = overview_row(client, student)
        assert row["enrollment"]["paid"] is False
        assert row["enrollment"]["guaranteed_centimes"] == 180 * DH
        (owed,) = client.get("/api/reports/arrears?up_to_month=2026-09").json()
        assert owed["total_owed"] == 300 * DH

    def test_paying_later_recovers_the_advance_exactly(self, client):
        # Quand l'étudiant règle enfin : tout atterrit comme un paiement
        # normal — salle 90, académie 30, professeur 180 — et l'académie
        # récupère son avance.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 201, paid.text
        money = totals(client)
        assert money[("teacher", teacher)] == 180 * DH
        assert money[("owner", academy_id(client))] == 30 * DH
        assert money[("venue", 1)] == 90 * DH
        assert cash_in(client) == 300 * DH

    def test_paying_after_a_partial_guarantee_lands_on_the_normal_split(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"present_until": "2026-09-15"},
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        money = totals(client)
        assert money[("teacher", teacher)] == 180 * DH
        assert money[("owner", academy_id(client))] == 30 * DH
        assert money[("venue", 1)] == 90 * DH

    def test_a_gift_after_a_guarantee_never_claws_back_the_professor(self, client):
        # Mois offert après garantie : le professeur GARDE ce qui lui a été
        # garanti — on ne reprend jamais l'argent d'un professeur.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "percent", "value": 10_000, "category": "gift"},
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        money = totals(client)
        assert money[("teacher", teacher)] == 180 * DH
        assert money[("owner", academy_id(client))] == -180 * DH

    def test_reversing_the_payment_restores_the_guarantee(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        payment = client.post(
            "/api/payments", json={"enrollment_id": enrollment}
        ).json()["payment_id"]
        client.post(f"/api/payments/{payment}/reverse", json={})
        money = totals(client)
        assert money[("teacher", teacher)] == 180 * DH
        assert money[("owner", academy_id(client))] == -180 * DH
        assert cash_in(client) == 0

    def test_guaranteeing_twice_or_a_paid_month_is_refused(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        again = client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        assert again.status_code == 409
        _, other = enroll(client, level, package, class_id, name="Nadia")
        client.post("/api/payments", json={"enrollment_id": other})
        refused = client.post(f"/api/enrollments/{other}/guarantee", json={})
        assert refused.status_code == 409
        assert "encaissé" in refused.json()["detail"]

    def test_presence_date_must_be_inside_the_month(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        refused = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"present_until": "2026-10-05"},
        )
        assert refused.status_code == 422


# --- 2. Les versements aux professeurs -------------------------------------


class TestPayouts:
    def test_summary_shows_due_paid_and_remaining(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 180 * DH
        assert row["paid_centimes"] == 0
        assert row["remaining_centimes"] == 180 * DH

    def test_marking_a_payout_in_installments(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        first = client.post(
            f"/api/teachers/{teacher}/payouts",
            json={"month": "2026-09", "amount_centimes": 100 * DH},
        )
        assert first.status_code == 201, first.text
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["paid_centimes"] == 100 * DH
        assert row["remaining_centimes"] == 80 * DH
        # No amount = the whole remaining.
        client.post(f"/api/teachers/{teacher}/payouts", json={"month": "2026-09"})
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["remaining_centimes"] == 0
        assert len(row["payouts"]) == 2

    def test_overpaying_a_professor_is_refused(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        refused = client.post(
            f"/api/teachers/{teacher}/payouts",
            json={"month": "2026-09", "amount_centimes": 200 * DH},
        )
        assert refused.status_code == 422
        assert "reste" in refused.json()["detail"]

    def test_a_late_arrear_reopens_what_is_left_to_pay(self, client):
        # Payé en fin de mois, puis un vieil impayé rentre : le reste à
        # verser se rouvre tout seul — rien à recalculer à la main.
        level, class_id, teacher, package = setup_base(client)
        _, first = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": first})
        client.post(f"/api/teachers/{teacher}/payouts", json={"month": "2026-09"})
        _, late = enroll(client, level, package, class_id, name="Nadia")
        client.post("/api/payments", json={"enrollment_id": late})
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 360 * DH
        assert row["paid_centimes"] == 180 * DH
        assert row["remaining_centimes"] == 180 * DH

    def test_a_guaranteed_share_is_due_to_the_professor_at_payday(self, client):
        # La garantie compte dans le dû : le jour de la paie, le
        # propriétaire lui verse aussi les élèves impayés garantis.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 180 * DH
        assert row["remaining_centimes"] == 180 * DH

    def test_a_professor_owed_nothing_cannot_be_paid(self, client):
        _, _, teacher, _ = setup_base(client)
        refused = client.post(
            f"/api/teachers/{teacher}/payouts", json={"month": "2026-09"}
        )
        assert refused.status_code == 422


# --- 3. Le dû se calcule sur les élèves INSCRITS ---------------------------


class TestDueOnEnrolled:
    def test_a_professor_is_owed_from_the_enrollment_not_the_payment(self, client):
        # Personne n'a payé : le professeur a quand même enseigné, il est dû.
        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 180 * DH
        assert row["collected_centimes"] == 0  # rien d'encaissé pour l'instant
        assert row["remaining_centimes"] == 180 * DH

    def test_he_can_be_paid_before_any_student_pays(self, client):
        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        paid = client.post(
            f"/api/teachers/{teacher}/payouts", json={"month": "2026-09"}
        )
        assert paid.status_code == 201, paid.text
        assert paid.json()["amount_centimes"] == 180 * DH

    def test_never_came_removes_the_due_entirely(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee", json={"never_came": True}
        )
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 0

    def test_partial_presence_lowers_the_due_to_the_days_taught(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"present_until": "2026-09-15"},
        )
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 90 * DH

    def test_once_the_student_pays_the_full_share_is_due_again(self, client):
        # Présence partielle actée, puis l'étudiant règle tout : il a bien
        # payé le mois entier, le professeur touche sa part entière.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"present_until": "2026-09-15"},
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        (row,) = [
            entry
            for entry in client.get("/api/payouts?month=2026-09").json()
            if entry["teacher_id"] == teacher
        ]
        assert row["due_centimes"] == 180 * DH

    def test_every_active_professor_is_listed(self, client):
        # Il doit tous les voir le jour de la paie, même ceux à zéro.
        setup_base(client)
        client.post("/api/teachers", json={"name": "Nadia"})
        names = [
            entry["teacher_name"]
            for entry in client.get("/api/payouts?month=2026-09").json()
        ]
        assert "Nadia" in names and "Ahmed" in names
