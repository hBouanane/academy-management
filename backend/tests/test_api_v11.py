"""Round 12: la caisse.

L'argent des élèves entre dans la CAISSE — pas dans la poche de quelqu'un.
Payer un professeur, la salle ou le propriétaire lui-même la vide d'autant :
il se paie comme il paie un professeur.

Le partage suit la règle du client :
  - le professeur touche sur les élèves INSCRITS, payés ou non ;
  - la salle ne touche QUE sur l'argent réellement encaissé ;
  - l'académie prend ce qui reste — et absorbe donc tout le manque.
Quand un impayé rentre plus tard, il retombe dans SON mois : la salle prend
son pourcentage, tout le reste va à l'académie qui avait avancé.
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


def caisse(client, month="2026-09"):
    response = client.get(f"/api/caisse?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


def line(data, kind, ref_id=None):
    return next(
        entry
        for entry in data["lines"]
        if entry["kind"] == kind and (ref_id is None or entry["ref_id"] == ref_id)
    )


def pay_out(client, kind, ref_id, month="2026-09", amount=None):
    body = {"kind": kind, "ref_id": ref_id, "month": month}
    if amount is not None:
        body["amount_centimes"] = amount
    return client.post("/api/payouts", json=body)


class TestCaisse:
    def test_an_empty_month_has_an_empty_caisse(self, client):
        setup_base(client)
        data = caisse(client)
        assert data["collected_centimes"] == 0
        assert data["paid_out_centimes"] == 0
        assert data["balance_centimes"] == 0

    def test_a_payment_goes_into_the_caisse_not_into_a_pocket(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        data = caisse(client)
        assert data["collected_centimes"] == 300 * DH
        assert data["paid_out_centimes"] == 0
        assert data["balance_centimes"] == 300 * DH  # tout est encore en caisse

    def test_paying_the_professor_takes_it_out(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        paid = pay_out(client, "teacher", teacher)
        assert paid.status_code == 201, paid.text
        assert paid.json()["amount_centimes"] == 180 * DH
        data = caisse(client)
        assert data["paid_out_centimes"] == 180 * DH
        assert data["balance_centimes"] == 120 * DH

    def test_the_owner_pays_himself_like_anyone_else(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        academy = client.get("/api/academies").json()[0]
        owner = line(caisse(client), "owner")
        assert owner["due_centimes"] == 30 * DH
        paid = pay_out(client, "owner", academy["id"])
        assert paid.status_code == 201, paid.text
        data = caisse(client)
        assert line(data, "owner")["paid_centimes"] == 30 * DH
        assert line(data, "owner")["remaining_centimes"] == 0
        assert data["balance_centimes"] == 270 * DH

    def test_the_venue_is_paid_from_the_caisse_too(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        venue = client.get("/api/academies").json()[0]["venue"]
        assert line(caisse(client), "venue")["due_centimes"] == 90 * DH
        assert pay_out(client, "venue", venue["id"]).status_code == 201
        data = caisse(client)
        assert line(data, "venue")["paid_centimes"] == 90 * DH
        assert data["balance_centimes"] == 210 * DH

    def test_the_venue_only_earns_on_money_actually_collected(self, client):
        # Deux élèves à 300 : un paie, l'autre non.
        # Professeur : 60% des DEUX = 360 (il les a enseignés tous les deux).
        # Salle : 30% des 300 encaissés seulement = 90.
        # Académie : 300 encaissés − 360 − 90 = −150. Elle absorbe le manque.
        level, class_id, teacher, package = setup_base(client)
        _, paid_enrollment = enroll(client, level, package, class_id)
        enroll(client, level, package, class_id, name="Nadia")
        client.post("/api/payments", json={"enrollment_id": paid_enrollment})
        data = caisse(client)
        assert line(data, "teacher", teacher)["due_centimes"] == 360 * DH
        assert line(data, "venue")["due_centimes"] == 90 * DH
        assert line(data, "owner")["due_centimes"] == -150 * DH
        assert data["unpaid_centimes"] == 300 * DH
        # Ce que l'impayé rapportera : 30% à la salle, tout le reste à
        # l'académie (elle a déjà payé le professeur pour cet élève).
        assert data["projection"]["venue_centimes"] == 90 * DH
        assert data["projection"]["owner_centimes"] == 210 * DH

    def test_the_late_payment_closes_the_balance_in_its_own_month(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, first = enroll(client, level, package, class_id)
        _, late = enroll(client, level, package, class_id, name="Nadia")
        client.post("/api/payments", json={"enrollment_id": first})
        client.post(f"/api/enrollments/{late}/guarantee", json={})
        # Le mois suivant s'ouvre, mais l'argent en retard retombe ici.
        clock.current_month = lambda: "2026-10"
        client.post("/api/payments", json={"enrollment_id": late})
        data = caisse(client, "2026-09")
        assert data["collected_centimes"] == 600 * DH
        assert line(data, "teacher", teacher)["due_centimes"] == 360 * DH
        assert line(data, "venue")["due_centimes"] == 180 * DH
        assert line(data, "owner")["due_centimes"] == 60 * DH
        assert data["unpaid_centimes"] == 0
        assert caisse(client, "2026-10")["collected_centimes"] == 0

    def test_paying_more_than_due_is_refused(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        refused = pay_out(client, "teacher", teacher, amount=200 * DH)
        assert refused.status_code == 422
        assert "reste" in refused.json()["detail"]

    def test_a_beneficiary_in_the_red_cannot_be_paid(self, client):
        # L'académie a avancé : il n'y a rien à lui verser, au contraire.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(f"/api/enrollments/{enrollment}/guarantee", json={})
        academy = client.get("/api/academies").json()[0]
        assert line(caisse(client), "owner")["due_centimes"] == -180 * DH
        assert pay_out(client, "owner", academy["id"]).status_code == 422

    def test_cancelling_a_payout_puts_the_money_back(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        payout_id = pay_out(client, "teacher", teacher).json()["id"]
        assert caisse(client)["balance_centimes"] == 120 * DH
        client.delete(f"/api/payouts/{payout_id}")
        assert caisse(client)["balance_centimes"] == 300 * DH

    def test_every_beneficiary_is_listed_even_at_zero(self, client):
        setup_base(client)
        kinds = {entry["kind"] for entry in caisse(client)["lines"]}
        assert kinds == {"venue", "owner", "teacher"}
