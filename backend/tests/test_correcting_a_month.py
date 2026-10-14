"""Round 37 : corriger un mois saisi de travers.

L'élève s'inscrit et paie septembre ; la saisie part sur octobre. Rien
n'en sortait : contre-passer laissait octobre en impayé pour toujours, et
supprimer était refusé dès qu'un paiement avait existé -- même contre-
passé.

Deux verbes, pas un. Contre-passer défait un fait RÉEL (il a payé, on lui
rend) et les deux mouvements restent. Une erreur de saisie décrit ce qui
n'a jamais eu lieu : elle ne se défait pas, elle se raye. La garder
affirme une fausseté -- qu'un élève était inscrit un mois où il n'a pas
étudié.

Et dans le cas réel, rien ne doit être annulé du tout. L'argent est vrai
et reste. Il est simplement dans le mauvais tiroir.
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


def overview(client, month):
    return client.get(f"/api/months/{month}/overview").json()


def row_of(client, month, student_id):
    return next(r for r in overview(client, month) if r["student_id"] == student_id)


def month_of(client, student_id, month):
    """La fiche de l'élève : c'est elle qui porte le jour payé et les
    matières du mois."""
    profile = client.get(f"/api/students/{student_id}/profile").json()
    return next((m for m in profile["months"] if m["month"] == month), None)


def pay(client, enrollment, **extra):
    return client.post(
        "/api/payments", json={"enrollment_id": enrollment, **extra}
    ).json()["payment_id"]


def journal_actions(client):
    return [e["action"] for e in client.get("/api/journal").json()["entries"]]


class TestStrikingAnEntryThatNeverHappened:
    def test_a_reversed_payment_no_longer_pins_the_month(self, client):
        """Après contre-passation chaque ligne a sa jumelle négative :
        l'empreinte est nulle, et il ne reste qu'une frappe à effacer."""
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        payment = pay(client, enrollment)
        client.post(f"/api/payments/{payment}/reverse", json={})

        struck = client.delete(f"/api/enrollments/{enrollment}")

        assert struck.status_code == 200
        assert row_of(client, "2026-09", student)["enrollment"] is None

    def test_the_month_stops_claiming_an_impaye(self, client):
        """Le reproche d'origine : octobre restait dû pour un mois jamais
        étudié."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")
        payment = pay(client, enrollment)
        client.post(f"/api/payments/{payment}/reverse", json={})

        client.delete(f"/api/enrollments/{enrollment}")

        owed = client.get("/api/reports/arrears?up_to_month=2026-10").json()
        assert owed == []

    def test_live_money_still_blocks_it(self, client):
        """La règle devient « aucun argent vivant », pas « tout est permis »."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        pay(client, enrollment)

        refused = client.delete(f"/api/enrollments/{enrollment}")

        assert refused.status_code == 409
        assert "contre-pass" in refused.json()["detail"]

    def test_a_settled_teacher_blocks_it(self, client):
        """« Solder le prof » est une décision délibérée sur ce qui a été
        enseigné, pas une frappe : elle ne s'efface pas en passant."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )

        refused = client.delete(f"/api/enrollments/{enrollment}")

        assert refused.status_code == 409
        assert "professeur" in refused.json()["detail"].lower()

    def test_nothing_of_it_is_left_in_the_ledger(self, client):
        """Les lignes miroir partent avec : laissées là, elles pointeraient
        vers une inscription disparue."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        payment = pay(client, enrollment)
        client.post(f"/api/payments/{payment}/reverse", json={})

        client.delete(f"/api/enrollments/{enrollment}")

        report = client.get("/api/reports/monthly?month=2026-09").json()
        assert report["cash_in"] == 0
        assert report["totals"] == []


class TestMovingItToTheRightMonth:
    """Le vrai cas. Rien ne doit être annulé : l'argent est vrai et reste."""

    def test_the_student_lands_on_the_right_month(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")
        pay(client, enrollment, paid_on="2026-09-04")

        moved = client.post(
            f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"}
        )

        assert moved.status_code == 200
        assert row_of(client, "2026-10", student)["enrollment"] is None
        assert row_of(client, "2026-09", student)["enrollment"] is not None

    def test_the_money_arrives_with_him(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")
        pay(client, enrollment, paid_on="2026-09-04")

        client.post(f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"})

        assert row_of(client, "2026-09", student)["enrollment"]["paid"] is True
        assert client.get("/api/reports/monthly?month=2026-09").json()["cash_in"] == (
            300 * DH
        )
        assert client.get("/api/reports/monthly?month=2026-10").json()["cash_in"] == 0

    def test_the_day_he_paid_is_kept(self, client):
        """Il a payé le 4 septembre. Le mois change ; le jour, non."""
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")
        pay(client, enrollment, paid_on="2026-09-04")

        client.post(f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"})

        assert month_of(client, student, "2026-09")["paid_on"] == "2026-09-04"

    def test_the_subjects_come_too(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")

        client.post(f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"})

        assert month_of(client, student, "2026-09")["subject_count"] == 1
        assert month_of(client, student, "2026-10") is None

    def test_an_unpaid_enrollment_moves_just_as_well(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")

        moved = client.post(
            f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"}
        )

        assert moved.status_code == 200
        assert row_of(client, "2026-09", student)["enrollment"]["paid"] is False

    def test_the_move_is_written_in_the_journal(self, client):
        """Une correction silencieuse dans une application d'argent, c'est
        un litige qu'on ne pourra plus trancher."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")
        pay(client, enrollment)

        client.post(f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"})

        assert journal_actions(client)[0] == "enrollment_moved"


class TestWhenMovingMustBeRefused:
    def test_the_target_month_is_already_taken(self, client):
        """Deux inscriptions pour un mois n'ont pas de sens -- et écraser
        celle qui existe serait une deuxième erreur, pas une correction."""
        level, class_id, _, package = setup_base(client)
        student, september = enroll(client, level, package, class_id)
        october = client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-10",
                "package_id": package,
                "class_ids": [class_id],
            },
        ).json()["id"]
        assert september

        refused = client.post(
            f"/api/enrollments/{october}/move", json={"month": "2026-09"}
        )

        assert refused.status_code == 409
        assert "déjà" in refused.json()["detail"]

    def test_a_settled_teacher_refuses_the_move(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )

        refused = client.post(
            f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"}
        )

        assert refused.status_code == 409

    def test_a_closed_month_can_still_receive_the_correction(self, client, monkeypatch):
        """Le verrou des mois passés ne s'applique pas ici, et c'est
        délibéré : on s'aperçoit d'un mois saisi de travers APRÈS coup, et
        exiger deux mois ouverts rendrait la correction impossible
        précisément quand on en a besoin.

        L'application admet déjà qu'un mois clos reçoive de l'argent —
        encaisser un impayé de septembre en octobre fait exactement cela.
        Ce qui rend le déplacement acceptable, ce sont les garde-fous et la
        ligne de journal : la figure d'un mois clos peut bouger, jamais
        sans trace."""
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-10")
        pay(client, enrollment)
        monkeypatch.setattr(clock, "current_month", lambda: "2026-11")

        moved = client.post(
            f"/api/enrollments/{enrollment}/move", json={"month": "2026-09"}
        )

        assert moved.status_code == 200
        assert month_of(client, student, "2026-09") is not None
        assert journal_actions(client)[0] == "enrollment_moved"

    def test_moving_nowhere_is_refused(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")

        refused = client.post(
            f"/api/enrollments/{enrollment}/move", json={"month": "2026-10"}
        )

        assert refused.status_code == 409
